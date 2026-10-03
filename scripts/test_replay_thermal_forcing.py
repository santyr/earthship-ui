import importlib.util
from copy import deepcopy
from datetime import datetime, timedelta, timezone
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


def test_forcing_recorder_restores_runtime_and_retains_actual_selected_inputs(monkeypatch):
    original = replay.pipeline._simulate_schedule
    initial = {'air_f': 70., 'mass_f': 68.}
    forcing = [{'at': 'next', 'indoor_shade_closed': 0.}]
    predictions = [{'at': 'next', 'air_f': 71., 'mass_f': 68.1}]
    monkeypatch.setattr(replay.pipeline, '_schedule_forcings', lambda *_: forcing)
    monkeypatch.setattr(replay.pipeline, 'simulate', lambda *_: predictions)
    def run(**kwargs):
        assert replay.pipeline._simulate_schedule('model', [], {}, initial) == predictions
        return {'status': 'fixture'}
    monkeypatch.setattr(replay.pipeline, 'run_shadow', run)
    records = []
    capture = {'current': {}, 'forecast_rows': [], 'decision_at': '2026-09-28T00:00:00+00:00'}
    assert replay._run(capture, None, records) == {'status': 'fixture'}
    assert replay.pipeline._simulate_schedule is original
    assert records == [{'initial': initial, 'forcings': forcing, 'predictions': predictions}]
    forcing[0]['indoor_shade_closed'] = 1.
    assert records[0]['forcings'][0]['indoor_shade_closed'] == 0.


def test_forcing_recorder_restores_runtime_after_failed_simulation(monkeypatch):
    original = replay.pipeline._simulate_schedule
    monkeypatch.setattr(replay.pipeline, '_schedule_forcings', lambda *_: [])
    def fail(*args): raise ValueError('fixture failure')
    monkeypatch.setattr(replay.pipeline, 'simulate', fail)
    monkeypatch.setattr(replay.pipeline, 'run_shadow',
                        lambda **kwargs: replay.pipeline._simulate_schedule(None, [], {}, {}))
    capture = {'current': {}, 'forecast_rows': [], 'decision_at': '2026-09-28T00:00:00+00:00'}
    with pytest.raises(ValueError, match='fixture failure'):
        replay._run(capture, None, [])
    assert replay.pipeline._simulate_schedule is original


def test_invalid_forcing_observer_refuses_before_capture_read(monkeypatch):
    monkeypatch.setattr(replay, 'verify_capture', lambda *_: pytest.fail('capture read'))
    with pytest.raises(ValueError, match='observer'):
        replay.replay('capture', selected_forcing_observer='unsafe')


def observer_fixture(monkeypatch):
    origin = datetime(2026, 9, 28, 14, 20, 30, 123000, tzinfo=timezone.utc)
    at = origin.replace(second=0, microsecond=0) + timedelta(minutes=5)
    selected = {'initial': {'air_f': 70., 'mass_f': 68.},
                'forcings': [{'at': at, 'indoor_shade_closed': 0.}],
                'predictions': [{'air_f': 70.1254, 'mass_f': 68.0014}]}
    issued = {'generatedAt': origin.isoformat(), 'status': 'shadow',
              'forecast': {'trajectory': [
                  {'at': at.isoformat(), 'hallwayF': 70.125, 'massF': 68.001}]}}
    capture = {'schema': 'earthship-thermal-shadow-forcing-capture/v2',
               'artifact': {}, 'decision_at': origin.isoformat(), 'output': issued,
               'sha256': {'output': 'c' * 64}}
    monkeypatch.setattr(replay, 'verify_capture', lambda _: capture)
    monkeypatch.setattr(replay, '_artifact_from_payload',
                        lambda _: SimpleNamespace(code_revision='a' * 64))
    monkeypatch.setattr(replay, '_runtime_manifest_revision', lambda _: 'a' * 64)
    def run(inputs, artifact, records):
        records.append(selected)
        result = deepcopy(issued)
        result['generatedAt'] = origin.replace(microsecond=0).isoformat()
        return result
    monkeypatch.setattr(replay, '_run', run)
    return origin, selected, issued


def test_observer_exports_only_verified_selected_native_grid_and_isolated_copy(monkeypatch):
    origin, selected, issued = observer_fixture(monkeypatch)
    exported = []
    result = replay.replay('capture', selected_forcing_observer=exported.append)
    assert result['exact_as_issued'] is True
    assert 'forcings' not in result
    assert exported == [{'origin': origin, **selected}]
    exported[0]['forcings'][0]['indoor_shade_closed'] = 1.
    assert selected['forcings'][0]['indoor_shade_closed'] == 0.
    assert issued['forecast']['trajectory'][0]['hallwayF'] == 70.125


@pytest.mark.parametrize('damage', ['air', 'mass', 'timestamp', 'short_grid', 'empty_trajectory'])
def test_observer_refuses_unverified_selected_grid_before_export(monkeypatch, damage):
    _, selected, issued = observer_fixture(monkeypatch)
    if damage == 'air': selected['predictions'][0]['air_f'] += .01
    if damage == 'mass': selected['predictions'][0]['mass_f'] += .01
    if damage == 'timestamp': selected['forcings'][0]['at'] += timedelta(minutes=5)
    if damage == 'short_grid': selected['predictions'].clear()
    if damage == 'empty_trajectory': issued['forecast']['trajectory'].clear()
    with pytest.raises(ValueError):
        replay.replay('capture', selected_forcing_observer=lambda _: pytest.fail('unverified export'))


def test_observer_refuses_changed_runtime_before_export(monkeypatch):
    observer_fixture(monkeypatch)
    pins = iter(['a' * 64, 'b' * 64])
    monkeypatch.setattr(replay, '_runtime_manifest_revision', lambda _: next(pins))
    with pytest.raises(ValueError, match='runtime source changed'):
        replay.replay('capture', selected_forcing_observer=lambda _: pytest.fail('drifted export'))


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
