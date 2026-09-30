import importlib.util
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).with_name('replay-thermal-forcing.py')
SPEC = importlib.util.spec_from_file_location('thermal_forcing_replay', SOURCE)
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def test_cli_requires_explicit_complete_runtime():
    runtime = SOURCE.resolve().parents[1] / 'openhab/scripts'
    help_result = subprocess.run([sys.executable, str(SOURCE), '--runtime-root',
                                  str(runtime), '--help'], capture_output=True, text=True)
    assert help_result.returncode == 0
    assert '--assume-vents-closed' in help_result.stdout
    assert '--solar-scale' in help_result.stdout
    missing = subprocess.run([sys.executable, str(SOURCE), '--runtime-root',
                              str(runtime / 'missing'), '--help'],
                             capture_output=True, text=True)
    assert missing.returncode != 0
    assert 'runtime root required' in missing.stderr


def test_closed_vent_schedule_changes_only_vent_assumptions():
    original = {'vent': 'open', 'ventFlow': 'baseline', 'ventForcing': 1.0,
                'ventOpenAt': 'later', 'airflowSegments': ('vent',),
                'indoorShadeInitial': 'closed'}
    changed = replay._closed_vent_schedule(None, [], lambda *_: original)
    assert original['vent'] == 'open'
    assert changed['vent'] == changed['ventFlow'] == 'closed'
    assert changed['ventForcing'] == 0.0
    assert changed['ventOpenAt'] is None
    assert changed['airflowSegments'] == ()
    assert changed['indoorShadeInitial'] == 'closed'


def test_horizon_deltas_keep_exact_target_and_sign():
    issued = {'forecast': {'trajectory': [
        {'at': '2026-09-28T01:00:00+00:00', 'hallwayF': 70.0},
        {'at': '2026-09-28T06:00:00+00:00', 'hallwayF': 66.0}]}}
    closed = {'forecast': {'trajectory': [
        {'at': '2026-09-28T01:00:00+00:00', 'hallwayF': 70.0},
        {'at': '2026-09-28T06:00:00+00:00', 'hallwayF': 67.25}]}}
    decision = replay.datetime.fromisoformat('2026-09-28T00:00:00+00:00')
    rows = replay._horizon_deltas(issued, closed, decision)
    assert [(row['hours'], row['delta_f']) for row in rows] == [(1, 0.0), (6, 1.25)]
    closed['forecast']['trajectory'][1]['at'] = '2026-09-28T06:05:00+00:00'
    with pytest.raises(ValueError, match='timestamps changed'):
        replay._horizon_deltas(issued, closed, decision)


def test_v1_and_source_mismatch_fail_before_simulation(monkeypatch):
    monkeypatch.setattr(replay, 'verify_capture', lambda _: {'schema': 'earthship-thermal-shadow-forcing-capture/v1'})
    with pytest.raises(ValueError, match='requires a v2'):
        replay.replay('capture')
    monkeypatch.setattr(replay, 'verify_capture', lambda _: {
        'schema': 'earthship-thermal-shadow-forcing-capture/v2', 'artifact': {}})
    monkeypatch.setattr(replay, '_artifact_from_payload', lambda _: SimpleNamespace(code_revision='a' * 64))
    monkeypatch.setattr(replay, '_runtime_manifest_revision', lambda _: 'b' * 64)
    monkeypatch.setattr(replay, '_run', lambda *_: pytest.fail('simulation must not run'))
    with pytest.raises(ValueError, match='does not match selected runtime'):
        replay.replay('capture')


def test_counterfactual_requires_exact_as_issued_replay(monkeypatch):
    issued = {'generatedAt': '2026-09-28T14:20:30.123000+00:00', 'status': 'shadow'}
    capture = {'schema': 'earthship-thermal-shadow-forcing-capture/v2',
               'artifact': {}, 'decision_at': issued['generatedAt'], 'output': issued,
               'sha256': {'output': 'c' * 64}}
    monkeypatch.setattr(replay, 'verify_capture', lambda _: capture)
    monkeypatch.setattr(replay, '_artifact_from_payload', lambda _: SimpleNamespace(code_revision='a' * 64))
    monkeypatch.setattr(replay, '_runtime_manifest_revision', lambda _: 'a' * 64)
    monkeypatch.setattr(replay, '_run', lambda *_: {
        'generatedAt': '2026-09-28T14:20:30+00:00', 'status': 'unavailable'})
    with pytest.raises(ValueError, match='failed exact replay'):
        replay.replay('capture', assume_vents_closed=True)


@pytest.mark.parametrize('revision', ['', 'a' * 12, 'A' * 64, True])
def test_explicit_runtime_pin_requires_full_lowercase_digest(revision):
    with pytest.raises(ValueError, match='runtime SHA-256'):
        replay.replay('capture', expected_runtime_revision=revision)


