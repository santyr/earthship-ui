"""Validated, race-safe local registry for reproducible thermal artifacts."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import re
import tempfile

from .behavior import AIRFLOW_LEVELS, FEATURE_NAMES, TRANSITIONS
from .dataset import (
    AUXILIARY_EXCLUSION_COUNT_KEYS,
    CORE_REJECTED_COUNT_KEYS,
    MASS_OBSERVER_TAU_MINUTES,
    MAX_HOLD_FORWARD_GAP,
    MAX_INTERPOLATION_GAP,
    MODE_COUNT_KEYS,
    RADIATION_PROVENANCE_LABELS,
    radiation_reconstruction_contract,
)
from .dynamics import (
    AIR_BOUNDS,
    AIR_NAMES,
    ENVELOPE_MAX_RADIATION_WM2,
    GLAZING_BOUNDS,
    GLAZING_NAMES,
    MASS_BOUNDS,
    MASS_NAMES,
    MAX_VENT_FORCING,
    OUTPUT_RANGE_F,
    MULTIHORIZON_OBJECTIVE_TOLERANCE,
    STABILITY_TOLERANCE,
    validate_physics,
)
from .schema import (
    BehaviorModel,
    DynamicsModel,
    SeasonalActionVocabulary,
    OPTIONAL_OBSERVATION_ITEMS,
    SOURCE_WEIGHTS,
    THERMAL_ITEMS,
    ThermalArtifact,
)

MODEL_SCHEMA = "earthship-thermal-model/v4"
MULTIHORIZON_CONTRACT = {
    "horizons_minutes": [5, 60, 360, 720, 1440],
    "daily_origin_selector": "longest_valid_future_then_earliest_utc",
    "max_origins_per_horizon": 64,
    "bounded_index_rule": "floor(i*(count-1)/63), i=0..63",
    "confidence_rule": "minimum_aggregate_action_confidence_over_prefix",
    "objective": "equal_air_mass_confidence_weighted_group_mse",
    "optimizer": {
        "method": "SLSQP",
        "ftol": 1e-10,
        "maxiter": 500,
        "random_restarts": 0,
        "gradient": "analytic_forward_sensitivity",
        "objective_regression_relative_tolerance": 1e-9,
    },
}
BACKTEST_SCHEMA = "earthship-thermal-backtest/v2"
MIN_SCORED_24H_FOLDS = 30
MIN_REGIME_24H_FOLDS = 5
MIN_24H_REGIMES = 2
THERMAL_UNITS = {
    "air": "F",
    "mass": "F",
    "glazing": "F",
    "outdoor": "F",
    "radiation": "W/m2",
    "living_office": "F",
}
MODEL_ITEMS = {**THERMAL_ITEMS, **OPTIONAL_OBSERVATION_ITEMS}
DEFAULT_STATE_DIRECTORY = Path("~/.local/state/thermal-intel/models").expanduser()
_SHA_RE = re.compile(r"[0-9a-f]{7,64}\Z")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_PROMOTION_GATES = {
    "physics_valid",
    "finite_metrics",
    "at_least_two_folds",
    "air_24h_beats_persistence",
    "at_least_30_scored_24h_folds",
    "at_least_two_24h_regimes",
}
_MANIFEST_KEYS = {
    "start",
    "end",
    "sample_count",
    "sample_counts_by_mode",
    "rejected_counts",
    "auxiliary_exclusion_counts",
    "interpolation_counts",
    "hold_forward_counts",
    "radiation_provenance_counts",
    "event_counts_by_source",
    "items",
    "units",
    "canonical_rows_sha256",
    "fit_diagnostics",
    "constraints",
}
_DIAGNOSTIC_KEYS = {
    "total_consecutive_pairs",
    "fitted_pairs",
    "excluded_passive_pairs",
    "excluded_unknown_action_pairs",
    "auxiliary_glazing_fitted_rows",
    "auxiliary_glazing_skipped_rows",
    "envelope_identification_pairs",
    "auxiliary_living_office_observation_rows",
    "auxiliary_living_office_hallway_mae_f",
    "action_label_coverage_fraction",
    "multihorizon_origin_counts",
    "multihorizon_initial_objective",
    "multihorizon_final_objective",
}
_ACTION_STATES = {
    "vent": ("closed", "open"),
    "indoor_shade": ("closed", "open"),
    "outdoor_shade": ("absent", "present"),
}
_SEASONAL_MODES = {"spring", "warm", "fall_charge", "winter"}
_DYNAMICS_PAYLOAD_KEYS = {
    "version",
    "step_minutes",
    "air_coefficients",
    "mass_coefficients",
    "glazing_observation_coefficients",
}
_BEHAVIOR_PAYLOAD_KEYS = {
    "version",
    "feature_names",
    "transitions",
    "seasonal_vocabulary",
}
_VOCABULARY_PAYLOAD_KEYS = {
    "mode",
    "action_states",
    "transitions",
    "airflow_levels",
    "boosted_windows",
}
_METRIC_PAYLOAD_KEYS = {
    "fold_count",
    "scored_fold_count",
    "overall",
    "by_regime",
    "by_horizon",
    "by_provenance",
    "action_evidence",
    "daily",
    "prediction_interval_coverage",
    "behavior",
    "threshold_baseline",
    "recent_cycle_definition",
    "promotion",
}
_REQUIRED_METRIC_PAYLOAD_KEYS = {
    "fold_count",
    "scored_fold_count",
    "overall",
    "by_regime",
    "by_horizon",
    "by_provenance",
    "promotion",
}


class ArtifactUnavailable(RuntimeError):
    """No validated accepted artifact is available."""


class ArtifactValidationError(ValueError):
    """An artifact violates the versioned reproducibility contract."""


class ArtifactPromotionRefused(ArtifactValidationError):
    """A valid candidate has not passed the provisional shadow gates."""


def _iso_utc(value, name):
    if not isinstance(value, str) or not value:
        raise ArtifactValidationError(f"{name} must be an ISO-8601 UTC string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArtifactValidationError(
            f"{name} must be an ISO-8601 UTC string"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ArtifactValidationError(f"{name} must be UTC")
    return parsed


def _real(value, path, *, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise ArtifactValidationError(f"{path} must not be boolean")
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ArtifactValidationError(f"{path} must be a finite number")
    if minimum is not None and value < minimum:
        raise ArtifactValidationError(f"{path} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ArtifactValidationError(f"{path} must be at most {maximum}")
    return value


def _integer(value, path, *, minimum=0):
    if isinstance(value, bool):
        raise ArtifactValidationError(f"{path} must not be boolean")
    if not isinstance(value, int) or value < minimum:
        raise ArtifactValidationError(
            f"{path} must be an integer of at least {minimum}"
        )
    return value


def _validate_finite(value, path="artifact"):
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, (int, float)):
        _real(value, path)
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ArtifactValidationError(f"{path} keys must be strings")
            _validate_finite(nested, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_finite(nested, f"{path}[{index}]")
        return
    raise ArtifactValidationError(
        f"{path} contains unsupported value {type(value).__name__}"
    )


def _validate_coefficient_map(coefficients, names, path, bounds=None, optional=False):
    if optional and coefficients == {}:
        return
    if not isinstance(coefficients, dict) or tuple(coefficients) != tuple(names):
        raise ArtifactValidationError(
            f"{path} coefficient names/order do not match the contract"
        )
    for index, name in enumerate(names):
        value = _real(coefficients[name], f"{path}.{name}")
        if bounds is not None:
            lower, upper = bounds[0][index], bounds[1][index]
            if not lower <= value <= upper:
                raise ArtifactValidationError(
                    f"{path}.{name} is outside fitted bounds [{lower}, {upper}]"
                )


def _validate_dynamics(model):
    if not isinstance(model, DynamicsModel):
        raise ArtifactValidationError("artifact dynamics type is invalid")
    _integer(model.version, "dynamics.version", minimum=1)
    _integer(model.step_minutes, "dynamics.step_minutes", minimum=1)
    if model.version != 2 or model.step_minutes != 5:
        raise ArtifactValidationError(
            "dynamics model must be version 2 at five-minute steps"
        )
    _validate_coefficient_map(
        model.air_coefficients, AIR_NAMES, "dynamics.air", AIR_BOUNDS
    )
    _validate_coefficient_map(
        model.mass_coefficients, MASS_NAMES, "dynamics.mass", MASS_BOUNDS
    )
    _validate_coefficient_map(
        model.glazing_observation_coefficients,
        GLAZING_NAMES,
        "dynamics.glazing",
        optional=True,
    )
    try:
        validate_physics(model)
    except (KeyError, TypeError, ValueError) as exc:
        raise ArtifactValidationError(
            f"artifact dynamics are invalid: {exc}"
        ) from exc


def _validate_vocabulary(vocabulary):
    if not isinstance(vocabulary, SeasonalActionVocabulary):
        raise ArtifactValidationError("seasonal vocabulary type is invalid")
    if vocabulary.mode not in _SEASONAL_MODES:
        raise ArtifactValidationError("seasonal vocabulary mode is invalid")
    if not isinstance(vocabulary.action_states, tuple):
        raise ArtifactValidationError("seasonal action states must be a tuple")
    actions = []
    for item in vocabulary.action_states:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ArtifactValidationError("seasonal action state entry is malformed")
        action, states = item
        if action not in _ACTION_STATES or not isinstance(states, tuple) or not states:
            raise ArtifactValidationError("seasonal action state is noncanonical")
        expected_order = tuple(
            state for state in _ACTION_STATES[action] if state in states
        )
        if states != expected_order or len(set(states)) != len(states):
            raise ArtifactValidationError("seasonal action states are noncanonical")
        actions.append(action)
    if actions != sorted(set(actions)):
        raise ArtifactValidationError(
            "seasonal action names must be unique and canonical"
        )
    if not isinstance(vocabulary.transitions, tuple):
        raise ArtifactValidationError("seasonal transitions must be a tuple")
    expected_transitions = tuple(
        transition
        for transition in TRANSITIONS
        if transition in vocabulary.transitions
    )
    if (
        vocabulary.transitions != expected_transitions
        or len(set(vocabulary.transitions)) != len(vocabulary.transitions)
    ):
        raise ArtifactValidationError("seasonal transitions are noncanonical")
    if not isinstance(vocabulary.airflow_levels, tuple):
        raise ArtifactValidationError("seasonal airflow levels must be a tuple")
    expected_airflow = tuple(
        level for level in AIRFLOW_LEVELS if level in vocabulary.airflow_levels
    )
    if (
        vocabulary.airflow_levels != expected_airflow
        or len(set(vocabulary.airflow_levels)) != len(vocabulary.airflow_levels)
        or any(not 0.0 <= AIRFLOW_LEVELS[level] <= 2.0 for level in expected_airflow)
    ):
        raise ArtifactValidationError("seasonal airflow levels are noncanonical")
    if not isinstance(vocabulary.boosted_windows, tuple):
        raise ArtifactValidationError("boosted windows must be a tuple")
    previous = None
    for window in vocabulary.boosted_windows:
        if not isinstance(window, tuple) or len(window) != 2:
            raise ArtifactValidationError("boosted window is malformed")
        start, end = window
        _integer(start, "boosted window start")
        _integer(end, "boosted window end")
        if not 0 <= start < end <= 1440:
            raise ArtifactValidationError("boosted window minutes are out of range")
        if previous is not None and window <= previous:
            raise ArtifactValidationError("boosted windows must be unique and sorted")
        previous = window


def _validate_behavior(model):
    if not isinstance(model, BehaviorModel):
        raise ArtifactValidationError("behavior model type is invalid")
    _integer(model.version, "behavior.version", minimum=1)
    if model.version != 1:
        raise ArtifactValidationError("behavior model must be version 1")
    if not isinstance(model.feature_names, tuple) or model.feature_names != FEATURE_NAMES:
        raise ArtifactValidationError("behavior feature names/order are incompatible")
    if not isinstance(model.transitions, dict) or set(model.transitions) != set(TRANSITIONS):
        raise ArtifactValidationError("behavior transition names do not match the contract")
    for transition in TRANSITIONS:
        coefficients = model.transitions[transition]
        if not isinstance(coefficients, tuple):
            raise ArtifactValidationError(
                f"behavior.{transition} coefficients must be a tuple"
            )
        if coefficients and len(coefficients) != len(FEATURE_NAMES):
            raise ArtifactValidationError(
                f"behavior.{transition} coefficient count must match features"
            )
        for index, value in enumerate(coefficients):
            _real(value, f"behavior.{transition}[{index}]")
    if not isinstance(model.seasonal_vocabulary, tuple):
        raise ArtifactValidationError("seasonal vocabulary must be a tuple")
    modes = []
    for vocabulary in model.seasonal_vocabulary:
        _validate_vocabulary(vocabulary)
        modes.append(vocabulary.mode)
    if modes != sorted(set(modes)):
        raise ArtifactValidationError(
            "seasonal vocabulary modes must be unique and canonical"
        )


def _validate_count_map(value, path, allowed_keys=None):
    if not isinstance(value, dict):
        raise ArtifactValidationError(f"{path} must be an object")
    if allowed_keys is not None and not set(value) <= set(allowed_keys):
        unknown = sorted(set(value) - set(allowed_keys))
        raise ArtifactValidationError(
            f"{path} contains unknown reasons: {', '.join(unknown)}"
        )
    for name, count in value.items():
        if not isinstance(name, str) or not name:
            raise ArtifactValidationError(f"{path} keys must be nonempty strings")
        _integer(count, f"{path}.{name}")


def _expected_constraints():
    return {
        "step_minutes": 5,
        "air_coefficient_names": list(AIR_NAMES),
        "mass_coefficient_names": list(MASS_NAMES),
        "glazing_observation_coefficient_names": list(GLAZING_NAMES),
        "air_bounds": [list(bound) for bound in AIR_BOUNDS],
        "mass_bounds": [list(bound) for bound in MASS_BOUNDS],
        "glazing_observation_bounds": [
            [value if math.isfinite(value) else None for value in bound]
            for bound in GLAZING_BOUNDS
        ],
        "output_range_f": list(OUTPUT_RANGE_F),
        "max_vent_forcing": MAX_VENT_FORCING,
        "stability_tolerance": STABILITY_TOLERANCE,
        "max_interpolation_gap_minutes": int(
            MAX_INTERPOLATION_GAP.total_seconds() / 60
        ),
        "max_every_change_hold_minutes": int(
            MAX_HOLD_FORWARD_GAP.total_seconds() / 60
        ),
        "radiation_reconstruction": radiation_reconstruction_contract(),
        "mass_observer": {
            "kind": "causal_ema",
            "source_role": "mass",
            "time_constant_minutes": MASS_OBSERVER_TAU_MINUTES,
        },
        "envelope_identification": {
            "max_radiation_wm2": ENVELOPE_MAX_RADIATION_WM2,
            "vent_forcing": 0.0,
        },
        "multihorizon_identification": deepcopy(MULTIHORIZON_CONTRACT),
    }


def _same_typed_value(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(
            _same_typed_value(actual[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _same_typed_value(left, right)
            for left, right in zip(actual, expected)
        )
    return actual == expected


def _validate_diagnostics(diagnostics, sample_count):
    if not isinstance(diagnostics, dict) or set(diagnostics) != _DIAGNOSTIC_KEYS:
        raise ArtifactValidationError(
            "fit diagnostics fields do not match the Task 4 contract"
        )
    integer_names = _DIAGNOSTIC_KEYS - {
        "action_label_coverage_fraction",
        "auxiliary_living_office_hallway_mae_f",
        "multihorizon_origin_counts",
        "multihorizon_initial_objective",
        "multihorizon_final_objective",
    }
    for name in integer_names:
        _integer(diagnostics[name], f"fit diagnostics.{name}")
    coverage = _real(
        diagnostics["action_label_coverage_fraction"],
        "fit diagnostics.action_label_coverage_fraction",
        minimum=0.0,
        maximum=1.0,
    )
    total = diagnostics["total_consecutive_pairs"]
    fitted = diagnostics["fitted_pairs"]
    excluded = (
        diagnostics["excluded_passive_pairs"]
        + diagnostics["excluded_unknown_action_pairs"]
    )
    if fitted + excluded != total:
        raise ArtifactValidationError(
            "fit diagnostics selected/excluded counts must equal total pairs"
        )
    if (
        diagnostics["auxiliary_glazing_fitted_rows"]
        + diagnostics["auxiliary_glazing_skipped_rows"]
        != fitted
    ):
        raise ArtifactValidationError(
            "fit diagnostics glazing counts must equal fitted pairs"
        )
    envelope_pairs = diagnostics["envelope_identification_pairs"]
    if envelope_pairs > fitted:
        raise ArtifactValidationError(
            "fit diagnostics envelope pairs must not exceed fitted pairs"
        )
    living_rows = diagnostics["auxiliary_living_office_observation_rows"]
    living_mae = diagnostics["auxiliary_living_office_hallway_mae_f"]
    if living_rows > sample_count:
        raise ArtifactValidationError(
            "fit diagnostics living-office rows must not exceed samples"
        )
    if living_rows == 0:
        if living_mae is not None:
            raise ArtifactValidationError(
                "fit diagnostics living-office MAE requires observations"
            )
    else:
        if living_mae is None:
            raise ArtifactValidationError(
                "fit diagnostics living-office observations require MAE"
            )
        _real(
            living_mae,
            "fit diagnostics.auxiliary_living_office_hallway_mae_f",
            minimum=0.0,
            maximum=180.0,
        )
    expected_coverage = fitted / total if total else 0.0
    if not math.isclose(coverage, expected_coverage, rel_tol=0.0, abs_tol=1e-12):
        raise ArtifactValidationError(
            "fit diagnostics coverage must match fitted/total pairs"
        )

    origin_counts = diagnostics["multihorizon_origin_counts"]
    expected_horizons = ("5", "60", "360", "720", "1440")
    if (
        not isinstance(origin_counts, dict)
        or set(origin_counts) != set(expected_horizons)
    ):
        raise ArtifactValidationError(
            "multihorizon origin counts are not exact or ordered"
        )
    for minutes, count in origin_counts.items():
        _integer(
            count,
            f"multihorizon origin count {minutes}",
            minimum=2,
        )
        if count > 64:
            raise ArtifactValidationError(
                "multihorizon origin count exceeds the bounded maximum"
            )
    initial_objective = _real(
        diagnostics["multihorizon_initial_objective"],
        "multihorizon initial objective",
        minimum=0.0,
    )
    final_objective = _real(
        diagnostics["multihorizon_final_objective"],
        "multihorizon final objective",
        minimum=0.0,
    )
    tolerance = (
        MULTIHORIZON_OBJECTIVE_TOLERANCE
        * max(1.0, initial_objective)
    )
    if final_objective > initial_objective + tolerance:
        raise ArtifactValidationError(
            "multihorizon final objective exceeds its initializer"
        )


def _validate_manifest(artifact):
    manifest = artifact.data_manifest
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
        raise ArtifactValidationError(
            "data manifest fields do not match the artifact contract"
        )
    if manifest["items"] != MODEL_ITEMS:
        raise ArtifactValidationError(
            "artifact sensor identities do not match the contract"
        )
    if manifest["units"] != THERMAL_UNITS:
        raise ArtifactValidationError(
            "artifact sensor units do not match the contract"
        )
    digest = manifest["canonical_rows_sha256"]
    if not isinstance(digest, str):
        raise ArtifactValidationError("dataset digest must be an exact string")
    if not _DIGEST_RE.fullmatch(digest):
        raise ArtifactValidationError("dataset digest must be lowercase SHA-256")
    start = _iso_utc(manifest["start"], "data manifest start")
    end = _iso_utc(manifest["end"], "data manifest end")
    if start >= end:
        raise ArtifactValidationError("data manifest range must be chronological")
    if (
        manifest["start"] != artifact.trained_from
        or manifest["end"] != artifact.trained_through
    ):
        raise ArtifactValidationError(
            "artifact training range must match the data manifest"
        )
    _integer(manifest["sample_count"], "data manifest sample_count", minimum=1)
    mode_counts = manifest["sample_counts_by_mode"]
    if not isinstance(mode_counts, dict) or set(mode_counts) != set(MODE_COUNT_KEYS):
        raise ArtifactValidationError(
            "sample mode count keys do not match the closed seasonal vocabulary"
        )
    for mode in MODE_COUNT_KEYS:
        _integer(mode_counts[mode], f"sample mode count {mode}", minimum=0)
    if sum(mode_counts.values()) != manifest["sample_count"]:
        raise ArtifactValidationError(
            "sample mode counts must sum to the manifest sample count"
        )
    _validate_count_map(
        manifest["rejected_counts"],
        "rejected counts",
        CORE_REJECTED_COUNT_KEYS,
    )
    _validate_count_map(
        manifest["auxiliary_exclusion_counts"],
        "auxiliary exclusion counts",
        AUXILIARY_EXCLUSION_COUNT_KEYS,
    )
    interpolation_counts = manifest["interpolation_counts"]
    if (
        not isinstance(interpolation_counts, dict)
        or set(interpolation_counts) != set(MODEL_ITEMS)
    ):
        raise ArtifactValidationError(
            "interpolation count roles do not match the sensor contract"
        )
    for role, count in interpolation_counts.items():
        _integer(count, f"interpolation count {role}", minimum=0)
    hold_counts = manifest["hold_forward_counts"]
    if not isinstance(hold_counts, dict) or set(hold_counts) != set(MODEL_ITEMS):
        raise ArtifactValidationError(
            "hold-forward count roles do not match the sensor contract"
        )
    for role, count in hold_counts.items():
        _integer(count, f"hold-forward count {role}", minimum=0)
    radiation_counts = manifest["radiation_provenance_counts"]
    if (
        not isinstance(radiation_counts, dict)
        or set(radiation_counts) != set(RADIATION_PROVENANCE_LABELS)
    ):
        raise ArtifactValidationError(
            "radiation provenance count fields are not exact"
        )
    for label, count in radiation_counts.items():
        _integer(count, f"radiation provenance count {label}", minimum=0)
    if sum(radiation_counts.values()) != manifest["sample_count"]:
        raise ArtifactValidationError(
            "radiation provenance counts must sum to the manifest sample count"
        )
    counts = manifest["event_counts_by_source"]
    _validate_count_map(counts, "action provenance")
    if not counts or not set(counts) <= set(SOURCE_WEIGHTS) or sum(counts.values()) <= 0:
        raise ArtifactValidationError(
            "action provenance counts must be nonempty canonical sources"
        )
    _validate_diagnostics(
        manifest["fit_diagnostics"], manifest["sample_count"]
    )
    constraints = manifest["constraints"]
    expected = _expected_constraints()
    if not _same_typed_value(constraints, expected):
        raise ArtifactValidationError(
            "constraints do not exactly match the Task 4 physical contract"
        )
    if constraints["air_coefficient_names"] != list(artifact.dynamics.air_coefficients):
        raise ArtifactValidationError(
            "constraints air coefficient ordering differs from artifact"
        )
    if constraints["mass_coefficient_names"] != list(artifact.dynamics.mass_coefficients):
        raise ArtifactValidationError(
            "constraints mass coefficient ordering differs from artifact"
        )
    glazing_names = list(artifact.dynamics.glazing_observation_coefficients)
    if glazing_names and constraints["glazing_observation_coefficient_names"] != glazing_names:
        raise ArtifactValidationError(
            "constraints glazing coefficient ordering differs from artifact"
        )


def _metric_summary_shape(value, path):
    if not isinstance(value, dict) or set(value) != {"count", "mae", "rmse", "bias"}:
        raise ArtifactValidationError(f"{path} metric fields are unknown or incomplete")


def _method_summary_shape(value, path):
    if not isinstance(value, dict) or not set(value) <= {"air", "mass"}:
        raise ArtifactValidationError(f"{path} state metric fields are unknown")
    for state, horizons in value.items():
        if not isinstance(horizons, dict) or not set(horizons) <= {
            "1", "6", "12", "24", "48", "72"
        }:
            raise ArtifactValidationError(f"{path}.{state} horizon fields are unknown")
        for horizon, summary in horizons.items():
            _metric_summary_shape(summary, f"{path}.{state}.{horizon}")


def _split_summary_shape(value, path, shorthand_pattern):
    if not isinstance(value, dict):
        raise ArtifactValidationError(f"{path} metric split must be an object")
    if not value:
        return
    if set(value) <= {"air", "mass"}:
        _method_summary_shape(value, path)
        return
    if any(not shorthand_pattern.fullmatch(key) for key in value):
        raise ArtifactValidationError(f"{path} metric fields are unknown")


def _validate_metrics_structure(metrics, path="metrics"):
    if (
        not isinstance(metrics, dict)
        or not _REQUIRED_METRIC_PAYLOAD_KEYS <= set(metrics)
        or not set(metrics) <= _METRIC_PAYLOAD_KEYS
    ):
        raise ArtifactValidationError(f"{path} fields are incomplete or unknown")
    overall = metrics["overall"]
    if (
        not isinstance(overall, dict)
        or not {"model", "persistence"} <= set(overall)
        or not set(overall) <= {"model", "persistence", "recent_cycle"}
    ):
        raise ArtifactValidationError(f"{path}.overall method fields are unknown")
    for method, summary in overall.items():
        _method_summary_shape(summary, f"{path}.overall.{method}")

    split_pattern = re.compile(
        r"(?:air|mass)_(?:1|6|12|24|48|72)h_(?:count|mae|rmse|bias)\Z"
    )
    by_regime = metrics["by_regime"]
    regimes = {"warm", "winter", "shoulder"}
    if not isinstance(by_regime, dict) or set(by_regime) != regimes:
        raise ArtifactValidationError(f"{path}.by_regime fields are unknown")
    for regime, methods in by_regime.items():
        if (
            not isinstance(methods, dict)
            or not {"model", "persistence"} <= set(methods)
            or not set(methods) <= {"model", "persistence", "recent_cycle"}
        ):
            raise ArtifactValidationError(
                f"{path}.by_regime.{regime} method fields are unknown"
            )
        for method, summary in methods.items():
            _method_summary_shape(
                summary, f"{path}.by_regime.{regime}.{method}"
            )

    by_provenance = metrics["by_provenance"]
    provenances = {
        "confirmed", "photosensor", "reconstructed", "model_inferred", "unknown"
    }
    if not isinstance(by_provenance, dict) or not set(by_provenance) <= provenances:
        raise ArtifactValidationError(f"{path}.by_provenance fields are unknown")
    for name, summary in by_provenance.items():
        _split_summary_shape(
            summary, f"{path}.by_provenance.{name}", split_pattern
        )

    action_evidence = metrics.get("action_evidence")
    if action_evidence is not None:
        if not isinstance(action_evidence, dict) or set(action_evidence) != {"confirmed"}:
            raise ArtifactValidationError(
                f"{path}.action_evidence fields are unknown or incomplete"
            )
        confirmed = action_evidence["confirmed"]
        expected = {"training_rows", "evaluation_targets", "disjoint_fold_count"}
        if not isinstance(confirmed, dict) or set(confirmed) != expected:
            raise ArtifactValidationError(
                f"{path}.action_evidence.confirmed fields are unknown or incomplete"
            )
        for name in expected:
            _integer(
                confirmed[name], f"{path}.action_evidence.confirmed.{name}"
            )
        if confirmed["disjoint_fold_count"] > metrics["scored_fold_count"]:
            raise ArtifactValidationError(
                f"{path}.action_evidence confirmed fold count exceeds scored folds"
            )
        if confirmed["disjoint_fold_count"] > 0 and (
            confirmed["training_rows"] == 0
            or confirmed["evaluation_targets"] == 0
        ):
            raise ArtifactValidationError(
                f"{path}.action_evidence disjoint evidence requires both sides"
            )

    by_horizon = metrics["by_horizon"]
    horizons = {"1", "6", "12", "24", "48", "72"}
    if not isinstance(by_horizon, dict) or not set(by_horizon) <= horizons:
        raise ArtifactValidationError(f"{path}.by_horizon fields are unknown")
    horizon_pattern = re.compile(r"(?:air|mass)_(?:count|mae|rmse|bias)\Z")
    for horizon, summary in by_horizon.items():
        if not isinstance(summary, dict):
            raise ArtifactValidationError(
                f"{path}.by_horizon.{horizon} must be an object"
            )
        if set(summary) <= {"air", "mass"}:
            for state, metric in summary.items():
                _metric_summary_shape(
                    metric, f"{path}.by_horizon.{horizon}.{state}"
                )
        elif any(not horizon_pattern.fullmatch(key) for key in summary):
            raise ArtifactValidationError(
                f"{path}.by_horizon.{horizon} metric fields are unknown"
            )

    coverage = metrics.get("prediction_interval_coverage")
    if coverage is not None:
        if not isinstance(coverage, dict) or not set(coverage) <= {"air", "mass"}:
            raise ArtifactValidationError(f"{path}.prediction_interval_coverage fields are unknown")
        for state, state_horizons in coverage.items():
            if not isinstance(state_horizons, dict) or not set(state_horizons) <= horizons:
                raise ArtifactValidationError(f"{path}.prediction_interval_coverage.{state} fields are unknown")
            for horizon, evidence in state_horizons.items():
                required = {"nominal", "count", "covered", "fraction"}
                allowed = required | {"calibration"}
                if not isinstance(evidence, dict) or not required <= set(evidence) or not set(evidence) <= allowed:
                    raise ArtifactValidationError(f"{path}.prediction_interval_coverage.{state}.{horizon} fields are unknown or incomplete")

    behavior = metrics.get("behavior")
    if behavior is not None:
        expected = {
            "available", "label_count", "precision", "recall",
            "median_timing_error_minutes", "classification_probability",
        }
        if not isinstance(behavior, dict) or set(behavior) != expected:
            raise ArtifactValidationError(f"{path}.behavior fields are unknown or incomplete")

    daily = metrics.get("daily")
    if daily is not None:
        expected = {"hallway_high_f", "hallway_low_f", "peak_time_minutes", "morning_mass_f"}
        if not isinstance(daily, dict) or set(daily) != expected:
            raise ArtifactValidationError(f"{path}.daily fields are unknown or incomplete")
        for name, summary in daily.items():
            _metric_summary_shape(summary, f"{path}.daily.{name}")

    threshold = metrics.get("threshold_baseline")
    if threshold is not None:
        expected = {
            "definition", "input", "class_counts", "comparison_target",
            "precision", "recall", "count",
        }
        if not isinstance(threshold, dict) or set(threshold) != expected:
            raise ArtifactValidationError(
                f"{path}.threshold_baseline fields are unknown or incomplete"
            )
        definition = threshold["definition"]
        classes = {"none", "vent_tonight", "close_up_tomorrow"}
        if not isinstance(definition, dict) or set(definition) != classes:
            raise ArtifactValidationError(
                f"{path}.threshold_baseline definition fields are unknown"
            )
        class_counts = threshold["class_counts"]
        if not isinstance(class_counts, dict) or set(class_counts) != classes:
            raise ArtifactValidationError(
                f"{path}.threshold_baseline class fields are unknown"
            )


def _validate_exact_method_summary(value, path):
    horizons = {"1", "6", "12", "24", "48", "72"}
    if not isinstance(value, dict) or set(value) != {"air", "mass"}:
        raise ArtifactValidationError(
            f"{path} state metric fields are incomplete or unknown"
        )
    for state, state_horizons in value.items():
        if not isinstance(state_horizons, dict) or set(state_horizons) != horizons:
            raise ArtifactValidationError(
                f"{path}.{state} horizon fields are incomplete or unknown"
            )
        for horizon, summary in state_horizons.items():
            _metric_summary_shape(summary, f"{path}.{state}.{horizon}")


def _validate_backtest_v2_metrics_structure(metrics):
    """Require the evaluator's exact v2 metric shape without tightening artifacts."""
    path = "backtest.metrics"
    horizons = {"1", "6", "12", "24", "48", "72"}
    methods = {"model", "persistence", "recent_cycle"}
    if not isinstance(metrics, dict) or set(metrics) != _METRIC_PAYLOAD_KEYS:
        raise ArtifactValidationError(
            f"{path} fields are incomplete or unknown"
        )
    overall = metrics["overall"]
    if not isinstance(overall, dict) or set(overall) != methods:
        raise ArtifactValidationError(
            f"{path}.overall method fields are incomplete or unknown"
        )
    for method, summary in overall.items():
        _validate_exact_method_summary(summary, f"{path}.overall.{method}")

    regimes = {"warm", "winter", "shoulder"}
    by_regime = metrics["by_regime"]
    if not isinstance(by_regime, dict) or set(by_regime) != regimes:
        raise ArtifactValidationError(f"{path}.by_regime fields are incomplete")
    for regime, regime_methods in by_regime.items():
        if not isinstance(regime_methods, dict) or set(regime_methods) != methods:
            raise ArtifactValidationError(
                f"{path}.by_regime.{regime} method fields are incomplete"
            )
        for method, summary in regime_methods.items():
            _validate_exact_method_summary(
                summary, f"{path}.by_regime.{regime}.{method}"
            )

    by_horizon = metrics["by_horizon"]
    if not isinstance(by_horizon, dict) or set(by_horizon) != horizons:
        raise ArtifactValidationError(
            f"{path}.by_horizon fields are incomplete or unknown"
        )
    for horizon, states in by_horizon.items():
        if not isinstance(states, dict) or set(states) != {"air", "mass"}:
            raise ArtifactValidationError(
                f"{path}.by_horizon.{horizon} state fields are incomplete"
            )
        for state, summary in states.items():
            _metric_summary_shape(
                summary, f"{path}.by_horizon.{horizon}.{state}"
            )

    provenances = {
        "confirmed", "photosensor", "reconstructed", "model_inferred", "unknown"
    }
    by_provenance = metrics["by_provenance"]
    if not isinstance(by_provenance, dict) or set(by_provenance) != provenances:
        raise ArtifactValidationError(
            f"{path}.by_provenance fields are incomplete or unknown"
        )
    for provenance, summary in by_provenance.items():
        if summary:
            _validate_exact_method_summary(
                summary, f"{path}.by_provenance.{provenance}"
            )

    coverage = metrics["prediction_interval_coverage"]
    if not isinstance(coverage, dict) or set(coverage) != {"air", "mass"}:
        raise ArtifactValidationError(
            f"{path}.prediction_interval_coverage states are incomplete"
        )
    coverage_fields = {"nominal", "count", "covered", "fraction", "calibration"}
    for state, state_horizons in coverage.items():
        if not isinstance(state_horizons, dict) or set(state_horizons) != horizons:
            raise ArtifactValidationError(
                f"{path}.prediction_interval_coverage.{state} horizons are incomplete"
            )
        for horizon, evidence in state_horizons.items():
            if not isinstance(evidence, dict) or set(evidence) != coverage_fields:
                raise ArtifactValidationError(
                    f"{path}.prediction_interval_coverage.{state}.{horizon} fields are incomplete"
                )
            if not isinstance(evidence["calibration"], str) or not evidence[
                "calibration"
            ]:
                raise ArtifactValidationError(
                    f"{path}.prediction_interval_coverage.{state}.{horizon}.calibration is invalid"
                )
    definition = metrics["recent_cycle_definition"]
    if not isinstance(definition, str) or not definition:
        raise ArtifactValidationError(
            f"{path}.recent_cycle_definition must be a nonempty string"
        )


