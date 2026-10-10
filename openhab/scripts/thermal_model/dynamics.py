"""Pure fitting and simulation for the two-state Earthship thermal model."""

from collections import deque
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, lsq_linear, minimize

from .schema import DynamicsModel
from .solar import clear_sky_fraction


_condition_capture = ContextVar("thermal_fit_condition_capture", default=None)


STEP = timedelta(minutes=5)
SITE_TIMEZONE = ZoneInfo("America/Denver")
IDENTIFICATION_HORIZON_STEPS = (1, 12, 72, 144, 288)
MAX_ORIGINS_PER_HORIZON = 64
MULTIHORIZON_FTOL = 1e-10
MULTIHORIZON_MAXITER = 500
MULTIHORIZON_OBJECTIVE_TOLERANCE = 1e-9
AIR_NAMES = (
    "outside_exchange",
    "mass_exchange",
    "solar_unshaded",
    "solar_indoor_closed",
    "solar_outdoor",
    "vent_exchange",
    "bias",
)
MASS_NAMES = (
    "air_exchange",
    "outside_exchange",
    "solar_unshaded",
    "solar_indoor_closed",
    "solar_outdoor",
)
NORMALIZED_CONDITION_NUMBER_LIMIT = 1.0 / math.sqrt(np.finfo(float).eps)
BLOCK_REFIT_GROUPS = 4
BLOCK_REFIT_MIN_INDEPENDENT_DAYS = 2 * (len(AIR_NAMES) + len(MASS_NAMES))
BLOCK_REFIT_MAX_BOUND_SPAN_FRACTION = 0.25
GLAZING_NAMES = (
    "intercept",
    "air",
    "outdoor",
    "solar_unshaded",
    "solar_indoor_closed",
    "solar_outdoor",
)
AIR_BOUNDS = (
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.20],
    [0.50, 0.50, 0.020, 0.010, 0.015, 0.80, 0.20],
)
MASS_BOUNDS = (
    [0.0, 0.0, 0.0, 0.0, 0.0],
    [0.20, 0.20, 0.008, 0.004, 0.006],
)
GLAZING_BOUNDS = (
    [-np.inf, -np.inf, -np.inf, 0.0, 0.0, 0.0],
    [np.inf, np.inf, np.inf, 0.012, 0.003, np.inf],
)
OUTPUT_RANGE_F = (-40.0, 140.0)
MAX_VENT_FORCING = 2.0
# Clear-sky-normalized solar terms live on [0, ~1.3]; scale to ~1000 W/m2
# equivalent magnitude so existing coefficient bounds keep physical meaning.
SOLAR_TERM_SCALE = 1000.0
VENT_FORCING_LEVELS = (
    ("closed", 0.0),
    ("baseline", 1.0),
    ("boosted", MAX_VENT_FORCING),
)
# Reject eigenvalues numerically indistinguishable from the unit circle.
STABILITY_TOLERANCE = 1e-9
SOLVER_FEASIBILITY_MARGIN = 1e-12
ENVELOPE_MAX_RADIATION_WM2 = 20.0
ENVELOPE_NAMES = ("outside_exchange", "mass_exchange", "bias")
ENVELOPE_BOUNDS = (
    [AIR_BOUNDS[0][0], AIR_BOUNDS[0][1], AIR_BOUNDS[0][6]],
    [AIR_BOUNDS[1][0], AIR_BOUNDS[1][1], AIR_BOUNDS[1][6]],
)


@dataclass(frozen=True)
class RolloutEndpoint:
    """One training-only open-loop endpoint and its complete forcing prefix."""

    origin: object
    forcings: tuple
    target: object
    confidence: float


def _uniform_origin_indices(count, limit=MAX_ORIGINS_PER_HORIZON):
    if count < 0 or limit < 2:
        raise ValueError("origin count and limit are invalid")
    if count <= limit:
        return tuple(range(count))
    return tuple(
        index * (count - 1) // (limit - 1)
        for index in range(limit)
    )


def _valid_rollout_row(row):
    at = _value(row, "at")
    if at is None or at.utcoffset() is None:
        return False
    if _value(row, "mode") not in {"spring", "warm", "fall_charge", "winter"}:
        return False
    if not bool(_value(row, "passive_fit_allowed")):
        return False
    for name in ("air_f", "mass_f", "outdoor_f", "radiation_wm2"):
        value = _value(row, name)
        if value is None or not math.isfinite(float(value)):
            return False
    confidence = _value(row, "action_confidence")
    if confidence is None or not math.isfinite(float(confidence)):
        return False
    if not 0.0 <= float(confidence) <= 1.0:
        return False
    vent = _value(row, "vent_open")
    indoor = _value(row, "indoor_shade_closed")
    outdoor = _value(row, "outdoor_shade_present")
    if any(value is None for value in (vent, indoor, outdoor)):
        return False
    if not math.isfinite(float(vent)) or not 0.0 <= float(vent) <= MAX_VENT_FORCING:
        return False
    for value in (indoor, outdoor):
        if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
            return False
    return True


def _inactive_forcing_is_safe(row, inactive_features):
    features = evaluation_forcing_features(row)
    return all(features[name] == 0.0 for name in inactive_features)


def _prepare_endpoint_rows(samples, inactive_features):
    """Validate and derive horizon-independent endpoint inputs once."""
    ordered = tuple(sorted(samples, key=lambda row: row.at))
    for row in ordered:
        _reject_split_airflow(row)
    if len({row.at for row in ordered}) != len(ordered):
        raise ValueError("duplicate thermal sample timestamp")
    inactive = tuple(inactive_features)
    unknown = set(inactive) - {
        "solar_unshaded",
        "solar_indoor_closed",
        "solar_outdoor",
        "vent_exchange",
    }
    if unknown:
        raise ValueError("unknown inactive forcing feature")

    valid_rows = tuple(_valid_rollout_row(row) for row in ordered)
    forcing_safe = tuple(
        valid and _inactive_forcing_is_safe(row, inactive)
        for row, valid in zip(ordered, valid_rows)
    )
    confidences = [
        float(row.action_confidence) if valid else math.inf
        for row, valid in zip(ordered, valid_rows)
    ]
    return ordered, valid_rows, forcing_safe, confidences


