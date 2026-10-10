"""Qualification latency must precede collection, never extend receipt validity."""
from copy import deepcopy
from datetime import datetime, timedelta
import json

import pytest

from test_thermal_release_runtime import release_case
from test_thermal_origin_capture import capture_inputs
from thermal_model.forcing_capture import _canonical


def advanced(value, delta):
    if isinstance(value, dict): return {key: advanced(entry, delta) for key, entry in value.items()}
    if isinstance(value, list): return [advanced(entry, delta) for entry in value]
    if isinstance(value, str):
        try:
            stamp = datetime.fromisoformat(value)
            if stamp.utcoffset() is not None: return (stamp+delta).isoformat()
        except ValueError: pass
    return value


@pytest.mark.parametrize('delay,remaining,expected', [(timedelta(hours=1), timedelta(hours=23), 'forecast_active'), (timedelta(hours=25), timedelta(hours=23), 'unavailable'), (timedelta(hours=1), timedelta(minutes=30), 'unavailable')])
def test_slow_raw_qualification_precedes_fresh_inputs_without_refreshing_report(tmp_path, monkeypatch, delay, remaining, expected):
    thermal, args, data, now = release_case(tmp_path, monkeypatch)
    from thermal_model import graduation_decision
    from test_thermal_release import shift
    phase = [now]; events = []
    report = data['qualification_loader'](now)
    # Controlled source-deadline boundary, not scientific release evidence.
    report['qualification_expires_at'] = (now+remaining).isoformat()
    from hashlib import sha256
    report['report_sha256'] = sha256(_canonical({key: value for key, value in report.items() if key != 'report_sha256'})).hexdigest()
    def evaluate(at):
        assert at == now
        events.append('qualification')
        phase[0] = now+delay
        return deepcopy(report)
    monkeypatch.setattr(graduation_decision, 'load_qualification_inputs', lambda _: evaluate)
    original = capture_inputs()
    proof = advanced(shift(json.loads(_canonical(original['origin_temperatures']))), delay)
    current = advanced(shift(json.loads(_canonical(original['current']))), delay)
    def observed(at, *, origin_observer=None):
        assert events == ['qualification']
        assert at == phase[0]
        events.append('native')
        origin_observer(deepcopy(proof))
        return deepcopy(current)
    monkeypatch.setattr(thermal, '_current_states', observed)
    forcing = [{**row, 'at': row['at']+delay} for row in data['forecast_rows']]
    monkeypatch.setattr(thermal, '_forecast_rows', lambda *_: deepcopy(forcing))
    def predict(**kwargs):
        kwargs['artifact_observer'](original['artifact'])
        output = deepcopy(data['shadow'])
        output['generatedAt'] = phase[0].isoformat()
        output['forecast'] = advanced(output['forecast'], delay)
        output['schedule'] = advanced(output['schedule'], delay)
        return output
    monkeypatch.setattr(thermal, 'run_shadow', predict)
    sent = []
    assert thermal._release(args, now, put_state=lambda *values: sent.append(values),
        decision_clock=lambda: phase[0], qualification_clock=lambda: phase[0]) == int(expected == 'unavailable')
    output = json.loads(sent[0][1])
    assert output['status'] == expected
    if expected == 'forecast_active':
        assert output['generatedAt'] == phase[0].isoformat()
        assert output['release']['qualifiedAt'] == now.isoformat()
    else:
        assert datetime.fromisoformat(output['generatedAt']) >= phase[0]
    assert events == ['qualification', 'native']


def test_each_invocation_recomputes_original_evidence_before_inputs(tmp_path, monkeypatch):
    thermal, args, data, now = release_case(tmp_path, monkeypatch)
    from thermal_model import graduation_decision
    previous_current = thermal._current_states; events = []
    report = data['qualification_loader'](now)
    def evaluate(at):
        events.append('qualification')
        return deepcopy(report)
    def observed(*values, **kwargs):
        events.append('native')
        return previous_current(*values, **kwargs)
    monkeypatch.setattr(graduation_decision, 'load_qualification_inputs', lambda _: evaluate)
    monkeypatch.setattr(thermal, '_current_states', observed)
    args.publish = False
    for _ in range(2):
        assert thermal._release(args, now, decision_clock=lambda: now,
            qualification_clock=lambda: now) == 0
    assert events == ['qualification', 'native', 'qualification', 'native']


def test_failed_raw_assessment_withdraws_without_collecting_inputs(tmp_path, monkeypatch):
    thermal, args, _, now = release_case(tmp_path, monkeypatch)
    from thermal_model import graduation_decision
    def rejected(_): raise ValueError('raw evidence rejected')
    monkeypatch.setattr(graduation_decision, 'load_qualification_inputs', lambda _: rejected)
    def prohibited(*_args, **_kwargs): raise AssertionError('failed qualification must not collect inputs')
    monkeypatch.setattr(thermal, '_current_states', prohibited)
    sent = []
    assert thermal._release(args, now, put_state=lambda *values: sent.append(values),
        decision_clock=lambda: now, qualification_clock=lambda: now) == 1
    assert len(sent) == 1 and json.loads(sent[0][1])['status'] == 'unavailable'


@pytest.mark.parametrize('clock', ['backward', 'naive'])
def test_invalid_postqualification_clock_withdraws_before_input_fetch(tmp_path, monkeypatch, clock):
    thermal, args, _, now = release_case(tmp_path, monkeypatch)
    def prohibited(*_args, **_kwargs): raise AssertionError('invalid clock must not fetch current inputs')
    monkeypatch.setattr(thermal, '_current_states', prohibited)
    at = now-timedelta(seconds=1) if clock == 'backward' else now.replace(tzinfo=None)
    sent = []
    assert thermal._release(args, now, put_state=lambda *values: sent.append(values),
        decision_clock=lambda: at, qualification_clock=lambda: now) == 1
    assert len(sent) == 1 and json.loads(sent[0][1])['status'] == 'unavailable'
