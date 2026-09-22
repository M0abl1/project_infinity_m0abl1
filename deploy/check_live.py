"""Read-only smoke check of a real installation; no process control or restoration."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from panel.backups import Backups
from panel.config import Settings
from panel.minecraft import Minecraft, ping
from panel.security import tailscale_identity
from panel.store import Store

configured = Settings.load()
root = configured.root
with tempfile.TemporaryDirectory(prefix='minecraft-panel-check-') as directory:
    settings = Settings(root, Path(directory), configured.owner, configured.bind)
    mc = Minecraft(settings)
    mc.metrics()
    time.sleep(1)
    print('metrics', json.dumps(mc.metrics()))
    print('manager', json.dumps(mc.manager_status()))
    print('protocol', json.dumps(ping()))
    store = Store(Path(directory)/'check.sqlite3')
    b = Backups(root, store)
    listing = b.listing()
    print('backups', len(listing))
    if listing:
        result = b.inspect(listing[0]['name'], verify=True)
        print('latest_backup_verified', result['name'], result['files'], result['verified'])
    if os.getenv('PANEL_CHECK_PEER'):
        print('owner_verified', tailscale_identity(os.environ['PANEL_CHECK_PEER'], settings.owner) == settings.owner)
