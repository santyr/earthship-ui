"""Validated, race-safe local registry for reproducible thermal artifacts."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
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

MODEL_SCHEMA = "earthship-thermal-model/v1"
BACKTEST_SCHEMA = "earthship-thermal-backtest/v1"
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
    if model.version != 1 or model.step_minutes != 5:
        raise ArtifactValidationError(
            "dynamics model must be version 1 at five-minute steps"
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
        "mass_observer": {
            "kind": "causal_ema",
            "source_role": "mass",
            "time_constant_minutes": MASS_OBSERVER_TAU_MINUTES,
        },
        "envelope_identification": {
            "max_radiation_wm2": ENVELOPE_MAX_RADIATION_WM2,
            "vent_forcing": 0.0,
        },
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
    for split_name, allowed in (
        ("by_regime", {"warm", "winter", "shoulder"}),
        (
            "by_provenance",
            {"confirmed", "photosensor", "reconstructed", "model_inferred", "unknown"},
        ),
    ):
        split = metrics[split_name]
        if not isinstance(split, dict) or not set(split) <= allowed:
            raise ArtifactValidationError(f"{path}.{split_name} fields are unknown")
        for name, summary in split.items():
            _split_summary_shape(
                summary, f"{path}.{split_name}.{name}", split_pattern
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
    *, physics_valid, finite_metrics, scored_fold_count, model_24, persistence_24
):
    """Return the only provisional shadow gates from explicit evidence."""
    return {
        "physics_valid": physics_valid is True,
        "finite_metrics": finite_metrics is True,
        "at_least_two_folds": scored_fold_count >= 2,
        "air_24h_beats_persistence": (
            model_24["count"] > 0
            and persistence_24["count"] > 0
            and model_24["mae"] < persistence_24["mae"]
        ),
    }


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
    actual = provisional_promotion_gates(
        physics_valid=True,
        finite_metrics=True,
        scored_fold_count=scored_folds,
        model_24=model,
        persistence_24=persistence,
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


def _validate_backtest_report(report):
    if not isinstance(report, dict) or report.get("schema") != BACKTEST_SCHEMA:
        raise ArtifactValidationError(
            f"backtest report schema must be {BACKTEST_SCHEMA}"
        )
    _iso_utc(report.get("generated_at"), "backtest generated_at")
    folds = report.get("folds")
    if not isinstance(folds, list):
        raise ArtifactValidationError("backtest folds must be a list")
    confirmed_training_rows = 0
    confirmed_evaluation_targets = 0
    confirmed_disjoint_folds = 0
    for fold in folds:
        if not isinstance(fold, dict):
            raise ArtifactValidationError("backtest fold must be an object")
        train_start = _iso_utc(fold.get("train_start"), "fold train_start")
        train_end = _iso_utc(fold.get("train_end"), "fold train_end")
        prediction_start = _iso_utc(
            fold.get("prediction_start"), "fold prediction_start"
        )
        prediction_end = _iso_utc(
            fold.get("prediction_end"), "fold prediction_end"
        )
        if not train_start <= train_end < prediction_start <= prediction_end:
            raise ArtifactValidationError(
                "backtest fold ranges must be strictly chronological"
            )
        action_provenance = fold.get("action_provenance")
        if action_provenance is None:
            raise ArtifactValidationError(
                "backtest fold action provenance is required"
            )
        if action_provenance is not None:
            if (
                not isinstance(action_provenance, dict)
                or set(action_provenance) != {"training", "evaluation_targets"}
            ):
                raise ArtifactValidationError(
                    "backtest fold action provenance fields are invalid"
                )
            provenance_labels = {
                "confirmed", "photosensor", "reconstructed",
                "model_inferred", "unknown",
            }
            for split_name, counts in action_provenance.items():
                if not isinstance(counts, dict) or set(counts) != provenance_labels:
                    raise ArtifactValidationError(
                        f"backtest fold {split_name} provenance fields are invalid"
                    )
                for label, count in counts.items():
                    _integer(count, f"backtest fold {split_name}.{label}")
            if "model_error" not in fold:
                training_confirmed = action_provenance["training"]["confirmed"]
                evaluation_confirmed = action_provenance["evaluation_targets"]["confirmed"]
                confirmed_training_rows += training_confirmed
                confirmed_evaluation_targets += evaluation_confirmed
                if training_confirmed > 0 and evaluation_confirmed > 0:
                    confirmed_disjoint_folds += 1
        horizons = fold.get("horizons_hours")
        if (
            not isinstance(horizons, list)
            or horizons != sorted(set(horizons))
            or any(value not in {1, 6, 12, 24, 48, 72} for value in horizons)
        ):
            raise ArtifactValidationError("backtest fold horizons are invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        raise ArtifactValidationError("backtest metrics must be an object")
    action_evidence = metrics.get("action_evidence")
    expected_action_evidence = {
        "confirmed": {
            "training_rows": confirmed_training_rows,
            "evaluation_targets": confirmed_evaluation_targets,
            "disjoint_fold_count": confirmed_disjoint_folds,
        }
    }
    if action_evidence != expected_action_evidence:
        raise ArtifactValidationError(
            "backtest action evidence does not match fold receipts"
        )
    _validate_finite(report, "backtest")
    promotion = metrics.get("promotion")
    metrics_without_promotion = {
        key: value for key, value in metrics.items() if key != "promotion"
    }
    _validate_metric_semantics(metrics_without_promotion, "backtest.metrics")
    if promotion is not None:
        _promotion_shape(metrics)
    records = report.get("prediction_records", [])
    if not isinstance(records, list):
        raise ArtifactValidationError("prediction records must be a list")
    for record in records:
        if not isinstance(record, dict):
            raise ArtifactValidationError("prediction record must be an object")
        origin = _iso_utc(record.get("origin_at"), "prediction origin_at")
        target = _iso_utc(record.get("target_at"), "prediction target_at")
        if origin >= target:
            raise ArtifactValidationError(
                "prediction target must be after its origin"
            )
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
