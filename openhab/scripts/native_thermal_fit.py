"""Bounded prior-regularized native-solar development fitting, never release."""
from collections import defaultdict
import math
import time
import numpy as np
from scipy.optimize import Bounds, minimize
from native_thermal_inputs import NativeDevelopmentData, select_native_endpoints, solar_feature_contract
from native_thermal_model import NativeInstalledShadeDynamics, normalize_forcings, RULE
from thermal_model.installed_shade_dynamics import LOWER, UPPER, STEP, _temperature
from thermal_model.installed_shade_fit import _objective, _constraints, _check_deadline, HORIZONS
from thermal_model.provisional_fit import DEFAULT_PRIOR, REGULARIZATION_STRENGTH
from thermal_model.dynamics import MAX_ORIGINS_PER_HORIZON
from thermal_model.offline_training import require_fitting_optin
from thermal_model.graduation_policy import _utc, _sha
from thermal_model.actions import DENVER

SCHEMA = 'earthship-native-solar-provisional-fit/v1'


def _points(data, start, end, guard, *, joint=False):
    if type(data) is not NativeDevelopmentData:
        raise ValueError('validated original native development dataset required')
    start, end = _utc(start), _utc(end)
    if not data.development.start <= start < end <= data.development.end:
        raise ValueError('native training interval outside original development data')
    points = []; support = {}
    for horizon in HORIZONS:
        guard(); selected = select_native_endpoints(data, horizon_hours=horizon, start=start, end=end, joint=joint)
        points.extend(selected); support[str(horizon)] = len(selected)
    if not points: raise ValueError('no original supported native development endpoints')
    if len(points) > len(HORIZONS)*MAX_ORIGINS_PER_HORIZON:
        raise ValueError('bounded native development endpoint set required')
    return tuple(points), support


def _prepare(points, data, *, deadline, guard, joint=False):
    from native_joint_shade import normalize_forcings as joint_normalize
    normalizer=joint_normalize if joint else normalize_forcings
    groups = defaultdict(list)
    def check(): guard(); _check_deadline(deadline)
    for point in points:
        check()
        if (point.dataset_sha256 != data.sha256 or point.series_sha256 != data.geometry.sha256 or
                point.source_snapshot_sha256 != data.development.source_snapshot_sha256):
            raise ValueError('native endpoint dataset/geometry/source lineage differs')
        steps = len(point.forcings)
        if not 1 <= steps <= 72*12 or point.target.at != point.origin.at + steps*STEP:
            raise ValueError('complete bounded native endpoint forcing required')
        for row in point.forcings:
            if row.indoor_shade_closed != point.origin.indoor_shade_closed or row.vent_open != point.origin.vent_open:
                raise ValueError('native endpoint origin actions were not frozen')
        normalized = normalizer(origin_at=point.origin.at, forcings=point.forcings, geometry=data.geometry, guard=check)
        groups[steps].append((point, normalized))
    batches = []
    for _, group in sorted(groups.items()):
        check()
        if len(group) > MAX_ORIGINS_PER_HORIZON: raise ValueError('native origin count exceeds horizon bound')
        origins = np.asarray([(_temperature(p.origin.air_f), _temperature(p.origin.mass_f)) for p, _ in group])
        targets = np.asarray([(_temperature(p.target.air_f), _temperature(p.target.mass_f)) for p, _ in group])
        vent = np.asarray([p.origin.vent_open for p, _ in group], dtype=float)
        outdoor = np.asarray([[row[0] for row in normalized] for _, normalized in group])
        features=tuple(np.asarray([[row[i] for row in normalized] for _, normalized in group]) for i in range(1,5 if joint else 3))
        batch = (origins, targets, vent, outdoor, *features)
        if any(not np.isfinite(array).all() for array in batch): raise ValueError('finite native endpoint arrays required')
        for array in batch: array.setflags(write=False)
        batches.append(batch)
    return tuple(batches)


def prepare_native_batches(data, *, training_start, training_end, deadline, guard, joint=False):
    guard(); _check_deadline(deadline)
    points, _ = _points(data, training_start, training_end, guard, joint=joint)
    return _prepare(points, data, deadline=deadline, guard=guard, joint=joint)