def _eligible_daily_endpoints_from_prepared(prepared, horizon_steps):
    if horizon_steps < 1:
        raise ValueError("identification horizon must be positive")
    ordered, valid_rows, forcing_safe, confidences = prepared
    run_lengths = [0] * len(ordered)
    for index in range(len(ordered) - 2, -1, -1):
        if (
            ordered[index + 1].at - ordered[index].at == STEP
            and forcing_safe[index + 1]
        ):
            run_lengths[index] = 1 + run_lengths[index + 1]

    # Every eligible prefix uses the minimum confidence of its next
    # horizon_steps rows. Compute those overlapping minima once, rather than
    # rescanning up to 288 rows for every candidate origin.
    confidence_window = deque()
    prefix_minimum = [None] * len(ordered)
    for end_index in range(1, len(ordered)):
        start_index = end_index - horizon_steps + 1
        while confidence_window and confidence_window[0] < start_index:
            confidence_window.popleft()
        while (confidence_window
               and confidences[end_index] <= confidences[confidence_window[-1]]):
            confidence_window.pop()
        confidence_window.append(end_index)
        if end_index >= horizon_steps:
            prefix_minimum[end_index - horizon_steps] = confidences[confidence_window[0]]

    best_by_day = {}
    for origin_index, origin in enumerate(ordered):
        if not valid_rows[origin_index]:
            continue
        run_length = run_lengths[origin_index]
        if run_length < horizon_steps:
            continue
        local_day = origin.at.astimezone(SITE_TIMEZONE).date()
        current = best_by_day.get(local_day)
        candidate_key = (-run_length, origin.at)
        if current is None or candidate_key < current[0]:
            best_by_day[local_day] = (candidate_key, origin_index)

    # Validation and daily ranking are complete. Materialize only the retained
    # prefixes, not every eligible timestamp that will immediately be discarded.
    endpoints = []
    for _, origin_index in sorted(best_by_day.values(), key=lambda value: ordered[value[1]].at):
        forcings = ordered[origin_index + 1:origin_index + horizon_steps + 1]
        endpoints.append(RolloutEndpoint(
            origin=ordered[origin_index],
            forcings=forcings,
            target=forcings[-1],
            confidence=prefix_minimum[origin_index],
        ))
    return tuple(endpoints)


def _eligible_daily_endpoints(samples, horizon_steps, inactive_features=()):
    if horizon_steps < 1:
        raise ValueError("identification horizon must be positive")
    return _eligible_daily_endpoints_from_prepared(
        _prepare_endpoint_rows(samples, inactive_features), horizon_steps
    )


def _select_multihorizon_endpoints(samples, inactive_features=()):
    prepared = _prepare_endpoint_rows(samples, inactive_features)
    selected = {}
    for steps in IDENTIFICATION_HORIZON_STEPS:
        eligible = _eligible_daily_endpoints_from_prepared(prepared, steps)
        indices = _uniform_origin_indices(
            len(eligible), MAX_ORIGINS_PER_HORIZON
        )
        selected[steps] = tuple(eligible[index] for index in indices)
    return selected


def _identification_origin_counts(endpoints):
    return {
        str(steps * 5): len(endpoints[steps])
        for steps in IDENTIFICATION_HORIZON_STEPS
    }


@dataclass(frozen=True)
class BlockRefitStabilityEvidence:
    """Independent-day support and movement for the strict initializer refits."""

    assessed: bool
    independent_days: int
    required_days: int
    refit_count: int
    max_bound_span_fraction: float | None
    worst_coefficient: str | None


@dataclass(frozen=True)
class BlockRefitCoefficientEvidence:
    """The actual optimized coefficients from one deterministic omitted block."""

    group: int
    omitted_days: tuple[str, ...]
    coefficients: tuple[float, ...]


@dataclass(frozen=True)
class ConditioningEvidence:
    """One actual normalized design/sensitivity check from a qualification fit."""

    stage: str
    label: str
    row_count: int
    column_count: int
    condition_number: float


@dataclass(frozen=True)
class MultihorizonEvidence:
    """Exact bounded evidence for one multihorizon refinement."""

    origin_counts: tuple[tuple[str, int], ...]
    initial_objective: float
    final_objective: float
    block_refit_stability: BlockRefitStabilityEvidence | None = None
    conditioning: tuple[ConditioningEvidence, ...] | None = None
    graduation_block_refit_stability: BlockRefitStabilityEvidence | None = None
    graduation_block_refits: tuple[BlockRefitCoefficientEvidence, ...] | None = None


@dataclass(frozen=True)
class MultihorizonDynamicsFit:
    """Refined dynamics plus inactive features and fit evidence."""

    dynamics: DynamicsModel
    inactive_forcing_features: tuple[str, ...]
    evidence: MultihorizonEvidence


@dataclass(frozen=True)
class EvaluationDynamicsFit:
    """Fold-only fit plus action features absent from its training window."""

    dynamics: DynamicsModel
    inactive_forcing_features: tuple[str, ...]
    evidence: MultihorizonEvidence


def _value(row, name):
    if isinstance(row, Mapping):
        return row.get(name)
    return getattr(row, name)


def _reject_split_airflow(row):
    version = row.get('airflow_vocabulary_version') if isinstance(row, Mapping) \
        else getattr(row, 'airflow_vocabulary_version', None)
    separate_fields = any(name in row for name in ('window_open', 'skylight_open')) \
        if isinstance(row, Mapping) else any(hasattr(row, name) for name in ('window_open', 'skylight_open'))
    if version is not None or separate_fields:
        raise ValueError('split-airflow inputs require the v2 dynamics path')


def _vent_forcing(row):
    value = _value(row, "vent_open")
    if value is None:
        raise ValueError("vent action state must be known")
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("vent forcing must be finite and nonnegative")
    if value > MAX_VENT_FORCING:
        raise ValueError(f"vent forcing must not exceed {MAX_VENT_FORCING}")
    return value


def _solar_terms(row):
    indoor = _value(row, "indoor_shade_closed")
    outdoor = _value(row, "outdoor_shade_present")
    if indoor is None or outdoor is None:
        raise ValueError("shade action states must be known")
    unshaded = (1.0 - indoor) * (1.0 - outdoor)
    indoor_closed = indoor
    outdoor_shaded = (1.0 - indoor) * outdoor
    radiation = _value(row, "radiation_wm2")
    at = _value(row, "at")
    if at is None:
        raise ValueError("solar forcing requires a timezone-aware timestamp")
    normalized = clear_sky_fraction(radiation, at)
    return (
        SOLAR_TERM_SCALE * normalized * unshaded,
        SOLAR_TERM_SCALE * normalized * indoor_closed,
        SOLAR_TERM_SCALE * normalized * outdoor_shaded,
    )


def _valid_glazing(sample):
    value = sample.glazing_f
    return value is not None and math.isfinite(value)


def _weight(sample):
    confidence = float(sample.action_confidence)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError("action confidence must be finite and within [0, 1]")
    return math.sqrt(confidence)


def _glazing_rows(pairs):
    design = []
    target = []
    for _, right in pairs:
        if not _valid_glazing(right):
            continue
        solar = _solar_terms(right)
        weight = _weight(right)
        design.append(
            np.asarray((1.0, right.air_f, right.outdoor_f, *solar)) * weight
        )
        target.append(right.glazing_f * weight)
    return design, target


