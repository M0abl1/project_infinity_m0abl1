import json
import os
import sys
import threading
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel.backups import Backups
from panel.retention import Retention
from panel.store import Store


def setup(tmp_path, count=11):
    root = tmp_path / 'game'
    directory = root / 'backups'
    directory.mkdir(parents=True)
    entries = []
    for i in range(1, count + 1):
        p = directory / f'2026-1-{i}_0-0-0.zip'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('world/level.dat', b'fixture world')
        os.utime(p, (time.time()-1000, time.time()-1000))
        entries.append({'backupLocation':str(p),'createTime':1767225600000+i*86400000,
                        'complete':True,'size':p.stat().st_size,'snapshot':i==1})
    (directory/'backups.json').write_text(json.dumps({'backups':entries}))
    b = Backups(root, Store(tmp_path/'state/panel.sqlite3'))
    return Retention(b, threading.Lock(), 10), entries


def test_retains_ten_by_creation_including_old_snapshot(tmp_path):
    r, entries = setup(tmp_path)
    assert r.sweep(dry_run=True) == ['2026-1-1_0-0-0.zip']
    assert len(list(r.backups.directory.glob('*.zip'))) == 11
    assert r.sweep() == ['2026-1-1_0-0-0.zip']
    assert len(list(r.backups.directory.glob('*.zip'))) == 10
    assert r.sweep() == []
    assert r.backups.store.events()[0]['action'] == 'retention_delete'


def test_legacy_file_uses_filename_date_not_copy_mtime(tmp_path):
    r, entries = setup(tmp_path)
    (r.backups.directory/'backups.json').write_text(json.dumps({'backups':entries[1:]}))
    assert r.sweep() == ['2026-1-1_0-0-0.zip']


@pytest.mark.parametrize('kind', ['corrupt', 'incomplete', 'recent', 'catalogue', 'unrelated'])
def test_safety_failures_prevent_deletion(tmp_path, kind):
    r, entries = setup(tmp_path)
    last = r.backups.directory/'2026-1-11_0-0-0.zip'
    if kind=='corrupt':
        data=last.read_bytes().replace(b'fixture world',b'broken! world')
        last.write_bytes(data)
        os.utime(last, (time.time()-1000, time.time()-1000))
    if kind=='incomplete':
        entries[-1]['complete']=False
        (r.backups.directory/'backups.json').write_text(json.dumps({'backups':entries}))
    if kind=='recent': os.utime(last, None)
    if kind=='catalogue': (r.backups.directory/'backups.json').write_text('{')
    if kind=='unrelated': last.rename(r.backups.directory/'unrelated.zip')
    with pytest.raises((ValueError, zipfile.BadZipFile)): r.sweep()
    assert len(list(r.backups.directory.glob('*.zip'))) == 11


def test_changed_inventory_and_failed_audit_prevent_deletion(tmp_path):
    r, _ = setup(tmp_path)
    original = r.backups.inspect
    def inspect(name, verify):
        result = original(name, verify)
        if name=='2026-1-1_0-0-0.zip':
            os.utime(r.backups.directory/name, None)
        return result
    with patch.object(r.backups, 'inspect', side_effect=inspect):
        with pytest.raises(ValueError): r.sweep()
    assert len(list(r.backups.directory.glob('*.zip'))) == 11


def test_disabled_and_recovery_untouched(tmp_path):
    r, _ = setup(tmp_path)
    recovery = r.backups.root/'.panel-recovery/saved/world'
    recovery.mkdir(parents=True)
    (recovery/'level.dat').write_bytes(b'preserve')
    r.keep=0
    assert r.sweep()==[]
    r.keep=10
    r.sweep()
    assert (recovery/'level.dat').read_bytes()==b'preserve'


def test_failed_audit_prevents_unlink(tmp_path):
    r, _ = setup(tmp_path)
    with patch.object(r.backups.store, 'audit', side_effect=RuntimeError('audit unavailable')):
        with pytest.raises(RuntimeError): r.sweep()
    assert len(list(r.backups.directory.glob('*.zip'))) == 11


def test_operation_lock_skips_cleanup(tmp_path):
    r, _ = setup(tmp_path)
    r.lock.acquire()
    with patch.object(r.stop_event, 'wait', side_effect=[False, True]), patch.object(r, 'sweep') as sweep:
        r.run()
        sweep.assert_not_called()
    r.lock.release()


def test_download_lock_released_even_on_response_error(tmp_path):
    import asyncio
    from panel.main import LockedFileResponse
    lock=threading.Lock()
    lock.acquire()
    response=LockedFileResponse(tmp_path/'missing.zip', operation_lock=lock)
    async def send(_): pass
    async def receive(): return {'type':'http.disconnect'}
    with pytest.raises(RuntimeError):
        asyncio.run(response({'type':'http','method':'GET','headers':[]}, receive, send))
    assert not lock.locked()
