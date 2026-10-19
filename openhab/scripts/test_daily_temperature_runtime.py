from zoneinfo import ZoneInfo
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest
import daily_temperature_runtime as runtime

START = datetime(2026, 9, 20, 6, tzinfo=timezone.utc)
END = START + timedelta(days=1)
ASSESSED = END + timedelta(hours=7)
REQUEST = dict(start=START.isoformat(), end=END.isoformat(), assessed_at=ASSESSED.isoformat())
ENV = dict(DAILY_TEMP_QUALIFIED_ENABLE='1', DAILY_TEMP_COVERAGE_POLICY=runtime.COVERAGE_POLICY,
           DAILY_TEMP_EVIDENCE_CUTOVER=START.isoformat())


def payload():
    return dict(version=1, request=dict(REQUEST), stream='outdoor',
                source_policy=dict(runtime.SOURCE_POLICY), coverage_policy=runtime.COVERAGE_POLICY,
                summary=dict(observed_high_f=80, observed_low_f=40, covered_seconds=86400,
                             total_seconds=86400, maximum_gap_seconds=0, gap_count=0,
                             fully_covered=True,
                             history_sha256='a' * 64))


def child(monkeypatch, result=None, error=None):
    calls = []
    def run(*args, **kwargs):
        calls.append((args, kwargs))
        if error: raise error
        return SimpleNamespace(stdout=json.dumps(payload() if result is None else result))
    monkeypatch.setattr(runtime.subprocess, 'run', run)
    return calls


def test_complete_window_is_bounded_and_keeps_evidence(monkeypatch):
    calls = child(monkeypatch)
    high, low, evidence = runtime.read_daily_actuals(START, END, ASSESSED, ENV)
    assert (high, low) == (80, 40)
    assert evidence['cutover'] == START.isoformat()
    assert evidence['summary']['history_sha256'] == 'a' * 64
    args, kwargs = calls[0]
    assert args[0][-1] == '--read'
    assert kwargs['timeout'] == 30 and kwargs['check']
    assert kwargs['stderr'] == runtime.subprocess.DEVNULL
    assert json.loads(kwargs['input']) == REQUEST


@pytest.mark.parametrize('update', [
    {'DAILY_TEMP_QUALIFIED_ENABLE': '0'}, {'DAILY_TEMP_QUALIFIED_ENABLE': 'bad'},
    {'DAILY_TEMP_COVERAGE_POLICY': 'ninety_percent'},
    {'DAILY_TEMP_EVIDENCE_CUTOVER': (START + timedelta(seconds=1)).isoformat()},
    {'DAILY_TEMP_EVIDENCE_CUTOVER': 'bad'},
])
def test_invalid_activation_never_reads_or_falls_back(monkeypatch, update):
    calls = child(monkeypatch)
    assert runtime.read_daily_actuals(START, END, ASSESSED, ENV | update) == (None, None, None)
    assert calls == []


def test_partial_coverage_is_not_a_daily_training_actual(monkeypatch):
    result = payload()
    result['summary'].update(covered_seconds=86399, maximum_gap_seconds=1,
                             gap_count=1, fully_covered=False)
    child(monkeypatch, result)
    assert runtime.read_daily_actuals(START, END, ASSESSED, ENV) == (None, None, None)


@pytest.mark.parametrize('key,value', [
    ('covered_seconds', True), ('covered_seconds', float('nan')),
    ('total_seconds', 86401), ('maximum_gap_seconds', 1),
    ('gap_count', 1), ('gap_count', True), ('gap_count', -1), ('gap_count', 10002),
    ('fully_covered', 1), ('fully_covered', False),
    ('observed_high_f', 141), ('observed_low_f', 81),
    ('observed_low_f', None), ('history_sha256', 'invalid'),
])
def test_invalid_summary_refuses_both_actuals(monkeypatch, key, value):
    result = payload()
    result['summary'][key] = value
    child(monkeypatch, result)
    assert runtime.read_daily_actuals(START, END, ASSESSED, ENV) == (None, None, None)


def test_missing_gap_count_refuses_both_actuals(monkeypatch):
    result = payload()
    del result['summary']['gap_count']
    child(monkeypatch, result)
    assert runtime.read_daily_actuals(START, END, ASSESSED, ENV) == (None, None, None)