def fit_native_development(data, *, expected_dataset_sha256, training_start, training_end,
                           guard, initial=DEFAULT_PRIOR, timeout_seconds=60, joint=False):
    import native_joint_shade as j
    model_type=j.NativeJointShadeDynamics if joint else NativeInstalledShadeDynamics
    objective_function=j.objective if joint else _objective
    constraint_function=j.constraints if joint else _constraints
    low,high=(j.LOWER,j.UPPER) if joint else (LOWER,UPPER)
    count=14 if joint else 10
    if joint and len(initial)==10:initial=j.expand_installed_prior(initial)
    require_fitting_optin()
    if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or
            not 0 < timeout_seconds <= 85 or not callable(guard)):
        raise ValueError('bounded native provisional fitting contract required')
    deadline = time.monotonic() + timeout_seconds
    def check(): guard(); _check_deadline(deadline)
    check()
    if type(data) is not NativeDevelopmentData or data.sha256 != _sha(expected_dataset_sha256):
        raise ValueError('original native training dataset pin required')
    original = model_type(initial, geometry=data.geometry, expected_series_sha256=data.geometry.sha256)
    points, support = _points(data, training_start, training_end, check, joint=joint)
    batches = _prepare(points, data, deadline=deadline, guard=guard, joint=joint)
    for point in points:
        check(); original.rollout(origin_at=point.origin.at, air_f=point.origin.air_f,
            mass_f=point.origin.mass_f, forcings=point.forcings, guard=check)
    lower = np.asarray(low); spans = np.asarray(high)-lower
    x0 = (np.asarray(initial)-lower)/spans
    initial_loss, _, sensitivity = objective_function(initial, batches, deadline=deadline)
    scaled = sensitivity*spans; rank = int(np.linalg.matrix_rank(scaled))
    singular = np.linalg.svd(scaled, compute_uv=False)
    condition = float(singular[0]/singular[-1]) if rank == count else None
    def objective(x):
        check(); value, gradient, _ = objective_function(lower+spans*x, batches, deadline=deadline)
        distance = x-x0
        return value+REGULARIZATION_STRENGTH*float(distance@distance), gradient*spans+2*REGULARIZATION_STRENGTH*distance
    result = minimize(objective, x0, jac=True, method='SLSQP', bounds=Bounds(np.zeros(count), np.ones(count)),
        constraints=constraint_function(lower, spans), options={'maxiter': 300, 'ftol': 1e-9})
    check()
    if result.success is not True and result.success != np.bool_(True):
        raise ValueError('native provisional optimizer failed')
    coefficients = tuple(float(x) for x in lower+spans*result.x)
    model = model_type(coefficients, geometry=data.geometry, expected_series_sha256=data.geometry.sha256)
    final_loss, _, _ = objective_function(coefficients, batches, deadline=deadline)
    if not math.isfinite(final_loss) or final_loss > initial_loss+1e-6:
        raise ValueError('native provisional fit worsened development loss')
    for point in points:
        check(); model.rollout(origin_at=point.origin.at, air_f=point.origin.air_f,
            mass_f=point.origin.mass_f, forcings=point.forcings, guard=check)
    result=dict(schema='earthship-native-solar-provisional-fit/v2' if joint else SCHEMA, model_rule=j.RULE if joint else RULE, solar_feature=solar_feature_contract(),
        dataset_sha256=data.sha256, geometry_series_sha256=data.geometry.sha256,
        source_snapshot_sha256=data.development.source_snapshot_sha256, sensor_epochs=dict(data.development.sensor_epochs),
        training_start=_utc(training_start).isoformat(), training_end=_utc(training_end).isoformat(),
        mode='provisional', confidence='low', coefficients=list(model.coefficients), initial_coefficients=list(original.coefficients),
        initial_objective=float(initial_loss), final_objective=float(final_loss), regularization_strength=REGULARIZATION_STRENGTH,
        conditioning_rank=rank, normalized_condition_number=condition, iterations=int(result.nit), endpoint_count=len(points),
        horizon_support=support, independent_origin_dates=len({p.origin.at.astimezone(DENVER).date() for p in points}),
        fit_executed=True, stability_assessed=False, graduated=False, prediction_intervals=None,
        as_issued_forecast=False, release_authorized=False, automatic_actuation=False)
    if joint:result.update(shade_context=j.shade_contract(),regime_support=j.regime_support(data,points,start=training_start,end=training_end))
    return result
