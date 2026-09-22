"""Opt-in retention of completed world ZIPs; never touches world or recovery copies."""
import hashlib
import json
import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path


class Retention:
    def __init__(self, backups, lock, keep=0):
        if keep not in (0, 10):
            raise ValueError('PANEL_BACKUP_KEEP deve ser 0 (desativado) ou 10.')
        self.backups, self.lock, self.keep = backups, lock, keep
        self.verified = set()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.status = {'enabled': bool(keep), 'keep': keep, 'state': 'waiting' if keep else 'disabled',
                       'checked_at': None, 'removed': [], 'message': 'Retenção aguardando verificação.' if keep else 'Retenção do painel desativada.'}

    def inventory(self):
        directory = self.backups.directory
        if directory.is_symlink() or directory.resolve() != self.backups.root.resolve() / 'backups':
            raise ValueError('Diretório de backups não autorizado para limpeza.')
        catalog = directory / 'backups.json'
        if catalog.is_symlink():
            raise ValueError('Catálogo com link simbólico: limpeza suspensa.')
        # Fail closed: never treat a temporarily broken catalogue as untracked files.
        raw = catalog.read_bytes()
        entries = json.loads(raw)['backups']
        manifest = {Path(e['backupLocation']).name: e for e in entries}
        if len(manifest) != len(entries):
            raise ValueError('Catálogo contém nomes duplicados.')
        rows = []
        for path in directory.glob('*.zip'):
            path = self.backups.path(path.name)
            info = path.stat()
            meta = manifest.get(path.name)
            if time.time() - info.st_mtime < 120 or (meta is not None and
                    (meta.get('complete') is not True or meta.get('size') != info.st_size)):
                raise ValueError('Há backup em gravação ou incompleto. Nenhum arquivo será apagado.')
            match = re.fullmatch(r'(\d{4})-(\d{1,2})-(\d{1,2})_(\d{1,2})-(\d{1,2})-(\d{1,2})\.zip', path.name)
            if meta is not None and isinstance(meta.get('createTime'), int):
                created = meta['createTime'] / 1000
            elif match:
                created = datetime(*map(int, match.groups())).timestamp()
            else:
                raise ValueError('Há ZIP sem data de criação identificável. Limpeza suspensa.')
            fingerprint = (path.name, info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                           meta.get('sha1', '') if meta else '')
            rows.append({'name': path.name, 'created': created, 'size': info.st_size, 'fingerprint': fingerprint})
        rows.sort(key=lambda row: (row['created'], row['name']), reverse=True)
        return rows, hashlib.sha256(raw).digest()

    def sweep(self, dry_run=False):
        if not self.keep:
            return []
        rows, catalog = self.inventory()
        victims = rows[self.keep:]
        if dry_run or not victims:
            return [r['name'] for r in victims]
        fingerprints = {r['fingerprint'] for r in rows}
        self.verified.intersection_update(fingerprints)
        # Verify all ten retained copies AND targets before irreversible deletion.
        for row in rows:
            if self.stop_event.is_set():
                raise ValueError('Limpeza interrompida antes da exclusão.')
            if row['fingerprint'] not in self.verified:
                self.backups.inspect(row['name'], verify=True)
                self.verified.add(row['fingerprint'])
        current, current_catalog = self.inventory()
        if current_catalog != catalog or {r['fingerprint'] for r in current} != fingerprints:
            raise ValueError('Backups mudaram durante a verificação. Limpeza adiada.')
        removed = []
        for row in victims:
            if self.stop_event.is_set():
                break
            # Re-check retained files and catalogue before every deletion.
            current, current_catalog = self.inventory()
            expected = {r['fingerprint'] for r in rows if r['name'] not in removed}
            if current_catalog != catalog or {r['fingerprint'] for r in current} != expected:
                raise ValueError('Backups mudaram durante a limpeza. Exclusões restantes adiadas.')
            path = self.backups.path(row['name'])
            self.backups.store.audit('system', 'retention_delete', row['name'], 'exclusão autorizada pela retenção de 10')
            path.unlink()
            removed.append(row['name'])
            self.backups.store.audit('system', 'retention_delete', row['name'], 'excluído permanentemente')
        return removed

    def run(self):
        while not self.stop_event.wait(5 if self.status['checked_at'] is None else 60):
            if not self.lock.acquire(blocking=False):
                continue
            try:
                self.status.update(state='running', message='Verificando backups para manter os 10 mais recentes.')
                removed = self.sweep()
                self.status.update(state='success', checked_at=time.time(), removed=removed,
                                   message='Retenção ativa: até 10 backups concluídos, incluindo snapshots.')
            except Exception as exc:
                logging.warning('Backup retention deferred: %s', type(exc).__name__)
                self.status.update(state='deferred', checked_at=time.time(),
                                   message='Limpeza adiada: arquivo incompleto, inválido ou alterado. Nenhuma exclusão adicional será feita nesta verificação.')
            finally:
                self.lock.release()

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=8)
