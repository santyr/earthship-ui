"""Offline guarded release checks; no production calls or pump commands."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import copy
import io
import json
from types import SimpleNamespace

import pytest

PATH = Path(__file__).with_name('deploy-greywater-durable-recovery.py')
spec = importlib.util.spec_from_file_location('greywater_recovery_release', PATH)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
NOW = datetime(2026, 10, 3, 23, tzinfo=timezone.utc)


def values():
    return {'BMS_Comms_Status': 'OK', 'BMS_SOC_Evidence_JSON': 'fixture',
            'DCData_Voltage': '53.6', 'SchneiderTelemetry_Status': 'OK,fixture',
            'Schneider_DCData_LastUpdate': NOW.isoformat(),
            'Sun_Position_Elevation': '20 °',
            'SouthOutlet_LastCycleStart': (NOW - timedelta(minutes=30)).isoformat()}


def test_good_preflight(monkeypatch):
    monkeypatch.setattr(release.guard.oh, 'atomic_soc_freshness', lambda *_: None)
    release.check_values(values(), NOW)


@pytest.mark.parametrize(('field', 'value'), [
    ('BMS_Comms_Status', 'STALE'), ('DCData_Voltage', 'NaN'), ('DCData_Voltage', '65'),
    ('SchneiderTelemetry_Status', 'STALE'), ('Schneider_DCData_LastUpdate', 'NULL'),
    ('Schneider_DCData_LastUpdate', (NOW - timedelta(minutes=6)).isoformat()),
    ('SouthOutlet_LastCycleStart', (NOW - timedelta(minutes=59)).isoformat()),
    ('SouthOutlet_LastCycleStart', (NOW + timedelta(minutes=1)).isoformat()),
    ('Sun_Position_Elevation', 'UNDEF'),
])
def test_unsafe_preflight_refused(monkeypatch, field, value):
    monkeypatch.setattr(release.guard.oh, 'atomic_soc_freshness', lambda *_: None)
    with pytest.raises(RuntimeError): release.check_values({**values(), field: value}, NOW)


def test_expired_soc_refused(monkeypatch):
    monkeypatch.setattr(release.guard.oh, 'atomic_soc_freshness', lambda *_: 'expired')
    with pytest.raises(RuntimeError): release.check_values(values(), NOW)


def test_apply_requires_attendance_and_physical_confirmation_before_live_reads(monkeypatch):
    monkeypatch.setattr(release.guard.oh, 'get', lambda *_: pytest.fail('unexpected live read'))
    with pytest.raises(RuntimeError, match='attendance'): release.main(['--apply'])


def test_pins_match_qualified_candidate():
    assert release.guard.OLD_SHA == 'e697e2626a5e1ab4e4d079612c4b85d16dd79178a4ff80a5208b4bb108970d18'
    assert release.guard.NEW_SHA == release.guard.digest(release.guard.SOURCE.read_text())


def transaction(monkeypatch, *, enable_failure=False, item_drift=False):
    baseline = {'uid': release.guard.UID, 'name': 'fixture', 'triggers': [], 'conditions': [],
                'actions': [{'configuration': {'script': 'fixture-original'}}],
                'status': {'status': 'IDLE', 'statusDetail': 'NONE'}}
    live = copy.deepcopy(baseline)
    calls = []
    monkeypatch.setattr(release.guard, 'OLD_SHA', release.guard.digest('fixture-original'))
    monkeypatch.setattr(release.sky, 'control_payload', lambda *_: {})
    monkeypatch.setattr(release.guard.oh, 'atomic_soc_freshness', lambda *_: None)
    monkeypatch.setattr(release, 'datetime', SimpleNamespace(now=lambda *_: NOW,
                                                          fromisoformat=datetime.fromisoformat))
    def get(path):
        if path == '/rules/' + release.guard.UID: return copy.deepcopy(live)
        if path == '/links': return []
        if path.startswith('/persistence/items/'): return {'data': []}
        if path.startswith('/items/'):
            name = path.split('/')[2].split('?')[0]
            result = {'name': name, 'type': 'String', 'state': values().get(name, 'OFF')}
            if item_drift and calls and any(method == 'PUT' for _, method in calls):
                result['label'] = 'unowned drift'
            return result
        pytest.fail('unscoped read')
    def request(path, method, payload, content_type):
        nonlocal enable_failure
        assert path.startswith('/rules/' + release.guard.UID)
        calls.append((path, method))
        if path.endswith('/enable'):
            flag = payload == b'true'
            if flag and enable_failure:
                enable_failure = False
                raise RuntimeError('synthetic enable failure')
            live['status'] = {'status': 'IDLE' if flag else 'UNINITIALIZED',
                              'statusDetail': 'NONE' if flag else 'DISABLED'}
        else:
            prior_status = live['status']
            live.clear(); live.update(json.loads(payload)); live['status'] = prior_status
    class MemoryBackup:
        def __truediv__(self, _): return SimpleNamespace(open=lambda _: io.StringIO())
        def __str__(self): return 'memory-only-test-backup'
    monkeypatch.setattr(release.guard.oh, 'get', get)
    monkeypatch.setattr(release.guard, 'request', request)
    monkeypatch.setattr(release.guard, 'backup', lambda *_: MemoryBackup())
    return baseline, live, calls


def test_default_preflight_performs_no_mutation(monkeypatch):
    _, _, calls = transaction(monkeypatch)
    release.main([])
    assert calls == []


def test_attended_exact_transaction_never_commands_items(monkeypatch):
    _, live, calls = transaction(monkeypatch)
    release.main(['--apply', '--attended', '--physical-pumps-off'])
    assert release.guard.digest(live['actions'][0]['configuration']['script']) == release.guard.NEW_SHA
    assert live['status'] == {'status': 'IDLE', 'statusDetail': 'NONE'}
    assert len([x for x in calls if x[1] == 'PUT']) == 1


def test_failed_enable_restores_original_source_and_enabled_state(monkeypatch):
    baseline, live, calls = transaction(monkeypatch, enable_failure=True)
    with pytest.raises(RuntimeError, match='synthetic enable failure'):
        release.main(['--apply', '--attended', '--physical-pumps-off'])
    assert live['actions'] == baseline['actions']
    assert live['status'] == baseline['status']
    assert len([x for x in calls if x[1] == 'PUT']) == 2


def test_unowned_item_drift_blocks_enable_and_unsafe_rollback(monkeypatch):
    _, live, calls = transaction(monkeypatch, item_drift=True)
    with pytest.raises(RuntimeError, match='definition drift'):
        release.main(['--apply', '--attended', '--physical-pumps-off'])
    assert live['status'] == {'status': 'UNINITIALIZED', 'statusDetail': 'DISABLED'}
    assert len([x for x in calls if x[1] == 'PUT']) == 1
