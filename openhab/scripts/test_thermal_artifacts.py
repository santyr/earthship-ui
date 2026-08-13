from copy import deepcopy
from dataclasses import replace
import pytest

import thermal_model.artifacts as artifacts_module

from thermal_model.artifacts import (
    THERMAL_UNITS,
    ArtifactPromotionRefused,
    ArtifactRegistry,
    ArtifactUnavailable,
    ArtifactValidationError,
)
from thermal_model.schema import (
    BehaviorModel,
    DynamicsModel,
    SeasonalActionVocabulary,
    THERMAL_ITEMS,
    ThermalArtifact,
)


def stable_dynamics():
    return DynamicsModel(
        version=1,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.018,
            "mass_exchange": 0.040,
            "solar_unshaded": 0.00015,
            "solar_indoor_closed": 0.00006,
            "solar_outdoor": 0.00003,
            "vent_exchange": 0.070,
            "bias": 0.002,
        },
        mass_coefficients={
            "air_exchange": 0.008,
            "solar_unshaded": 0.000035,
            "solar_indoor_closed": 0.000014,
            "solar_outdoor": 0.000007,
        },
        glazing_observation_coefficients={
            "intercept": 4.0,
            "air": 0.72,
            "outdoor": 0.20,
            "solar_unshaded": 0.0030,
            "solar_indoor_closed": 0.0013,
            "solar_outdoor": 0.0008,
        },
    )


def valid_artifact(**changes):
    artifact = ThermalArtifact(
        schema="earthship-thermal-model/v1",
        created_at="2026-08-13T12:00:00Z",
        trained_from="2026-06-01T00:00:00Z",
        trained_through="2026-08-01T00:00:00Z",
        code_revision="0123456789abcdef0123456789abcdef01234567",
        dynamics=stable_dynamics(),
        behavior=BehaviorModel(
            version=1,
            feature_names=("intercept", "outdoor_minus_air"),
            transitions={
                "vent_open": (0.1, -0.2),
                "vent_close": (),
            },
            seasonal_vocabulary=(
                SeasonalActionVocabulary(
                    mode="warm",
                    action_states=(("vent", ("closed", "open")),),
                    transitions=("vent_open",),
                    airflow_levels=("closed", "baseline"),
                    boosted_windows=(),
                ),
            ),
        ),
        metrics={
            "fold_count": 2,
            "scored_fold_count": 2,
            "overall": {
                "model": {"air": {"24": {"mae": 0.5}}},
                "persistence": {"air": {"24": {"mae": 1.0}}},
            },
            "by_regime": {"warm": {"air_24h_mae": 0.5}},
            "by_horizon": {"24": {"air_mae": 0.5}},
            "by_provenance": {"confirmed": {"air_24h_mae": 0.5}},
            "promotion": {
                "eligible": True,
                "shadow_only": True,
                "gates": {
                    "physics_valid": True,
                    "finite_metrics": True,
                    "at_least_two_folds": True,
                    "air_24h_beats_persistence": True,
                },
            },
        },
        data_manifest={
            "start": "2026-06-01T00:00:00Z",
            "end": "2026-08-01T00:00:00Z",
            "sample_count": 17568,
            "items": dict(THERMAL_ITEMS),
            "units": dict(THERMAL_UNITS),
            "canonical_rows_sha256": "a" * 64,
            "event_counts_by_source": {
                "nostr_confirmed": 8,
                "historical_reconstruction": 10,
            },
            "fit_diagnostics": {
                "fitted_pairs": 17000,
                "action_label_coverage_fraction": 0.97,
            },
            "constraints": {
                "step_minutes": 5,
                "stability_tolerance": 1e-9,
                "output_range_f": [-40.0, 140.0],
            },
        },
    )
    return replace(artifact, **changes)


def test_artifact_write_is_atomic_and_corruption_is_quarantined(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    registry.save_candidate(valid_artifact())
    registry.promote_candidate()

    loaded = registry.load_accepted()
    assert loaded.schema == "earthship-thermal-model/v1"
    assert isinstance(loaded.dynamics, DynamicsModel)
    assert isinstance(loaded.behavior.seasonal_vocabulary, tuple)
    assert loaded.behavior.seasonal_vocabulary[0].action_states == (
        ("vent", ("closed", "open")),
    )
    assert not registry.candidate_path.with_suffix(".json.tmp").exists()

    registry.accepted_path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ArtifactUnavailable, match="quarantined"):
        registry.load_accepted()
    quarantined = list(tmp_path.glob("accepted.json.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "{broken"
    assert not registry.accepted_path.exists()




def test_recursive_nonfinite_value_is_rejected_before_write(tmp_path):
    metrics = deepcopy(valid_artifact().metrics)
    metrics["by_regime"]["warm"]["air_24h_mae"] = float("nan")
    registry = ArtifactRegistry(tmp_path)

    with pytest.raises(ArtifactValidationError, match="finite"):
        registry.save_candidate(valid_artifact(metrics=metrics))
    assert not registry.candidate_path.exists()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"code_revision": "working-tree"}, "code revision"),
        ({"trained_through": "2026-05-01T00:00:00Z"}, "chronological"),
    ],
)
def test_revision_and_chronology_are_validated(tmp_path, change, message):
    registry = ArtifactRegistry(tmp_path)
    with pytest.raises(ArtifactValidationError, match=message):
        registry.save_candidate(valid_artifact(**change))