def _full_rank(design, names):
    if len(design) < len(names):
        return False
    matrix = np.asarray(design, dtype=float)
    return np.isfinite(matrix).all() and np.linalg.matrix_rank(matrix) == len(names)


def _normalized_design_condition_number(matrix):
    """Condition number after column scaling; dense row count is not evidence."""
    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or not values.size or not np.isfinite(values).all():
        raise ValueError("design matrix must be finite and two-dimensional")
    norms = np.linalg.norm(values, axis=0)
    if not np.isfinite(norms).all() or np.any(norms == 0.0):
        return math.inf
    singular = np.linalg.svd(values / norms, compute_uv=False)
    if (
        singular.ndim != 1
        or len(singular) != values.shape[1]
        or not np.isfinite(singular).all()
        or singular[-1] <= 0.0
    ):
        return math.inf
    return float(singular[0] / singular[-1])


def _require_well_conditioned(matrix, label):
    condition = _normalized_design_condition_number(matrix)
    if (
        not math.isfinite(condition)
        or condition > NORMALIZED_CONDITION_NUMBER_LIMIT
    ):
        raise ValueError(
            f"{label} is ill-conditioned after column normalization "
            f"(condition={condition:.6g})"
        )
    capture = _condition_capture.get()
    if capture is not None:
        stage, measurements, _ = capture
        values = np.asarray(matrix)
        measurements.append(ConditioningEvidence(
            stage=stage, label=label, row_count=values.shape[0],
            column_count=values.shape[1], condition_number=condition,
        ))
    return condition


def _set_condition_stage(stage):
    capture = _condition_capture.get()
    if capture is not None:
        _condition_capture.set((stage, capture[1], capture[2]))


def _selection_with_glazing(samples):
    """Select and validate once; retain auxiliary rows for this fit only."""
    ordered = tuple(samples)
    for row in ordered:
        _reject_split_airflow(row)
    selected = []
    total = 0
    excluded_passive = 0
    excluded_unknown = 0
    for left, right in zip(ordered, ordered[1:]):
        if right.at - left.at != STEP:
            continue
        total += 1
        if not left.passive_fit_allowed or not right.passive_fit_allowed:
            excluded_passive += 1
            continue
        actions = (
            right.vent_open,
            right.indoor_shade_closed,
            right.outdoor_shade_present,
        )
        if any(value is None for value in actions):
            excluded_unknown += 1
            continue
        selected.append((left, right))
    glazing_design, glazing_target = _glazing_rows(selected)
    auxiliary_fitted = (
        len(glazing_design) if _full_rank(glazing_design, GLAZING_NAMES) else 0
    )
    envelope_pairs = sum(
        _vent_forcing(right) == 0.0
        and float(right.radiation_wm2) <= ENVELOPE_MAX_RADIATION_WM2
        for _, right in selected
    )
    living_office_deltas = tuple(
        abs(float(sample.living_office_f) - float(sample.air_f))
        for sample in ordered
        if sample.living_office_f is not None
        and math.isfinite(float(sample.living_office_f))
    )
    diagnostics = {
        "total_consecutive_pairs": total,
        "fitted_pairs": len(selected),
        "excluded_passive_pairs": excluded_passive,
        "excluded_unknown_action_pairs": excluded_unknown,
        "auxiliary_glazing_fitted_rows": auxiliary_fitted,
        "auxiliary_glazing_skipped_rows": len(selected) - auxiliary_fitted,
        "envelope_identification_pairs": envelope_pairs,
        "auxiliary_living_office_observation_rows": len(living_office_deltas),
        "auxiliary_living_office_hallway_mae_f": (
            sum(living_office_deltas) / len(living_office_deltas)
            if living_office_deltas
            else None
        ),
        "action_label_coverage_fraction": len(selected) / total if total else 0.0,
    }
    return selected, diagnostics, glazing_design, glazing_target


def _selection(samples):
    selected, diagnostics, _, _ = _selection_with_glazing(samples)
    return selected, diagnostics


def _selected_pairs(samples):
    return _selection(samples)[0]


def fit_diagnostics(samples):
    """Report deterministic row selection and action-label coverage."""
    return _selection(samples)[1]


def _solar_gain_pairs(names):
    pairs = [('solar_unshaded', 'solar_indoor_closed'), ('solar_unshaded', 'solar_outdoor')]
    if 'solar_both_closed' in names:
        pairs.extend((name, 'solar_both_closed') for name in ('solar_indoor_closed', 'solar_outdoor'))
    return tuple((high, low) for high, low in pairs if high in names and low in names)


def _solar_order_constraints(names, scale):
    rows = []
    margins = []
    for high, low in _solar_gain_pairs(names):
        row = np.zeros(len(names), dtype=float)
        row[names.index(high)] = 1.0 / scale[names.index(high)]
        row[names.index(low)] = -1.0 / scale[names.index(low)]
        rows.append(row)
        margins.append(0.0 if low == 'solar_both_closed' else SOLVER_FEASIBILITY_MARGIN)
    if not rows:
        return ()
    matrix = np.asarray(rows, dtype=float)
    return (
        LinearConstraint(
            matrix,
            np.asarray(margins),
            np.full(len(rows), np.inf),
        ),
    )


def _fit(design, target, bounds, names, *, ordered_solar=False):
    if len(design) < len(names):
        raise ValueError(f"insufficient fitted pairs for {len(names)} coefficients")
    matrix = np.asarray(design, dtype=float)
    values = np.asarray(target, dtype=float)
    if not np.isfinite(matrix).all() or not np.isfinite(values).all():
        raise ValueError("fit inputs must be finite")
    if np.linalg.matrix_rank(matrix) < len(names):
        raise ValueError("fit design is rank deficient")
    _require_well_conditioned(matrix, "fit design")
    result = lsq_linear(matrix, values, bounds=bounds, method="trf", lsmr_tol="auto")
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError("bounded least-squares fit failed")
    coefficients = result.x
    if ordered_solar:
        lower = np.asarray(bounds[0], dtype=float)
        upper = np.asarray(bounds[1], dtype=float)
        initial = np.clip(coefficients, lower, upper)
        unshaded = names.index("solar_unshaded")
        initial[unshaded] = max(
            initial[names.index(name)]
            for name in (
                "solar_unshaded",
                "solar_indoor_closed",
                "solar_outdoor",
            )
            if name in names
        )
        if 'solar_both_closed' in names:
            initial[names.index('solar_both_closed')] = min(
                initial[names.index(name)] for name in
                ('solar_both_closed', 'solar_indoor_closed', 'solar_outdoor') if name in names)
        scale = np.linalg.norm(matrix, axis=0)
        scaled_matrix = matrix / scale
        scaled_initial = initial * scale
        scaled_lower = lower * scale
        scaled_upper = upper * scale

        def objective(candidate):
            residual = scaled_matrix @ candidate - values
            return 0.5 * float(residual @ residual)

        def gradient(candidate):
            return scaled_matrix.T @ (scaled_matrix @ candidate - values)

        result = minimize(
            objective,
            scaled_initial,
            method="SLSQP",
            jac=gradient,
            bounds=Bounds(scaled_lower, scaled_upper),
            constraints=_solar_order_constraints(names, scale),
            options={"ftol": 1e-12, "maxiter": 2000},
        )
        coefficients = result.x / scale
        if not result.success or not np.isfinite(coefficients).all():
            raise ValueError("constrained least-squares fit failed")
        if np.any(coefficients < lower) or np.any(coefficients > upper):
            raise ValueError("constrained least-squares fit violated bounds")
        if any(
            coefficients[names.index(high)] < coefficients[names.index(low)]
            for high, low in _solar_gain_pairs(names)
        ):
            raise ValueError("constrained least-squares fit violated solar order")
    return dict(zip(names, (float(value) for value in coefficients)))


