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
    assert '--outdoor-offset-f' in help_result.stdout
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


@pytest.mark.parametrize('offset', [True, '1', -20.01, 20.01, float('nan'), float('inf')])
def test_outdoor_offset_refuses_before_loading_capture(offset, monkeypatch):
    monkeypatch.setattr(replay, 'verify_capture', lambda _: pytest.fail('invalid offset must refuse first'))
    with pytest.raises(ValueError, match='outdoor offset'):
        replay.replay('capture', outdoor_offset_f=offset)


def test_outdoor_copy_changes_only_forecast_temperature():
    capture = {'forecast_rows': [{'radiationWm2': 300., 'tempF': 75., 'at': 'target',
                                 '_modeTimeline': [['origin', 'warm']]}],
               'current': {'outdoor': {'value': 80}}, 'sha256': {'inputs': 'original'}}
    before = deepcopy(capture)
    shifted = replay._outdoor_shifted_capture(capture, -10.)
    assert capture == before
    assert shifted['forecast_rows'][0]['tempF'] == 65.
    assert shifted['forecast_rows'][0]['radiationWm2'] == 300.
    assert shifted['current'] == before['current'] and shifted['sha256'] == before['sha256']
    shifted['forecast_rows'][0]['_modeTimeline'][0][1] = 'winter'
    assert capture == before


@pytest.mark.parametrize('value, offset', [
    (True, 0), (float('nan'), 0), (float('inf'), 0),
    (-41, 10), (141, -10), (-35, -10), (135, 10),
])
def test_outdoor_shift_refuses_invalid_original_or_shifted_temperature(value, offset):
    with pytest.raises(ValueError, match='physical range'):
        replay._outdoor_shifted_capture({'forecast_rows': [{'tempF': value}]}, offset)


def test_outdoor_sensitivity_requires_exact_replay_and_preserves_capture(monkeypatch):
    issued = {'generatedAt': '2026-09-28T00:00:00.123000+00:00', 'status': 'shadow',
              'confidence': {'grade': 'low'},
              'schedule': {'baseline': {'vent': 'closed'}, 'candidate': None,
                           'effect': {'hallwayPeakDeltaF': 0}},
              'forecast': {'trajectory': [{'at': '2026-09-28T06:00:00+00:00', 'hallwayF': 70.}]}}
    capture = {'schema': 'earthship-thermal-shadow-forcing-capture/v2',
               'artifact': {}, 'decision_at': issued['generatedAt'], 'output': issued,
               'forecast_rows': [{'tempF': 75., 'radiationWm2': 500}],
               'sha256': {'output': 'c' * 64}}
    before = deepcopy(capture)
    monkeypatch.setattr(replay, 'verify_capture', lambda _: capture)
    monkeypatch.setattr(replay, '_artifact_from_payload', lambda _: SimpleNamespace(code_revision='a' * 64))
    monkeypatch.setattr(replay, '_runtime_manifest_revision', lambda _: 'a' * 64)
    calls = []
    def run(inputs, artifact):
        calls.append(inputs['forecast_rows'][0]['tempF'])
        output = deepcopy(issued)
        output['generatedAt'] = '2026-09-28T00:00:00+00:00'
        if len(calls) > 1:
            output['forecast']['trajectory'][0]['hallwayF'] = 68.
            # Modeled effect changes do not mean selected schedule times changed.
            output['schedule']['effect']['hallwayPeakDeltaF'] = -1.
        return output
    monkeypatch.setattr(replay, '_run', run)
    result = replay.replay('capture', outdoor_offset_f=-10.)
    assert calls == [75., 65.] and capture == before
    scenario = result['outdoor_temperature_sensitivity']
    assert scenario['offset_f'] == -10.
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
        replay.replay('capture', outdoor_offset_f=-10.)
    assert calls == ['broken']


def test_schedule_change_ignores_effect_but_detects_selected_timing():
    issued = {'baseline': {'ventOpenAt': 'evening'}, 'candidate': None,
              'effect': {'hallwayPeakDeltaF': 0}}
    hypothetical = deepcopy(issued)
    hypothetical['effect']['hallwayPeakDeltaF'] = -1
    assert replay._schedule_changed(issued, hypothetical) is False
    hypothetical['baseline']['ventOpenAt'] = 'later'
    assert replay._schedule_changed(issued, hypothetical) is True


@pytest.mark.parametrize('offset', [-20., 0., 20.])
def test_solar_and_outdoor_scenarios_are_independent(monkeypatch, offset):
    issued = {'generatedAt': '2026-09-28T00:00:00.123000+00:00', 'status': 'shadow',
              'confidence': {'grade': 'low'}, 'schedule': {'candidate': None},
              'forecast': {'trajectory': [{'at': '2026-09-28T06:00:00+00:00', 'hallwayF': 70.}]}}
    capture = {'schema': 'earthship-thermal-shadow-forcing-capture/v2',
               'artifact': {}, 'decision_at': issued['generatedAt'], 'output': issued,
               'forecast_rows': [{'tempF': 75., 'radiationWm2': 500}],
               'sha256': {'output': 'c' * 64}}
    before = deepcopy(capture)
    monkeypatch.setattr(replay, 'verify_capture', lambda _: capture)
    monkeypatch.setattr(replay, '_artifact_from_payload', lambda _: SimpleNamespace(code_revision='a' * 64))
    monkeypatch.setattr(replay, '_runtime_manifest_revision', lambda _: 'a' * 64)
    calls = []
    def run(inputs, artifact):
        row = inputs['forecast_rows'][0]
        calls.append((row['tempF'], row['radiationWm2']))
        return {**deepcopy(issued), 'generatedAt': '2026-09-28T00:00:00+00:00'}
    monkeypatch.setattr(replay, '_run', run)
    result = replay.replay('capture', solar_scale=1.5, outdoor_offset_f=offset)
    assert calls == [(75., 500), (75., 750), (75. + offset, 500)]
    assert capture == before
    assert result['outdoor_temperature_sensitivity']['horizons'][0]['delta_f'] == 0


@pytest.mark.parametrize('unusable', [
    {'status': 'unavailable', 'confidence': {'grade': 'unavailable'}},
    {'status': 'shadow', 'confidence': {'grade': 'unavailable'}},
])
def test_outdoor_sensitivity_refuses_unusable_scenario(monkeypatch, unusable):
    issued = {'generatedAt': '2026-09-28T00:00:00.123000+00:00', 'status': 'shadow'}
    capture = {'schema': 'earthship-thermal-shadow-forcing-capture/v2',
               'artifact': {}, 'decision_at': issued['generatedAt'], 'output': issued,
               'forecast_rows': [{'tempF': 75.}], 'sha256': {'output': 'c' * 64}}
    monkeypatch.setattr(replay, 'verify_capture', lambda _: capture)
    monkeypatch.setattr(replay, '_artifact_from_payload', lambda _: SimpleNamespace(code_revision='a' * 64))
    monkeypatch.setattr(replay, '_runtime_manifest_revision', lambda _: 'a' * 64)
    def run(inputs, _):
        if inputs['forecast_rows'][0]['tempF'] != 75.:
            return unusable
        return {**issued, 'generatedAt': '2026-09-28T00:00:00+00:00'}
    monkeypatch.setattr(replay, '_run', run)
    with pytest.raises(ValueError, match='outdoor diagnostic'):
        replay.replay('capture', outdoor_offset_f=-10.)
