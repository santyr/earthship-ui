"""Validated, atomic local registry for reproducible thermal model artifacts."""

from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re

from .dynamics import validate_physics
from .schema import (
    BehaviorModel,
    DynamicsModel,
    SeasonalActionVocabulary,
    SOURCE_WEIGHTS,
    THERMAL_ITEMS,
    ThermalArtifact,
)

MODEL_SCHEMA = "earthship-thermal-model/v1"
THERMAL_UNITS = {
    "air": "F", "mass": "F", "glazing": "F",
    "outdoor": "F", "radiation": "W/m2",
}
DEFAULT_STATE_DIRECTORY = Path("~/.local/state/thermal-intel/models").expanduser()
_SHA_RE = re.compile(r"[0-9a-f]{7,64}\Z")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")


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
        raise ArtifactValidationError(f"{name} must be an ISO-8601 UTC string") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ArtifactValidationError(f"{name} must be UTC")
    return parsed


def _validate_finite(value, path="artifact"):
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ArtifactValidationError(f"{path} must be finite")
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            _validate_finite(nested, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_finite(nested, f"{path}[{index}]")
        return
    raise ArtifactValidationError(
        f"{path} contains unsupported value {type(value).__name__}"
    )


def _validate_behavior(model):
    if not isinstance(model, BehaviorModel) or model.version != 1:
        raise ArtifactValidationError("behavior model must be version 1")
    if not model.feature_names or len(set(model.feature_names)) != len(model.feature_names):
        raise ArtifactValidationError("behavior feature names must be nonempty and unique")
    for transition, coefficients in model.transitions.items():
        if not isinstance(transition, str) or not isinstance(coefficients, tuple):
            raise ArtifactValidationError("behavior transitions must preserve tuple coefficients")
        if coefficients and len(coefficients) != len(model.feature_names):
            raise ArtifactValidationError("behavior coefficient count must match features")
    modes = []
    for vocabulary in model.seasonal_vocabulary:
        if not isinstance(vocabulary, SeasonalActionVocabulary):
            raise ArtifactValidationError("seasonal vocabulary type is invalid")
        if vocabulary.mode not in {"spring", "warm", "fall_charge", "winter"}:
            raise ArtifactValidationError("seasonal vocabulary mode is invalid")
        modes.append(vocabulary.mode)
    if len(modes) != len(set(modes)):
        raise ArtifactValidationError("seasonal vocabulary modes must be unique")


def _validate_manifest(artifact):
    manifest = artifact.data_manifest
    required = {
        "start", "end", "sample_count", "items", "units",
        "canonical_rows_sha256", "event_counts_by_source",
        "fit_diagnostics", "constraints",
    }
    if not isinstance(manifest, dict) or not required <= set(manifest):
        raise ArtifactValidationError("data manifest is missing reproducibility fields")
    if manifest["items"] != THERMAL_ITEMS:
        raise ArtifactValidationError("artifact sensor identities do not match the contract")
    if manifest["units"] != THERMAL_UNITS:
        raise ArtifactValidationError("artifact sensor units do not match the contract")
    if not _DIGEST_RE.fullmatch(str(manifest["canonical_rows_sha256"])):
        raise ArtifactValidationError("dataset digest must be lowercase SHA-256")
    start = _iso_utc(manifest["start"], "data manifest start")
    end = _iso_utc(manifest["end"], "data manifest end")
    if start >= end:
        raise ArtifactValidationError("data manifest range must be chronological")
    if manifest["start"] != artifact.trained_from or manifest["end"] != artifact.trained_through:
        raise ArtifactValidationError("artifact training range must match the data manifest")
    if not isinstance(manifest["sample_count"], int) or manifest["sample_count"] <= 0:
        raise ArtifactValidationError("data manifest sample count must be positive")
    counts = manifest["event_counts_by_source"]
    if not isinstance(counts, dict) or not set(counts) <= set(SOURCE_WEIGHTS):
        raise ArtifactValidationError("action provenance sources do not match the contract")
    if any(not isinstance(count, int) or count < 0 for count in counts.values()):
        raise ArtifactValidationError("action provenance counts must be nonnegative integers")
    if not isinstance(manifest["fit_diagnostics"], dict) or not manifest["fit_diagnostics"]:
        raise ArtifactValidationError("fitted diagnostics must be recorded")
    if not isinstance(manifest["constraints"], dict) or not manifest["constraints"]:
        raise ArtifactValidationError("fitted constraints must be recorded")


def _promotion_gates(metrics):
    promotion = metrics.get("promotion") if isinstance(metrics, dict) else None
    gates = promotion.get("gates") if isinstance(promotion, dict) else None
    required = {
        "physics_valid", "finite_metrics", "at_least_two_folds",
        "air_24h_beats_persistence",
    }
    if not isinstance(gates, dict) or set(gates) != required:
        raise ArtifactPromotionRefused(
            "candidate lacks the provisional promotion gates"
        )
    try:
        model_24 = metrics["overall"]["model"]["air"]["24"]["mae"]
        persistence_24 = metrics["overall"]["persistence"]["air"]["24"]["mae"]
        scored_folds = metrics["scored_fold_count"]
    except (KeyError, TypeError) as exc:
        raise ArtifactPromotionRefused(
            "candidate promotion evidence is incomplete"
        ) from exc
    numeric = (int, float)
    if (
        isinstance(model_24, bool)
        or not isinstance(model_24, numeric)
        or isinstance(persistence_24, bool)
        or not isinstance(persistence_24, numeric)
        or isinstance(scored_folds, bool)
        or not isinstance(scored_folds, int)
    ):
        raise ArtifactPromotionRefused(
            "candidate promotion evidence has invalid numeric types"
        )
    actual = {
        "physics_valid": True,
        "finite_metrics": True,
        "at_least_two_folds": scored_folds >= 2,
        "air_24h_beats_persistence": model_24 < persistence_24,
    }
    mismatched = sorted(
        name for name in required if gates.get(name) is not actual[name]
    )
    if mismatched:
        raise ArtifactPromotionRefused(
            "candidate report does not match evidence for gates: "
            + ", ".join(mismatched)
        )
    failed = sorted(name for name, passed in actual.items() if not passed)
    eligible = all(actual.values())
    if promotion.get("eligible") is not eligible:
        raise ArtifactPromotionRefused(
            "candidate eligibility does not match evidence"
        )
    if promotion.get("shadow_only") is not True:
        raise ArtifactPromotionRefused(
            "candidate promotion must remain shadow-only"
        )
    if failed:
        raise ArtifactPromotionRefused(
            "candidate promotion refused: " + ", ".join(failed)
        )


def validate_artifact(artifact, *, require_promotion=False):
    """Validate type fidelity, provenance, chronology, physics, and all numbers."""
    if not isinstance(artifact, ThermalArtifact):
        raise ArtifactValidationError("artifact must be a ThermalArtifact")
    if artifact.schema != MODEL_SCHEMA:
        raise ArtifactValidationError(f"artifact schema must be {MODEL_SCHEMA}")
    _iso_utc(artifact.created_at, "artifact created_at")
    trained_from = _iso_utc(artifact.trained_from, "artifact trained_from")
    trained_through = _iso_utc(artifact.trained_through, "artifact trained_through")
    if trained_from >= trained_through:
        raise ArtifactValidationError("artifact training range must be chronological")
    if not _SHA_RE.fullmatch(str(artifact.code_revision)):
        raise ArtifactValidationError("code revision must be a hexadecimal revision")
    if not isinstance(artifact.dynamics, DynamicsModel):
        raise ArtifactValidationError("artifact dynamics type is invalid")
    try:
        validate_physics(artifact.dynamics)
    except (KeyError, TypeError, ValueError) as exc:
        raise ArtifactValidationError(f"artifact dynamics are invalid: {exc}") from exc
    _validate_behavior(artifact.behavior)
    required_splits = {
        "overall", "by_regime", "by_horizon", "by_provenance", "promotion",
    }
    if not isinstance(artifact.metrics, dict) or not required_splits <= set(artifact.metrics):
        raise ArtifactValidationError("artifact metrics are missing required evidence splits")
    _validate_manifest(artifact)
    _validate_finite(asdict(artifact))
    if require_promotion:
        _promotion_gates(artifact.metrics)
    return artifact


def _artifact_payload(artifact):
    validate_artifact(artifact)
    return asdict(artifact)


def _artifact_from_payload(payload):
    if not isinstance(payload, dict):
        raise ArtifactValidationError("artifact JSON root must be an object")
    expected = {
        "schema", "created_at", "trained_from", "trained_through", "code_revision",
        "dynamics", "behavior", "metrics", "data_manifest",
    }
    if set(payload) != expected:
        raise ArtifactValidationError("artifact JSON fields do not match the schema")
    dynamics = payload["dynamics"]
    behavior = payload["behavior"]
    if not isinstance(dynamics, dict) or not isinstance(behavior, dict):
        raise ArtifactValidationError("model payloads must be objects")
    vocabulary = tuple(
        SeasonalActionVocabulary(
            mode=item["mode"],
            action_states=tuple(
                (str(action), tuple(states))
                for action, states in item.get("action_states", ())
            ),
            transitions=tuple(item.get("transitions", ())),
            airflow_levels=tuple(item.get("airflow_levels", ())),
            boosted_windows=tuple(
                tuple(window) for window in item.get("boosted_windows", ())
            ),
        )
        for item in behavior.get("seasonal_vocabulary", ())
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
            air_coefficients=dict(dynamics["air_coefficients"]),
            mass_coefficients=dict(dynamics["mass_coefficients"]),
            glazing_observation_coefficients=dict(
                dynamics["glazing_observation_coefficients"]
            ),
        ),
        behavior=BehaviorModel(
            version=behavior["version"],
            feature_names=tuple(behavior["feature_names"]),
            transitions={
                name: tuple(coefficients)
                for name, coefficients in behavior["transitions"].items()
            },
            seasonal_vocabulary=vocabulary,
        ),
        metrics=payload["metrics"],
        data_manifest=payload["data_manifest"],
    )
    return validate_artifact(artifact)


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    encoded = json.dumps(
        payload, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": ")
    ) + "\n"
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_TRUNC
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _validate_backtest_report(report):
    if not isinstance(report, dict) or report.get("schema") != "earthship-thermal-backtest/v1":
        raise ArtifactValidationError(
            "backtest report schema must be earthship-thermal-backtest/v1"
        )
    _iso_utc(report.get("generated_at"), "backtest generated_at")
    folds = report.get("folds")
    if not isinstance(folds, list):
        raise ArtifactValidationError("backtest folds must be a list")
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
        horizons = fold.get("horizons_hours")
        if (
            not isinstance(horizons, list)
            or horizons != sorted(set(horizons))
            or any(value not in {1, 6, 12, 24, 48, 72} for value in horizons)
        ):
            raise ArtifactValidationError("backtest fold horizons are invalid")
    if not isinstance(report.get("metrics"), dict):
        raise ArtifactValidationError("backtest metrics must be an object")
    _validate_finite(report, "backtest")
    return report