def _fit_envelope_exchange(pairs):
    design = []
    target = []
    for left, right in pairs:
        if (
            _vent_forcing(right) != 0.0
            or float(right.radiation_wm2) > ENVELOPE_MAX_RADIATION_WM2
        ):
            continue
        weight = _weight(right)
        design.append(
            np.asarray(
                (
                    right.outdoor_f - left.air_f,
                    left.mass_f - left.air_f,
                    1.0,
                )
            )
            * weight
        )
        target.append((right.air_f - left.air_f) * weight)
    if len(design) < len(ENVELOPE_NAMES):
        raise ValueError("insufficient closed low-radiation envelope evidence")
    try:
        coefficients = _fit(
            design, target, ENVELOPE_BOUNDS, ENVELOPE_NAMES
        )
    except ValueError as exc:
        raise ValueError(
            f"closed low-radiation envelope evidence is invalid: {exc}"
        ) from exc
    return coefficients["outside_exchange"], len(design)


def _fit_with_inactive_action_columns(
    design, target, bounds, names, allowed_inactive
):
    """Fit a fold after removing only action columns that are exactly zero."""
    if not design:
        return _fit(design, target, bounds, names, ordered_solar=True), ()
    matrix = np.asarray(design, dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError("fit inputs must be finite")
    inactive = tuple(
        name
        for index, name in enumerate(names)
        if np.all(matrix[:, index] == 0.0)
    )
    if not inactive:
        return (
            _fit(
                design, target, bounds, names, ordered_solar=True
            ),
            (),
        )
    if any(name not in allowed_inactive for name in inactive):
        raise ValueError("fit design is rank deficient")
    active_indices = tuple(
        index for index, name in enumerate(names) if name not in inactive
    )
    active_names = tuple(names[index] for index in active_indices)
    active_design = matrix[:, active_indices]
    active_bounds = (
        [bounds[0][index] for index in active_indices],
        [bounds[1][index] for index in active_indices],
    )
    fitted = _fit(
        active_design,
        target,
        active_bounds,
        active_names,
        ordered_solar=True,
    )
    completed = {name: 0.0 for name in names}
    completed.update(fitted)
    return completed, inactive


def _fit_five_minute_dynamics(samples, *, allow_inactive_action_forcing):
    pairs, _, glazing_design, glazing_target = _selection_with_glazing(samples)
    air_design = []
    air_target = []
    mass_design = []
    mass_target = []
    outside_exchange, _ = _fit_envelope_exchange(pairs)
    if outside_exchange <= 0.0:
        raise ValueError("positive envelope exchange was not identified")

    for left, right in pairs:
        solar = _solar_terms(right)
        weight = _weight(right)
        air_design.append(
            np.asarray(
                (
                    left.mass_f - left.air_f,
                    *solar,
                    _vent_forcing(right) * (right.outdoor_f - left.air_f),
                    1.0,
                )
            )
            * weight
        )
        air_target.append(
            (
                right.air_f
                - left.air_f
                - outside_exchange * (right.outdoor_f - left.air_f)
            )
            * weight
        )
        mass_design.append(
            np.asarray((
                left.air_f - left.mass_f,
                right.outdoor_f - left.mass_f,
                *solar,
            )) * weight
        )
        mass_target.append((right.mass_f - left.mass_f) * weight)

    if allow_inactive_action_forcing:
        air_fit, air_inactive = _fit_with_inactive_action_columns(
            air_design,
            air_target,
            (AIR_BOUNDS[0][1:], AIR_BOUNDS[1][1:]),
            AIR_NAMES[1:],
            frozenset({"solar_outdoor", "vent_exchange"}),
        )
        mass, mass_inactive = _fit_with_inactive_action_columns(
            mass_design,
            mass_target,
            MASS_BOUNDS,
            MASS_NAMES,
            frozenset({"solar_outdoor"}),
        )
    else:
        air_fit = _fit(
            air_design,
            air_target,
            (AIR_BOUNDS[0][1:], AIR_BOUNDS[1][1:]),
            AIR_NAMES[1:],
            ordered_solar=True,
        )
        mass = _fit(
            mass_design, mass_target, MASS_BOUNDS, MASS_NAMES, ordered_solar=True
        )
        air_inactive = ()
        mass_inactive = ()

    air = {"outside_exchange": outside_exchange, **air_fit}
    glazing = (
        _fit(
            glazing_design,
            glazing_target,
            GLAZING_BOUNDS,
            GLAZING_NAMES,
            ordered_solar=True,
        )
        if _full_rank(glazing_design, GLAZING_NAMES)
        else {}
    )
    model = DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients=air,
        mass_coefficients=mass,
        glazing_observation_coefficients=glazing,
    )
    validate_physics(model)
    inactive = tuple(
        name
        for name in ("solar_outdoor", "vent_exchange")
        if name in set(air_inactive) | set(mass_inactive)
    )
    return model, inactive


def _coefficient_vector(model):
    vector = np.asarray(
        [
            *(model.air_coefficients[name] for name in AIR_NAMES),
            *(model.mass_coefficients[name] for name in MASS_NAMES),
        ],
        dtype=float,
    )
    if vector.shape != (len(AIR_NAMES) + len(MASS_NAMES),):
        raise ValueError("multihorizon coefficient vector has invalid shape")
    if not np.isfinite(vector).all():
        raise ValueError("multihorizon coefficient vector must be finite")
    return vector


def _coefficient_bound_spans():
    spans = np.asarray(
        AIR_BOUNDS[1] + MASS_BOUNDS[1], dtype=float
    ) - np.asarray(AIR_BOUNDS[0] + MASS_BOUNDS[0], dtype=float)
    if (
        spans.shape != (len(AIR_NAMES) + len(MASS_NAMES),)
        or not np.isfinite(spans).all()
        or np.any(spans <= 0.0)
    ):
        raise ValueError("coefficient bound spans are invalid")
    return spans