def _validate_metric_semantics(value, path="metrics", key=None):
    is_count = key in {"count", "covered"} or (
        key is not None and key.endswith("_count")
    )
    is_error = key in {"mae", "rmse"} or (
        key is not None and key.endswith(("_mae", "_rmse"))
    )
    is_coverage = key in {
        "coverage",
        "fraction",
        "precision",
        "recall",
        "nominal",
        "classification_probability",
    }
    is_timing = key is not None and "timing_error" in key
    is_bias = key == "bias" or (
        key is not None and key.endswith("_bias")
    )
    numeric_semantic = is_count or is_error or is_coverage or is_timing or is_bias

    if key == "available":
        if not isinstance(value, bool):
            raise ArtifactValidationError(f"{path} must be boolean")
        return
    if value is None:
        if is_count:
            raise ArtifactValidationError(f"{path} must be a nonnegative integer")
        return
    if numeric_semantic:
        if is_count:
            _integer(value, path)
            return
        number = _real(value, path)
        if (is_error or is_timing) and number < 0.0:
            raise ArtifactValidationError(f"{path} must be nonnegative")
        if is_coverage and not 0.0 <= number <= 1.0:
            raise ArtifactValidationError(f"{path} must be within [0, 1]")
        return
    if isinstance(value, str):
        return
    if isinstance(value, bool):
        raise ArtifactValidationError(f"{path} must not be boolean")
    if isinstance(value, dict):
        for nested_key, nested in value.items():
            if not isinstance(nested_key, str):
                raise ArtifactValidationError(f"{path} keys must be strings")
            _validate_metric_semantics(
                nested, f"{path}.{nested_key}", nested_key
            )
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_metric_semantics(nested, f"{path}[{index}]", key)
        return
    _real(value, path)