class ArtifactRegistry:
    """Local candidate/accepted registry; never touches PostgreSQL or OpenHAB."""

    def __init__(self, directory=DEFAULT_STATE_DIRECTORY):
        self.directory = Path(directory).expanduser()
        self.candidate_path = self.directory / "candidate.json"
        self.accepted_path = self.directory / "accepted.json"
        self.backtest_report_path = self.directory / "backtest-report.json"

    def save_candidate(self, artifact):
        validate_artifact(artifact)
        _atomic_json_write(self.candidate_path, _artifact_payload(artifact))
        return artifact


    def save_backtest_report(self, report):
        _validate_backtest_report(report)
        _atomic_json_write(self.backtest_report_path, report)
        return report

    def _load(self, path):
        if path.is_symlink():
            raise ArtifactValidationError(
                f"artifact path must not be a symbolic link: {path.name}"
            )
        try:
            with path.open("r", encoding="utf-8") as source:
                payload = json.load(source)
            return _artifact_from_payload(payload)
        except FileNotFoundError as exc:
            raise ArtifactUnavailable(f"artifact is unavailable: {path.name}") from exc

    def promote_candidate(self):
        candidate = self._load(self.candidate_path)
        validate_artifact(candidate, require_promotion=True)
        _atomic_json_write(self.accepted_path, _artifact_payload(candidate))
        return candidate

    def _quarantine_accepted(self):
        suffix = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = self.directory / f"accepted.json.corrupt-{suffix}"
        counter = 1
        while target.exists():
            target = self.directory / f"accepted.json.corrupt-{suffix}-{counter}"
            counter += 1
        os.replace(self.accepted_path, target)
        _fsync_directory(self.directory)
        return target

    def load_accepted(self):
        try:
            return self._load(self.accepted_path)
        except ArtifactUnavailable:
            raise
        except (ArtifactValidationError, KeyError, TypeError, json.JSONDecodeError) as exc:
            try:
                quarantined = self._quarantine_accepted()
            except FileNotFoundError:
                raise ArtifactUnavailable("accepted artifact is unavailable") from exc
            raise ArtifactUnavailable(
                f"accepted artifact was corrupt and quarantined as {quarantined.name}"
            ) from exc