def _validate_block_refit_stability(samples, baseline, *, fitter=None):
    """Reject large coefficient movement when independent day blocks are omitted.

    This runs only for the strict artifact fit. It deliberately uses local days
    rather than five-minute rows as the resampling unit.
    """
    ordered = tuple(samples)
    fitted_pairs = _selected_pairs(ordered)
    unique_days = tuple(sorted({
        right.at.astimezone(SITE_TIMEZONE).date()
        for _, right in fitted_pairs
    }))
    if len(unique_days) < BLOCK_REFIT_MIN_INDEPENDENT_DAYS:
        return {
            "assessed": False,
            "independent_days": len(unique_days),
            "required_days": BLOCK_REFIT_MIN_INDEPENDENT_DAYS,
            "refit_count": 0,
            "max_bound_span_fraction": None,
            "worst_coefficient": None,
        }

    base = _coefficient_vector(baseline)
    spans = _coefficient_bound_spans()
    names = AIR_NAMES + MASS_NAMES
    refit = fitter or (
        lambda rows: _fit_five_minute_dynamics(
            rows, allow_inactive_action_forcing=False
        )[0]
    )
    worst_fraction = 0.0
    worst_name = None
    refit_count = 0
    for group in range(BLOCK_REFIT_GROUPS):
        withheld = {
            day for index, day in enumerate(unique_days)
            if index % BLOCK_REFIT_GROUPS == group
        }
        retained = tuple(
            row for row in ordered
            if row.at.astimezone(SITE_TIMEZONE).date() not in withheld
        )
        try:
            candidate = _coefficient_vector(refit(retained))
        except ValueError as exc:
            raise ValueError(
                f"block-refit stability fit failed for group {group}: {exc}"
            ) from exc
        capture = _condition_capture.get()
        if capture is not None and capture[0] == "graduation_block_refit":
            capture[2].append(BlockRefitCoefficientEvidence(
                group=group, omitted_days=tuple(day.isoformat() for day in sorted(withheld)),
                coefficients=tuple(map(float, candidate)),
            ))
        fractions = np.abs(candidate - base) / spans
        if not np.isfinite(fractions).all():
            raise ValueError("block-refit stability produced non-finite movement")
        index = int(np.argmax(fractions))
        fraction = float(fractions[index])
        refit_count += 1
        if fraction > worst_fraction:
            worst_fraction = fraction
            worst_name = names[index]

    if worst_fraction > BLOCK_REFIT_MAX_BOUND_SPAN_FRACTION:
        raise ValueError(
            "block-refit coefficient instability exceeds allowed physical span: "
            f"{worst_name} moved {worst_fraction:.6f}"
        )
    return {
        "assessed": True,
        "independent_days": len(unique_days),
        "required_days": BLOCK_REFIT_MIN_INDEPENDENT_DAYS,
        "refit_count": refit_count,
        "max_bound_span_fraction": worst_fraction,
        "worst_coefficient": worst_name,
    }


def _model_from_vector(vector, glazing):
    values = np.asarray(vector, dtype=float)
    expected = len(AIR_NAMES) + len(MASS_NAMES)
    if values.shape != (expected,) or not np.isfinite(values).all():
        raise ValueError("multihorizon coefficient vector is invalid")
    air_count = len(AIR_NAMES)
    return DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients={
            name: float(values[index])
            for index, name in enumerate(AIR_NAMES)
        },
        mass_coefficients={
            name: float(values[air_count + index])
            for index, name in enumerate(MASS_NAMES)
        },
        glazing_observation_coefficients=dict(glazing),
    )


def _prepare_multihorizon_forcings(endpoints):
    """Compute coefficient-independent forcing features once per fit."""
    prepared = {}
    for group in endpoints.values():
        for endpoint in group:
            for forcing in endpoint.forcings:
                key = id(forcing)
                if key not in prepared:
                    prepared[key] = (
                        float(_value(forcing, "outdoor_f")),
                        _vent_forcing(forcing),
                        _solar_terms(forcing),
                    )
    return prepared


def _prepare_multihorizon_batches(endpoints, prepared_forcings):
    """Prepare fit-local immutable rollout arrays; never cache across runs."""
    batches = []
    for steps in IDENTIFICATION_HORIZON_STEPS:
        group = tuple(endpoints.get(steps, ()))
        if not group:
            raise ValueError(
                f"insufficient multihorizon origins for {steps * 5} minutes"
            )
        if any(len(endpoint.forcings) != steps for endpoint in group):
            raise ValueError("multihorizon forcing prefix is malformed")
        forcings = []
        for endpoint in group:
            rows = []
            for forcing in endpoint.forcings:
                if prepared_forcings is None:
                    outdoor = float(_value(forcing, "outdoor_f"))
                    vent = _vent_forcing(forcing)
                    solar = _solar_terms(forcing)
                else:
                    outdoor, vent, solar = prepared_forcings[id(forcing)]
                rows.append((outdoor, vent, *solar))
            forcings.append(rows)
        origins = np.asarray(
            [(e.origin.air_f, e.origin.mass_f) for e in group], dtype=float
        )
        targets = np.asarray(
            [(e.target.air_f, e.target.mass_f) for e in group], dtype=float
        )
        confidence = np.asarray([float(e.confidence) for e in group], dtype=float)
        batches.append(
            (steps, origins, targets, confidence, np.asarray(forcings, dtype=float))
        )
    for batch in batches:
        for array in batch[1:]:
            array.setflags(write=False)
    return tuple(batches)


