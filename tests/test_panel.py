import json
import os
import stat
import sys
import time
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel.backups import Backups
from panel.config import Settings
from panel.main import create_app
from panel.security import tailscale_identity
from panel.store import Store
from panel.minecraft import Minecraft
from panel.monitor import Monitor


@pytest.fixture
def installation(tmp_path):
    root = tmp_path / 'minecraft'
    (root / 'world').mkdir(parents=True)
    (root / 'world/level.dat').write_bytes(b'current-world')
    (root / 'mods').mkdir()
    (root / 'mods/keep.jar').write_bytes(b'mod')
    (root / 'backups').mkdir()
    store = Store(tmp_path / 'state/panel.sqlite3')
    return root, Backups(root, store), store


def archive(root, entries, name='test.zip'):
    p = root / 'backups' / name
    with zipfile.ZipFile(p, 'w') as z:
        for key, value in entries.items():
            info = zipfile.ZipInfo()
            info.filename = key  # Preserve hostile separators even on Windows.
            z.writestr(info, value)
    os.utime(p, (time.time()-180, time.time()-180))
    return p


def test_restore_preserves_current_world_and_mods(installation):
    root, backups, store = installation
    archive(root, {'world/level.dat': b'restored', 'world/region/r.0.0.mca': b'region'})
    minecraft = Mock()
    result = backups.restore('test.zip', minecraft, lambda _: None)
    minecraft.stop.assert_called_once()
    assert (root / 'world/level.dat').read_bytes() == b'restored'
    assert (root / result['recovery'] / 'level.dat').read_bytes() == b'current-world'
    assert (root / 'mods/keep.jar').read_bytes() == b'mod'
    minecraft.start.assert_not_called()


@pytest.mark.parametrize('bad', ['../outside', '/tmp/outside', 'world/../../outside', 'world\\escape', 'mods/replace.jar', 'world/C:drive'])
def test_reject_zip_slip_and_non_world_files(installation, bad):
    root, backups, _ = installation
    archive(root, {'world/level.dat': b'ok', bad: b'bad'})
    with pytest.raises(ValueError):
        backups.restore('test.zip', Mock(), lambda _: None)
    assert (root/'world/level.dat').read_bytes() == b'current-world'


def test_reject_symlink(installation):
    root, backups, _ = installation
    info = zipfile.ZipInfo('world/link')
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(root/'backups/test.zip', 'w') as z:
        z.writestr('world/level.dat', b'ok')
        z.writestr(info, '../../outside')
    os.utime(root/'backups/test.zip', (0, 0))
    with pytest.raises(ValueError):
        backups.inspect('test.zip')


def test_do_not_touch_world_if_stop_fails(installation):
    root, backups, _ = installation
    archive(root, {'world/level.dat': b'restored'})
    minecraft = Mock()
    minecraft.stop.side_effect = RuntimeError('still running')
    with pytest.raises(RuntimeError):
        backups.restore('test.zip', minecraft, lambda _: None)
    assert (root/'world/level.dat').read_bytes() == b'current-world'


def test_reject_incomplete_backup(installation):
    root, backups, _ = installation
    archive(root, {'world/level.dat': b'restored'})
    (root/'backups/backups.json').write_text(json.dumps({'backups':[{'backupLocation':'test.zip','complete':False,'size':1}]}))
    with pytest.raises(ValueError):
        backups.inspect('test.zip')


def test_hash_mismatch_does_not_stop_game(installation):
    root, backups, _ = installation
    p = archive(root, {'world/level.dat': b'restored'})
    (root/'backups/backups.json').write_text(json.dumps({'backups':[{'backupLocation':'test.zip','complete':True,'size':p.stat().st_size,'sha1':'bad'}]}))
    mc = Mock()
    with pytest.raises(ValueError):
        backups.restore('test.zip', mc, lambda _: None)
    mc.stop.assert_not_called()


def test_old_backups_have_no_invented_metrics(installation):
    root, backups, store = installation
    archive(root, {'world/level.dat': b'world'})
    assert backups.listing()[0]['metrics'] is None
    store.observe('test.zip', {'cpu_percent': 12, 'ram_bytes': 100})
    store.observe('test.zip', {'cpu_percent': 99, 'ram_bytes': 900})
    assert backups.listing()[0]['metrics']['cpu_percent'] == 12


