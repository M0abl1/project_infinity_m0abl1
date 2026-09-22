import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath


class Backups:
    def __init__(self, root, store):
        self.root, self.store = root, store
        self.directory = root / 'backups'

    def manifest(self):
        try:
            data = json.loads((self.directory / 'backups.json').read_text())
            return {Path(x['backupLocation']).name: x for x in data['backups']}
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def path(self, name):
        if not name or Path(name).name != name or '/' in name or '\\' in name or not name.endswith('.zip'):
            raise ValueError('Nome de backup inválido.')
        path = self.directory / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != self.directory.resolve():
            raise ValueError('Backup não encontrado ou caminho não autorizado.')
        return path

    def complete(self, path, manifest):
        entry = manifest.get(path.name)
        if entry is not None:
            return entry.get('complete') is True and entry.get('size') == path.stat().st_size
        return time.time()-path.stat().st_mtime > 120

    def listing(self):
        manifest, observations = self.manifest(), self.store.observations()
        result = []
        for path in self.directory.glob('*.zip'):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                s = path.stat()
                complete = self.complete(path, manifest)
            except FileNotFoundError:
                continue  # A native or panel retention pass removed it during listing.
            result.append({'name': path.name, 'size': s.st_size, 'modified': s.st_mtime,
                           'complete': complete,
                           'metrics': observations.get(path.name),
                           'source': 'FTB Backups 2', 'catalogued': path.name in manifest})
        return sorted(result, key=lambda row: row['modified'], reverse=True)

    def validated(self, name):
        path = self.path(name)
        manifest = self.manifest()
        if not self.complete(path, manifest):
            raise ValueError('Backup ainda em gravação ou com tamanho diferente do catálogo.')
        return path, manifest.get(name, {})

    @staticmethod
    def members(archive):
        """Only a full world backup; reject traversal, links, collisions and zip bombs."""
        items = archive.infolist()
        if len(items) > 200000:
            raise ValueError('Arquivo com entradas demais.')
        total, names = 0, set()
        for info in items:
            raw = info.orig_filename
            p = PurePosixPath(raw)
            mode = info.external_attr >> 16
            if (not raw or '\x00' in raw or '\\' in raw
                    or (os.name == 'nt' and ':' in raw)
                    or any(re.match(r'^[A-Za-z]:', part) for part in p.parts)
                    or p.is_absolute() or '..' in p.parts
                    or p.parts[0] != 'world' or (len(p.parts) == 1 and not info.is_dir())
                    or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR})
                    or info.flag_bits & 1 or str(p).casefold() in names):
                raise ValueError('Backup contém caminhos, links ou formatos não permitidos.')
            names.add(str(p).casefold())
            total += info.file_size
            if total > 40 * 1024**3 or info.file_size > 8 * 1024**3:
                raise ValueError('Backup ultrapassa o limite de extração segura.')
        if 'world/level.dat' not in names:
            raise ValueError('Backup não contém world/level.dat; restauração recusada.')
        return items, total

    def inspect(self, name, verify=False):
        path, meta = self.validated(name)
        with path.open('rb') as f:
            if verify:
                digest = hashlib.sha1()
                for block in iter(lambda: f.read(1024*1024), b''):
                    digest.update(block)
                if meta.get('sha1') and digest.hexdigest() != meta['sha1']:
                    raise ValueError('A soma de integridade difere do catálogo do modpack.')
                f.seek(0)
            with zipfile.ZipFile(f) as z:
                items, total = self.members(z)
                if verify and z.testzip():
                    raise ValueError('Backup corrompido (CRC).')
                return {'name': name, 'files': len(items), 'uncompressed': total,
                        'verified': verify, 'entries': [x.filename for x in items[:150]],
                        'truncated': len(items) > 150}

    def restore(self, name, minecraft, progress):
        path, meta = self.validated(name)
        world = self.root / 'world'
        if world.is_symlink() or not world.is_dir():
            raise ValueError('Diretório world inválido; restauração cancelada.')
        # Open once: protects against replacement of the ZIP between validation and extraction.
        with path.open('rb') as f:
            before = os.fstat(f.fileno())
            with zipfile.ZipFile(f) as z:
                items, total = self.members(z)
                if shutil.disk_usage(self.root).free < total + 512*1024**2:
                    raise ValueError('Espaço insuficiente para preparar a restauração.')
                progress('Verificando a integridade do backup')
                if z.testzip():
                    raise ValueError('Backup corrompido (CRC).')
                f.seek(0)
                digest = hashlib.sha1()
                for block in iter(lambda: f.read(1024*1024), b''):
                    digest.update(block)
                if meta.get('sha1') and digest.hexdigest() != meta['sha1']:
                    raise ValueError('A soma de integridade difere do catálogo.')
                after = os.fstat(f.fileno())
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('O backup mudou durante a leitura.')
                with tempfile.TemporaryDirectory(prefix='.panel-restore-', dir=self.root) as tmp:
                    staging = Path(tmp)
                    progress('Preparando os arquivos do mundo')
                    for info in items:
                        dest = staging / info.filename
                        if info.is_dir():
                            dest.mkdir(parents=True, exist_ok=True)
                        else:
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            with z.open(info) as source, dest.open('xb') as target:
                                shutil.copyfileobj(source, target, length=1024*1024)
                    progress('Parando o Minecraft antes de substituir o mundo')
                    minecraft.stop()
                    recovery_base = self.root / '.panel-recovery'
                    if recovery_base.is_symlink():
                        raise ValueError('Diretório de recuperação inválido.')
                    recovery_base.mkdir(exist_ok=True)
                    recovery = Path(tempfile.mkdtemp(prefix=time.strftime('%Y%m%d-%H%M%S-'), dir=recovery_base)) / 'world'
                    progress('Preservando o mundo atual e ativando o backup')
                    world.rename(recovery)
                    try:
                        (staging / 'world').rename(world)
                    except BaseException:
                        recovery.rename(world)
                        raise
                    return {'recovery': str(recovery.relative_to(self.root)),
                            'message': 'Mundo restaurado. Minecraft permanece parado; use Iniciar quando desejar.'}
