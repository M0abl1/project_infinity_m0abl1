import threading
import time
import logging

from .minecraft import ping


class Monitor:
    def __init__(self, minecraft, backups, store):
        self.minecraft, self.backups, self.store = minecraft, backups, store
        self.stop_event = threading.Event()
        self.status = {'ready': False, 'sampled_at': None, 'error': 'Aguardando primeira leitura'}
        self.known = {p.name for p in backups.directory.glob('*.zip')}
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        count, protocol, manager = 0, {}, {}
        while not self.stop_event.is_set():
            try:
                metrics = self.minecraft.metrics()
                # Record first observation before any slower network/PM2 probe.
                current = {p.name for p in self.backups.directory.glob('*.zip')}
                for name in current-self.known:
                    self.store.observe(name, {**metrics, 'method': 'file-detected',
                                             'approximate': True, 'sample_interval_seconds': 2})
                self.known = current
                if count % 5 == 0:
                    protocol = ping()
                    manager = self.minecraft.manager_status()
                self.status = {**metrics, **protocol, 'manager': manager,
                               'sampled_at': time.time(), 'error': None}
                count += 1
            except Exception:
                if not self.status.get('error') or self.status.get('sampled_at') is None:
                    logging.exception('Falha na leitura do monitor Minecraft')
                self.status = {**self.status, 'error': 'Falha ao consultar o processo. Verifique os logs do painel.'}
            self.stop_event.wait(2)

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=8)
