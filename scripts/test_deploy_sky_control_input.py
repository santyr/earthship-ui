"""Offline tests for the default-off, protected sky-provider handoff."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('protected_sky_release',
    Path(__file__).with_name('deploy-sky-control-input.py'))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
NOW = datetime(2026, 10, 4, 18, tzinfo=timezone.utc)


def safety_values():
    return {'BMS_Comms_Status': 'OK', 'BMS_SOC_Evidence_JSON': 'native-fixture',
            'DCData_Voltage': '53.6 V', 'SchneiderTelemetry_Status': 'OK,dc',
            'Schneider_DCData_LastUpdate': NOW.isoformat(),
            'Sun_Position_Elevation': '30',
            'Sun_Rise_Start': (NOW-timedelta(hours=5)).isoformat(),
            'SouthOutlet_LastCycleStart': (NOW-timedelta(minutes=20)).isoformat(),
            'WeatherData_HealthStatus': 'OK', 'WeatherData_WH65B_AgeSeconds': '20',
            **{n: 'OFF' for n in release.sky.PUMPS}}


def test_closed_release_gate_refuses_apply_before_reads_or_backups(monkeypatch):
    monkeypatch.setattr(release.engine, 'preflight', lambda *_: pytest.fail('unexpected read'))
    monkeypatch.setattr(release.engine, 'backup', lambda *_: pytest.fail('unexpected backup'))
    with pytest.raises(RuntimeError, match='release gate'):
        release.main(['--apply', '--attended', '--physical-pumps-off'])


def test_read_only_preflight_never_creates_backup_or_mutates(monkeypatch):
    monkeypatch.setattr(release.engine,'preflight',lambda *_: ({},{}))
    monkeypatch.setattr(release,'healthy_off',lambda: 'native-evidence')
    monkeypatch.setattr(release,'continuity',lambda _: {'original':'snapshot'})
    monkeypatch.setattr(release.engine,'backup',lambda *_: pytest.fail('unexpected backup'))
    monkeypatch.setattr(release.engine,'request',lambda *_: pytest.fail('unexpected mutation'))
    release.main([])


@pytest.mark.parametrize('flags',[[],['--attended'],['--physical-pumps-off']])
def test_even_open_gate_requires_both_attendance_flags_before_reads(monkeypatch,flags):
    monkeypatch.setattr(release,'RELEASE_READY',True)
    monkeypatch.setattr(release.engine,'preflight',lambda *_: pytest.fail('unexpected read'))
    with pytest.raises(RuntimeError,match='attendance'):
        release.main(['--apply',*flags])


@pytest.mark.parametrize('damage', ['comms', 'soc', 'voltage', 'stamp', 'weather',
                                   'weather-age', 'pump', 'cooldown', 'sun'])
def test_unsafe_inputs_refuse_handoff(monkeypatch, damage):
    values = safety_values()
    monkeypatch.setattr(release.engine.oh, 'atomic_soc_freshness',
                        lambda *_: 'invalid' if damage == 'soc' else None)
    if damage == 'comms': values['BMS_Comms_Status'] = 'STALE'
    elif damage == 'voltage': values['DCData_Voltage'] = 'NaN'
    elif damage == 'stamp': values['Schneider_DCData_LastUpdate'] = (NOW-timedelta(minutes=6)).isoformat()
    elif damage == 'weather': values['WeatherData_HealthStatus'] = 'STALE'
    elif damage == 'weather-age': values['WeatherData_WH65B_AgeSeconds'] = '500'
    elif damage == 'pump': values[release.sky.PUMPS[0]] = 'ON'
    elif damage == 'cooldown': values['SouthOutlet_LastCycleStart'] = (NOW-timedelta(minutes=50)).isoformat()
    elif damage == 'sun': values['Sun_Position_Elevation'] = 'UNDEF'
    with pytest.raises(RuntimeError): release.check_safety(values, NOW)


def test_safe_daytime_cooldown_and_native_future_sunrise(monkeypatch):
    monkeypatch.setattr(release.engine.oh, 'atomic_soc_freshness', lambda *_: None)
    values = safety_values()
    release.check_safety(values, NOW)
    values['Sun_Position_Elevation'] = '-12'
    values['Sun_Rise_Start'] = (NOW+timedelta(hours=1)).isoformat()
    release.check_safety(values, NOW)
    values['Sun_Rise_Start'] = (NOW-timedelta(hours=12)).isoformat()
    with pytest.raises(RuntimeError): release.check_safety(values, NOW)


@pytest.mark.parametrize('health',['ok','degraded'])
def test_weather_health_matches_existing_sky_case_normalization(monkeypatch,health):
    monkeypatch.setattr(release.engine.oh,'atomic_soc_freshness',lambda *_: None)
    values=safety_values(); values['WeatherData_HealthStatus']=health
    release.check_safety(values,NOW)


@pytest.fixture
def transaction(tmp_path, monkeypatch):
    config = replace(release.CONFIG, target=tmp_path/'sky.js')
    original = {'uid': config.uid, 'editable': True, 'name': 'Original',
                'visibility':'HIDDEN','configuration':{'custom':'preserved'},
                'status': {'status': 'IDLE', 'statusDetail': 'NONE'},
                'triggers': [{'type': t, 'configuration': dict(c)} for t,c in config.triggers],
                'conditions': [], 'actions': [{'configuration': {'script': 'original'}}]}
    current = copy.deepcopy(original)
    calls=[]; guards=[]; fault={'install':False, 'drift':False}
    def read(_=None):
        if config.target.exists():
            return {'uid':config.uid,'editable':False,'triggers':original['triggers'],
                    'status':{'status':'IDLE','statusDetail':'NONE'}}
        return copy.deepcopy(current) if current is not None else None
    def request(method, path, body=None):
        nonlocal current
        assert path in ('/rules', '/rules/'+config.uid)
        assert (method,path) in [('POST','/rules'),('DELETE','/rules/'+config.uid)]
        calls.append((method,path))
        if method=='DELETE': current=None; return 204
        current=copy.deepcopy(body); current.update(editable=True,status=original['status']); return 201
    def wait(predicate, *_):
        actual=read()
        assert predicate(actual), 'fixture provider predicate failed'
        if fault['install'] and config.target.exists():
            fault['install']=False
            raise RuntimeError('synthetic file readback failure')
        return actual
    def guard():
        guards.append(True)
        if fault['drift']: raise RuntimeError('unowned continuity drift')
    monkeypatch.setattr(release.engine,'rule_or_none',read)
    monkeypatch.setattr(release.engine,'request',request)
    monkeypatch.setattr(release.engine,'wait_rule',wait)
    monkeypatch.setattr(release.engine.oh,'get',lambda *_: [read()] if read() else [])
    receipt=tmp_path/'private'; receipt.mkdir(mode=0o700)
    tx=release.Transaction(original,receipt,guard,config=config)
    return tx,config,original,calls,guards,fault,read


def test_complete_round_trip_preserves_source_and_scopes_rest_writes(transaction):
    tx,config,_,calls,guards,_,read=transaction
    tx.apply()
    assert config.target.read_bytes()==config.source.read_bytes()
    assert read()['editable'] is False
    assert [m for m,_ in calls]==['DELETE','POST','DELETE']
    assert len(guards)>=8


@pytest.mark.parametrize('field',['visibility','configuration'])
def test_managed_preimage_metadata_drift_refused(transaction,field):
    tx,_,original,_,_,_,_=transaction
    changed={**original,field:'unowned change'}
    assert not tx.managed_original(changed)


def test_failed_file_readback_returns_exact_managed_original(transaction):
    tx,config,original,calls,_,fault,read=transaction
    fault['install']=True
    with pytest.raises(RuntimeError,match='readback failure'): tx.apply()
    assert not config.target.exists()
    assert release.engine.managed_rule_ok(read(),original)
    assert [m for m,_ in calls]==['DELETE','POST']


def test_unowned_target_never_overwritten_or_withdrawn(transaction):
    tx,config,_,calls,_,_,_=transaction
    config.target.write_bytes(b'unowned source')
    with pytest.raises(RuntimeError): tx.apply()
    assert config.target.read_bytes()==b'unowned source'
    assert calls==[]


def test_exclusive_install_refuses_a_racing_target(transaction):
    tx,config,_,_,_,_,_=transaction
    config.target.write_bytes(b'racing source')
    with pytest.raises(FileExistsError): tx.install_exclusive()
    assert config.target.read_bytes()==b'racing source'


def test_unowned_continuity_drift_stops_before_any_mutation(transaction):
    tx,_,_,calls,_,fault,_=transaction
    fault['drift']=True
    with pytest.raises(RuntimeError,match='continuity drift'): tx.apply()
    assert calls==[]


def test_rollback_refuses_an_unowned_replacement_file(transaction):
    tx,config,_,calls,_,_,_=transaction
    tx.to_file()
    replacement=config.target.with_suffix('.replacement')
    replacement.write_bytes(config.target.read_bytes())
    replacement.replace(config.target)
    with pytest.raises(RuntimeError,match='unowned sky file'): tx.to_managed()
    assert config.target.exists()
    assert [m for m,_ in calls]==['DELETE']


def test_final_source_drift_cannot_be_reported_as_success(transaction):
    tx,config,_,calls,_,_,_=transaction
    observed=[]
    def guard():
        observed.append(True)
        if len(observed)==3: config.target.write_bytes(b'unowned changed action')
    tx.guard=guard
    with pytest.raises(RuntimeError,match='unowned sky file'): tx.to_file()
    assert config.target.read_bytes()==b'unowned changed action'
    assert [m for m,_ in calls]==['DELETE']