def _promotion_shape(metrics):
    if not isinstance(metrics, dict):
        raise ArtifactValidationError("artifact metrics must be an object")
    promotion = metrics.get("promotion")
    if not isinstance(promotion, dict):
        raise ArtifactValidationError("promotion evidence must be an object")
    allowed = {"eligible", "shadow_only", "gates", "graduation_thresholds"}
    if "shadow_only" not in promotion:
        raise ArtifactValidationError(
            "promotion safety invariant shadow_only is required"
        )
    if not {"eligible", "gates"} <= set(promotion) or not set(promotion) <= allowed:
        raise ArtifactValidationError(
            "promotion evidence fields are incomplete or unknown"
        )
    if promotion.get("shadow_only") is not True:
        raise ArtifactValidationError(
            "promotion safety invariant shadow_only must be true"
        )
    if not isinstance(promotion.get("eligible"), bool):
        raise ArtifactValidationError("promotion eligible must be boolean")
    if "graduation_thresholds" in promotion and promotion["graduation_thresholds"] is not None:
        raise ArtifactValidationError("graduation thresholds must remain unset")
    gates = promotion.get("gates")
    if not isinstance(gates, dict) or set(gates) != _PROMOTION_GATES:
        raise ArtifactValidationError(
            "promotion gates do not match the provisional contract"
        )
    if any(not isinstance(value, bool) for value in gates.values()):
        raise ArtifactValidationError("promotion gates must be boolean")
    if promotion["eligible"] is not all(gates.values()):
        raise ArtifactValidationError(
            "promotion eligibility does not match reported gates"
        )
    return promotion, gates


