"""Pure fitting and simulation for the two-state Earthship thermal model."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
import math

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, lsq_linear, minimize

from .schema import DynamicsModel


STEP = timedelta(minutes=5)
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
    [np.inf, np.inf, np.inf, np.inf, np.inf, np.inf],
)
OUTPUT_RANGE_F = (-40.0, 140.0)
MAX_VENT_FORCING = 2.0
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
class EvaluationDynamicsFit:
    """Fold-only fit plus action features absent from its training window."""

    dynamics: DynamicsModel
    inactive_forcing_features: tuple[str, ...]


def _value(row, name):
    if isinstance(row, Mapping):
        return row.get(name)
    return getattr(row, name)


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
    return (
        radiation * unshaded,
        radiation * indoor_closed,
        radiation * outdoor_shaded,
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


def _selection(samples):
    ordered = tuple(samples)
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
    glazing_design, _ = _glazing_rows(selected)
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
    return selected, diagnostics


def _selected_pairs(samples):
    return _selection(samples)[0]


def fit_diagnostics(samples):
    """Report deterministic row selection and action-label coverage."""
    return _selection(samples)[1]


def _solar_order_constraints(names, scale):
    if "solar_unshaded" not in names:
        return ()
    unshaded = names.index("solar_unshaded")
    rows = []
    for shaded_name in ("solar_indoor_closed", "solar_outdoor"):
        if shaded_name not in names:
            continue
        row = np.zeros(len(names), dtype=float)
        row[unshaded] = 1.0 / scale[unshaded]
        shaded = names.index(shaded_name)
        row[shaded] = -1.0 / scale[shaded]
        rows.append(row)
    if not rows:
        return ()
    matrix = np.asarray(rows, dtype=float)
    return (
        LinearConstraint(
            matrix,
            np.full(len(rows), SOLVER_FEASIBILITY_MARGIN),
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
        gains = {
            name: coefficients[names.index(name)]
            for name in (
                "solar_unshaded",
                "solar_indoor_closed",
                "solar_outdoor",
            )
            if name in names
        }
        if any(
            gains["solar_unshaded"] < gains[name]
            for name in ("solar_indoor_closed", "solar_outdoor")
            if name in gains
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


def _fit_dynamics(samples, *, allow_inactive_action_forcing):
    pairs = _selected_pairs(samples)
    air_design = []
    air_target = []
    mass_design = []
    mass_target = []
    glazing_design, glazing_target = _glazing_rows(pairs)
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


def fit_dynamics(samples):
    """Fit the strict full-evidence artifact dynamics."""
    return _fit_dynamics(
        samples, allow_inactive_action_forcing=False
    )[0]


def fit_dynamics_for_evaluation(samples):
    """Fit a fold while tracking action forcing absent from its history."""
    model, inactive = _fit_dynamics(
        samples, allow_inactive_action_forcing=True
    )
    return EvaluationDynamicsFit(
        dynamics=model, inactive_forcing_features=inactive
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
        row = {
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