def test_explicit_runtime_pin_preserves_exact_output_requirement(monkeypatch):
    issued = {'generatedAt': '2026-09-28T14:20:30.123000+00:00', 'status': 'shadow'}
    capture = {'schema': 'earthship-thermal-shadow-forcing-capture/v2',
               'artifact': {}, 'decision_at': issued['generatedAt'], 'output': issued,
               'sha256': {'output': 'c' * 64}}
    monkeypatch.setattr(replay, 'verify_capture', lambda _: capture)
    monkeypatch.setattr(replay, '_artifact_from_payload', lambda _: SimpleNamespace(code_revision='a' * 64))
    monkeypatch.setattr(replay, '_runtime_manifest_revision', lambda _: 'b' * 64)
    monkeypatch.setattr(replay, '_run', lambda *_: pytest.fail('wrong pin must not simulate'))
    with pytest.raises(ValueError, match='explicit revision pin'):
        replay.replay('capture', expected_runtime_revision='d' * 64)
    monkeypatch.setattr(replay, '_run', lambda *_: {
        'generatedAt': '2026-09-28T14:20:30+00:00', 'status': 'unavailable'})
    with pytest.raises(ValueError, match='failed exact replay'):
        replay.replay('capture', expected_runtime_revision='b' * 64)
    monkeypatch.setattr(replay, '_run', lambda *_: {
        'generatedAt': '2026-09-28T14:20:30+00:00', 'status': 'shadow'})
    result = replay.replay('capture', expected_runtime_revision='b' * 64)
    assert result['exact_as_issued'] is True
    assert result['runtime_binding'] == 'explicit_sha256'
    assert result['training_revision_matches_runtime'] is False
    assert result['artifact_code_revision'] == 'a' * 64
    assert result['runtime_manifest_revision'] == 'b' * 64


@pytest.mark.parametrize('scale', [True, '1', -0.1, 2.01, float('nan'), float('inf')])
def test_solar_scale_refuses_before_loading_capture(scale, monkeypatch):
    monkeypatch.setattr(replay, 'verify_capture', lambda _: pytest.fail('invalid scale must refuse first'))
    with pytest.raises(ValueError, match='solar scale'):
        replay.replay('capture', solar_scale=scale)


def test_solar_copy_changes_only_radiation_and_preserves_captured_facts():
    capture = {'forecast_rows': [{'radiationWm2': 300., 'tempF': 75., 'at': 'target',
                                 '_modeTimeline': [['origin', 'warm']]}],
               'current': {'radiation': {'value': 200}}, 'sha256': {'inputs': 'original'}}
    before = deepcopy(capture)
    scaled = replay._solar_scaled_capture(capture, 1.5)
    assert capture == before
    assert scaled['forecast_rows'][0]['radiationWm2'] == 450
    assert scaled['current'] == before['current'] and scaled['sha256'] == before['sha256']
    scaled['forecast_rows'][0]['_modeTimeline'][0][1] = 'winter'
    assert capture == before
    with pytest.raises(ValueError, match='physical range'):
        replay._solar_scaled_capture({'forecast_rows': [{'radiationWm2': 1500}]}, 1.5)


def test_solar_sensitivity_requires_exact_replay_and_preserves_capture(monkeypatch):
    issued = {'generatedAt': '2026-09-28T00:00:00.123000+00:00', 'status': 'shadow',
              'confidence': {'grade': 'low'}, 'schedule': {'candidate': None},
              'forecast': {'trajectory': [{'at': '2026-09-28T06:00:00+00:00', 'hallwayF': 70.}]}}
    capture = {'schema': 'earthship-thermal-shadow-forcing-capture/v2',
               'artifact': {}, 'decision_at': issued['generatedAt'], 'output': issued,
               'forecast_rows': [{'radiationWm2': 500}], 'sha256': {'output': 'c' * 64}}
    before = deepcopy(capture)
    monkeypatch.setattr(replay, 'verify_capture', lambda _: capture)
    monkeypatch.setattr(replay, '_artifact_from_payload', lambda _: SimpleNamespace(code_revision='a' * 64))
    monkeypatch.setattr(replay, '_runtime_manifest_revision', lambda _: 'a' * 64)
    calls = []
    def run(inputs, artifact):
        calls.append(inputs['forecast_rows'][0]['radiationWm2'])
        output = deepcopy(issued)
        output['generatedAt'] = '2026-09-28T00:00:00+00:00'
        if len(calls) > 1:
            output['forecast']['trajectory'][0]['hallwayF'] = 68.
        return output
    monkeypatch.setattr(replay, '_run', run)
    result = replay.replay('capture', solar_scale=0)
    assert calls == [500, 0] and capture == before
    scenario = result['solar_sensitivity']
    assert scenario['schedule_changed'] is False
    assert scenario['horizons'][0]['delta_f'] == -2
    assert scenario['horizons'][0]['hypothetical_f'] == 68
    assert result['counterfactual_is_action_evidence'] is False
    calls.clear()
    def broken(*_):
        calls.append('broken')
        return {**issued, 'generatedAt': '2026-09-28T00:00:00+00:00', 'status': 'unavailable'}
    monkeypatch.setattr(replay, '_run', broken)
    with pytest.raises(ValueError, match='failed exact replay'):
        replay.replay('capture', solar_scale=0)
    assert calls == ['broken']