def _summary(metrics, method):
    try:
        summary = metrics["overall"][method]["air"]["24"]
    except (KeyError, TypeError) as exc:
        raise ArtifactPromotionRefused(
            "candidate promotion evidence is incomplete"
        ) from exc
    if not isinstance(summary, dict) or set(summary) != {"count", "mae", "rmse", "bias"}:
        raise ArtifactPromotionRefused(
            f"candidate {method} 24-hour summary is incomplete"
        )
    try:
        _integer(summary["count"], f"metrics.overall.{method}.air.24.count")
        for name in ("mae", "rmse", "bias"):
            _real(summary[name], f"metrics.overall.{method}.air.24.{name}")
    except ArtifactValidationError as exc:
        raise ArtifactPromotionRefused(
            "candidate promotion evidence has invalid numeric types"
        ) from exc
    return summary


def provisional_promotion_gates(
    *, physics_valid, finite_metrics, scored_fold_count, model_24, persistence_24,
    scored_24h_by_regime,
):
    """Return the only provisional shadow gates from explicit evidence."""
    regimes = {"warm", "winter", "shoulder"}
    if (
        not isinstance(scored_24h_by_regime, dict)
        or set(scored_24h_by_regime) != regimes
    ):
        raise ArtifactValidationError(
            "scored 24-hour regime count fields are incomplete or unknown"
        )
    for regime, count in scored_24h_by_regime.items():
        _integer(count, f"scored 24-hour regime count {regime}")
    return {
        "physics_valid": physics_valid is True,
        "finite_metrics": finite_metrics is True,
        "at_least_two_folds": scored_fold_count >= 2,
        "air_24h_beats_persistence": (
            model_24["count"] > 0
            and persistence_24["count"] > 0
            and model_24["mae"] < persistence_24["mae"]
        ),
        "at_least_30_scored_24h_folds": (
            model_24["count"] >= MIN_SCORED_24H_FOLDS
        ),
        "at_least_two_24h_regimes": sum(
            count >= MIN_REGIME_24H_FOLDS
            for count in scored_24h_by_regime.values()
        ) >= MIN_24H_REGIMES,
    }


