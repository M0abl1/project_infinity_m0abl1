"""Read-only, local spark reports with bounded parsing and explicit attribution."""
import math
import re
import threading
import time
from collections import defaultdict

from google.protobuf.message import DecodeError

from .spark_format import Profile

MAX_BYTES = 32 * 1024 * 1024
MAX_NODES = 200000


def summarize(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Relatório vazio ou maior que 32 MiB.')
    profile = Profile()
    try:
        profile.ParseFromString(data)
    except DecodeError as exc:
        raise ValueError('Arquivo spark inválido ou incompleto.') from exc
    if not profile.HasField('metadata') or not profile.threads:
        raise ValueError('O arquivo não contém um perfil de execução do spark.')
    if profile.metadata.sampler_mode != 0:
        raise ValueError('Perfil de alocações: não representa processamento. Gere um perfil de execução.')
    if sum(len(t.children) for t in profile.threads) > MAX_NODES:
        raise ValueError('Relatório excede o limite de 200 mil métodos.')
    maps = [{e.key: e.value for e in entries} for entries in
            (profile.class_sources, profile.method_sources, profile.line_sources)]
    sources = {e.key: e.value for e in profile.metadata.sources}
    direct, inclusive, methods = defaultdict(float), defaultdict(float), defaultdict(lambda: defaultdict(float))
    total = 0.0

    def weight(values):
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError('Relatório contém tempos inválidos.')
        result = sum(values)
        if not math.isfinite(result):
            raise ValueError('Relatório contém tempos inválidos.')
        return result

    def source(node):
        key = f'{node.class_name};{node.method_name};{node.method_desc}'
        found = maps[1].get(key) or maps[2].get(f'{node.class_name};{node.line_number}') or maps[0].get(node.class_name)
        if found:
            return found
        if node.class_name.startswith(('java.', 'javax.', 'jdk.', 'sun.')):
            return 'java'
        if node.class_name.startswith('net.minecraft.'):
            return 'minecraft'
        return 'unattributed'

    for thread in profile.threads:
        nodes = thread.children
        if nodes and not thread.children_refs:
            raise ValueError('Formato antigo sem referências de métodos não suportado. Atualize o spark para exportar este perfil.')
        root_time = weight(thread.times)
        if not thread.times:
            raise ValueError('Perfil sem tempos amostrados compatíveis.')
        total += root_time
        seen = set()
        stack = [(ref, frozenset(), 0) for ref in thread.children_refs]
        root_children = 0.0
        for ref in thread.children_refs:
            if ref < 0 or ref >= len(nodes):
                raise ValueError('Referência de método inválida.')
            root_children += weight(nodes[ref].times)
        if root_children > root_time + max(.01, root_time * .000001):
            raise ValueError('Tempos inconsistentes na raiz do perfil.')
        direct['unattributed'] += max(0, root_time - root_children)
        while stack:
            ref, ancestors, depth = stack.pop()
            if depth > 512:
                raise ValueError('Árvore de métodos excede a profundidade suportada.')
            if ref < 0 or ref >= len(nodes) or ref in seen:
                raise ValueError('Referência inválida, duplicada ou cíclica no relatório.')
            seen.add(ref)
            node = nodes[ref]
            elapsed = weight(node.times)
            children_time = 0.0
            owner = source(node)
            for child in node.children_refs:
                if child < 0 or child >= len(nodes):
                    raise ValueError('Referência de método inválida.')
                children_time += weight(nodes[child].times)
                stack.append((child, ancestors | {owner}, depth + 1))
            if children_time > elapsed + max(.01, elapsed * .000001):
                raise ValueError('Tempos inconsistentes entre métodos e chamadas.')
            own = max(0, elapsed - children_time)
            direct[owner] += own
            methods[owner][f'{node.class_name}.{node.method_name}{node.method_desc}'] += own
            if owner not in ancestors:
                inclusive[owner] += elapsed
        if len(seen) != len(nodes):
            raise ValueError('Relatório contém métodos sem ligação à árvore.')
    if total <= 0 or not math.isfinite(total):
        raise ValueError('O relatório não contém tempo amostrado suficiente.')
    names = {'minecraft': 'Minecraft (base)', 'java': 'Java / bibliotecas padrão', 'unattributed': 'Não atribuído pelo spark'}
    rows = []
    # Include known but unsampled mods; zero is not proof that the mod has no cost.
    for key in set(sources) | set(direct) | set(inclusive):
        metadata = sources.get(key)
        rows.append({'id': key, 'name': names.get(key) or (metadata.name if metadata else '') or key,
                     'version': metadata.version if metadata else '',
                     'direct_ms': round(direct[key], 3), 'direct_percent': round(direct[key] / total * 100, 3),
                     'inclusive_ms': round(inclusive[key], 3), 'inclusive_percent': round(inclusive[key] / total * 100, 3),
                     'methods': [{'name': name, 'direct_ms': round(value, 3), 'percent': round(value / total * 100, 3)}
                                 for name, value in sorted(methods[key].items(), key=lambda x: -x[1])[:15] if value > 0]})
    rows.sort(key=lambda r: (-r['direct_ms'], r['name']))
    meta = profile.metadata
    return {'start': meta.start_time / 1000, 'end': meta.end_time / 1000,
            'sampled_ms': round(total, 3), 'threads': [t.name for t in profile.threads],
            'mapped': bool(any(maps)), 'rows': rows,
            'minecraft_version': meta.platform.minecraft_version,
            'spark_version': meta.platform.spark_version}


class SparkReports:
    def __init__(self, root):
        self.directory = root / 'config' / 'spark'
        self.cache = {}
        self.lock = threading.Lock()

    def path(self, name):
        if not re.fullmatch(r'[\w .-]{1,150}\.sparkprofile', name, re.ASCII):
            raise ValueError('Nome de relatório inválido.')
        path = self.directory / name
        if self.directory.is_symlink() or self.directory.parent.is_symlink() or path.is_symlink():
            raise ValueError('Links simbólicos não são aceitos.')
        if not path.is_file():
            raise ValueError('Relatório não encontrado.')
        info = path.stat()
        if info.st_size > MAX_BYTES or info.st_size == 0:
            raise ValueError('Relatório vazio ou maior que 32 MiB.')
        if time.time() - info.st_mtime < 3:
            raise ValueError('Relatório ainda em gravação. Aguarde alguns segundos.')
        return path

    def listing(self):
        if not self.directory.is_dir() or self.directory.is_symlink() or self.directory.parent.is_symlink():
            return []
        entries = []
        for path in self.directory.glob('*.sparkprofile'):
            try:
                path = self.path(path.name)
                stat = path.stat()
                entries.append({'name': path.name, 'size': stat.st_size, 'modified': stat.st_mtime})
            except (ValueError, OSError):
                continue
        return sorted(entries, key=lambda p: -p['modified'])[:100]

    def read(self, name):
        with self.lock:
            path = self.path(name)
            before = path.stat()
            key = (name, before.st_mtime_ns, before.st_size)
            if key not in self.cache:
                with path.open('rb') as stream:
                    data = stream.read(MAX_BYTES + 1)
                after = path.stat()
                if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                    raise ValueError('Relatório mudou durante a leitura. Tente novamente.')
                result = summarize(data)
                self.cache.clear()  # Bound memory: only the most recently selected report.
                self.cache[key] = result
            return {'name': name, **self.cache[key]}
