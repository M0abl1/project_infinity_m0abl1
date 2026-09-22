import json
import re
import socket
import struct
import subprocess
import time

import psutil


def varint(value):
    value &= 0xffffffff
    result = bytearray()
    while True:
        b = value & 127
        value >>= 7
        result.append(b | (128 if value else 0))
        if not value:
            return bytes(result)


def read_varint(sock):
    n = 0
    for shift in range(0, 35, 7):
        b = sock.recv(1)
        if not b:
            raise ValueError('Resposta incompleta')
        n |= (b[0] & 127) << shift
        if not b[0] & 128:
            return n
    raise ValueError('Resposta inválida')


def ping():
    """Minecraft Java status handshake. No login, RCON or server configuration changes."""
    try:
        with socket.create_connection(('127.0.0.1', 25565), timeout=2) as s:
            host = b'localhost'
            packet = b'\x00' + varint(-1) + varint(len(host)) + host + struct.pack('>H', 25565) + b'\x01'
            s.sendall(varint(len(packet)) + packet + b'\x01\x00')
            length = read_varint(s)
            if not 0 < length <= 1048576 or read_varint(s) != 0:
                raise ValueError('Resposta inválida')
            length = read_varint(s)
            if not 0 < length <= 1048576:
                raise ValueError('Resposta inválida')
            body = bytearray()
            while len(body) < length:
                part = s.recv(min(65536, length-len(body)))
                if not part:
                    raise ValueError('Resposta incompleta')
                body.extend(part)
            data = json.loads(body)
            return {'ready': True, 'players': data.get('players', {}).get('online'),
                    'max_players': data.get('players', {}).get('max'),
                    'version': data.get('version', {}).get('name')}
    except (OSError, ValueError, KeyError):
        return {'ready': False, 'players': None, 'max_players': None, 'version': None}


def redact(text):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'(?i)((?:password|token|secret|authorization|api[_-]?key)\s*[:=]\s*)\S+', r'\1[oculto]', text)
    return ''.join(c for c in text if c in '\n\t' or ord(c) >= 32)


def log_tail(root, limit=131072):
    path = root / 'logs/latest.log'
    if not path.is_file() or path.is_symlink():
        return ''
    with path.open('rb') as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell()-limit))
        return redact(f.read(limit).decode('utf-8', errors='replace'))


class Minecraft:
    def __init__(self, settings):
        self.settings = settings
        self.processes = {}

    def java(self):
        found = []
        for p in psutil.process_iter(['pid', 'name']):
            try:
                if 'java' in (p.info['name'] or '').lower() and p.cwd() == str(self.settings.root):
                    found.append(self.processes.setdefault(p.pid, p))
            except (psutil.Error, OSError):
                pass
        self.processes = {p.pid: p for p in found}
        return found

    def metrics(self):
        processes = self.java()
        cpu, ram, started = 0.0, 0, None
        for p in processes:
            try:
                cpu += p.cpu_percent()
                ram += p.memory_info().rss
                started = min(started or p.create_time(), p.create_time())
            except psutil.Error:
                pass
        mem = psutil.virtual_memory()
        return {'cpu_percent': round(cpu, 1), 'ram_bytes': ram, 'running': bool(processes),
                'uptime_seconds': int(time.time()-started) if started else 0,
                'host_cpu_percent': psutil.cpu_percent(), 'host_ram_bytes': mem.total-mem.available,
                'host_ram_total': mem.total, 'cores': psutil.cpu_count()}

    def pm2(self, action):
        if action not in {'start', 'stop', 'jlist'}:
            raise ValueError('Ação inválida')
        args = ['pm2', action]
        if action != 'jlist':
            args.append(self.settings.process)
        r = subprocess.run(args, capture_output=True, text=True, timeout=150, check=True)
        return r.stdout

    def manager_status(self):
        for p in json.loads(self.pm2('jlist')):
            if p.get('name') == self.settings.process:
                e = p['pm2_env']
                return {'state': e.get('status'), 'restarts': e.get('restart_time'),
                        'kill_timeout': e.get('kill_timeout', 1600)}
        raise RuntimeError('Processo não encontrado no PM2.')

    def capture_spark(self):
        if not self.java():
            raise RuntimeError('O Minecraft precisa estar em execução para analisar o processamento.')
        matches = [p for p in json.loads(self.pm2('jlist')) if p.get('name') == self.settings.process]
        if len(matches) != 1 or type(matches[0].get('pm_id')) is not int:
            raise RuntimeError('Não foi possível identificar um único processo Minecraft no PM2.')
        # No arbitrary input, RCON credentials, shell, upload or game-state command.
        command = 'spark profiler start --timeout 60 --save-to-file'
        result = subprocess.run(['pm2', 'send', str(matches[0]['pm_id']), command],
                                capture_output=True, text=True, timeout=10, check=True)
        if '[ERROR]' in result.stdout or '[ERROR]' in result.stderr:
            raise RuntimeError('O PM2 não conseguiu enviar o comando ao console do jogo.')

    def stop(self):
        state = self.manager_status()
        if state['kill_timeout'] < 120000:
            raise RuntimeError('Configure kill_timeout de pelo menos 120000 ms no PM2 antes de parar pelo painel.')
        self.pm2('stop')
        if self.java():
            raise RuntimeError('O processo Java ainda está ativo. Operação cancelada.')
        if self.manager_status()['state'] not in {'stopped', 'errored'}:
            raise RuntimeError('Não foi possível confirmar a parada no PM2.')

    def start(self):
        world = self.settings.root / 'world'
        if world.is_symlink() or not (world / 'level.dat').is_file():
            raise RuntimeError('O mundo não está disponível. Confira a cópia preservada antes de iniciar; o painel não criará um mundo vazio.')
        self.pm2('start')