def _scored_24h_by_regime(metrics):
    try:
        by_regime = metrics["by_regime"]
    except (KeyError, TypeError) as exc:
        raise ArtifactPromotionRefused(
            "candidate regime promotion evidence is incomplete"
        ) from exc
    if not isinstance(by_regime, dict) or set(by_regime) != {
        "warm", "winter", "shoulder"
    }:
        raise ArtifactPromotionRefused(
            "candidate regime promotion evidence is incomplete"
        )
    model_counts = {}
    persistence_counts = {}
    try:
        for regime, methods in by_regime.items():
            for method, destination in (
                ("model", model_counts),
                ("persistence", persistence_counts),
            ):
                summary = methods[method]["air"]["24"]
                if set(summary) != {"count", "mae", "rmse", "bias"}:
                    raise KeyError(method)
                destination[regime] = _integer(
                    summary["count"],
                    f"metrics.by_regime.{regime}.{method}.air.24.count",
                )
    except (ArtifactValidationError, KeyError, TypeError) as exc:
        raise ArtifactPromotionRefused(
            "candidate regime promotion evidence is incomplete or invalid"
        ) from exc
    return model_counts, persistence_counts


def _promotion_evidence(metrics):
    promotion, gates = _promotion_shape(metrics)
    try:
        fold_count = metrics["fold_count"]
        scored_folds = metrics["scored_fold_count"]
    except KeyError as exc:
        raise ArtifactPromotionRefused(
            "candidate promotion evidence is incomplete"
        ) from exc
    try:
        _integer(fold_count, "metrics.fold_count")
        _integer(scored_folds, "metrics.scored_fold_count")
    except ArtifactValidationError as exc:
        raise ArtifactPromotionRefused(
            "candidate promotion evidence has invalid numeric types"
        ) from exc
    if scored_folds > fold_count:
        raise ArtifactPromotionRefused(
            "candidate scored fold count exceeds fold count"
        )
    model = _summary(metrics, "model")
    persistence = _summary(metrics, "persistence")
    model_by_regime, persistence_by_regime = _scored_24h_by_regime(metrics)
    if (
        model["count"] != persistence["count"]
        or model_by_regime != persistence_by_regime
        or sum(model_by_regime.values()) != model["count"]
        or model["count"] > scored_folds
    ):
        raise ArtifactPromotionRefused(
            "candidate 24-hour aggregate and regime evidence is contradictory"
        )
    actual = provisional_promotion_gates(
        physics_valid=True,
        finite_metrics=True,
        scored_fold_count=scored_folds,
        model_24=model,
        persistence_24=persistence,
        scored_24h_by_regime=model_by_regime,
    )
    mismatched = sorted(
        name for name in _PROMOTION_GATES if gates[name] is not actual[name]
    )
    if mismatched:
        raise ArtifactPromotionRefused(
            "candidate report does not match evidence for gates: "
            + ", ".join(mismatched)
        )
    return promotion, actual


def _require_eligible(metrics):
    promotion, actual = _promotion_evidence(metrics)
    failed = sorted(name for name, passed in actual.items() if not passed)
    if promotion["eligible"] is not True or failed:
        raise ArtifactPromotionRefused(
            "candidate promotion refused: "
            + (", ".join(failed) if failed else "not eligible")
        )