def _multihorizon_objective_and_gradient(
    vector, endpoints, *, sensitivity_rows=None, prepared_forcings=None,
    prepared_batches=None,
):
    """Batch independent endpoints, preserving scalar arithmetic/reduction order."""
    values = np.asarray(vector, dtype=float)
    expected = len(AIR_NAMES) + len(MASS_NAMES)
    if values.shape != (expected,) or not np.isfinite(values).all():
        raise ValueError('multihorizon objective coefficients are invalid')
    if prepared_batches is None:
        prepared_batches = _prepare_multihorizon_batches(endpoints, prepared_forcings)
    (air_outside, air_mass, air_solar_unshaded, air_solar_indoor,
     air_solar_outdoor, air_vent, air_bias, mass_air, mass_outside,
     mass_solar_unshaded, mass_solar_indoor, mass_solar_outdoor) = values
    jacobian_air_self = 1.0 - air_outside - air_mass
    jacobian_mass_self = 1.0 - mass_air - mass_outside
    loss = 0.0
    gradient = np.zeros(expected, dtype=float)
    for steps, origins, targets, confidence, forcing in prepared_batches:
        count = len(origins)
        divisor = float(count)
        state = origins.copy()
        sensitivity = np.zeros((count, 2, expected), dtype=float)
        jacobian = np.empty((count, 2, 2), dtype=float)
        jacobian[:, 0, 1] = air_mass
        jacobian[:, 1, 0] = mass_air
        jacobian[:, 1, 1] = jacobian_mass_self
        direct = np.zeros((count, 2, expected), dtype=float)
        for step in range(steps):
            (outdoor, vent, solar_unshaded, solar_indoor, solar_outdoor) = (
                forcing[:, step, index] for index in range(5)
            )
            jacobian[:, 0, 0] = jacobian_air_self - air_vent * vent
            direct[:, 0, 0] = outdoor - state[:, 0]
            direct[:, 0, 1] = state[:, 1] - state[:, 0]
            direct[:, 0, 2] = solar_unshaded
            direct[:, 0, 3] = solar_indoor
            direct[:, 0, 4] = solar_outdoor
            direct[:, 0, 5] = vent * (outdoor - state[:, 0])
            direct[:, 0, 6] = 1.0
            direct[:, 1, 7] = state[:, 0] - state[:, 1]
            direct[:, 1, 8] = outdoor - state[:, 1]
            direct[:, 1, 9] = solar_unshaded
            direct[:, 1, 10] = solar_indoor
            direct[:, 1, 11] = solar_outdoor
            next_air = (
                state[:, 0]
                + air_outside * (outdoor - state[:, 0])
                + air_mass * (state[:, 1] - state[:, 0])
                + air_solar_unshaded * solar_unshaded
                + air_solar_indoor * solar_indoor
                + air_solar_outdoor * solar_outdoor
                + air_vent * vent * (outdoor - state[:, 0])
                + air_bias
            )
            next_mass = (
                state[:, 1]
                + mass_air * (state[:, 0] - state[:, 1])
                + mass_outside * (outdoor - state[:, 1])
                + mass_solar_unshaded * solar_unshaded
                + mass_solar_indoor * solar_indoor
                + mass_solar_outdoor * solar_outdoor
            )
            sensitivity = jacobian @ sensitivity + direct
            state[:, 0], state[:, 1] = (next_air, next_mass)
            if not np.isfinite(state).all():
                raise ValueError('multihorizon rollout state or sensitivity is invalid')
        if not np.isfinite(sensitivity).all():
            raise ValueError('multihorizon rollout state or sensitivity is invalid')
        residual = state - targets
        if (
            not np.isfinite(targets).all()
            or not np.isfinite(residual).all()
            or not np.isfinite(confidence).all()
            or np.any(confidence < 0)
            or np.any(confidence > 1)
        ):
            raise ValueError('multihorizon endpoint evidence is invalid')
        # Keep the original endpoint/state accumulation order: a vectorized
        # sum would change rounding, optimizer steps and reproducible fits.
        for endpoint in range(count):
            weight = float(confidence[endpoint])
            for state_index in (0, 1):
                error = residual[endpoint, state_index]
                loss += weight * error * error / divisor
                gradient += (
                    2.0 * weight * error * sensitivity[endpoint, state_index] / divisor
                )
                if sensitivity_rows is not None:
                    sensitivity_rows.append(
                        math.sqrt(weight / divisor)
                        * sensitivity[endpoint, state_index].copy()
                    )
    if not math.isfinite(loss) or not np.isfinite(gradient).all():
        raise ValueError('multihorizon objective is non-finite')
    return float(loss), gradient


def _validate_multihorizon_rank(sensitivity_rows, active_indices, *,
                                label="multihorizon sensitivity matrix"):
    matrix = np.asarray(sensitivity_rows, dtype=float)[:, list(active_indices)]
    if not np.isfinite(matrix).all():
        raise ValueError("multihorizon sensitivity matrix is non-finite")
    column_norms = np.linalg.norm(matrix, axis=0)
    if (
        not np.isfinite(column_norms).all()
        or np.any(column_norms == 0.0)
    ):
        raise ValueError("multihorizon objective inputs are rank deficient")
    normalized = matrix / column_norms
    if np.linalg.matrix_rank(normalized) < len(active_indices):
        raise ValueError("multihorizon objective inputs are rank deficient")
    _require_well_conditioned(
        normalized, label
    )


def _multihorizon_linear_constraints(
    active_indices, initial_vector, lower_bounds, spans
):
    rows = []
    constraint_lower = []
    total = len(initial_vector)
    active_set = set(active_indices)
    fixed_indices = tuple(
        index for index in range(total) if index not in active_set
    )
    for offset, names in (
        (0, AIR_NAMES),
        (len(AIR_NAMES), MASS_NAMES),
    ):
        unshaded = offset + names.index("solar_unshaded")
        for shaded_name in ("solar_indoor_closed", "solar_outdoor"):
            shaded = offset + names.index(shaded_name)
            full_row = np.zeros(total, dtype=float)
            full_row[unshaded] = 1.0
            full_row[shaded] = -1.0
            active_row = full_row[list(active_indices)]
            rows.append(active_row * spans[list(active_indices)])
            offset_value = float(
                active_row @ lower_bounds[list(active_indices)]
            )
            if fixed_indices:
                offset_value += float(
                    full_row[list(fixed_indices)]
                    @ initial_vector[list(fixed_indices)]
                )
            constraint_lower.append(
                SOLVER_FEASIBILITY_MARGIN - offset_value
            )
    return (
        LinearConstraint(
            np.asarray(rows, dtype=float),
            np.asarray(constraint_lower, dtype=float),
            np.full(len(rows), np.inf),
        ),
    )


