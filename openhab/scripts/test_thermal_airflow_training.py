"""Offline numerical and chronological tests; no household promotion claim."""
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import numpy as np
import pytest

import thermal_model.airflow_training as t
from thermal_model.airflow import fit_airflow_seed_with_evidence, simulate_airflow
from thermal_model.dynamics import IDENTIFICATION_HORIZON_STEPS
from test_thermal_airflow import make_synthetic_samples, seed
from test_thermal_dataset import START, END, action, fixture_series, fully_labeled_events
from thermal_model.airflow import build_airflow_samples


@pytest.fixture(scope='module')
def samples():
    return make_synthetic_samples()


def reference_objective(model, endpoints):
    loss = 0.
    for group in endpoints.values():
        for e in group:
            prediction = simulate_airflow(model, e.origin, e.forcings)[-1]
            loss += e.confidence/len(group) * sum(
                (prediction[k+'_f']-getattr(e.target, k+'_f'))**2 for k in ('air', 'mass'))
    return loss


def test_batched_objective_matches_independent_scalar_simulation(samples):
    endpoints = t.select_endpoints(samples)
    prepared = t.prepare_rollouts(endpoints)
    model = replace(seed(), air_coefficients={**seed().air_coefficients, 'window_exchange': .025})
    loss, _ = t.objective_and_gradient(t.coefficient_vector(model), prepared)
    assert loss == pytest.approx(reference_objective(model, endpoints), rel=1e-11, abs=1e-12)


def test_analytic_gradient_matches_centered_finite_difference(samples):
    endpoints = t.select_endpoints(samples)
    prepared = t.prepare_rollouts(endpoints)
    model = replace(seed(), air_coefficients={**seed().air_coefficients, 'window_exchange': .025})
    vector = t.coefficient_vector(model)
    _, gradient = t.objective_and_gradient(vector, prepared)
    numerical = []
    for i in range(len(vector)):
        eps = 1e-7 if i not in (2, 3, 4, 11, 12, 13) else 1e-9
        plus, minus = vector.copy(), vector.copy()
        plus[i] += eps; minus[i] -= eps
        numerical.append((t.objective_and_gradient(plus, prepared)[0]
                          - t.objective_and_gradient(minus, prepared)[0])/(2*eps))
    np.testing.assert_allclose(gradient, numerical, rtol=2e-5, atol=2e-5)


def test_refinement_reduces_open_loop_drift_and_retains_independent_effects(samples):
    # Reproduce a latent-observer mismatch, not an accepted household fit.
    rows = [replace(row, mass_f=row.mass_f + .25*np.sin(i/40)) for i, row in enumerate(samples)]
    fitted = t.fit_airflow_dynamics(rows)
    assert fitted.final_objective < fitted.initial_objective
    assert fitted.dynamics.air_coefficients['window_exchange'] > 0
    assert fitted.dynamics.air_coefficients['skylight_exchange'] > 0
    assert fitted.dynamics.air_coefficients['joint_open_exchange'] > 0
    assert all(count >= 2 for _, count in fitted.origin_counts)


def test_refinement_is_deterministic(samples):
    a, b = t.fit_airflow_dynamics(samples), t.fit_airflow_dynamics(samples)
    assert a == b


@pytest.mark.parametrize('damage', ['unknown', 'heat', 'confidence', 'gap'])
def test_invalid_interior_forcing_breaks_endpoint_prefix(samples, damage):
    rows = list(samples)
    i = 200
    if damage == 'unknown': rows[i] = replace(rows[i], skylight_open=None)
    elif damage == 'heat': rows[i] = replace(rows[i], passive_fit_allowed=False)
    elif damage == 'confidence': rows[i] = replace(rows[i], window_confidence=0.)
    else: rows.pop(i)
    endpoints = t.select_endpoints(rows)
    assert all(not (e.origin.at < samples[i].at <= e.target.at)
               for group in endpoints.values() for e in group)


