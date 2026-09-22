import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel.config import Settings
from panel.main import create_app
from panel.minecraft import Minecraft
from panel.spark import SparkReports, summarize
from panel.spark_format import Profile


def sample():
    p = Profile()
    p.metadata.start_time = 1700000000000
    p.metadata.end_time = 1700000060000
    p.metadata.sources.add(key='examplemod').value.name = 'Example mod'
    p.class_sources.add(key='example.Tick', value='examplemod')
    thread = p.threads.add(name='Server thread', times=[100], children_refs=[0])
    thread.children.add(class_name='net.minecraft.Server', method_name='tick', times=[100], children_refs=[1])
    thread.children.add(class_name='example.Tick', method_name='tick', times=[80], children_refs=[2])
    thread.children.add(class_name='java.util.List', method_name='sort', times=[30])
    return p


def test_partition_and_inclusive_do_not_double_count():
    data = summarize(sample().SerializeToString())
    rows = {r['id']: r for r in data['rows']}
    assert rows['examplemod']['direct_percent'] == 50
    assert rows['examplemod']['inclusive_percent'] == 80
    assert rows['minecraft']['direct_percent'] == 20
    assert rows['java']['direct_percent'] == 30
    assert sum(r['direct_percent'] for r in rows.values()) == 100


def test_method_mapping_overrides_class_and_recursion_is_not_double_counted():
    p = sample()
    p.method_sources.add(key='java.util.List;sort;()V', value='examplemod')
    p.threads[0].children[2].method_desc = '()V'
    rows = {r['id']: r for r in summarize(p.SerializeToString())['rows']}
    assert rows['examplemod']['direct_percent'] == 80
    assert rows['examplemod']['inclusive_percent'] == 80


@pytest.mark.parametrize('kind', ['cycle', 'duplicate', 'outside', 'nan', 'negative', 'inconsistent', 'allocation', 'empty'])
def test_malformed_profiles_rejected(kind):
    p = sample()
    if kind == 'cycle': p.threads[0].children[2].children_refs.append(0)
    if kind == 'duplicate': p.threads[0].children[0].children_refs.append(1)
    if kind == 'outside': p.threads[0].children_refs[0] = 999
    if kind == 'nan': p.threads[0].times[0] = float('nan')
    if kind == 'negative': p.threads[0].times[0] = -1
    if kind == 'inconsistent': p.threads[0].children[1].times[0] = 200
    if kind == 'allocation': p.metadata.sampler_mode = 1
    if kind == 'empty': p.ClearField('threads')
    with pytest.raises(ValueError): summarize(p.SerializeToString())


def test_file_validation_cache_and_no_sensitive_metadata(tmp_path):
    directory = tmp_path / 'config/spark'
    directory.mkdir(parents=True)
    path = directory / 'test.sparkprofile'
    path.write_bytes(sample().SerializeToString())
    os.utime(path, (time.time()-10, time.time()-10))
    reports = SparkReports(tmp_path)
    assert reports.listing()[0]['name'] == path.name
    assert reports.read(path.name)['sampled_ms'] == 100
    assert reports.read(path.name)['sampled_ms'] == 100
    assert 'server_configurations' not in json.dumps(reports.read(path.name))
    with pytest.raises(ValueError): reports.read('../test.sparkprofile')
    with pytest.raises(ValueError): reports.read('config.json')
    path.write_bytes(b'not a valid profile')
    os.utime(path, (time.time()-10, time.time()-10))
    with pytest.raises(ValueError): reports.read(path.name)


def test_empty_report_and_zero_weight():
    with pytest.raises(ValueError): summarize(b'')
    p = sample()
    for node in [p.threads[0], *p.threads[0].children]: node.times[0] = 0
    with pytest.raises(ValueError): summarize(p.SerializeToString())


def test_api_permissions_and_demo(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path / 'state', 'owner@example.com', '127.0.0.1', demo=True))
    with TestClient(app) as client:
        assert client.get('/api/spark').json() == []
        assert client.get('/api/spark/missing.sparkprofile').status_code == 400
        assert client.post('/api/actions', json={'action':'spark'}).status_code == 403
        csrf = client.get('/api/status').json()['csrf']
        assert client.post('/api/actions', json={'action':'spark'}, headers={'x-panel-csrf':csrf}).status_code == 403
        assert client.get('/assets/spark.js').status_code == 200
    app = create_app(Settings(tmp_path, tmp_path / 'state2', 'owner@example.com', '100.64.0.1'))
    with patch('panel.main.tailscale_identity', side_effect=PermissionError('denied')):
        assert TestClient(app).get('/api/spark').status_code == 403


def test_console_command_is_fixed_and_numeric(tmp_path):
    mc = Minecraft(Settings(tmp_path, tmp_path/'state', 'owner@example.com', '100.64.0.1'))
    mc.java = Mock(return_value=[Mock()])
    mc.pm2 = Mock(return_value=json.dumps([{'name':'project-infinity','pm_id':3}]))
    with patch('panel.minecraft.subprocess.run', return_value=Mock(stdout='sent',stderr='')) as run:
        mc.capture_spark()
    assert run.call_args.args[0] == ['pm2','send','3','spark profiler start --timeout 60 --save-to-file']
    assert 'shell' not in run.call_args.kwargs
