"""Constrained native-input development fitting for the installed-shade domain.

Observed-weather endpoint loss is not as-issued release evidence. This module
never installs a model, creates a release artifact or publishes forecasts.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import defaultdict
import math
import time
from typing import ClassVar

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, minimize

from .actions import DENVER
from .dynamics import (NORMALIZED_CONDITION_NUMBER_LIMIT, BLOCK_REFIT_GROUPS,
    BLOCK_REFIT_MIN_INDEPENDENT_DAYS, BLOCK_REFIT_MAX_BOUND_SPAN_FRACTION,
    MAX_ORIGINS_PER_HORIZON, MULTIHORIZON_FTOL, MULTIHORIZON_MAXITER,
    MULTIHORIZON_OBJECTIVE_TOLERANCE, SOLVER_FEASIBILITY_MARGIN,
    SOLAR_TERM_SCALE, STABILITY_TOLERANCE, OUTPUT_RANGE_F)
from .graduation_policy import _utc
from .installed_shade_dynamics import (InstalledShadeDynamics, LOWER, UPPER,
    PARAMETER_NAMES, STEP)
from .installed_shade_inputs import (DevelopmentEndpoint, build_development_inputs,
    select_development_endpoints)
from .offline_training import require_fitting_optin
from .solar import clear_sky_fraction

HORIZONS = (1, 6, 12, 24)


@dataclass(frozen=True)
class EndpointFit:
    model: InstalledShadeDynamics
    initial_objective: float
    final_objective: float
    conditioning_rank: int
    normalized_condition_number: float
    iterations: int
    release_authorized: ClassVar[bool] = False


@dataclass(frozen=True)
class BlockRefit:
    group: int
    omitted_days: tuple[str, ...]
    coefficients: tuple[float, ...]


@dataclass(frozen=True)
class StabilityAssessment:
    assessed: bool
    independent_days: int
    required_days: int
    refits: tuple[BlockRefit, ...]
    max_bound_span_fraction: float | None
    worst_coefficient: str | None
    release_authorized: ClassVar[bool] = False


@dataclass(frozen=True)
class DevelopmentFit:
    fit: EndpointFit
    stability: StabilityAssessment
    source_snapshot_sha256: str
    sensor_epochs: tuple[tuple[str, str], ...]
    training_start: datetime
    training_end: datetime
    origin_counts: tuple[tuple[int, int], ...]
    independent_window_counts: tuple[tuple[int, int], ...]
    release_authorized: ClassVar[bool] = False
    as_issued_evidence: ClassVar[bool] = False


def _check_deadline(deadline):
    if type(deadline) not in (int, float) or not math.isfinite(deadline) or time.monotonic() >= deadline:
        raise ValueError('bounded fitting deadline exceeded')


def _prepare_batches(points):
    if type(points) is not tuple or not 1 <= len(points) <= len(HORIZONS)*MAX_ORIGINS_PER_HORIZON:
        raise ValueError('bounded immutable development endpoints required')
    groups = defaultdict(list)
    for point in points:
        if not isinstance(point, DevelopmentEndpoint):
            raise ValueError('explicit development endpoint required')
        steps = len(point.forcings)
        if not 1 <= steps <= 72*12 or point.target.at != point.origin.at + steps*STEP:
            raise ValueError('complete bounded endpoint forcing required')
        at = point.origin.at
        for row in point.forcings:
            at += STEP
            if (row.at != at or row.outdoor_shade_present != 1 or
                    row.indoor_shade_closed != point.origin.indoor_shade_closed or
                    row.vent_open != point.origin.vent_open or
                    not 0 <= row.indoor_shade_closed <= 1 or
                    not 0 <= row.vent_open <= 2 or
                    not -40 <= row.outdoor_f <= 140 or
                    not 0 <= row.radiation_wm2 <= 1600):
                raise ValueError('complete origin-action installed-shade forcing required')
        groups[steps].append(point)
    batches = []
    for steps, group in sorted(groups.items()):
        if len(group) > MAX_ORIGINS_PER_HORIZON:
            raise ValueError('development origin count exceeds horizon limit')
        origins = np.asarray([(p.origin.air_f, p.origin.mass_f) for p in group])
        targets = np.asarray([(p.target.air_f, p.target.mass_f) for p in group])
        vent = np.asarray([p.origin.vent_open for p in group])
        indoor = np.asarray([p.origin.indoor_shade_closed for p in group])
        outdoor = np.asarray([[r.outdoor_f for r in p.forcings] for p in group])
        solar = np.asarray([[SOLAR_TERM_SCALE*clear_sky_fraction(r.radiation_wm2, r.at)
                            for r in p.forcings] for p in group])
        if (not np.isfinite(origins).all() or not np.isfinite(targets).all() or
                np.any(origins < OUTPUT_RANGE_F[0]) or np.any(origins > OUTPUT_RANGE_F[1]) or
                np.any(targets < OUTPUT_RANGE_F[0]) or np.any(targets > OUTPUT_RANGE_F[1])):
            raise ValueError('finite physical endpoint temperatures required')
        batches.append((origins, targets, vent, outdoor,
                        solar*indoor[:, None], solar*(1-indoor[:, None])))
    return tuple(batches)


def _objective(coefficients, batches, *, deadline=None):
    p = np.asarray(coefficients, dtype=float)
    if p.shape != (10,) or not np.isfinite(p).all():
        raise ValueError('finite ten-parameter objective vector required')
    loss = 0.; gradient = np.zeros(10); sensitivity = []
    for origins, targets, vent, weather, both, outdoor_only in batches:
        state = origins.copy(); jac = np.zeros((len(state), 2, 10))
        matrix = np.zeros((len(state), 2, 2))
        matrix[:, 0, 0] = 1-p[0]-p[1]-vent*p[4]; matrix[:, 0, 1] = p[1]
        matrix[:, 1, 0] = p[6]; matrix[:, 1, 1] = 1-p[6]-p[7]
        for step in range(weather.shape[1]):
            if deadline is not None: _check_deadline(deadline)
            air, mass = state[:, 0].copy(), state[:, 1].copy()
            outside = weather[:, step]
            direct = np.zeros((len(state), 2, 10))
            direct[:, 0, 0] = outside-air; direct[:, 0, 1] = mass-air
            direct[:, 0, 2] = both[:, step]; direct[:, 0, 3] = outdoor_only[:, step]
            direct[:, 0, 4] = vent*(outside-air); direct[:, 0, 5] = 1
            direct[:, 1, 6] = air-mass; direct[:, 1, 7] = outside-mass
            direct[:, 1, 8] = both[:, step]; direct[:, 1, 9] = outdoor_only[:, step]
            jac = matrix@jac+direct
            state[:, 0] = air+p[0]*(outside-air)+p[1]*(mass-air)+p[2]*both[:, step]+p[3]*outdoor_only[:, step]+p[4]*vent*(outside-air)+p[5]
            state[:, 1] = mass+p[6]*(air-mass)+p[7]*(outside-mass)+p[8]*both[:, step]+p[9]*outdoor_only[:, step]
            # Solver trial states are mathematical candidates, not forecasts.
            # Permit finite trial excursions so line search can recover; exact
            # physical/output guards apply to the seed and returned model.
            if not np.isfinite(state).all() or not np.isfinite(jac).all():
                raise ValueError('nonfinite development trial rollout')
        residual = state-targets
        divisor = len(state)*len(batches)
        loss += float(np.sum(residual**2))/divisor
        gradient += 2*np.einsum('ni,nij->j', residual, jac)/divisor
        sensitivity.extend(jac.reshape(-1, 10)/math.sqrt(divisor))
    if not math.isfinite(loss) or not np.isfinite(gradient).all():
        raise ValueError('nonfinite horizon objective')
    return loss, gradient, np.asarray(sensitivity)


def _conditioning(matrix):
    norms = np.linalg.norm(matrix, axis=0)
    if not np.isfinite(matrix).all() or np.any(norms == 0) or np.linalg.matrix_rank(matrix) < 10:
        raise ValueError('installed-shade horizon sensitivity rank deficient')
    normalized = matrix/norms
    rank = int(np.linalg.matrix_rank(normalized))
    condition = float(np.linalg.cond(normalized))
    if rank < 10: raise ValueError('installed-shade horizon sensitivity rank deficient')
    if not math.isfinite(condition) or condition > NORMALIZED_CONDITION_NUMBER_LIMIT:
        raise ValueError('installed-shade horizon sensitivity ill-conditioned')
    return rank, condition


def _constraints(lower, spans):
    rows = []; bounds = []
    for indoor, outdoor in ((2, 3), (8, 9)):
        row = np.zeros(10); row[outdoor] = 1; row[indoor] = -1
        rows.append(row*spans); bounds.append(SOLVER_FEASIBILITY_MARGIN-float(row@lower))
    for indexes, values in (((0, 1, 4), (-1, -1, -2)), ((6, 7), (-1, -1))):
        row = np.zeros(10)
        for index, value in zip(indexes, values): row[index] = value
        rows.append(row*spans); bounds.append(-1+STABILITY_TOLERANCE-float(row@lower))
    return [LinearConstraint(np.asarray(rows), np.asarray(bounds), np.full(len(rows), np.inf))]


def _fit_endpoints(points, *, initial, deadline):
    require_fitting_optin(); _check_deadline(deadline)
    original = InstalledShadeDynamics(initial)
    batches = _prepare_batches(points)
    for point in points:
        _check_deadline(deadline)
        original.rollout(origin_at=point.origin.at, air_f=point.origin.air_f,
                         mass_f=point.origin.mass_f, forcings=point.forcings)
    lower, spans = np.asarray(LOWER), np.asarray(UPPER)-LOWER
    initial_loss, _, initial_sensitivity = _objective(initial, batches, deadline=deadline)
    _conditioning(initial_sensitivity)
    cache = {}
    def evaluate(x):
        _check_deadline(deadline)
        key = np.asarray(x).tobytes()
        if cache.get('key') != key:
            value, gradient, sensitivity = _objective(lower+spans*x, batches, deadline=deadline)
            cache.update(key=key, value=(value, gradient*spans, sensitivity))
        return cache['value']
    result = minimize(lambda x: evaluate(x)[0], (np.asarray(initial)-lower)/spans,
        jac=lambda x: evaluate(x)[1], method='SLSQP',
        bounds=Bounds(np.zeros(10), np.ones(10)), constraints=_constraints(lower, spans),
        options={'maxiter': MULTIHORIZON_MAXITER, 'ftol': MULTIHORIZON_FTOL})
    _check_deadline(deadline)
    if not result.success or np.asarray(result.x).shape != (10,) or not np.isfinite(result.x).all():
        raise ValueError('installed-shade horizon optimizer failed')
    loss, _, sensitivity = evaluate(result.x)
    if loss > initial_loss+MULTIHORIZON_OBJECTIVE_TOLERANCE*max(1., initial_loss):
        raise ValueError('horizon optimizer worsened training objective')
    model = InstalledShadeDynamics(tuple(map(float, lower+spans*result.x)))
    rank, condition = _conditioning(sensitivity)
    # Recheck against the strict numerical core rather than trusting only the
    # vectorized optimizer implementation; this also checks every output step.
    for point in points:
        _check_deadline(deadline)
        model.rollout(origin_at=point.origin.at, air_f=point.origin.air_f,
                      mass_f=point.origin.mass_f, forcings=point.forcings)
    return EndpointFit(model, initial_loss, loss, rank, condition, int(result.nit))


def _window_days(point):
    first = point.origin.at.astimezone(DENVER).date()
    last = point.target.at.astimezone(DENVER).date()
    return {first+timedelta(days=index) for index in range((last-first).days+1)}


def _assess_stability(points, baseline, *, refitter):
    days = tuple(sorted({p.origin.at.astimezone(DENVER).date() for p in points}))
    required = BLOCK_REFIT_MIN_INDEPENDENT_DAYS
    if len(days) < required:
        return StabilityAssessment(False, len(days), required, (), None, None)
    base = np.asarray(baseline); spans = np.asarray(UPPER)-LOWER
    horizons = {len(point.forcings) for point in points}
    refits = []; worst = 0.; worst_name = None
    for group in range(BLOCK_REFIT_GROUPS):
        omitted = {day for index, day in enumerate(days) if index % BLOCK_REFIT_GROUPS == group}
        retained = tuple(p for p in points if not _window_days(p) & omitted)
        if {len(point.forcings) for point in retained} != horizons:
            raise ValueError('independent-day block loses original horizon support')
        candidate = InstalledShadeDynamics(tuple(refitter(retained))).coefficients
        fractions = np.abs(np.asarray(candidate)-base)/spans
        index = int(np.argmax(fractions)); movement = float(fractions[index])
        if not np.isfinite(fractions).all(): raise ValueError('nonfinite coefficient movement')
        if movement > worst: worst = movement; worst_name = PARAMETER_NAMES[index]
        refits.append(BlockRefit(group, tuple(day.isoformat() for day in sorted(omitted)), candidate))
    if worst > BLOCK_REFIT_MAX_BOUND_SPAN_FRACTION:
        raise ValueError('block-refit coefficient instability exceeds physical-span limit')
    return StabilityAssessment(True, len(days), required, tuple(refits), worst, worst_name)


def fit_development_inputs(record, *, expected_snapshot_sha256, sensor_epochs,
        assessed_at, training_start, training_end, initial, timeout_seconds=60):
    """Fit original training endpoints only, with a single deadline for all refits.

    The caller must enforce process CPU/memory/no-swap limits. No release or
    holdout outcomes are accepted here; the exclusive training boundary controls
    every selected origin and target. Model identity/artifacts remain separate.
    """
    require_fitting_optin()
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 90:
        raise ValueError('bounded fitting timeout required')
    deadline = time.monotonic()+timeout_seconds
    data = build_development_inputs(record, expected_snapshot_sha256=expected_snapshot_sha256,
                                   sensor_epochs=sensor_epochs, assessed_at=assessed_at)
    start, end = _utc(training_start), _utc(training_end)
    groups = tuple((hours, select_development_endpoints(data, horizon_hours=hours,
        start=start, end=end)[:MAX_ORIGINS_PER_HORIZON]) for hours in HORIZONS)
    if any(not points for _, points in groups):
        raise ValueError('training lacks required horizon endpoint/forcing support')
    points = tuple(point for _, group in groups for point in group)
    fit = _fit_endpoints(points, initial=initial, deadline=deadline)
    stability = _assess_stability(points, fit.model.coefficients,
        refitter=lambda retained: _fit_endpoints(retained,
            initial=fit.model.coefficients, deadline=deadline).model.coefficients)
    _check_deadline(deadline)
    return DevelopmentFit(fit, stability, data.source_snapshot_sha256, data.sensor_epochs,
                          start, end, tuple((hours, len(group)) for hours, group in groups),
                          tuple((hours, _nonoverlap_count(group)) for hours, group in groups))


def _nonoverlap_count(points):
    available = None; count = 0
    for point in sorted(points, key=lambda p: (p.target.at, p.origin.at)):
        if available is None or point.origin.at >= available:
            count += 1; available = point.target.at
    return count
