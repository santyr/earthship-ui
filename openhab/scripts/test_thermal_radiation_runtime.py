"""Receipt-only thermal radiation input; no live activation or fallback."""
from datetime import datetime, timedelta
import json
import math
from types import SimpleNamespace
from pathlib import Path

import pytest

from test_weather_radiation_reader import AT, POLICY, raw
from weather_radiation_reader import _snapshot
import thermal_radiation_runtime as runtime


@pytest.fixture(autouse=True)
def assessment_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return AT+timedelta(days=1)
    monkeypatch.setattr(runtime, 'datetime', Clock)


def evidence(target=AT, **changes):
    value = _snapshot(raw(), AT, POLICY)[1]
    value.update(changes)
    return value


def env():
    return dict(THERMAL_RADIATION_SHADOW_QUALIFIED_ENABLE='1',
                THERMAL_RADIATION_DB_CONFIG='/private/reader.jdbc',
                THERMAL_RADIATION_POLICY='/private/radiation.json',
                THERMAL_RADIATION_EVIDENCE_CUTOVER=(AT-timedelta(hours=1)).isoformat())


def encoded(value):
    return json.dumps(value, default=lambda value: value.isoformat())


def test_default_off_does_not_start_worker(monkeypatch):
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k: pytest.fail('worker ran'))
    assert runtime.configured_shadow_radiation(AT, environ={}) is None


@pytest.mark.parametrize('flag', ['', '0', 'true'])
def test_explicit_bad_flag_refuses_without_legacy_fallback(flag):
    with pytest.raises(ValueError, match='^qualified shadow radiation evidence unavailable$'):
        runtime.configured_shadow_radiation(AT, environ={**env(),
            'THERMAL_RADIATION_SHADOW_QUALIFIED_ENABLE': flag})


def test_worker_is_single_target_bounded_and_preserves_native_metadata(monkeypatch):
    calls = []
    now = AT+timedelta(seconds=30)
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=encoded([[now, evidence()]]))
    monkeypatch.setattr(runtime.subprocess, 'run', run)
    result = runtime.configured_shadow_radiation(now, environ=env())
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[-1] == '--read' and 'password' not in ' '.join(args)
    assert kwargs['timeout'] == 30 and kwargs['stderr'] == runtime.subprocess.DEVNULL
    assert json.loads(kwargs['input']) == dict(target=now.isoformat(),
        assessed_at=now.isoformat(), cutover=env()['THERMAL_RADIATION_EVIDENCE_CUTOVER'])
    assert result['history'] == ()  # No unnecessary 24-hour numeric radiation query.
    assert result['current']['at'] == AT
    assert result['current']['validUntil'] == AT+timedelta(seconds=120)
    assert result['current']['value'] == 100
    assert result['current']['sourceEvidence'] == evidence()


@pytest.mark.parametrize('damage', ['missing', 'target', 'legacy', 'expired', 'future',
    'cutover', 'conversion', 'hash', 'epoch', 'counter', 'extra', 'boolean', 'nan'])
def test_worker_receipt_validation_refuses_unqualified_result(monkeypatch, damage):
    value = evidence()
    target = AT
    if damage == 'missing': value = None
    elif damage == 'target': target += timedelta(seconds=1)
    elif damage == 'legacy': value.update(fault_visibility='unverified', faultCount=None)
    elif damage == 'expired': value['validUntil'] = AT
    elif damage == 'future': value['storedAt'] = AT+timedelta(seconds=1)
    elif damage == 'cutover': value['radioDecodedAt'] = AT-timedelta(hours=2)
    elif damage == 'conversion': value['irradianceWm2'] = 101
    elif damage == 'hash': value['snapshotSha256'] = 'invalid'
    elif damage == 'epoch': value['streamEpoch'] = 'not-a-uuid'
    elif damage == 'counter': value['faultCount'] = value['sequence']
    elif damage == 'extra': value['fresh'] = True
    elif damage == 'boolean': value['irradianceWm2'] = True
    elif damage == 'nan': value['irradianceWm2'] = math.nan
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k:
        SimpleNamespace(stdout=encoded([[target, value]])))
    with pytest.raises(ValueError, match='^qualified shadow radiation evidence unavailable$'):
        runtime.configured_shadow_radiation(AT, environ=env())