def test_identity_units_digest_and_physics_are_validated(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    for key, replacement, message in (
        ("items", {**THERMAL_ITEMS, "air": "Wrong_Item"}, "identities"),
        ("units", {**THERMAL_UNITS, "air": "C"}, "units"),
        ("canonical_rows_sha256", "not-a-digest", "SHA-256"),
    ):
        manifest = deepcopy(valid_artifact().data_manifest)
        manifest[key] = replacement
        with pytest.raises(ArtifactValidationError, match=message):
            registry.save_candidate(valid_artifact(data_manifest=manifest))

    dynamics = stable_dynamics()
    bad_air = dict(dynamics.air_coefficients)
    bad_air["outside_exchange"] = -0.01
    with pytest.raises(ArtifactValidationError, match="dynamics"):
        registry.save_candidate(
            valid_artifact(dynamics=replace(dynamics, air_coefficients=bad_air))
        )


def test_refused_candidate_does_not_replace_accepted_artifact(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    accepted = valid_artifact(code_revision="a" * 40)
    registry.save_candidate(accepted)
    registry.promote_candidate()

    metrics = deepcopy(valid_artifact().metrics)
    metrics["promotion"]["eligible"] = False
    metrics["promotion"]["gates"]["air_24h_beats_persistence"] = False
    registry.save_candidate(
        valid_artifact(code_revision="b" * 40, metrics=metrics)
    )
    with pytest.raises(ArtifactPromotionRefused, match="air_24h"):
        registry.promote_candidate()

    assert registry.load_accepted().code_revision == "a" * 40


def test_backtest_report_write_is_canonical_atomic_and_finite(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    report = {
        "schema": "earthship-thermal-backtest/v1",
        "generated_at": "2026-08-13T12:00:00Z",
        "folds": [
            {
                "train_start": "2026-06-01T00:00:00Z",
                "train_end": "2026-06-14T23:55:00Z",
                "prediction_start": "2026-06-15T00:00:00Z",
                "prediction_end": "2026-06-18T00:00:00Z",
                "horizons_hours": [1, 6, 12, 24, 48, 72],
            }
        ],
        "metrics": {"mae": 0.5},
    }
    registry.save_backtest_report(report)
    first = registry.backtest_report_path.read_bytes()
    assert first.endswith(b"\n")
    registry.save_backtest_report(deepcopy(report))
    assert registry.backtest_report_path.read_bytes() == first
    assert not registry.backtest_report_path.with_name(
        "backtest-report.json.tmp"
    ).exists()

    invalid = deepcopy(report)
    invalid["metrics"]["mae"] = float("inf")
    with pytest.raises(ArtifactValidationError, match="finite"):
        registry.save_backtest_report(invalid)
    assert registry.backtest_report_path.read_bytes() == first



def test_promotion_recomputes_provisional_gates_instead_of_trusting_flags(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    metrics = deepcopy(valid_artifact().metrics)
    metrics["scored_fold_count"] = 1
    metrics["overall"]["model"]["air"]["24"]["mae"] = 2.0
    metrics["overall"]["persistence"]["air"]["24"]["mae"] = 1.0
    assert all(metrics["promotion"]["gates"].values())
    assert metrics["promotion"]["eligible"] is True

    registry.save_candidate(valid_artifact(metrics=metrics))
    with pytest.raises(ArtifactPromotionRefused, match="does not match evidence"):
        registry.promote_candidate()
    assert not registry.accepted_path.exists()



def test_atomic_writer_fsyncs_file_replaces_then_fsyncs_directory(
    tmp_path, monkeypatch
):
    events = []
    real_fsync = artifacts_module.os.fsync
    real_replace = artifacts_module.os.replace

    def tracked_fsync(descriptor):
        events.append("fsync")
        return real_fsync(descriptor)

    def tracked_replace(source, target):
        events.append("replace")
        return real_replace(source, target)

    monkeypatch.setattr(artifacts_module.os, "fsync", tracked_fsync)
    monkeypatch.setattr(artifacts_module.os, "replace", tracked_replace)
    ArtifactRegistry(tmp_path).save_candidate(valid_artifact())

    assert events == ["fsync", "replace", "fsync"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scored_fold_count", 2.5),
        ("model_mae", "0.5"),
        ("persistence_mae", True),
    ],
)
def test_promotion_evidence_preserves_numeric_types(
    tmp_path, field, value
):
    registry = ArtifactRegistry(tmp_path)
    metrics = deepcopy(valid_artifact().metrics)
    if field == "scored_fold_count":
        metrics[field] = value
    elif field == "model_mae":
        metrics["overall"]["model"]["air"]["24"]["mae"] = value
    else:
        metrics["overall"]["persistence"]["air"]["24"]["mae"] = value
    registry.save_candidate(valid_artifact(metrics=metrics))

    with pytest.raises(ArtifactPromotionRefused, match="numeric types"):
        registry.promote_candidate()



def test_atomic_writer_never_follows_preexisting_temporary_symlink(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    victim = tmp_path / "outside.json"
    victim.write_text("operator-owned", encoding="utf-8")
    temporary = registry.candidate_path.with_name("candidate.json.tmp")
    temporary.symlink_to(victim)

    with pytest.raises(OSError):
        registry.save_candidate(valid_artifact())
    assert victim.read_text(encoding="utf-8") == "operator-owned"
    assert not registry.candidate_path.exists()


def test_promotion_rejects_candidate_symlink_without_touching_target(tmp_path):
    registry = ArtifactRegistry(tmp_path / "registry")
    registry.save_candidate(valid_artifact())
    outside = tmp_path / "outside-candidate.json"
    registry.candidate_path.replace(outside)
    registry.candidate_path.symlink_to(outside)

    with pytest.raises(ArtifactValidationError, match="symbolic link"):
        registry.promote_candidate()
    assert outside.exists()
    assert not registry.accepted_path.exists()
