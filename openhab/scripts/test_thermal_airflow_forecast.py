"""Offline origin/replay contracts; no household collection or control claim."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json
import math

import pytest

import thermal_model.airflow_artifact as a
from thermal_model.airflow_forecast import forecast_at_origin, replay_capture, _from_inputs
from thermal_model.airflow_training import fit_airflow_dynamics
from thermal_model.dataset import STEP
from thermal_model.forecast_history import _window
from thermal_model.schema import ACTION_KINDS_V2
from thermal_model.solar import clear_sky_expected_wm2, CLEAR_SKY_MAX_FRACTION
from test_thermal_airflow import make_synthetic_samples

EPOCH = '864142d5-99ee-4b7a-b5fc-e6a96e7274d8'


@pytest.fixture(scope='module')
def candidate():
    rows = make_synthetic_samples()
    fit = fit_airflow_dynamics(rows)
    created = rows[-1].at + STEP
    return a.build_artifact(fit, rows, [], [], created_at=created)


@pytest.fixture
def origin(candidate):
    return a.utc(candidate['created_at']) + timedelta(minutes=40)


def receipt(at, temperature):
    return {'temperatureF': temperature, 'receivedAt': at-timedelta(seconds=40),
        'storedAt': at-timedelta(seconds=30), 'validUntil': at+timedelta(seconds=80),
        'streamEpoch': EPOCH, 'snapshotSha256': 'b'*64}


def weather(*, origin, horizon_hours):
    _, times = _window(origin, horizon_hours)
    return {'source': 'open_meteo_openhab', 'origin': origin, 'horizon_hours': horizon_hours,
        'issued_at': origin-timedelta(hours=1), 'captured_at': origin-timedelta(minutes=20),
        # The archive digest includes per-metric capture times not exposed in rows.
        'rows_sha256': 'a'*64, 'rows': [{'at': at, 'tempF': 59., 'radiationWm2': 0.,
            'windMph': 2., 'weatherCode': 0} for at in times]}


def actions(*, origin):
    states = {'window': 'open', 'skylight': 'closed', 'indoor_shade': 'open',
              'outdoor_shade': 'absent', 'kiva': 'off'}
    return {'source': 'thermal_intel_append_only_journal', 'origin': origin,
        'vocabulary_version': 2, 'actions': {name: {'state': state,
            'source': 'nostr_confirmed', 'confidence': 1., 'event_id': name,
            'effective_at': origin-timedelta(hours=4), 'received_at': origin-timedelta(hours=3),
            'created_at': origin-timedelta(hours=2)} for name, state in states.items()},
        'mode': None, 'missing_actions': sorted(set(ACTION_KINDS_V2)-set(states)),
        'status': 'as_of_snapshot_not_outcome_confirmation'}


def temperatures(*, stream, targets, assessed_at):
    assert all(at <= assessed_at for at in targets)
    # A recently cooled wall differs from its causally observed latent mass.
    return [(at, receipt(at, 62. if assessed_at-at < timedelta(hours=1) else 70.))
            if stream == 'north_wall' else
            (at, receipt(at, {'indoor': 70., 'outdoor': 59.}[stream])) for at in targets]


def run(candidate, origin, **readers):
    return forecast_at_origin(candidate, origin, horizon_hours=6,
        forecast_reader=readers.get('forecast_reader', weather),
        temperature_reader=readers.get('temperature_reader', temperatures),
        action_reader=readers.get('action_reader', actions))


def rehash(capture):
    capture['sha256'] = sha256(a.canonical({k: v for k, v in capture.items() if k != 'sha256'})).hexdigest()
    return capture


def test_candidate_and_forecast_roundtrip_are_exact_non_actuating(candidate, origin):
    assert a.validate_artifact(json.loads(a.canonical(candidate))) == json.loads(a.canonical(candidate))
    result = run(candidate, origin)
    assert result['status'] == 'available'
    output = result['output']
    assert output['control_enabled'] is False
    assert output['status'] == 'shadow_candidate'
    assert output['action_assumption'] == 'qualified_origin_states_held_not_future_confirmation'
    assert output['states']['window_open'] == 1. and output['states']['skylight_open'] == 0.
    assert output['initial']['mass_f'] > output['initial']['north_wall_f'] == 62.
    assert len(output['trajectory']) == 72
    assert output['trajectory'][0]['at'] == (origin+STEP).isoformat()
    assert output['trajectory'][-1]['at'] == (origin+timedelta(hours=6)).isoformat()
    assert replay_capture(json.loads(a.canonical(result['capture']))) == output
    assert run(candidate, origin)['output'] == output


def test_window_and_skylight_predictions_remain_distinct(candidate, origin):
    baseline = run(candidate, origin)['output']['trajectory'][0]['air_f']
    def skylight_only(**kwargs):
        value = actions(**kwargs)
        value['actions']['window']['state'] = 'closed'
        value['actions']['skylight']['state'] = 'open'
        return value
    other = run(candidate, origin, action_reader=skylight_only)['output']['trajectory'][0]['air_f']
    assert baseline != pytest.approx(other)


def test_observer_and_interpolated_first_step_match_independent_equations(candidate, origin):
    origin += timedelta(hours=18)  # Daylight, with a nonzero normalized solar term.
    def changing(**kwargs):
        value = weather(**kwargs)
        for i, row in enumerate(value['rows']):
            row.update(tempF=55.+i*2, radiationWm2=100.+i*20)
        return value
    result = run(candidate, origin, forecast_reader=changing)
    latent = 70.
    alpha = 1-math.exp(-5/120)
    targets = [origin-timedelta(hours=24)+i*STEP for i in range(289)]
    for at in targets[1:]:
        wall = 62. if origin-at < timedelta(hours=1) else 70.
        latent += alpha*(wall-latent)
    assert result['output']['initial']['mass_f'] == pytest.approx(latent, abs=1e-12)
    first_hour = origin.replace(minute=0)
    fraction = (origin+STEP-first_hour).total_seconds()/3600
    outdoor, radiation = 55.+fraction*2, 100.+fraction*20
    expected_radiation = clear_sky_expected_wm2(origin+STEP)
    assert expected_radiation > 0
    solar_term = 1000*min(radiation/expected_radiation, CLEAR_SKY_MAX_FRACTION)
    air = 70.
    c, m = candidate['fit']['dynamics']['air_coefficients'], candidate['fit']['dynamics']['mass_coefficients']
    expected_air = air+(c['outside_exchange']+c['window_exchange'])*(outdoor-air) \
        +c['mass_exchange']*(latent-air)+c['solar_unshaded']*solar_term+c['bias']
    expected_mass = latent+m['air_exchange']*(air-latent)+m['outside_exchange']*(outdoor-latent) \
        +m['solar_unshaded']*solar_term
    first = result['output']['trajectory'][0]
    assert first['air_f'] == pytest.approx(expected_air, abs=1e-12)
    assert first['mass_f'] == pytest.approx(expected_mass, abs=1e-12)


@pytest.mark.parametrize('hours', [1, 24, 72])
def test_all_supported_forecast_lengths_replay_within_capture_bound(candidate, origin, hours):
    # Also exercise exact-hour origins, which need one fewer weather bracket.
    origin = origin.replace(minute=0)+timedelta(hours=1)
    result = forecast_at_origin(candidate, origin, horizon_hours=hours,
        forecast_reader=weather, temperature_reader=temperatures, action_reader=actions)
    assert len(result['output']['trajectory']) == hours*12
    assert len(a.canonical(result['capture'])) < 1_000_000
    assert replay_capture(json.loads(a.canonical(result['capture']))) == result['output']


@pytest.mark.parametrize('field', ['window', 'skylight', 'kiva', 'indoor_shade', 'outdoor_shade'])
def test_missing_actions_withhold_instead_of_using_legacy_vent(candidate, origin, field):
    def missing(**kwargs):
        value = actions(**kwargs)
        value['actions']['vent'] = {**value['actions']['window'], 'event_id': 'vent'}
        del value['actions'][field]
        value['missing_actions'] = sorted(set(ACTION_KINDS_V2)-set(value['actions']))
        return value
    assert run(candidate, origin, action_reader=missing)['status'] == 'unavailable'


@pytest.mark.parametrize('bad', ['model_inferred', 'historical_reconstruction', 0., float('nan'), True])
def test_unqualified_action_states_withhold(candidate, origin, bad):
    def invalid(**kwargs):
        value = actions(**kwargs)
        key = 'source' if isinstance(bad, str) else 'confidence'
        value['actions']['window'][key] = bad
        return value
    assert run(candidate, origin, action_reader=invalid)['status'] == 'unavailable'


def test_kiva_uses_the_same_two_hour_cooldown_as_training(candidate, origin):
    def event(age):
        def reader(**kwargs):
            value = actions(**kwargs)
            at = origin-timedelta(hours=age)
            value['actions']['kiva'].update(effective_at=at, received_at=at, created_at=at)
            return value
        return reader
    assert run(candidate, origin, action_reader=event(1.9))['status'] == 'unavailable'
    assert run(candidate, origin, action_reader=event(2))['status'] == 'available'


@pytest.mark.parametrize('damage', ['gap', 'stale', 'endpoint'])
def test_mass_history_must_be_complete_qualified_and_match_origin(candidate, origin, damage):
    def invalid(**kwargs):
        rows = temperatures(**kwargs)
        if len(rows) > 1:
            if damage == 'gap': rows[80] = (rows[80][0], None)
            elif damage == 'stale': rows[80][1]['validUntil'] = rows[80][0]
            else: rows[-1][1]['temperatureF'] += 1.
        return rows
    if damage == 'gap':
        assert run(candidate, origin, temperature_reader=invalid)['status'] == 'unavailable'
    else:
        with pytest.raises(ValueError, match='receipt|endpoint'):
            run(candidate, origin, temperature_reader=invalid)


def test_semantically_equal_iso_mass_endpoint_is_accepted(candidate, origin):
    capture = json.loads(a.canonical(run(candidate, origin)['capture']))
    value = capture['inputs']['mass_history'][-1]['receipt']
    value['storedAt'] = value['storedAt'].replace('+00:00', 'Z')
    assert _from_inputs(capture['artifact'], capture['inputs']) == capture['output']


@pytest.mark.parametrize('damage', ['late', 'old', 'early_capture', 'digest', 'missing_row', 'nan', 'extra'])
def test_invalid_as_issued_weather_is_refused(candidate, origin, damage):
    def invalid(**kwargs):
        value = weather(**kwargs)
        if damage == 'late': value['captured_at'] = origin+timedelta(seconds=1)
        elif damage == 'old': value['issued_at'] = origin-timedelta(hours=7)
        elif damage == 'early_capture': value['captured_at'] = value['issued_at']-timedelta(seconds=1)
        elif damage == 'digest': value['rows_sha256'] = 'invalid'
        elif damage == 'missing_row': value['rows'].pop()
        elif damage == 'nan': value['rows'][1]['tempF'] = float('nan')
        else: value['extra'] = 'not allowed'
        return value
    with pytest.raises(ValueError):
        run(candidate, origin, forecast_reader=invalid)


def test_late_action_knowledge_is_refused(candidate, origin):
    def late(**kwargs):
        value = actions(**kwargs)
        value['actions']['window']['created_at'] = origin+timedelta(seconds=1)
        return value
    with pytest.raises(ValueError, match='not available'):
        run(candidate, origin, action_reader=late)


@pytest.mark.parametrize('damage', ['future_artifact', 'stale_training', 'unaligned'])
def test_origin_and_training_chronology_are_enforced(candidate, origin, damage):
    value = deepcopy(candidate)
    if damage == 'future_artifact': value['created_at'] = (origin+STEP).isoformat()
    elif damage == 'stale_training': origin += timedelta(hours=27)
    else: origin += timedelta(minutes=1)
    with pytest.raises(ValueError, match='future|stale|align'):
        run(value, origin)


@pytest.mark.parametrize('damage', ['control', 'runtime', 'fit_revision', 'fit_data', 'items', 'mode_counts',
    'state_counts', 'radiation_counts', 'bad_count', 'unknown_count', 'objective', 'nonfinite', 'origins', 'boolean_version', 'extra'])
def test_artifact_rejects_inconsistent_or_unsupported_evidence(candidate, damage):
    value = deepcopy(candidate)
    if damage == 'control': value['control_enabled'] = True
    elif damage == 'runtime': value['runtime']['sha256'] = '0'*64
    elif damage == 'fit_revision': value['fit']['training_revision'] = '0'*64
    elif damage == 'fit_data': value['fit']['training_data_sha256'] = '0'*64
    elif damage == 'items': value['data_manifest']['dataset']['items']['air'] = 'AnotherSensor'
    elif damage == 'mode_counts': value['data_manifest']['dataset']['sample_counts_by_mode']['unknown'] += 1
    elif damage == 'state_counts': value['data_manifest']['state_counts']['window_open']['closed'] += 1
    elif damage == 'radiation_counts': value['data_manifest']['dataset']['radiation_provenance_counts']['observed'] += 1
    elif damage == 'bad_count': value['data_manifest']['dataset']['interpolation_counts']['air'] = True
    elif damage == 'unknown_count': value['data_manifest']['dataset']['rejected_counts']['invented'] = 1
    elif damage == 'objective': value['fit']['final_objective'] = value['fit']['initial_objective']+1
    elif damage == 'nonfinite': value['fit']['initial_objective'] = float('nan')
    elif damage == 'origins': value['fit']['origin_counts'] = (('5', 1),)*5
    elif damage == 'boolean_version': value['fit']['dynamics']['version'] = True
    else: value['extra'] = 0
    with pytest.raises(ValueError): a.validate_artifact(value)


def test_fitted_data_cannot_be_swapped_after_training(candidate):
    rows = make_synthetic_samples()
    fitted = fit_airflow_dynamics(rows)
    rows[100] = replace(rows[100], air_f=rows[100].air_f+1)
    with pytest.raises(ValueError, match='training data'):
        a.build_artifact(fitted, rows, [], [], created_at=a.utc(candidate['created_at']))


def test_runtime_cannot_hash_a_different_installed_tree(tmp_path):
    with pytest.raises(ValueError, match='executing'):
        a.runtime_manifest(tmp_path)


def test_runtime_must_not_change_during_fit(monkeypatch):
    original = a.runtime_manifest
    calls = []
    def changing():
        value = original()
        if calls: value['sha256'] = '0'*64
        calls.append(1)
        return value
    monkeypatch.setattr(a, 'runtime_manifest', changing)
    with pytest.raises(ValueError, match='runtime changed'):
        fit_airflow_dynamics(make_synthetic_samples())


def test_training_rows_must_not_change_during_fit(monkeypatch):
    import thermal_model.airflow_training as training
    rows = make_synthetic_samples()
    original = training.minimize
    def changing(*args, **kwargs):
        result = original(*args, **kwargs)
        rows[100] = replace(rows[100], air_f=rows[100].air_f+1)
        return result
    # Preserve the metadata-carrying dataset; the fitter owns ordinary tuples.
    from thermal_model.dataset import ThermalDataset
    dataset = ThermalDataset(rows, start=rows[0].at, end=rows[-1].at+STEP,
        rejected_counts={}, auxiliary_exclusion_counts={})
    def changing_dataset(*args, **kwargs):
        result = changing(*args, **kwargs)
        dataset[100] = rows[100]
        return result
    monkeypatch.setattr(training, 'minimize', changing_dataset)
    with pytest.raises(ValueError, match='data changed'):
        fit_airflow_dynamics(dataset)


@pytest.mark.parametrize('damage', ['digest', 'output', 'invalid_weather', 'invalid_current'])
def test_replay_rejects_tampering_even_with_recomputed_transport_digest(candidate, origin, damage):
    capture = run(candidate, origin)['capture']
    if damage == 'digest': capture['sha256'] = '0'*64
    elif damage == 'output':
        capture['output']['trajectory'][0]['air_f'] += 1
        rehash(capture)
    elif damage == 'invalid_weather':
        capture['inputs']['forecast']['captured_at'] = origin+STEP
        rehash(capture)
    else:
        capture['inputs']['current']['air']['storedAt'] = origin+STEP
        rehash(capture)
    with pytest.raises(ValueError): replay_capture(capture)


def test_unidentified_open_skylight_cannot_be_forecast(origin):
    rows = make_synthetic_samples(skylight_open=0.)
    fitted = fit_airflow_dynamics(rows, allow_inactive_action_forcing=True)
    candidate = a.build_artifact(fitted, rows, [], [], created_at=rows[-1].at+STEP)
    assert run(candidate, origin)['status'] == 'available'
    def activated(**kwargs):
        value = actions(**kwargs)
        value['actions']['skylight']['state'] = 'open'
        return value
    with pytest.raises(ValueError, match='unidentified'):
        run(candidate, origin, action_reader=activated)