def _refine_multihorizon(initial, endpoints, inactive_features):
    counts = _identification_origin_counts(endpoints)
    for minutes, count in counts.items():
        if count < 2:
            raise ValueError(
                f"insufficient multihorizon origins for {minutes} minutes"
            )

    initial_vector = _coefficient_vector(initial)
    prepared_forcings = _prepare_multihorizon_forcings(endpoints)
    prepared_batches = _prepare_multihorizon_batches(endpoints, prepared_forcings)
    inactive = set(inactive_features)
    active_indices = tuple(
        index
        for index, name in enumerate(AIR_NAMES + MASS_NAMES)
        if name not in inactive
    )
    if not active_indices:
        raise ValueError("multihorizon refinement has no active coefficients")
    active = list(active_indices)
    lower = np.asarray(AIR_BOUNDS[0] + MASS_BOUNDS[0], dtype=float)
    upper = np.asarray(AIR_BOUNDS[1] + MASS_BOUNDS[1], dtype=float)
    spans = upper - lower
    if not np.isfinite(spans).all() or np.any(spans <= 0.0):
        raise ValueError("multihorizon coefficient bounds are invalid")
    initial_scaled = (
        initial_vector[active] - lower[active]
    ) / spans[active]
    sensitivity_rows = []
    initial_objective, _ = _multihorizon_objective_and_gradient(
        initial_vector, endpoints, sensitivity_rows=sensitivity_rows,
        prepared_forcings=prepared_forcings, prepared_batches=prepared_batches,
    )
    _validate_multihorizon_rank(sensitivity_rows, active_indices)
    cache = {}

    def evaluate(scaled_active):
        scaled = np.asarray(scaled_active, dtype=float)
        candidate = initial_vector.copy()
        candidate[active] = lower[active] + spans[active] * scaled
        key = candidate.tobytes()
        if key not in cache:
            loss, physical_gradient = (
                _multihorizon_objective_and_gradient(
                    candidate, endpoints, prepared_forcings=prepared_forcings,
                    prepared_batches=prepared_batches,
                )
            )
            cache[key] = (
                loss,
                physical_gradient[active] * spans[active],
                candidate,
            )
        return cache[key]

    result = minimize(
        lambda candidate: evaluate(candidate)[0],
        initial_scaled,
        method="SLSQP",
        jac=lambda candidate: evaluate(candidate)[1],
        bounds=Bounds(
            np.zeros(len(active_indices)), np.ones(len(active_indices))
        ),
        constraints=_multihorizon_linear_constraints(
            active_indices, initial_vector, lower, spans
        ),
        options={
            "ftol": MULTIHORIZON_FTOL,
            "maxiter": MULTIHORIZON_MAXITER,
        },
    )
    if (
        not result.success
        or np.asarray(result.x).shape != (len(active_indices),)
        or not np.isfinite(result.x).all()
    ):
        raise ValueError("multihorizon optimizer failed")

    final_objective, _, final_vector = evaluate(result.x)
    final_model = _model_from_vector(
        final_vector, initial.glazing_observation_coefficients
    )
    validate_physics(final_model)
    tolerance = MULTIHORIZON_OBJECTIVE_TOLERANCE * max(
        1.0, initial_objective
    )
    if final_objective > initial_objective + tolerance:
        raise ValueError("multihorizon objective increased")
    if _condition_capture.get() is not None:
        final_sensitivity_rows = []
        _multihorizon_objective_and_gradient(
            final_vector, endpoints, sensitivity_rows=final_sensitivity_rows,
            prepared_forcings=prepared_forcings, prepared_batches=prepared_batches,
        )
        _validate_multihorizon_rank(
            final_sensitivity_rows, active_indices,
            label="multihorizon final sensitivity matrix",
        )
    evidence = MultihorizonEvidence(
        origin_counts=tuple(counts.items()),
        initial_objective=float(initial_objective),
        final_objective=float(final_objective),
    )
    return MultihorizonDynamicsFit(
        dynamics=final_model,
        inactive_forcing_features=tuple(inactive_features),
        evidence=evidence,
    )


def fit_dynamics_with_evidence(
    samples, *, allow_inactive_action_forcing=False,
    collect_graduation_evidence=False,
):
    """Preserve default fitting; explicitly collect strict final-fit evidence.

    Qualification adds final sensitivity checks and full optimized independent-
    day block refits. It does not turn a shadow artifact into production.
    """
    if type(collect_graduation_evidence) is not bool:
        raise ValueError("graduation evidence request must be boolean")
    if collect_graduation_evidence and allow_inactive_action_forcing:
        raise ValueError("graduation measurements require strict full-evidence fitting")
    measurements = []
    blocks = []
    token = _condition_capture.set(
        ("initializer", measurements, blocks) if collect_graduation_evidence else None
    )
    try:
        return _fit_dynamics_with_evidence(
            tuple(samples) if collect_graduation_evidence else samples,
            allow_inactive_action_forcing=allow_inactive_action_forcing,
        )
    finally:
        _condition_capture.reset(token)


def _fit_dynamics_with_evidence(samples, *, allow_inactive_action_forcing):
    """Shared fitting body, with qualification measurements isolated by context."""
    initial, inactive = _fit_five_minute_dynamics(
        samples,
        allow_inactive_action_forcing=allow_inactive_action_forcing,
    )
    endpoints = _select_multihorizon_endpoints(samples, inactive)
    _set_condition_stage("refinement")
    refined = _refine_multihorizon(initial, endpoints, inactive)
    if not allow_inactive_action_forcing:
        _set_condition_stage("initializer_block_refit")
        assessment = BlockRefitStabilityEvidence(
            **_validate_block_refit_stability(samples, initial)
        )
        refined = replace(
            refined,
            evidence=replace(refined.evidence, block_refit_stability=assessment),
        )
    capture = _condition_capture.get()
    if capture is not None:
        _set_condition_stage("graduation_block_refit")
        def final_refit(rows):
            block_initial, block_inactive = _fit_five_minute_dynamics(
                rows, allow_inactive_action_forcing=False
            )
            if block_inactive:
                raise ValueError("graduation block refit contains inactive forcing")
            block_endpoints = _select_multihorizon_endpoints(rows, block_inactive)
            return _refine_multihorizon(
                block_initial, block_endpoints, block_inactive
            ).dynamics
        final_assessment = BlockRefitStabilityEvidence(
            **_validate_block_refit_stability(
                samples, refined.dynamics, fitter=final_refit
            )
        )
        refined = replace(refined, evidence=replace(
            refined.evidence, conditioning=tuple(capture[1]),
            graduation_block_refit_stability=final_assessment,
            graduation_block_refits=tuple(capture[2]),
        ))
    return refined


def fit_dynamics(samples):
    """Fit strict full-evidence artifact dynamics across forecast horizons."""
    return fit_dynamics_with_evidence(samples).dynamics


def fit_dynamics_for_evaluation(samples):
    """Fit one chronological fold without using held-out evidence."""
    fitted = fit_dynamics_with_evidence(
        samples, allow_inactive_action_forcing=True
    )
    return EvaluationDynamicsFit(
        dynamics=fitted.dynamics,
        inactive_forcing_features=fitted.inactive_forcing_features,
        evidence=fitted.evidence,
    )


def evaluation_forcing_features(row):
    """Return action-feature activation used to guard held-out folds."""
    solar = _solar_terms(row)
    return {
        "solar_unshaded": float(solar[0]),
        "solar_indoor_closed": float(solar[1]),
        "solar_outdoor": float(solar[2]),
        "vent_exchange": float(_vent_forcing(row)),
    }

def _checked_output(value, name):
    if not math.isfinite(value):
        raise ValueError(f"{name} prediction is non-finite")
    if not OUTPUT_RANGE_F[0] <= value <= OUTPUT_RANGE_F[1]:
        raise ValueError(f"{name} prediction is out of range")
    return float(value)


