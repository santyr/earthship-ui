from copy import deepcopy
import json
from types import SimpleNamespace
from datetime import timedelta
import subprocess
import pytest
import hourly_temperature_runtime as runtime
from test_hourly_qualified_scoring import initial, receipt, TARGET, CUTOVER, fi


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv('HOURLY_TEMP_QUALIFIED_ENABLE', '1')
    monkeypatch.setenv('HOURLY_TEMP_EVIDENCE_CUTOVER', CUTOVER)
    monkeypatch.setattr(fi, 'series', lambda *_: pytest.fail('no numeric fallback'))


def run(state):
    return runtime.score_runtime_hourly(state, TARGET + timedelta(minutes=30), fi.score_hourly_targets)


def output(value):
    return SimpleNamespace(stdout=json.dumps({TARGET.isoformat(): value}, default=lambda v: v.isoformat()))


def test_process_bound_and_qualified_update(monkeypatch):
    def worker(argv, **kwargs):
        assert argv[-1] == '--read'
        assert kwargs['timeout'] == 30 and kwargs['check'] is True
        assert json.loads(kwargs['input'])['targets'] == [TARGET.isoformat()]
        return output(receipt())
    monkeypatch.setattr(runtime.subprocess, 'run', worker)
    state = initial()
    assert run(state) == 1
    assert state['hourly_temp_model']['12']['count'] == 1
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *_a, **_k: pytest.fail('no replay'))
    assert run(state) == 0


@pytest.mark.parametrize('failure', [subprocess.TimeoutExpired('worker', 30),
    subprocess.CalledProcessError(1, 'worker'), ValueError('bad response')])
def test_worker_failure_preserves_state(monkeypatch, failure):
    def fail(*_a, **_k): raise failure
    monkeypatch.setattr(runtime.subprocess, 'run', fail)
    state = initial(); before = deepcopy(state)
    assert run(state) == 0 and state == before


@pytest.mark.parametrize('response', ['{}', 'null', '[]', 'x', ' ' * 32769,
    json.dumps({TARGET.isoformat(): {'receivedAt': 'bad'}})])
def test_bad_output_preserves_state(monkeypatch, response):
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(stdout=response))
    state = initial(); before = deepcopy(state)
    assert run(state) == 0 and state == before


@pytest.mark.parametrize('enabled,cutover', [('0', CUTOVER), ('true', CUTOVER),
    ('1', ''), ('1', '2026-09-18T00:00:00'), ('1', '2099-01-01T00:00:00Z')])
def test_invalid_activation_never_queries_or_changes(monkeypatch, enabled, cutover):
    monkeypatch.setenv('HOURLY_TEMP_QUALIFIED_ENABLE', enabled)
    monkeypatch.setenv('HOURLY_TEMP_EVIDENCE_CUTOVER', cutover)
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *_a, **_k: pytest.fail('no query'))
    state = initial(); before = deepcopy(state)
    assert run(state) == 0 and state == before


def test_absent_opt_in_preserves_legacy(monkeypatch):
    monkeypatch.delenv('HOURLY_TEMP_QUALIFIED_ENABLE')
    assert runtime.score_runtime_hourly({}, TARGET, lambda *_a: 7) == 7


def test_unqualified_history_does_not_consume(monkeypatch):
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *_a, **_k: output(None))
    state = initial(); before = deepcopy(state)
    assert run(state) == 0 and state == before


def test_private_db_config(tmp_path):
    path = tmp_path / 'db.json'
    config = dict(host='127.0.0.1', port=5432, dbname='openhab',
                  user='weather_temperature_reader', password='test-only')
    path.write_text(json.dumps(config)); path.chmod(0o600)
    assert runtime.read_db_config(str(path)) == config
    path.chmod(0o640)
    with pytest.raises(ValueError): runtime.read_db_config(str(path))
    path.chmod(0o600)
    link = tmp_path / 'link'; link.symlink_to(path)
    with pytest.raises(OSError): runtime.read_db_config(str(link))
    config['user'] = 'openhab'; path.write_text(json.dumps(config))
    with pytest.raises(ValueError): runtime.read_db_config(str(path))


@pytest.mark.parametrize('targets', [[], ['2099-01-01T00:00:00Z'], ['2026-01-01T00:00:00'],
    ['2026-01-01T00:00:00Z'] * 25, ['2026-01-01T00:00:00Z'] * 2])
def test_worker_rejects_invalid_targets_before_connection(targets):
    with pytest.raises(ValueError):
        runtime.collect({'targets': targets, 'assessed_at': '2026-09-19T00:00:00Z'},
                        config_path=None, policy_path=None)
