"""Bounded split-airflow multihorizon fitting and retrospective fold diagnosis.

Pure offline computation: no registry write, accepted-artifact promotion,
as-issued forecast claim, journal mutation or control capability.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from numbers import Real

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, minimize

from .airflow import (AIRFLOW_NAMES, AirflowSample, AirflowSeed, SEED_AIR_BOUNDS,
                      SEED_AIR_NAMES, _split_contract, airflow_features, airflow_manifest,
                      fit_airflow_seed_with_evidence, simulate_airflow, validate_airflow_physics)
from .dataset import STEP, ThermalDataset
from .dynamics import (IDENTIFICATION_HORIZON_STEPS, MAX_ORIGINS_PER_HORIZON,
                       MASS_BOUNDS, MASS_NAMES, MULTIHORIZON_FTOL,
                       MULTIHORIZON_MAXITER, MULTIHORIZON_OBJECTIVE_TOLERANCE,
                       SOLVER_FEASIBILITY_MARGIN,
                       _eligible_daily_endpoints_from_prepared, _solar_terms,
                       _uniform_origin_indices, _validate_multihorizon_rank)


@dataclass(frozen=True)
class AirflowFit:
    dynamics: AirflowSeed
    inactive_forcing_features: tuple[str, ...]
    origin_counts: tuple[tuple[str, int], ...]
    initial_objective: float
    final_objective: float
    training_revision: str | None = None
    training_data_sha256: str | None = None


def _confidence(row):
    values = (row.action_confidence, row.window_confidence, row.skylight_confidence)
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError('invalid split-airflow confidence')
    return min(values)


def _ordered(samples):
    rows = tuple(samples)
    for row in rows:
        if not isinstance(row, AirflowSample) or not isinstance(row.at, datetime) or row.at.utcoffset() is None:
            raise ValueError('aware v2 split-airflow samples required')
        _split_contract(row)
    if len({row.at for row in rows}) != len(rows):
        raise ValueError('duplicate split-airflow timestamp')
    return tuple(sorted(rows, key=lambda row: row.at))


def forcing_features(row):
    solar = _solar_terms(row)
    return {**dict(zip(SEED_AIR_NAMES[2:5], solar)), **dict(zip(AIRFLOW_NAMES, airflow_features(row)))}


def _valid(row):
    if not row.passive_fit_allowed or _confidence(row) <= 0:
        return False
    values = (row.air_f, row.mass_f, row.outdoor_f, row.radiation_wm2,
              row.window_open, row.skylight_open, row.indoor_shade_closed, row.outdoor_shade_present)
    if any(not isinstance(v, Real) or isinstance(v, (bool, np.bool_)) or not math.isfinite(v) for v in values):
        return False
    if row.mode not in {'spring', 'warm', 'fall_charge', 'winter'}:
        return False
    return all(0 <= v <= 1 for v in (row.indoor_shade_closed, row.outdoor_shade_present))


def select_endpoints(samples, inactive_features=()):
    rows = _ordered(samples)
    inactive = tuple(inactive_features)
    if set(inactive) - set((*AIRFLOW_NAMES, 'solar_indoor_closed', 'solar_outdoor')):
        raise ValueError('unknown inactive split-airflow feature')
    valid = tuple(_valid(row) for row in rows)
    safe = []
    for row, ok in zip(rows, valid):
        features = forcing_features(row) if ok and inactive else {}
        safe.append(ok and all(features[name] == 0.0 for name in inactive))
    safe = tuple(safe)
    prepared = rows, valid, safe, [_confidence(row) if ok else math.inf for row, ok in zip(rows, valid)]
    selected = {}
    for steps in IDENTIFICATION_HORIZON_STEPS:
        eligible = _eligible_daily_endpoints_from_prepared(prepared, steps)
        selected[steps] = tuple(eligible[i] for i in _uniform_origin_indices(
            len(eligible), MAX_ORIGINS_PER_HORIZON))
    return selected


def prepare_rollouts(endpoints):
    """Cache unique solar/opening features once; bound batches to daily origins."""
    cache, prepared = {}, {}
    for steps in IDENTIFICATION_HORIZON_STEPS:
        group = tuple(endpoints.get(steps, ()))
        if not 2 <= len(group) <= MAX_ORIGINS_PER_HORIZON:
            raise ValueError('two to 64 daily origins required at each identification horizon')
        forcing_rows = []
        for endpoint in group:
            if len(endpoint.forcings) != steps:
                raise ValueError('invalid split-airflow forcing prefix')
            prefix = []
            for row in endpoint.forcings:
                if id(row) not in cache:
                    cache[id(row)] = (row.outdoor_f, *_solar_terms(row), *airflow_features(row))
                prefix.append(cache[id(row)])
            forcing_rows.append(prefix)
        prepared[steps] = {
            'forcing': np.asarray(forcing_rows, dtype=float),
            'initial': np.asarray([(e.origin.air_f, e.origin.mass_f) for e in group], dtype=float),
            'target': np.asarray([(e.target.air_f, e.target.mass_f) for e in group], dtype=float),
            'weights': np.asarray([e.confidence / len(group) for e in group], dtype=float)}
    return prepared


def coefficient_vector(model):
    return np.asarray([model.air_coefficients[k] for k in SEED_AIR_NAMES]
                      + [model.mass_coefficients[k] for k in MASS_NAMES], dtype=float)


def _model(vector, glazing):
    split = len(SEED_AIR_NAMES)
    return AirflowSeed(1, 5, dict(zip(SEED_AIR_NAMES, map(float, vector[:split]))),
                       dict(zip(MASS_NAMES, map(float, vector[split:]))), dict(glazing))


def objective_and_gradient(vector, prepared, *, sensitivity_rows=None):
    """Analytic recurrence vectorized across origins, never across future time."""
    p = np.asarray(vector, dtype=float)
    n_air, n_coeff = len(SEED_AIR_NAMES), len(SEED_AIR_NAMES) + len(MASS_NAMES)
    if p.shape != (n_coeff,) or not np.isfinite(p).all():
        raise ValueError('invalid split-airflow optimizer vector')
    a, m = p[:n_air], p[n_air:]
    loss, gradient = 0.0, np.zeros(n_coeff)
    try:
        with np.errstate(over='raise', invalid='raise'):
            for steps in IDENTIFICATION_HORIZON_STEPS:
                group = prepared[steps]
                forcing = group['forcing']
                state = group['initial'].copy()
                count = len(state)
                if (forcing.shape != (count, steps, 7) or group['target'].shape != (count, 2)
                        or group['weights'].shape != (count,) or count < 2
                        or not all(np.isfinite(x).all() for x in group.values())
                        or np.any(group['weights'] < 0) or np.any(group['weights'] > 1/count)):
                    raise ValueError('invalid split-airflow endpoint evidence')
                sa, sm = np.zeros((count, n_coeff)), np.zeros((count, n_coeff))
                da, dm = np.zeros((count, n_coeff)), np.zeros((count, n_coeff))
                for step in range(steps):
                    f = forcing[:, step, :]
                    solar, openings = f[:, 1:4], f[:, 4:7]
                    outside_delta, mass_delta = f[:, 0] - state[:, 0], state[:, 1] - state[:, 0]
                    exchange = openings @ a[5:8]
                    da[:, :n_air] = np.column_stack((outside_delta, mass_delta, solar,
                                                     openings * outside_delta[:, None], np.ones(count)))
                    dm[:, n_air:] = np.column_stack((-mass_delta, f[:, 0] - state[:, 1], solar))
                    next_sa = (1-a[0]-a[1]-exchange)[:, None] * sa + a[1] * sm + da
                    next_sm = m[0] * sa + (1-m[0]-m[1]) * sm + dm
                    next_air = state[:, 0] + (a[0]+exchange)*outside_delta + a[1]*mass_delta \
                        + solar @ a[2:5] + a[8]
                    next_mass = state[:, 1] - m[0]*mass_delta + m[1]*(f[:, 0]-state[:, 1]) \
                        + solar @ m[2:5]
                    state[:, 0], state[:, 1] = next_air, next_mass
                    sa, sm = next_sa, next_sm
                residual = state - group['target']
                sensitivity = np.stack((sa, sm), axis=1)
                weights = group['weights']
                loss += float(np.sum(weights[:, None] * residual**2))
                gradient += 2 * np.einsum('n,nc,ncp->p', weights, residual, sensitivity)
                if sensitivity_rows is not None:
                    sensitivity_rows.extend((np.sqrt(weights)[:, None, None] * sensitivity).reshape(-1, n_coeff))
    except FloatingPointError as error:
        raise ValueError('nonfinite split-airflow rollout') from error
    if not math.isfinite(loss) or not np.isfinite(gradient).all():
        raise ValueError('nonfinite split-airflow objective')
    return loss, gradient


def _constraints(active, initial, lower, spans):
    total = len(initial)
    rows, lo, hi = [], [], []
    for offset, names in ((0, SEED_AIR_NAMES), (len(SEED_AIR_NAMES), MASS_NAMES)):
        for shaded in ('solar_indoor_closed', 'solar_outdoor'):
            row = np.zeros(total)
            row[offset + names.index('solar_unshaded')] = 1
            row[offset + names.index(shaded)] = -1
            rows.append(row); lo.append(SOLVER_FEASIBILITY_MARGIN); hi.append(np.inf)
    row = np.zeros(total)
    for name in AIRFLOW_NAMES:
        row[SEED_AIR_NAMES.index(name)] = 1
    rows.append(row); lo.append(0.0); hi.append(0.80 - SOLVER_FEASIBILITY_MARGIN)
    matrix = np.asarray(rows)
    fixed = [i for i in range(total) if i not in active]
    offset = matrix[:, active] @ lower[active] + matrix[:, fixed] @ initial[fixed]
    return LinearConstraint(matrix[:, active] * spans[active], np.asarray(lo)-offset, np.asarray(hi)-offset)


def fit_airflow_dynamics(samples, *, allow_inactive_action_forcing=False):
    from .airflow_artifact import runtime_manifest
    runtime = runtime_manifest()
    rows = _ordered(samples)
    training_source = samples if isinstance(samples, ThermalDataset) else rows
    data_sha256 = airflow_manifest(training_source, [], [])['dataset']['canonical_rows_sha256']
    seed, inactive = fit_airflow_seed_with_evidence(rows,
        allow_inactive_action_forcing=allow_inactive_action_forcing)
    endpoints = select_endpoints(rows, inactive)
    prepared = prepare_rollouts(endpoints)
    initial = coefficient_vector(seed)
    lower = np.asarray(SEED_AIR_BOUNDS[0] + MASS_BOUNDS[0], dtype=float)
    upper = np.asarray(SEED_AIR_BOUNDS[1] + MASS_BOUNDS[1], dtype=float)
    spans = upper-lower
    names = SEED_AIR_NAMES + MASS_NAMES
    active = [i for i, name in enumerate(names) if name not in inactive]
    sensitivities = []
    initial_loss, _ = objective_and_gradient(initial, prepared, sensitivity_rows=sensitivities)
    _validate_multihorizon_rank(sensitivities, active)
    # Keep only the last evaluation: scipy requests value/Jacobian separately.
    cache = {}
    def evaluate(scaled):
        p = initial.copy()
        p[active] = lower[active] + spans[active]*scaled
        key = p.tobytes()
        if cache.get('key') != key:
            value, gradient = objective_and_gradient(p, prepared)
            cache.update(key=key, result=(value, gradient[active]*spans[active], p))
        return cache['result']
    result = minimize(lambda x: evaluate(x)[0], (initial[active]-lower[active])/spans[active],
        method='SLSQP', jac=lambda x: evaluate(x)[1], bounds=Bounds(np.zeros(len(active)), np.ones(len(active))),
        constraints=_constraints(active, initial, lower, spans),
        options={'ftol': MULTIHORIZON_FTOL, 'maxiter': MULTIHORIZON_MAXITER})
    if (not result.success or np.asarray(result.x).shape != (len(active),)
            or not np.isfinite(result.x).all() or np.any(result.x < 0) or np.any(result.x > 1)):
        raise ValueError('split-airflow optimizer failed')
    final_loss, _, vector = evaluate(result.x)
    fitted = validate_airflow_physics(_model(vector, seed.glazing_observation_coefficients))
    if final_loss > initial_loss + MULTIHORIZON_OBJECTIVE_TOLERANCE*max(1.0, initial_loss):
        raise ValueError('split-airflow multihorizon objective increased')
    if runtime_manifest() != runtime:
        raise ValueError('split-airflow runtime changed during fitting')
    if airflow_manifest(training_source, [], [])['dataset']['canonical_rows_sha256'] != data_sha256:
        raise ValueError('split-airflow data changed during fitting')
    return AirflowFit(fitted, inactive,
        tuple((str(steps*5), len(endpoints[steps])) for steps in IDENTIFICATION_HORIZON_STEPS),
        float(initial_loss), float(final_loss), runtime['sha256'], data_sha256)


def evaluate_airflow_fold(samples, origin, *, training_reader, fit=fit_airflow_dynamics,
                          horizons_hours=(1, 6, 12, 24, 48, 72)):
    """One explicit retrospective fold; observed future forcing is NOT a forecast.

    The caller rebuilds training with its receipt cutoff. Journal commit-time
    availability and as-issued weather must be qualified separately before
    operational forecast scoring. This report cannot promote an artifact.
    """
    if not isinstance(origin, datetime) or origin.utcoffset() is None:
        raise ValueError('aware fold origin required')
    if origin.second or origin.microsecond or origin.minute % 5:
        raise ValueError('fold origin must align to five minutes')
    if (not horizons_hours or any(type(h) is not int or h not in (1, 6, 12, 24, 48, 72) for h in horizons_hours)
            or len(set(horizons_hours)) != len(horizons_hours)):
        raise ValueError('invalid fold horizons')
    rows = _ordered(samples)
    by_at = {row.at: row for row in rows}
    train = _ordered(training_reader(origin=origin))
    if any(row.at >= origin for row in train):
        raise ValueError('fold training includes origin or future data')
    if not train or origin-train[0].at < timedelta(days=14):
        raise ValueError('fourteen days of prior fold training required')
    if origin not in by_at:
        raise ValueError('fold origin observation unavailable')
    fitted = fit(train, allow_inactive_action_forcing=True)
    validate_airflow_physics(fitted.dynamics)
    scores, withheld, available = [], [], {}
    feature_cache = {}
    for hours in horizons_hours:
        times = [origin+i*STEP for i in range(1, hours*12+1)]
        if any(at not in by_at or not _valid(by_at[at]) for at in times):
            withheld.append({'hours': hours, 'reason': 'unknown_or_incomplete_observed_forcing'})
            continue
        future = [by_at[at] for at in times]
        for row in future:
            if fitted.inactive_forcing_features and row.at not in feature_cache:
                feature_cache[row.at] = forcing_features(row)
        activated = sorted({name for row in future for name in fitted.inactive_forcing_features
                            if feature_cache[row.at][name] != 0.0})
        if activated:
            withheld.append({'hours': hours, 'reason': 'unidentified_forcing_activated', 'features': activated})
            continue
        available[hours] = future
    predictions = simulate_airflow(fitted.dynamics, by_at[origin], available[max(available)]) if available else []
    for hours, future in available.items():
        prediction = predictions[hours*12-1]
        target = future[-1]
        scores.append({'hours': hours, 'target': target.at.isoformat(),
            'model_error_f': {state: prediction[state+'_f']-getattr(target, state+'_f') for state in ('air', 'mass')},
            'persistence_error_f': {state: getattr(by_at[origin], state+'_f')-getattr(target, state+'_f')
                                    for state in ('air', 'mass')}})
    return {'schema': 'earthship-split-airflow-retrospective-fold/v1',
            'forcing_evidence': 'observed_held_out_not_as_issued', 'promotion_eligible': False,
            'origin': origin.isoformat(), 'training_rows': len(train),
            'training_through': train[-1].at.isoformat(), 'scores': scores, 'withheld': withheld}