@pytest.mark.parametrize('output', ['{}', '[]', 'null', '['*300, 'x'*262145])
def test_worker_output_is_closed_and_bounded(monkeypatch, output):
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=output))
    with pytest.raises(ValueError, match='^qualified shadow radiation evidence unavailable$'):
        runtime.configured_shadow_radiation(AT, environ=env())


def test_timeout_does_not_leak_private_diagnostics(monkeypatch):
    def failed(*args, **kwargs):
        raise runtime.subprocess.TimeoutExpired('private-dsn-secret', 30)
    monkeypatch.setattr(runtime.subprocess, 'run', failed)
    with pytest.raises(ValueError, match='^qualified shadow radiation evidence unavailable$') as failure:
        runtime.configured_shadow_radiation(AT, environ=env())
    assert failure.value.__suppress_context__


def test_current_radiation_never_reads_held_numeric_or_item_update(monkeypatch):
    import thermal_intel
    from thermal_model.schema import THERMAL_ITEMS
    monkeypatch.setattr(runtime, 'configured_shadow_radiation', lambda now: dict(
        history=(), current=dict(at=AT, value=100, validUntil=AT+timedelta(seconds=120),
                                 sourceEvidence=evidence())))
    def history(item, *args):
        assert item != THERMAL_ITEMS['radiation']
        return [(AT, 70)]
    def state(item):
        assert item != THERMAL_ITEMS['radiation']
        return dict(name=item, state='70', lastStateUpdate=AT.timestamp()*1000)
    result = thermal_intel._current_states(AT, series_reader=history, state_reader=state)
    assert result['radiation']['sourceEvidence'] == evidence()