def _require_year_round_mode_coverage(manifest):
    missing = [
        mode
        for mode in MODE_COUNT_KEYS
        if mode != "unknown" and manifest["sample_counts_by_mode"][mode] == 0
    ]
    if missing:
        raise ArtifactPromotionRefused(
            "candidate promotion refused: seasonal mode coverage missing "
            + ", ".join(missing)
        )


def validate_artifact(artifact, *, require_eligible=False):
    """Validate complete type, semantic, provenance, and physical invariants."""
    if not isinstance(artifact, ThermalArtifact):
        raise ArtifactValidationError("artifact must be a ThermalArtifact")
    if artifact.schema != MODEL_SCHEMA:
        raise ArtifactValidationError(f"artifact schema must be {MODEL_SCHEMA}")
    created_at = _iso_utc(artifact.created_at, "artifact created_at")
    trained_from = _iso_utc(artifact.trained_from, "artifact trained_from")
    trained_through = _iso_utc(
        artifact.trained_through, "artifact trained_through"
    )
    if trained_from >= trained_through:
        raise ArtifactValidationError(
            "artifact training range must be chronological"
        )
    if created_at < trained_through:
        raise ArtifactValidationError(
            "artifact creation must not precede training completion"
        )
    if not isinstance(artifact.code_revision, str):
        raise ArtifactValidationError("code revision must be an exact string")
    if not _SHA_RE.fullmatch(artifact.code_revision):
        raise ArtifactValidationError(
            "code revision must be a hexadecimal revision"
        )
    _validate_dynamics(artifact.dynamics)
    _validate_behavior(artifact.behavior)
    required_splits = {
        "overall",
        "by_regime",
        "by_horizon",
        "by_provenance",
        "promotion",
    }
    if not isinstance(artifact.metrics, dict) or not required_splits <= set(
        artifact.metrics
    ):
        raise ArtifactValidationError(
            "artifact metrics are missing required evidence splits"
        )
    _validate_metrics_structure(artifact.metrics)
    _validate_finite(asdict(artifact))
    _promotion_shape(artifact.metrics)
    _promotion_evidence(artifact.metrics)
    metrics_without_promotion = {
        key: value for key, value in artifact.metrics.items() if key != "promotion"
    }
    _validate_metric_semantics(metrics_without_promotion)
    _validate_manifest(artifact)
    if require_eligible:
        _require_year_round_mode_coverage(artifact.data_manifest)
        _require_eligible(artifact.metrics)
    return artifact


def _artifact_payload(artifact):
    validate_artifact(artifact)
    return asdict(artifact)


def _exact_payload_keys(value, expected, path):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ArtifactValidationError(
            f"{path} fields do not exactly match the schema"
        )


def _validate_payload_shape(payload):
    """Reject unknown or missing JSON keys before any normalization."""
    root_keys = {
        "schema",
        "created_at",
        "trained_from",
        "trained_through",
        "code_revision",
        "dynamics",
        "behavior",
        "metrics",
        "data_manifest",
    }
    _exact_payload_keys(payload, root_keys, "artifact JSON")
    dynamics = payload["dynamics"]
    behavior = payload["behavior"]
    _exact_payload_keys(dynamics, _DYNAMICS_PAYLOAD_KEYS, "dynamics")
    _exact_payload_keys(
        dynamics["air_coefficients"], AIR_NAMES, "air coefficients"
    )
    _exact_payload_keys(
        dynamics["mass_coefficients"], MASS_NAMES, "mass coefficients"
    )
    glazing = dynamics["glazing_observation_coefficients"]
    if not isinstance(glazing, dict) or (glazing and set(glazing) != set(GLAZING_NAMES)):
        raise ArtifactValidationError(
            "glazing observation coefficient fields do not exactly match the schema"
        )
    _exact_payload_keys(behavior, _BEHAVIOR_PAYLOAD_KEYS, "behavior")
    _exact_payload_keys(behavior["transitions"], TRANSITIONS, "behavior transitions")
    vocabulary = behavior["seasonal_vocabulary"]
    if not isinstance(vocabulary, list):
        raise ArtifactValidationError("seasonal vocabulary must be a list")
    for index, item in enumerate(vocabulary):
        _exact_payload_keys(
            item, _VOCABULARY_PAYLOAD_KEYS, f"seasonal vocabulary[{index}]"
        )
    metrics = payload["metrics"]
    _validate_metrics_structure(metrics, "metric payload")
    manifest = payload["data_manifest"]
    _exact_payload_keys(manifest, _MANIFEST_KEYS, "data manifest")
    _exact_payload_keys(
        manifest["sample_counts_by_mode"], MODE_COUNT_KEYS, "sample mode counts"
    )
    _exact_payload_keys(manifest["items"], MODEL_ITEMS, "sensor items")
    _exact_payload_keys(manifest["units"], THERMAL_UNITS, "sensor units")
    _validate_count_map(
        manifest["rejected_counts"],
        "rejected count payload",
        CORE_REJECTED_COUNT_KEYS,
    )
    _validate_count_map(
        manifest["auxiliary_exclusion_counts"],
        "auxiliary exclusion count payload",
        AUXILIARY_EXCLUSION_COUNT_KEYS,
    )
    _exact_payload_keys(
        manifest["interpolation_counts"], MODEL_ITEMS, "interpolation counts"
    )
    _exact_payload_keys(
        manifest["hold_forward_counts"], MODEL_ITEMS, "hold-forward counts"
    )
    _exact_payload_keys(
        manifest["radiation_provenance_counts"],
        RADIATION_PROVENANCE_LABELS,
        "radiation provenance counts",
    )
    _exact_payload_keys(
        manifest["fit_diagnostics"], _DIAGNOSTIC_KEYS, "fit diagnostics"
    )
    _exact_payload_keys(
        manifest["constraints"], _expected_constraints(), "constraints"
    )


def _artifact_from_payload(payload):
    if not isinstance(payload, dict):
        raise ArtifactValidationError("artifact JSON root must be an object")
    _validate_payload_shape(payload)
    dynamics = payload["dynamics"]
    behavior = payload["behavior"]
    if not isinstance(dynamics, dict) or not isinstance(behavior, dict):
        raise ArtifactValidationError("model payloads must be objects")
    try:
        air_raw = dynamics["air_coefficients"]
        mass_raw = dynamics["mass_coefficients"]
        glazing_raw = dynamics["glazing_observation_coefficients"]
        vocabulary_raw = behavior["seasonal_vocabulary"]
        transitions_raw = behavior["transitions"]
        vocabulary = tuple(
            SeasonalActionVocabulary(
                mode=item["mode"],
                action_states=tuple(
                    (str(action), tuple(states))
                    for action, states in item["action_states"]
                ),
                transitions=tuple(item["transitions"]),
                airflow_levels=tuple(item["airflow_levels"]),
                boosted_windows=tuple(
                    tuple(window) for window in item["boosted_windows"]
                ),
            )
            for item in vocabulary_raw
        )
        artifact = ThermalArtifact(
            schema=payload["schema"],
            created_at=payload["created_at"],
            trained_from=payload["trained_from"],
            trained_through=payload["trained_through"],
            code_revision=payload["code_revision"],
            dynamics=DynamicsModel(
                version=dynamics["version"],
                step_minutes=dynamics["step_minutes"],
                air_coefficients={name: air_raw[name] for name in AIR_NAMES},
                mass_coefficients={name: mass_raw[name] for name in MASS_NAMES},
                glazing_observation_coefficients=(
                    {name: glazing_raw[name] for name in GLAZING_NAMES}
                    if glazing_raw
                    else {}
                ),
            ),
            behavior=BehaviorModel(
                version=behavior["version"],
                feature_names=tuple(behavior["feature_names"]),
                transitions={
                    name: tuple(transitions_raw[name]) for name in TRANSITIONS
                },
                seasonal_vocabulary=vocabulary,
            ),
            metrics=payload["metrics"],
            data_manifest=payload["data_manifest"],
        )
    except (KeyError, TypeError) as exc:
        raise ArtifactValidationError(
            "artifact JSON model fields are incomplete"
        ) from exc
    return validate_artifact(artifact)