@pytest.mark.parametrize('key,value', [('version', True), ('stream', 'indoor'),
    ('coverage_policy', 'partial'), ('source_policy', {'sensor_id': 235}),
    ('request', REQUEST | {'end': START.isoformat()})])
def test_wrong_metadata_is_rejected(monkeypatch, key, value):
    result = payload()
    result[key] = value
    child(monkeypatch, result)
    assert runtime.read_daily_actuals(START, END, ASSESSED, ENV) == (None, None, None)


def test_worker_errors_are_sanitized(monkeypatch, capsys):
    child(monkeypatch, error=RuntimeError('PRIVATE_SENTINEL'))
    assert runtime.read_daily_actuals(START, END, ASSESSED, ENV) == (None, None, None)
    assert 'PRIVATE_SENTINEL' not in capsys.readouterr().err


@pytest.mark.parametrize('stdout', ['x' * 8193, '{"version":1,"version":1}', 'null', 'NaN'])
def test_invalid_worker_json_never_becomes_an_actual(monkeypatch, stdout):
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=stdout))
    assert runtime.read_daily_actuals(START, END, ASSESSED, ENV) == (None, None, None)


def test_partial_calendar_day_is_rejected_before_worker(monkeypatch):
    calls = child(monkeypatch)
    assert runtime.read_daily_actuals(START, START + timedelta(hours=12), ASSESSED, ENV) == (None, None, None)
    assert calls == []


@pytest.mark.parametrize('month,day,hours', [(3, 8, 23), (11, 1, 25)])
def test_complete_dst_calendar_day_is_accepted(month, day, hours):
    start = datetime(2026, month, day, tzinfo=runtime.SITE_ZONE)
    end = datetime(2026, month, day + 1, tzinfo=runtime.SITE_ZONE)
    request = dict(start=start.isoformat(), end=end.isoformat(), assessed_at=end.isoformat())
    result = payload()
    result['request'] = request
    result['summary'].update(total_seconds=hours * 3600, covered_seconds=hours * 3600)
    assert runtime.validate_result(result, request) is result


def test_collect_rejects_future_day_before_private_config(monkeypatch):
    import hourly_temperature_runtime
    monkeypatch.setattr(hourly_temperature_runtime, 'read_db_config', lambda path: pytest.fail('read private config'))
    start = datetime.now(runtime.SITE_ZONE).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2)
    end = start + timedelta(days=1)
    with pytest.raises(ValueError, match='future assessment'):
        runtime.collect(dict(start=start.isoformat(), end=end.isoformat(), assessed_at=end.isoformat()),
                        config_path='unused', policy_path='unused')






def test_origin_cutover_and_forecast_horizons_are_not_relabelled():
    evidence = payload() | {'cutover': (START - timedelta(days=4)).isoformat()}
    origin = dict(temperature_origin_version=1, temperature_issued_at=(START + timedelta(hours=6)).isoformat())
    assert runtime.origin_eligible(origin, START.date(), evidence, ZoneInfo('America/Denver'), 0)
    assert not runtime.origin_eligible(origin, START.date(), evidence, ZoneInfo('America/Denver'), 3)
    assert not runtime.origin_eligible({}, START.date(), evidence, ZoneInfo('America/Denver'), 0)
    assert not runtime.origin_eligible(origin | {'temperature_origin_version': True}, START.date(), evidence, ZoneInfo('America/Denver'), 0)
    evidence['cutover'] = (START + timedelta(hours=7)).isoformat()
    assert not runtime.origin_eligible(origin, START.date(), evidence, ZoneInfo('America/Denver'), 0)








def test_provenance_bound_keeps_recent_records():
    state = {}
    prediction = dict(hi=80, temperature_issued_at=START.isoformat())
    for n in range(100): runtime.record_score(state, str(n), 'hi', prediction, 78, payload())
    assert len(state['daily_temperature_evidence']) == 96
    assert state['daily_temperature_evidence'][0]['day'] == '4'




@pytest.mark.parametrize('value', [True, '80', float('nan'), float('inf'), None])
def test_qualified_learning_rejects_bad_forecast_values(value):
    assert not runtime.forecast_value_eligible({'hi': value}, 'hi', payload())