def predict_step(model, sample):
    """Return end state/observation using one explicit end-forcing row."""
    _reject_split_airflow(sample)
    air = float(_value(sample, "air_f"))
    mass = float(_value(sample, "mass_f"))
    outdoor = float(_value(sample, "outdoor_f"))
    vent = _vent_forcing(sample)
    solar = _solar_terms(sample)
    air_c = model.air_coefficients
    mass_c = model.mass_coefficients
    next_air = air + (
        air_c["outside_exchange"] * (outdoor - air)
        + air_c["mass_exchange"] * (mass - air)
        + air_c["solar_unshaded"] * solar[0]
        + air_c["solar_indoor_closed"] * solar[1]
        + air_c["solar_outdoor"] * solar[2]
        + air_c["vent_exchange"] * vent * (outdoor - air)
        + air_c["bias"]
    )
    next_mass = mass + (
        mass_c["air_exchange"] * (air - mass)
        + mass_c["outside_exchange"] * (outdoor - mass)
        + mass_c["solar_unshaded"] * solar[0]
        + mass_c["solar_indoor_closed"] * solar[1]
        + mass_c["solar_outdoor"] * solar[2]
    )
    glazing = None
    glazing_c = model.glazing_observation_coefficients
    if glazing_c:
        glazing = (
            glazing_c["intercept"]
            + glazing_c["air"] * next_air
            + glazing_c["outdoor"] * outdoor
            + glazing_c["solar_unshaded"] * solar[0]
            + glazing_c["solar_indoor_closed"] * solar[1]
            + glazing_c["solar_outdoor"] * solar[2]
        )
    return (
        _checked_output(next_air, "air"),
        _checked_output(next_mass, "mass"),
        _checked_output(glazing, "glazing") if glazing is not None else None,
    )


def simulate(model, initial, forcings):
    """Simulate explicit end-forcing rows from an explicit two-state initial value."""
    air = float(_value(initial, "air_f"))
    mass = float(_value(initial, "mass_f"))
    _checked_output(air, "initial air")
    _checked_output(mass, "initial mass")
    results = []
    for forcing in forcings:
        _reject_split_airflow(forcing)
        row = {
            "at": _value(forcing, "at"),
            "air_f": air,
            "mass_f": mass,
            "outdoor_f": _value(forcing, "outdoor_f"),
            "radiation_wm2": _value(forcing, "radiation_wm2"),
            "vent_open": _value(forcing, "vent_open"),
            "indoor_shade_closed": _value(forcing, "indoor_shade_closed"),
            "outdoor_shade_present": _value(forcing, "outdoor_shade_present"),
        }
        air, mass, glazing = predict_step(model, row)
        results.append({"air_f": air, "mass_f": mass, "glazing_f": glazing})
    return results


def _validate_gain_relationship(coefficients):
    if not coefficients:
        return
    gains = (
        coefficients["solar_unshaded"],
        coefficients["solar_indoor_closed"],
        coefficients["solar_outdoor"],
    )
    if any(gain < 0.0 for gain in gains):
        raise ValueError("solar gain coefficients must be nonnegative")
    unshaded = coefficients["solar_unshaded"]
    if (
        unshaded < coefficients["solar_indoor_closed"]
        or unshaded < coefficients["solar_outdoor"]
    ):
        raise ValueError("shade gain exceeds unshaded gain")
    if 'solar_both_closed' in coefficients:
        both = coefficients['solar_both_closed']
        if both < 0 or any(both > coefficients[name] for name in
                           ('solar_indoor_closed', 'solar_outdoor')):
            raise ValueError('joint shade gain exceeds single-shade gain')


def _transition_matrix(model, vent_forcing):
    air = model.air_coefficients
    mass = model.mass_coefficients
    return np.asarray(
        (
            (
                1.0
                - air["outside_exchange"]
                - air["mass_exchange"]
                - air["vent_exchange"] * vent_forcing,
                air["mass_exchange"],
            ),
            (
                mass["air_exchange"],
                1.0 - mass["air_exchange"] - mass["outside_exchange"],
            ),
        ),
        dtype=float,
    )


def _validate_transition_stability(model):
    for name, vent_forcing in VENT_FORCING_LEVELS:
        eigenvalues = np.linalg.eigvals(_transition_matrix(model, vent_forcing))
        spectral_radius = float(np.max(np.abs(eigenvalues)))
        if (
            not math.isfinite(spectral_radius)
            or spectral_radius >= 1.0 - STABILITY_TOLERANCE
        ):
            raise ValueError(
                "transition stability failed for "
                f"{name} ventilation: spectral radius {spectral_radius:.12g} "
                f"must be below {1.0 - STABILITY_TOLERANCE:.12g}"
            )


def validate_physics(model):
    """Reject sign, gain-order, spectral, and 72-hour violations."""
    if model.version != 2 or model.step_minutes != 5:
        raise ValueError("dynamics model must be version 2 at five-minute steps")
    for coefficients, names, bounds in (
        (model.air_coefficients, AIR_NAMES, AIR_BOUNDS),
        (model.mass_coefficients, MASS_NAMES, MASS_BOUNDS),
    ):
        if set(coefficients) != set(names):
            raise ValueError("dynamics coefficient names do not match the contract")
        if not all(math.isfinite(value) for value in coefficients.values()):
            raise ValueError("dynamics coefficients must be finite")
    if model.glazing_observation_coefficients and set(
        model.glazing_observation_coefficients
    ) != set(GLAZING_NAMES):
        raise ValueError(
            "glazing observation coefficient names do not match the contract"
        )
    exchanges = (
        model.air_coefficients["outside_exchange"],
        model.air_coefficients["mass_exchange"],
        model.air_coefficients["vent_exchange"],
        model.mass_coefficients["air_exchange"],
        model.mass_coefficients["outside_exchange"],
    )
    if any(value < 0.0 for value in exchanges):
        raise ValueError("exchange coefficients must be nonnegative")
    for coefficients in (
        model.air_coefficients,
        model.mass_coefficients,
        model.glazing_observation_coefficients,
    ):
        _validate_gain_relationship(coefficients)

    for coefficients, names, bounds in (
        (model.air_coefficients, AIR_NAMES, AIR_BOUNDS),
        (model.mass_coefficients, MASS_NAMES, MASS_BOUNDS),
    ):
        for index, name in enumerate(names):
            if not bounds[0][index] <= coefficients[name] <= bounds[1][index]:
                raise ValueError("dynamics coefficient violates declared bounds")

    _validate_transition_stability(model)
    for _, vent_forcing in VENT_FORCING_LEVELS:
        forcing = {
            "at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "outdoor_f": 70.0,
            "radiation_wm2": 0.0,
            "vent_open": vent_forcing,
            "indoor_shade_closed": 0.0,
            "outdoor_shade_present": 0.0,
        }
        simulate(
            model,
            {"air_f": 90.0, "mass_f": 50.0},
            [forcing] * (72 * 12),
        )
    return model