def test_radiation_expiry_during_compute_prevents_publication(monkeypatch, tmp_path):
    import thermal_intel
    from test_thermal_pipeline import current_states, NOW
    current = current_states()
    current['radiation']['validUntil'] = NOW+timedelta(seconds=1)
    ticks = iter([0, 2])
    monkeypatch.setattr(thermal_intel.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(thermal_intel.forecast_intel, 'load_site_settings', lambda: None)
    monkeypatch.setattr(thermal_intel, '_current_states', lambda now: current)
    monkeypatch.setattr(thermal_intel.forecast_intel, 'fetch_forecast', lambda: {})
    monkeypatch.setattr(thermal_intel, '_forecast_rows', lambda *args: [{'mode': 'warm'}])
    monkeypatch.setattr(thermal_intel, 'run_shadow', lambda **kwargs: {'confidence': {'grade': 'high'}})
    monkeypatch.setattr(thermal_intel, 'ArtifactRegistry', lambda *args: None)
    published = []
    status = thermal_intel._shadow(SimpleNamespace(output=tmp_path/'shadow.json', publish=True),
        NOW, put_state=lambda *args: published.append(args))
    assert status == 1 and published == []
    assert 'expired current radiation' in (tmp_path/'shadow.json').read_text()


def test_private_jdbc_loader_uses_only_approved_local_role(tmp_path):
    path = tmp_path/'reader.jdbc'
    path.write_text('url="jdbc:postgresql://127.0.0.1:5432/openhab"\n'
                    'user="energy_power_reader"\npassword="test-only"\n')
    path.chmod(0o600)
    assert runtime.read_db_config(str(path)) == dict(host='127.0.0.1', port=5432,
        dbname='openhab', user='energy_power_reader', password='test-only')
    path.chmod(0o644)
    with pytest.raises(ValueError): runtime.read_db_config(str(path))
    path.chmod(0o600)
    link = tmp_path/'link.jdbc'; link.symlink_to(path)
    with pytest.raises((ValueError, OSError)): runtime.read_db_config(str(link))


@pytest.mark.parametrize('change', ['role', 'remote', 'duplicate', 'extra', 'oversize'])
def test_private_jdbc_loader_refuses_ambiguous_or_broader_configuration(tmp_path, change):
    text = 'url=jdbc:postgresql://127.0.0.1:5432/openhab\nuser=energy_power_reader\npassword=test-only\n'
    if change == 'role': text = text.replace('energy_power_reader', 'postgres')
    elif change == 'remote': text = text.replace('127.0.0.1', 'example.org')
    elif change == 'duplicate': text += 'user=energy_power_reader\n'
    elif change == 'extra': text += 'sslmode=disable\n'
    elif change == 'oversize': text += '#'+('x'*4096)
    path = tmp_path/'reader.jdbc'; path.write_text(text); path.chmod(0o600)
    with pytest.raises(ValueError): runtime.read_db_config(str(path))


def test_collect_reads_one_grid_with_exact_policy_and_original_cutover(monkeypatch):
    import psycopg2
    import weather_radiation_config
    import weather_radiation_history
    from weather_radiation_evidence import RadiationPolicy
    calls = []
    monkeypatch.setattr(weather_radiation_config, 'load_radiation_policy', lambda path: POLICY)
    monkeypatch.setattr(runtime, 'read_db_config', lambda path: dict(user='energy_power_reader'))
    monkeypatch.setattr(psycopg2, 'connect', lambda **kwargs: calls.append(kwargs))
    def fetch(factory, **kwargs):
        factory(); calls.append(kwargs)
        return [(AT, evidence())]
    monkeypatch.setattr(weather_radiation_history, 'fetch_radiation_grid', fetch)
    request = dict(target=AT.isoformat(), assessed_at=AT.isoformat(),
                   cutover=env()['THERMAL_RADIATION_EVIDENCE_CUTOVER'])
    assert runtime.collect(request, config_path='/private/db', policy_path='/private/policy') == [(AT, evidence())]
    assert calls[0]['connect_timeout'] == 3 and calls[0]['hostaddr'] == '127.0.0.1'
    assert calls[0]['options'] == '-c default_transaction_read_only=on'
    assert calls[1]['targets'] == [AT] and calls[1]['policy'] == POLICY
    monkeypatch.setattr(weather_radiation_config, 'load_radiation_policy',
                        lambda path: RadiationPolicy(sensor_id=207))
    with pytest.raises(ValueError): runtime.collect(request, config_path='/private/db', policy_path='/private/policy')


@pytest.mark.parametrize('damage', ['extra', 'future', 'naive', 'precutover', 'future_assessment'])
def test_collect_refuses_bad_request_before_database_configuration(monkeypatch, damage):
    request = dict(target=AT.isoformat(), assessed_at=AT.isoformat(),
                   cutover=env()['THERMAL_RADIATION_EVIDENCE_CUTOVER'])
    if damage == 'extra': request['history'] = True
    elif damage == 'future': request['target'] = (AT+timedelta(seconds=1)).isoformat()
    elif damage == 'naive': request['target'] = AT.replace(tzinfo=None).isoformat()
    elif damage == 'precutover': request['cutover'] = (AT+timedelta(seconds=1)).isoformat()
    elif damage == 'future_assessment': request['assessed_at'] = (AT+timedelta(days=2)).isoformat()
    monkeypatch.setattr(runtime, 'read_db_config', lambda path: pytest.fail('DB config accessed'))
    with pytest.raises(ValueError): runtime.collect(request, config_path='/private/db', policy_path='/private/policy')


def test_decoder_clock_skew_within_original_policy_is_not_reclassified():
    value = evidence(radioDecodedAt=AT+timedelta(seconds=5))
    verified = runtime._validate_receipt(value, target=AT+timedelta(seconds=5),
        cutover=AT-timedelta(hours=1))
    assert verified['radioDecodedAt'] == AT+timedelta(seconds=5)
    assert verified['receivedAt'] == AT and verified['validUntil'] == AT+timedelta(seconds=120)


@pytest.mark.parametrize('key', ['PGSERVICE', 'PGSERVICEFILE'])
def test_implicit_database_service_is_rejected_before_connection(monkeypatch, key):
    import weather_radiation_config
    monkeypatch.setenv(key, 'test-service')
    monkeypatch.setattr(weather_radiation_config, 'load_radiation_policy', lambda path: POLICY)
    monkeypatch.setattr(runtime, 'read_db_config', lambda path: pytest.fail('DB configuration accessed'))
    with pytest.raises(ValueError, match='implicit database services refused'):
        runtime.collect(dict(target=AT, assessed_at=AT, cutover=AT-timedelta(hours=1)),
                        config_path='/private/db', policy_path='/private/policy')


def test_original_radiation_receipt_survives_immutable_capture_reopening(tmp_path):
    from thermal_model.forcing_capture import capture_shadow_inputs, verify_capture
    from test_thermal_forcing_capture import inputs
    tmp_path.chmod(0o700)
    data = inputs()
    data['output']['generatedAt'] = AT.isoformat()
    data['current']['radiation'] = dict(at=AT, value=100,
        validUntil=AT+timedelta(seconds=120), sourceEvidence=evidence())
    path = capture_shadow_inputs(tmp_path, **data, inputs_available_at=AT,
                                 published_at=AT+timedelta(seconds=2))
    original = json.loads(encoded(data['current']['radiation']))
    assert verify_capture(path)['current']['radiation'] == original


@pytest.mark.parametrize('args,payload', [([], '{}'), (['--read'], '{'),
    (['--read'], 'x'*32769), (['--read'], '{"target":1,"target":2}')])
def test_actual_worker_cli_refuses_invalid_invocations_without_private_output(args, payload):
    result = runtime.subprocess.run([runtime.sys.executable,
        str(Path(runtime.__file__).resolve()), *args], input=payload,
        text=True, capture_output=True, timeout=5)
    assert result.returncode == 1 and result.stdout == result.stderr == ''


def test_unavailable_qualified_radiation_cannot_enter_any_legacy_read(monkeypatch):
    import thermal_intel
    def unavailable(now):
        raise ValueError('qualified shadow radiation evidence unavailable')
    monkeypatch.setattr(runtime, 'configured_shadow_radiation', unavailable)
    with pytest.raises(ValueError, match='qualified shadow radiation evidence unavailable'):
        thermal_intel._current_states(AT, series_reader=lambda *args: pytest.fail('legacy history read'),
                                      state_reader=lambda *args: pytest.fail('legacy state read'))


@pytest.mark.parametrize('elapsed,expected',[(70,0),(130,1)])
def test_input_fetch_latency_is_not_counted_twice_in_receipt_expiry(monkeypatch,tmp_path,elapsed,expected):
    import thermal_intel
    from test_thermal_pipeline import current_states,NOW
    current=current_states()
    for role in ('air','mass','outdoor','radiation'):
        current[role]['at']=NOW
        current[role]['validUntil']=NOW+timedelta(seconds=120)
    ticks=iter([0,elapsed])
    monkeypatch.setattr(thermal_intel.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(thermal_intel.forecast_intel,'load_site_settings',lambda:None)
    monkeypatch.setattr(thermal_intel,'_current_states',lambda now:current)
    monkeypatch.setattr(thermal_intel.forecast_intel,'fetch_forecast',lambda:{})
    monkeypatch.setattr(thermal_intel,'_forecast_rows',lambda *args:[{'mode':'warm'}])
    monkeypatch.setattr(thermal_intel,'run_shadow',lambda **kwargs:{'confidence':{'grade':'high'}})
    monkeypatch.setattr(thermal_intel,'ArtifactRegistry',lambda *args:None)
    monkeypatch.setattr(thermal_intel,'write_shadow_output',lambda *args:None)
    monkeypatch.delenv('THERMAL_SHADOW_CAPTURE_DIR',raising=False)
    published=[]
    monkeypatch.setattr(thermal_intel,'publish_shadow_output',lambda *args,**kwargs:published.append(args))
    result=thermal_intel._shadow(SimpleNamespace(output=tmp_path/'shadow.json',publish=True),NOW,
        decision_clock=lambda:NOW+timedelta(seconds=60))
    # Total elapsed is 70 seconds, not 60+70. Source expiry remains 120s.
    assert result==expected and len(published)==(0 if expected else 1)