def _fsync_directory(path):
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            payload,
            allow_nan=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        )
        + "\n"
    )
    descriptor = None
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.tmp-", dir=path.parent
        )
        temporary = Path(temporary_name)
        output = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = None
        with output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(path.parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


_BACKTEST_REPORT_KEYS = {
    "schema", "generated_at", "data_range", "folds", "prediction_records",
    "metrics",
}
_FOLD_REQUIRED_KEYS = {
    "train_start", "train_end", "prediction_start", "prediction_end",
    "horizons_hours", "training_row_count", "evaluation_target_row_count",
    "radiation_provenance", "action_provenance",
}
_FOLD_OPTIONAL_KEYS = {"fit_error", "model_error", "inactive_forcing_features"}
_INACTIVE_FORCING_FEATURE_NAMES = (
    "solar_unshaded",
    "solar_indoor_closed",
    "solar_outdoor",
    "vent_exchange",
)
_PREDICTION_RECORD_REQUIRED_KEYS = {
    "origin_at", "target_at", "horizon", "regime", "provenance", "model",
    "persistence",
}


def _fold_is_error_free(fold):
    return "fit_error" not in fold and "model_error" not in fold


def valid_paired_24h_prediction_record(record, fold):
    """Return whether one record is paired 24-hour evidence for its fold."""
    if (
        not isinstance(record, dict)
        or not isinstance(fold, dict)
        or not _fold_is_error_free(fold)
        or record.get("horizon") != 24
    ):
        return False
    origin = record.get("origin_at")
    if isinstance(origin, datetime):
        if origin.tzinfo is None or origin.utcoffset() is None:
            return False
        origin = origin.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if origin != fold.get("prediction_start"):
        return False
    for method in ("model", "persistence"):
        errors = record.get(method)
        if not isinstance(errors, dict) or set(errors) != {"air", "mass"}:
            return False
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in errors.values()
        ):
            return False
    return True


def _validate_count_split(value, labels, row_count, path):
    if not isinstance(value, dict) or set(value) != {"training", "evaluation_targets"}:
        raise ArtifactValidationError(f"{path} split fields are invalid")
    for split, expected_count in (
        ("training", row_count[0]),
        ("evaluation_targets", row_count[1]),
    ):
        counts = value[split]
        if not isinstance(counts, dict) or set(counts) != set(labels):
            raise ArtifactValidationError(f"{path}.{split} fields are invalid")
        for label, count in counts.items():
            _integer(count, f"{path}.{split}.{label}")
        if sum(counts.values()) != expected_count:
            raise ArtifactValidationError(
                f"{path}.{split} counts do not match local row count"
            )


def _validate_backtest_report(report):
    if not isinstance(report, dict) or set(report) != _BACKTEST_REPORT_KEYS:
        raise ArtifactValidationError(
            "backtest report fields are incomplete or unknown"
        )
    if report["schema"] != BACKTEST_SCHEMA:
        raise ArtifactValidationError(
            f"backtest report schema must be {BACKTEST_SCHEMA}"
        )
    _iso_utc(report["generated_at"], "backtest generated_at")
    data_range = report["data_range"]
    if not isinstance(data_range, dict) or set(data_range) != {"start", "end"}:
        raise ArtifactValidationError("backtest data_range fields are invalid")
    if _iso_utc(data_range["start"], "backtest data_range start") >= _iso_utc(
        data_range["end"], "backtest data_range end"
    ):
        raise ArtifactValidationError("backtest data range must be increasing")

    folds = report["folds"]
    if not isinstance(folds, list):
        raise ArtifactValidationError("backtest folds must be a list")
    confirmed_training_rows = 0
    confirmed_evaluation_targets = 0
    confirmed_disjoint_folds = 0
    error_free_folds = 0
    fold_by_origin = {}
    expected_record_keys = set()
    for fold in folds:
        if (
            not isinstance(fold, dict)
            or not _FOLD_REQUIRED_KEYS <= set(fold)
            or not set(fold) <= _FOLD_REQUIRED_KEYS | _FOLD_OPTIONAL_KEYS
        ):
            raise ArtifactValidationError(
                "backtest fold fields are incomplete or unknown"
            )
        if "fit_error" in fold and "model_error" in fold:
            raise ArtifactValidationError("backtest fold error fields conflict")
        for error_key in ("fit_error", "model_error"):
            if error_key in fold and (
                not isinstance(fold[error_key], str) or not fold[error_key]
            ):
                raise ArtifactValidationError(
                    f"backtest fold {error_key} must be a nonempty string"
                )
        if "inactive_forcing_features" in fold:
            inactive = fold["inactive_forcing_features"]
            if (
                not isinstance(inactive, list)
                or len(inactive) != len(set(inactive))
                or any(
                    name not in _INACTIVE_FORCING_FEATURE_NAMES
                    for name in inactive
                )
            ):
                raise ArtifactValidationError(
                    "backtest fold inactive forcing fields are invalid"
                )
        train_start = _iso_utc(fold["train_start"], "fold train_start")
        train_end = _iso_utc(fold["train_end"], "fold train_end")
        prediction_start = _iso_utc(
            fold["prediction_start"], "fold prediction_start"
        )
        prediction_end = _iso_utc(fold["prediction_end"], "fold prediction_end")
        if not train_start <= train_end < prediction_start < prediction_end:
            raise ArtifactValidationError(
                "backtest fold ranges must be strictly chronological"
            )
        if fold["prediction_start"] in fold_by_origin:
            raise ArtifactValidationError("backtest fold origins must be unique")
        fold_by_origin[fold["prediction_start"]] = fold
        horizons = fold["horizons_hours"]
        if (
            not isinstance(horizons, list)
            or not horizons
            or horizons != sorted(set(horizons))
            or any(value not in {1, 6, 12, 24, 48, 72} for value in horizons)
            or prediction_end - prediction_start != timedelta(hours=max(horizons))
        ):
            raise ArtifactValidationError("backtest fold horizons are invalid")
        training_rows = _integer(
            fold["training_row_count"], "backtest fold training_row_count",
            minimum=1,
        )
        evaluation_rows = _integer(
            fold["evaluation_target_row_count"],
            "backtest fold evaluation_target_row_count", minimum=1,
        )
        if evaluation_rows != max(horizons) * 12:
            raise ArtifactValidationError(
                "backtest fold evaluation target row count is invalid"
            )
        _validate_count_split(
            fold["radiation_provenance"], RADIATION_PROVENANCE_LABELS,
            (training_rows, evaluation_rows), "backtest fold radiation provenance",
        )
        _validate_count_split(
            fold["action_provenance"],
            ("confirmed", "photosensor", "reconstructed", "model_inferred", "unknown"),
            (training_rows, evaluation_rows), "backtest fold action provenance",
        )
        if _fold_is_error_free(fold):
            error_free_folds += 1
            action = fold["action_provenance"]
            training_confirmed = action["training"]["confirmed"]
            evaluation_confirmed = action["evaluation_targets"]["confirmed"]
            confirmed_training_rows += training_confirmed
            confirmed_evaluation_targets += evaluation_confirmed
            if training_confirmed > 0 and evaluation_confirmed > 0:
                confirmed_disjoint_folds += 1
            expected_record_keys.update(
                (fold["prediction_start"], horizon) for horizon in horizons
            )

    records = report["prediction_records"]
    if not isinstance(records, list):
        raise ArtifactValidationError("prediction records must be a list")
    actual_record_keys = set()
    valid_24_records = []
    records_24h_by_regime = {"warm": 0, "winter": 0, "shoulder": 0}
    for record in records:
        if (
            not isinstance(record, dict)
            or set(record) not in (
                _PREDICTION_RECORD_REQUIRED_KEYS,
                _PREDICTION_RECORD_REQUIRED_KEYS | {"recent_cycle"},
            )
        ):
            raise ArtifactValidationError(
                "prediction record fields are incomplete or unknown"
            )
        origin = _iso_utc(record["origin_at"], "prediction origin_at")
        target = _iso_utc(record["target_at"], "prediction target_at")
        horizon = _integer(record["horizon"], "prediction horizon", minimum=1)
        if horizon not in {1, 6, 12, 24, 48, 72} or target - origin != timedelta(hours=horizon):
            raise ArtifactValidationError("prediction record horizon is invalid")
        if record["regime"] not in records_24h_by_regime:
            raise ArtifactValidationError("prediction record regime is invalid")
        if record["provenance"] not in {
            "confirmed", "photosensor", "reconstructed", "model_inferred", "unknown"
        }:
            raise ArtifactValidationError("prediction record provenance is invalid")
        for method in ("model", "persistence", "recent_cycle"):
            if method not in record:
                continue
            errors = record[method]
            if not isinstance(errors, dict) or set(errors) != {"air", "mass"}:
                raise ArtifactValidationError(
                    f"prediction record {method} fields are invalid"
                )
            for state, error in errors.items():
                _real(error, f"prediction record {method}.{state}")
        key = (record["origin_at"], horizon)
        if key in actual_record_keys:
            raise ArtifactValidationError("prediction record keys must be unique")
        actual_record_keys.add(key)
        fold = fold_by_origin.get(record["origin_at"])
        if fold is None or horizon not in fold["horizons_hours"]:
            raise ArtifactValidationError("prediction record has no matching fold")
        if not _fold_is_error_free(fold):
            raise ArtifactValidationError("prediction record references an error fold")
        if valid_paired_24h_prediction_record(record, fold):
            valid_24_records.append(record)
            records_24h_by_regime[record["regime"]] += 1
    if actual_record_keys != expected_record_keys:
        raise ArtifactValidationError(
            "prediction records do not match scored fold horizons"
        )

    metrics = report["metrics"]
    _validate_metrics_structure(metrics, "backtest.metrics")
    _validate_backtest_v2_metrics_structure(metrics)
    if metrics["fold_count"] != len(folds) or metrics["scored_fold_count"] != error_free_folds:
        raise ArtifactValidationError(
            "backtest fold aggregate evidence is contradictory"
        )
    expected_action_evidence = {
        "confirmed": {
            "training_rows": confirmed_training_rows,
            "evaluation_targets": confirmed_evaluation_targets,
            "disjoint_fold_count": confirmed_disjoint_folds,
        }
    }
    if metrics.get("action_evidence") != expected_action_evidence:
        raise ArtifactValidationError(
            "backtest action evidence does not match fold receipts"
        )
    _validate_finite(report, "backtest")
    metrics_without_promotion = {
        key: value for key, value in metrics.items() if key != "promotion"
    }
    _validate_metric_semantics(metrics_without_promotion, "backtest.metrics")
    model_by_regime, persistence_by_regime = _scored_24h_by_regime(metrics)
    model_count = _summary(metrics, "model")["count"]
    persistence_count = _summary(metrics, "persistence")["count"]
    if (
        model_count != persistence_count
        or sum(model_by_regime.values()) != model_count
        or sum(persistence_by_regime.values()) != persistence_count
        or model_count != len(valid_24_records)
        or model_by_regime != records_24h_by_regime
        or persistence_by_regime != records_24h_by_regime
    ):
        raise ArtifactValidationError(
            "backtest 24-hour aggregate, regime, and prediction record evidence is contradictory"
        )
    _promotion_evidence(metrics)
    return report


