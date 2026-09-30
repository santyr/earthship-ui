"""Synthetic split-airflow identification; not household labels or promotion."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import random

import pytest

from thermal_model.airflow import (AIRFLOW_NAMES, AirflowSample, AirflowSeed,
    airflow_features, airflow_manifest, build_airflow_samples, fit_airflow_seed,
    predict_airflow_step, simulate_airflow, validate_airflow_physics)
from thermal_model.dynamics import fit_dynamics, predict_step, simulate
from thermal_model.schema import DynamicsModel
from test_thermal_dataset import START, END, action, fixture_series, fully_labeled_events


def seed():
    return AirflowSeed(1, 5, {
        'outside_exchange': .018, 'mass_exchange': .04,
        'solar_unshaded': .00015, 'solar_indoor_closed': .00006,
        'solar_outdoor': .00003, 'window_exchange': .02,
        'skylight_exchange': .035, 'joint_open_exchange': .015, 'bias': .002}, {
        'air_exchange': .008, 'outside_exchange': .003,
        'solar_unshaded': .000035, 'solar_indoor_closed': .000014,
        'solar_outdoor': .000007}, {})


def forcing(**values):
    return {'at': datetime(2026, 8, 13, 6, tzinfo=timezone.utc),
            'air_f': 75., 'mass_f': 72., 'outdoor_f': 60., 'radiation_wm2': 0.,
            'window_open': 0., 'skylight_open': 0.,
            'indoor_shade_closed': 0., 'outdoor_shade_present': 0., **values}


def test_dataset_keeps_separate_states_and_label_provenance():
    events = fully_labeled_events() + [action('window', 'window', 'open', START),
        action('sky', 'skylight', 'closed', START),
        action('sky-open', 'skylight', 'open', START + timedelta(minutes=30))]
    samples = build_airflow_samples(fixture_series(), events, [], START, END)
    assert samples[0].window_open == 1 and samples[0].skylight_open == 0
    assert samples[0].window_event_id == 'window' and samples[0].skylight_event_id == 'sky'
    assert samples[0].window_source == samples[0].skylight_source == 'manual_dm'
    later = next(row for row in samples if row.at >= START + timedelta(minutes=30))
    assert later.window_open == later.skylight_open == 1
    assert later.skylight_event_id == 'sky-open'
    assert all(row.vent_open is None and row.vent_confidence == 0 for row in samples)
    assert samples.confirmed_action_rows == ()
    assert START in samples.split_action_observation_rows
    manifest = airflow_manifest(samples, events, [])
    assert manifest['legacy_promotion_eligible'] is False
    assert manifest['state_counts']['skylight_open']['closed'] > 0
    assert manifest['state_counts']['skylight_open']['open'] > 0
    assert manifest == airflow_manifest(samples, list(reversed(events)), [])


def test_legacy_vent_does_not_label_windows_or_skylights():
    samples = build_airflow_samples(fixture_series(), fully_labeled_events(), [], START, END)
    assert all(row.window_open is None and row.skylight_open is None
               and row.action_confidence == 0 for row in samples)
    assert samples.confirmed_action_rows == ()
    with pytest.raises(ValueError, match='insufficient'):
        fit_airflow_seed(samples)


def test_unknown_window_does_not_erase_skylight_or_become_closed():
    events = fully_labeled_events() + [action('sky', 'skylight', 'closed', START)]
    row = build_airflow_samples(fixture_series(), events, [], START, END)[0]
    assert row.window_open is None and row.window_confidence == 0
    assert row.skylight_open == 0 and row.skylight_confidence == 1
    with pytest.raises(ValueError, match='independently known'):
        airflow_features(row)


def test_legacy_fit_and_prediction_cannot_silently_ignore_split_states():
    sample = build_airflow_samples(fixture_series(), fully_labeled_events(), [], START, END)[0]
    # Supply a legacy vent as well: the presence of v2 fields must still refuse.
    sample = replace(sample, vent_open=0.)
    with pytest.raises(ValueError, match='v2 dynamics'):
        fit_dynamics([sample])
    legacy = DynamicsModel(2, 5, {}, {}, {})
    with pytest.raises(ValueError, match='v2 dynamics'):
        predict_step(legacy, sample)
    with pytest.raises(ValueError, match='v2 dynamics'):
        simulate(legacy, {'air_f': 70., 'mass_f': 70.}, [forcing(vent_open=0.)])


def test_openings_have_independent_and_joint_temperature_effects():
    model = validate_airflow_physics(seed())
    closed = predict_airflow_step(model, forcing())[0]
    window = predict_airflow_step(model, forcing(window_open=1.))[0]
    skylight = predict_airflow_step(model, forcing(skylight_open=1.))[0]
    both = predict_airflow_step(model, forcing(window_open=1., skylight_open=1.))[0]
    assert closed-window == pytest.approx(.02*15)
    assert closed-skylight == pytest.approx(.035*15)
    assert closed-both == pytest.approx((.02+.035+.015)*15)
    # Openings reverse their heat-transfer direction when outside is warmer.
    assert predict_airflow_step(model, forcing(outdoor_f=90., window_open=1.))[0] \
        > predict_airflow_step(model, forcing(outdoor_f=90.))[0]


@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), -1., 2., True])
def test_invalid_or_unknown_opening_refused(value):
    with pytest.raises(ValueError, match='independently known'):
        predict_airflow_step(seed(), forcing(window_open=value))


def make_synthetic_samples(count=600, *, skylight_open=None):
    rng = random.Random(812)
    model = seed()
    at = datetime(2026, 8, 13, tzinfo=timezone.utc)
    air, mass = 75., 72.
    rows = []
    for step in range(count):
        row = AirflowSample(at=at, air_f=air, mass_f=mass, glazing_f=None,
            outdoor_f=55.+rng.random()*25, radiation_wm2=rng.random()*800,
            vent_open=None, vent_confidence=0.,
            indoor_shade_closed=float(rng.randrange(2)), indoor_shade_confidence=1.,
            outdoor_shade_present=float(rng.randrange(2)), outdoor_shade_confidence=1.,
            action_confidence=1., passive_fit_allowed=True, mode='warm',
            window_open=float(rng.randrange(2)), window_confidence=1.,
            skylight_open=float(rng.randrange(2)), skylight_confidence=1.)
        if skylight_open is not None:
            row = replace(row, skylight_open=float(skylight_open))
        if rows:
            air, mass, _ = predict_airflow_step(model, replace(row, air_f=air, mass_f=mass))
            row = replace(row, air_f=air, mass_f=mass)
        rows.append(row)
        at += timedelta(minutes=5)
    return rows


@pytest.fixture(scope='module')
def synthetic_samples():
    return make_synthetic_samples()


def test_seed_recovers_independent_coefficients_on_synthetic_data(synthetic_samples):
    fitted = fit_airflow_seed(synthetic_samples)
    for name, value in seed().air_coefficients.items():
        assert fitted.air_coefficients[name] == pytest.approx(value, abs=1e-6)
    for name, value in seed().mass_coefficients.items():
        assert fitted.mass_coefficients[name] == pytest.approx(value, abs=1e-6)


def test_simulation_uses_each_future_state_without_rewriting_vent():
    later = forcing(at=forcing()['at'] + timedelta(minutes=5), skylight_open=1.)
    result = simulate_airflow(seed(), {'air_f': 75., 'mass_f': 72.},
        [forcing(window_open=1.), later])
    first = predict_airflow_step(seed(), forcing(window_open=1.))
    second = predict_airflow_step(seed(), {**later, 'air_f': first[0], 'mass_f': first[1]})
    assert result[-1]['air_f'] == second[0]
    assert result[-1]['mass_f'] == second[1]


def test_split_prediction_refuses_legacy_combined_vent_and_duplicate_forecast_times():
    with pytest.raises(ValueError, match='legacy vent'):
        predict_airflow_step(seed(), forcing(vent_open=1.))
    with pytest.raises(ValueError, match='consecutive'):
        simulate_airflow(seed(), {'air_f': 75., 'mass_f': 72.}, [forcing(), forcing()])


def test_wrong_sample_vocabulary_version_is_not_accepted(synthetic_samples):
    rows = [replace(row, airflow_vocabulary_version=3) for row in synthetic_samples]
    with pytest.raises(ValueError, match='vocabulary'):
        fit_airflow_seed(rows)


def test_same_opening_history_cannot_identify_two_effects(synthetic_samples):
    rows = [replace(row, skylight_open=row.window_open) for row in synthetic_samples]
    with pytest.raises(ValueError, match='rank deficient'):
        fit_airflow_seed(rows)


@pytest.mark.parametrize('kind', ['unknown', 'exceptional', 'nonconsecutive', 'zero_confidence'])
def test_unusable_pairs_cannot_fit(synthetic_samples, kind):
    if kind == 'unknown':
        rows = [replace(row, window_open=None) for row in synthetic_samples]
    elif kind == 'exceptional':
        rows = [replace(row, passive_fit_allowed=False) for row in synthetic_samples]
    elif kind == 'zero_confidence':
        rows = [replace(row, skylight_confidence=0.) for row in synthetic_samples]
    else:
        rows = synthetic_samples[::2]
    with pytest.raises(ValueError, match='insufficient'):
        fit_airflow_seed(rows)


def test_combined_exchange_bound_and_transition_stability():
    model = seed()
    high = {**model.air_coefficients, **{k: .4 for k in AIRFLOW_NAMES}}
    with pytest.raises(ValueError, match='combined opening'):
        validate_airflow_physics(replace(model, air_coefficients=high))
    marginal = replace(model, air_coefficients={**model.air_coefficients, 'outside_exchange': 0.,
                                              'mass_exchange': 0.},
                        mass_coefficients={**model.mass_coefficients, 'air_exchange': 0.,
                                           'outside_exchange': 0.})
    with pytest.raises(ValueError, match='not stable'):
        validate_airflow_physics(marginal)