def test_identity_blocks_other_users_and_tagged_devices():
    with patch('panel.security.subprocess.run') as run:
        run.return_value.stdout = json.dumps({'UserProfile':{'LoginName':'other@example.com'},'Node':{}})
        with pytest.raises(PermissionError):
            tailscale_identity('100.64.0.2', 'owner@example.com')
        run.return_value.stdout = json.dumps({'UserProfile':{'LoginName':'owner@example.com'},'Node':{'Tags':['tag:server']}})
        with pytest.raises(PermissionError):
            tailscale_identity('100.64.0.2', 'owner@example.com')
        run.return_value.stdout = json.dumps({'UserProfile':{'LoginName':'owner@example.com'},'Node':{}})
        assert tailscale_identity('100.64.0.2', 'owner@example.com') == 'owner@example.com'
    with pytest.raises(PermissionError):
        tailscale_identity('192.0.2.1', 'owner@example.com')


def test_http_csrf_demo_and_security_headers(installation, tmp_path):
    root, _, _ = installation
    app = create_app(Settings(root, tmp_path/'state2', '', '127.0.0.1', demo=True))
    with TestClient(app) as client:
        response = client.get('/')
        assert response.status_code == 200
        assert "script-src 'self'" in response.headers['content-security-policy']
        assert client.post('/api/actions', json={'action':'start'}).status_code == 403
        token = client.get('/api/status').json()['csrf']
        assert client.post('/api/actions', headers={'X-Panel-CSRF':token}, json={'action':'start'}).status_code == 403
        assert client.get('/assets/missing').status_code == 404


def test_http_denies_proxy_header_impersonation(installation, tmp_path):
    root, _, _ = installation
    app = create_app(Settings(root, tmp_path/'state2', 'owner@example.com', '100.64.0.1'))
    # No lifespan: do not start real process monitoring in this isolated test.
    with patch('panel.main.tailscale_identity', side_effect=PermissionError('denied')) as identity:
        client = TestClient(app)
        r = client.get('/api/status', headers={'X-Forwarded-For':'100.64.0.2','Tailscale-User-Login':'owner@example.com'})
        assert r.status_code == 403
        identity.assert_called_once_with('testclient', 'owner@example.com')


def test_start_never_generates_empty_world_after_interrupted_restore(tmp_path):
    mc = Minecraft(Settings(tmp_path, tmp_path/'state', '', '127.0.0.1'))
    with patch.object(mc, 'pm2') as pm2:
        with pytest.raises(RuntimeError):
            mc.start()
        pm2.assert_not_called()


def test_restore_rolls_back_if_installing_world_fails(installation):
    root, backups, _ = installation
    archive(root, {'world/level.dat': b'restored'})
    original = Path.rename
    def rename(path, target):
        if path.parent.name.startswith('.panel-restore-'):
            raise OSError('simulated rename failure')
        return original(path, target)
    with patch.object(Path, 'rename', rename):
        with pytest.raises(OSError):
            backups.restore('test.zip', Mock(), lambda _: None)
    assert (root/'world/level.dat').read_bytes() == b'current-world'


def test_monitor_records_only_new_backup_resources(installation):
    root, backups, store = installation
    archive(root, {'world/level.dat': b'old'}, 'old.zip')
    mc = Mock()
    mc.metrics.return_value = {'cpu_percent': 125.5, 'ram_bytes': 6000000000}
    mc.manager_status.return_value = {'state': 'online'}
    monitor = Monitor(mc, backups, store)
    archive(root, {'world/level.dat': b'new'}, 'new.zip')
    with patch('panel.monitor.ping', return_value={'ready':True}), patch.object(monitor.stop_event, 'wait', side_effect=lambda _: monitor.stop_event.set()):
        monitor.run()
    records = store.observations()
    assert 'old.zip' not in records
    assert records['new.zip']['cpu_percent'] == 125.5
    assert records['new.zip']['ram_bytes'] == 6000000000
    assert records['new.zip']['approximate'] is True


@pytest.mark.skipif(os.name == 'nt', reason='Colon in mod filenames is a Linux world format')
def test_restore_ftb_mod_filename_on_linux(installation):
    root, backups, _ = installation
    archive(root, {'world/level.dat': b'world', 'world/data/dankstorage:max_id.dat': b'dank-data'})
    backups.restore('test.zip', Mock(), lambda _: None)
    assert (root/'world/data/dankstorage:max_id.dat').read_bytes() == b'dank-data'