def test_seed_and_multihorizon_allow_only_identified_inactive_features(samples):
    # Generate genuine closed-skylight transitions; do not relabel open truth.
    rows = make_synthetic_samples(skylight_open=0.)
    model, inactive = fit_airflow_seed_with_evidence(rows, allow_inactive_action_forcing=True)
    assert inactive == ('skylight_exchange', 'joint_open_exchange')
    assert model.air_coefficients['skylight_exchange'] == 0
    fitted = t.fit_airflow_dynamics(rows, allow_inactive_action_forcing=True)
    assert fitted.inactive_forcing_features == inactive
    assert fitted.dynamics.air_coefficients['skylight_exchange'] == 0


def test_too_few_daily_origins_refuses(samples):
    endpoints = t.select_endpoints(samples)
    endpoints[288] = endpoints[288][:1]
    with pytest.raises(ValueError, match='daily origins'):
        t.prepare_rollouts(endpoints)


def test_daily_selector_is_bounded_and_covers_long_training_range(samples):
    rows = [replace(samples[i % len(samples)], at=samples[0].at+i*timedelta(minutes=5))
            for i in range(100*288)]
    selected = t.select_endpoints(rows)
    assert set(selected) == set(IDENTIFICATION_HORIZON_STEPS)
    for group in selected.values():
        assert len(group) == 64
        assert group[0].origin.at == rows[0].at
        assert group[-1].origin.at > rows[-1].at-timedelta(days=2)


def test_nonfinite_endpoint_evidence_refuses(samples):
    prepared = t.prepare_rollouts(t.select_endpoints(samples))
    prepared[1]['target'][0, 0] = np.nan
    with pytest.raises(ValueError, match='endpoint evidence'):
        t.objective_and_gradient(t.coefficient_vector(seed()), prepared)


def test_optimizer_cannot_publish_a_worse_objective(monkeypatch, samples):
    def bad(*args, **kwargs):
        x = np.asarray(args[1]).copy()
        x[8] = 1.0  # Bounded, physically stable but strongly wrong air bias.
        return SimpleNamespace(success=True, x=x)
    monkeypatch.setattr(t, 'minimize', bad)
    with pytest.raises(ValueError, match='objective increased'):
        t.fit_airflow_dynamics(samples)


@pytest.mark.parametrize('failure', ['failed', 'nan', 'wrong_shape', 'out_of_bounds'])
def test_optimizer_result_is_not_trusted(monkeypatch, samples, failure):
    def bad(*args, **kwargs):
        x = np.asarray(args[1]).copy()
        if failure == 'nan': x[0] = np.nan
        elif failure == 'wrong_shape': x = x[:-1]
        elif failure == 'out_of_bounds': x[0] = 2.
        return SimpleNamespace(success=failure != 'failed', x=x)
    monkeypatch.setattr(t, 'minimize', bad)
    with pytest.raises(ValueError, match='optimizer failed'):
        t.fit_airflow_dynamics(samples)


def test_knowledge_cutoff_does_not_use_future_confirmation_or_temperature():
    future = action('later-window', 'window', 'open', START)
    future = replace(future, received_at=END + timedelta(minutes=10))
    rows = fixture_series()
    # A future point that would otherwise bridge/alter the last training bucket.
    rows['air'].append((END + timedelta(minutes=5), 139.))
    a = build_airflow_samples(rows, fully_labeled_events() + [future], [], START, END, known_by=END)
    assert all(row.window_open is None for row in a)
    rows['air'][-1] = (END + timedelta(minutes=5), -39.)
    b = build_airflow_samples(rows, fully_labeled_events() + [future], [], START, END, known_by=END)
    assert a == b
    with pytest.raises(ValueError, match='exceeds knowledge cutoff'):
        build_airflow_samples(rows, [], [], START, END, known_by=START)