class ArtifactRegistry:
    """Local candidate/accepted registry; never touches PostgreSQL or OpenHAB."""

    def __init__(self, directory=DEFAULT_STATE_DIRECTORY):
        self.directory = Path(directory).expanduser()
        self.candidate_path = self.directory / "candidate.json"
        self.accepted_path = self.directory / "accepted.json"
        self.previous_path = self.directory / "previous.json"
        self.backtest_report_path = self.directory / "backtest-report.json"
        self.lock_path = self.directory / ".registry.lock"
        self.last_load_source = None
        self.last_load_reason = None

    @contextmanager
    def _locked(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(self.lock_path, flags, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def save_candidate(self, artifact):
        validate_artifact(artifact)
        payload = asdict(artifact)
        with self._locked():
            _atomic_json_write(self.candidate_path, payload)
        return artifact

    def save_backtest_report(self, report):
        _validate_backtest_report(report)
        with self._locked():
            _atomic_json_write(self.backtest_report_path, report)
        return report

    def _read_bytes(self, path):
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
            os, "O_NOFOLLOW", 0
        )
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError as exc:
            raise ArtifactUnavailable(
                f"artifact is unavailable: {path.name}"
            ) from exc
        except OSError as exc:
            raise ArtifactUnavailable(
                f"artifact could not be opened safely: {path.name}"
            ) from exc
        try:
            stat_result = os.fstat(descriptor)
            with os.fdopen(descriptor, "rb") as source:
                descriptor = None
                data = source.read()
        except OSError as exc:
            raise ArtifactUnavailable(
                f"artifact could not be read: {path.name}"
            ) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
        return data, stat_result

    @staticmethod
    def _decode(data):
        text = data.decode("utf-8")
        return json.loads(text)

    def _load_candidate(self):
        if self.candidate_path.is_symlink():
            raise ArtifactValidationError(
                "artifact path must not be a symbolic link: candidate.json"
            )
        data, _ = self._read_bytes(self.candidate_path)
        try:
            return _artifact_from_payload(self._decode(data))
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ArtifactValidationError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
            RecursionError,
        ) as exc:
            if isinstance(exc, ArtifactValidationError):
                raise
            raise ArtifactValidationError(
                f"candidate artifact is corrupt: {exc}"
            ) from exc

    @staticmethod
    def _artifact_errors():
        return (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ArtifactValidationError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
            RecursionError,
        )

    def _decode_validated(self, data, label):
        try:
            artifact = _artifact_from_payload(self._decode(data))
            validate_artifact(artifact, require_eligible=True)
            return artifact
        except self._artifact_errors() as exc:
            if isinstance(exc, ArtifactValidationError):
                raise
            raise ArtifactValidationError(
                f"{label} artifact is corrupt: {exc}"
            ) from exc

    def promote_candidate(self):
        with self._locked():
            # The candidate is fully validated before current or previous moves.
            candidate = self._load_candidate()
            validate_artifact(candidate, require_eligible=True)

            try:
                os.lstat(self.accepted_path)
            except FileNotFoundError:
                pass
            else:
                data, stat_result = self._read_bytes(self.accepted_path)
                try:
                    accepted = self._decode_validated(data, "accepted")
                except ArtifactValidationError:
                    # Preserve an already verified previous slot; a corrupt current
                    # generation is never rotated into it.
                    self._quarantine_accepted(stat_result)
                else:
                    _atomic_json_write(self.previous_path, asdict(accepted))
            _atomic_json_write(self.accepted_path, asdict(candidate))
        return candidate

    def _quarantine_path(self, path, label, expected_stat=None):
        try:
            current = os.lstat(path)
        except FileNotFoundError as exc:
            raise ArtifactUnavailable(
                f"{label} artifact disappeared during diagnosis"
            ) from exc
        if expected_stat is not None and (
            current.st_dev != expected_stat.st_dev
            or current.st_ino != expected_stat.st_ino
        ):
            raise ArtifactUnavailable(
                f"{label} artifact changed during corruption diagnosis"
            )
        suffix = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = None
        target_descriptor = None
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        for counter in range(10000):
            candidate = self.directory / (
                f"{path.name}.corrupt-{suffix}-{os.getpid()}-{counter:04d}"
            )
            try:
                target_descriptor = os.open(candidate, flags, 0o600)
                target = candidate
                break
            except FileExistsError:
                continue
            except OSError as exc:
                raise ArtifactUnavailable(
                    f"{label} artifact could not reserve quarantine safely"
                ) from exc
        if target is None:
            raise ArtifactUnavailable(
                f"{label} artifact quarantine namespace is exhausted"
            )
        source_descriptor = None
        try:
            source_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
                os, "O_NOFOLLOW", 0
            )
            source_descriptor = os.open(path, source_flags)
            source_stat = os.fstat(source_descriptor)
            if expected_stat is not None and (
                source_stat.st_dev != expected_stat.st_dev
                or source_stat.st_ino != expected_stat.st_ino
            ):
                raise ArtifactUnavailable(
                    f"{label} artifact changed during corruption quarantine"
                )
            while True:
                chunk = os.read(source_descriptor, 1024 * 1024)
                if not chunk:
                    break
                view = memoryview(chunk)
                while view:
                    written = os.write(target_descriptor, view)
                    view = view[written:]
            os.fsync(target_descriptor)
            os.close(target_descriptor)
            target_descriptor = None
            current = os.lstat(path)
            if expected_stat is not None and (
                current.st_dev != expected_stat.st_dev
                or current.st_ino != expected_stat.st_ino
            ):
                raise ArtifactUnavailable(
                    f"{label} artifact changed during corruption quarantine"
                )
            os.unlink(path)
            _fsync_directory(self.directory)
            return target
        except Exception:
            if target_descriptor is not None:
                os.close(target_descriptor)
                target_descriptor = None
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
            raise
        finally:
            if source_descriptor is not None:
                os.close(source_descriptor)
            if target_descriptor is not None:
                os.close(target_descriptor)

    def _quarantine_accepted(self, expected_stat=None):
        return self._quarantine_path(
            self.accepted_path, "accepted", expected_stat
        )

    def _quarantine_previous(self, expected_stat=None):
        return self._quarantine_path(
            self.previous_path, "previous", expected_stat
        )

    def load_accepted(self):
        with self._locked():
            self.last_load_source = None
            self.last_load_reason = None
            data, stat_result = self._read_bytes(self.accepted_path)
            try:
                artifact = self._decode_validated(data, "accepted")
            except ArtifactValidationError:
                quarantined = self._quarantine_accepted(stat_result)
                try:
                    previous_data, previous_stat = self._read_bytes(
                        self.previous_path
                    )
                except ArtifactUnavailable as previous_exc:
                    raise ArtifactUnavailable(
                        "accepted artifact was corrupt and quarantined as "
                        f"{quarantined.name}; no verified previous generation is available"
                    ) from previous_exc
                try:
                    previous = self._decode_validated(
                        previous_data, "previous"
                    )
                except ArtifactValidationError as previous_exc:
                    previous_quarantine = self._quarantine_previous(previous_stat)
                    raise ArtifactUnavailable(
                        "accepted artifact was corrupt and quarantined as "
                        f"{quarantined.name}; previous artifact was invalid and "
                        f"quarantined as {previous_quarantine.name}"
                    ) from previous_exc
                _atomic_json_write(self.accepted_path, asdict(previous))
                self.last_load_source = "previous_restored"
                self.last_load_reason = (
                    "accepted model recovered from verified prior accepted generation"
                )
                return previous
            self.last_load_source = "accepted"
            return artifact
