from copy import deepcopy
import json
from types import SimpleNamespace
from datetime import timedelta
import subprocess
import pytest
import hourly_temperature_runtime as runtime


from datetime import datetime,timedelta,timezone
import json
TARGET = datetime(2026, 9, 20, 18, tzinfo=timezone.utc)
CUTOVER = (TARGET - timedelta(days=2)).isoformat()
def receipt(target=TARGET):
    return {'temperatureF': 70.0, 'receivedAt': target - timedelta(seconds=40),
            'storedAt': target - timedelta(seconds=30), 'validUntil': target + timedelta(seconds=80),
            'snapshotSha256': 'a' * 64, 'streamEpoch': '882078a7-c0f2-4079-a979-120a100c5e92'}

@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv('HOURLY_TEMP_QUALIFIED_ENABLE', '1')
    monkeypatch.setenv('HOURLY_TEMP_EVIDENCE_CUTOVER', CUTOVER)




def output(value):
    return SimpleNamespace(stdout=json.dumps({TARGET.isoformat(): value}, default=lambda v: v.isoformat()))










def test_absent_opt_in_preserves_legacy(monkeypatch):
    monkeypatch.delenv('HOURLY_TEMP_QUALIFIED_ENABLE')
    assert runtime.score_runtime_hourly({}, TARGET, lambda *_a: 7) == 7




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