@pytest.fixture(scope='module')
def fold_samples():
    return make_synthetic_samples(18*288)


def fitted_stub(train, *, allow_inactive_action_forcing):
    assert allow_inactive_action_forcing
    return t.AirflowFit(seed(), (), (('5', 2),), 0., 0.)


def test_fold_trains_strictly_before_origin_and_labels_hindcast(fold_samples):
    origin = fold_samples[14*288].at
    calls = []
    def fit(train, **kwargs):
        calls.append(tuple(train))
        return fitted_stub(train, **kwargs)
    result = t.evaluate_airflow_fold(fold_samples, origin,
        training_reader=lambda **_: fold_samples[:14*288], fit=fit)
    assert all(row.at < origin for row in calls[0])
    assert result['forcing_evidence'] == 'observed_held_out_not_as_issued'
    assert result['promotion_eligible'] is False
    assert [record['hours'] for record in result['scores']] == [1, 6, 12, 24, 48, 72]
    assert max(abs(record['model_error_f']['air']) for record in result['scores']) < 1e-9


def test_held_out_outcome_mutation_cannot_change_training(fold_samples):
    origin = fold_samples[14*288].at
    inputs = []
    def fit(train, **kwargs):
        inputs.append(tuple(train))
        return fitted_stub(train, **kwargs)
    kwargs = dict(training_reader=lambda **_: fold_samples[:14*288], fit=fit, horizons_hours=(1,))
    before = t.evaluate_airflow_fold(fold_samples, origin, **kwargs)
    mutated = list(fold_samples)
    idx = 14*288+12
    mutated[idx] = replace(mutated[idx], air_f=mutated[idx].air_f+3.)
    after = t.evaluate_airflow_fold(mutated, origin, **kwargs)
    assert inputs[0] == inputs[1]
    assert after['scores'][0]['model_error_f']['air'] == pytest.approx(
        before['scores'][0]['model_error_f']['air']-3.)


def test_origin_or_future_in_training_is_refused(fold_samples):
    origin = fold_samples[14*288].at
    with pytest.raises(ValueError, match='origin or future'):
        t.evaluate_airflow_fold(fold_samples, origin,
            training_reader=lambda **_: fold_samples[:14*288+1], fit=fitted_stub)


def test_held_out_unidentified_opening_is_withheld(fold_samples):
    origin = fold_samples[14*288].at
    def fit(*args, **kwargs):
        model = replace(seed(), air_coefficients={**seed().air_coefficients,
                       'skylight_exchange': 0., 'joint_open_exchange': 0.})
        return t.AirflowFit(model, ('skylight_exchange', 'joint_open_exchange'), (), 0., 0.)
    result = t.evaluate_airflow_fold(fold_samples, origin,
        training_reader=lambda **_: fold_samples[:14*288], fit=fit)
    assert result['scores'] == []
    assert all(record['reason'] == 'unidentified_forcing_activated' for record in result['withheld'])


def test_unknown_future_state_is_withheld_not_closed(fold_samples):
    rows = list(fold_samples); index = 14*288+5
    rows[index] = replace(rows[index], window_open=None)
    result = t.evaluate_airflow_fold(rows, rows[14*288].at,
        training_reader=lambda **_: rows[:14*288], fit=fitted_stub)
    assert not result['scores']
    assert all(record['reason'] == 'unknown_or_incomplete_observed_forcing' for record in result['withheld'])


def test_one_unknown_later_state_does_not_suppress_complete_shorter_horizon(fold_samples):
    rows = list(fold_samples)
    rows[14*288+24] = replace(rows[14*288+24], skylight_open=None)
    result = t.evaluate_airflow_fold(rows, rows[14*288].at,
        training_reader=lambda **_: rows[:14*288], fit=fitted_stub, horizons_hours=(1, 6))
    assert [record['hours'] for record in result['scores']] == [1]
    assert [record['hours'] for record in result['withheld']] == [6]
