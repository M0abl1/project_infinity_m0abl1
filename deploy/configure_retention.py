"""Explicit setup of the owner's requested ten-backup policy; preview by default."""
import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from panel.config import Settings
from panel.retention import Retention
from panel.backups import Backups
from panel.store import Store
import threading


def configure(app, root):
    config = root / 'config/ftbbackups2.json'
    env = app / '.env'
    if config.is_symlink() or env.is_symlink():
        raise ValueError('Links simbólicos não são aceitos para configurar retenção.')
    content = config.read_text()
    updated, count = re.subn(r'("max_backups"\s*:\s*)\d+', r'\g<1>10', content)
    updated, modes = re.subn(r'("retention_mode"\s*:\s*)"[^"]+"', r'\g<1>"MAX_BACKUPS"', updated)
    if count != 1 or modes != 1:
        raise ValueError('Configuração FTB inesperada; nenhuma alteração aplicada.')
    env_text = env.read_text()
    env_text = re.sub(r'^PANEL_BACKUP_KEEP=.*(?:\n|$)', '', env_text, flags=re.M).rstrip() + '\nPANEL_BACKUP_KEEP=10\n'
    for path, original, replacement in ((config, content, updated), (env, env.read_text(), env_text)):
        backup = path.with_name(path.name + '.before-retention')
        if not backup.exists():
            with backup.open('x') as stream:
                stream.write(original)
            backup.chmod(0o600)
        # Config watcher sees a complete file, never a partially written JSON.
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(replacement)
        temporary.chmod(0o600)
        os.replace(temporary, path)
    print('Configured: native max_backups=10; panel total completed backups=10. Restart only the panel to activate.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply-settings', action='store_true')
    parser.add_argument('--app', type=Path, required=True)
    args = parser.parse_args()
    settings = Settings.load()
    if args.apply_settings:
        configure(args.app.resolve(), settings.root)
    else:
        with tempfile.TemporaryDirectory() as temp:
            backups = Backups(settings.root, Store(Path(temp) / 'preview.sqlite3'))
            retention = Retention(backups, threading.Lock(), 10)
            print('Oldest completed files exceeding ten:', retention.sweep(dry_run=True))
