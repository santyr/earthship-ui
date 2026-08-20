from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
import threading

import pytest

import thermal_model.artifacts as artifacts_module

from thermal_model.behavior import (
    AIRFLOW_LEVELS,
    FEATURE_NAMES,
    TRANSITIONS,
)
from thermal_model.dynamics import (
    AIR_BOUNDS,
    AIR_NAMES,
    GLAZING_NAMES,
    MASS_BOUNDS,
    MASS_NAMES,
    MAX_VENT_FORCING,
    OUTPUT_RANGE_F,
    STABILITY_TOLERANCE,
)
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
    total_pairs = 17567
    fitted_pairs = 17000
    artifact = ThermalArtifact(
        schema="earthship-thermal-model/v1",
        created_at="2026-08-13T12:00:00Z",
        trained_from="2026-06-01T00:00:00Z",
        trained_through="2026-08-01T00:00:00Z",
        code_revision="0123456789abcdef0123456789abcdef01234567",
        dynamics=stable_dynamics(),
        behavior=BehaviorModel(
            version=1,
            feature_names=FEATURE_NAMES,
            transitions={
                transition: (
                    tuple(0.0 for _ in FEATURE_NAMES)
                    if transition == "vent_open"
                    else ()
                )
                for transition in TRANSITIONS
            },
            seasonal_vocabulary=(
                SeasonalActionVocabulary(
                    mode="warm",
                    action_states=(
                        ("indoor_shade", ("closed", "open")),
                        ("outdoor_shade", ("absent", "present")),
                        ("vent", ("closed", "open")),
                    ),
                    transitions=("vent_open",),
                    airflow_levels=tuple(AIRFLOW_LEVELS),
                    boosted_windows=((390, 420),),
                ),
            ),
        ),
        metrics={
            "fold_count": 2,
            "scored_fold_count": 2,
            "overall": {
                "model": {
                    "air": {
                        "24": {
                            "count": 2, "mae": 0.5,
                            "rmse": 0.6, "bias": 0.1,
                        }
                    }
                },
                "persistence": {
                    "air": {
                        "24": {
                            "count": 2, "mae": 1.0,
                            "rmse": 1.1, "bias": -0.2,
                        }
                    }
                },
            },
            "by_regime": {"warm": {"air_24h_mae": 0.5}},
            "by_horizon": {"24": {"air_mae": 0.5}},
            "by_provenance": {"confirmed": {"air_24h_mae": 0.5}},
            "prediction_interval_coverage": {
                "air": {
                    "24": {
                        "nominal": 0.9, "count": 1,
                        "covered": 1, "fraction": 1.0,
                    }
                }
            },
            "behavior": {
                "available": True,
                "label_count": 2,
                "precision": 1.0,
                "recall": 1.0,
                "median_timing_error_minutes": 5.0,
                "classification_probability": 0.5,
            },
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
            "sample_counts_by_mode": {
                "unknown": 568,
                "fall_charge": 4250,
                "winter": 4250,
                "spring": 4250,
                "warm": 4250,
            },
            "rejected_counts": {"missing_required": 3},
            "auxiliary_exclusion_counts": {"glazing_missing": 5},
            "items": dict(THERMAL_ITEMS),
            "units": dict(THERMAL_UNITS),
            "canonical_rows_sha256": "a" * 64,
            "event_counts_by_source": {
                "nostr_confirmed": 8,
                "historical_reconstruction": 10,
            },
            "fit_diagnostics": {
                "total_consecutive_pairs": total_pairs,
                "fitted_pairs": fitted_pairs,
                "excluded_passive_pairs": 300,
                "excluded_unknown_action_pairs": 267,
                "auxiliary_glazing_fitted_rows": 16000,
                "auxiliary_glazing_skipped_rows": 1000,
                "action_label_coverage_fraction": fitted_pairs / total_pairs,
            },
            "constraints": {
                "step_minutes": 5,
                "air_coefficient_names": list(AIR_NAMES),
                "mass_coefficient_names": list(MASS_NAMES),
                "glazing_observation_coefficient_names": list(GLAZING_NAMES),
                "air_bounds": [list(bound) for bound in AIR_BOUNDS],
                "mass_bounds": [list(bound) for bound in MASS_BOUNDS],
                "glazing_observation_bounds": [
                    [None, None, None, 0.0, 0.0, 0.0],
                    [None, None, None, None, None, None],
                ],
                "output_range_f": list(OUTPUT_RANGE_F),
                "max_vent_forcing": MAX_VENT_FORCING,
                "stability_tolerance": STABILITY_TOLERANCE,
            },
        },
    )
    return replace(artifact, **changes)


def test_artifact_accepts_exact_disjoint_action_evidence(tmp_path):
    metrics = deepcopy(valid_artifact().metrics)
    metrics["action_evidence"] = {
        "confirmed": {
            "training_rows": 8,
            "evaluation_targets": 2,
            "disjoint_fold_count": 1,
        }
    }
    registry = ArtifactRegistry(tmp_path)

    registry.save_candidate(valid_artifact(metrics=metrics))

    assert registry.candidate_path.exists()


def test_artifact_write_is_atomic_and_corruption_is_quarantined(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    registry.save_candidate(valid_artifact())
    registry.promote_candidate()

    loaded = registry.load_accepted()
    assert loaded.schema == "earthship-thermal-model/v1"
    assert isinstance(loaded.dynamics, DynamicsModel)
    assert isinstance(loaded.behavior.seasonal_vocabulary, tuple)
    assert loaded.behavior.seasonal_vocabulary[0].action_states == (
        ("indoor_shade", ("closed", "open")),
        ("outdoor_shade", ("absent", "present")),
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


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "boolean", "negative", "noninteger", "sum"],
)
def test_candidate_manifest_rejects_invalid_sample_counts_by_mode(
    tmp_path, mutation
):
    manifest = deepcopy(valid_artifact().data_manifest)
    counts = manifest["sample_counts_by_mode"]
    if mutation == "missing":
        del counts["winter"]
    elif mutation == "extra":
        counts["monsoon"] = 1
    elif mutation == "boolean":
        counts["winter"] = True
    elif mutation == "negative":
        counts["winter"] = -1
    elif mutation == "noninteger":
        counts["winter"] = 1.5
    else:
        counts["unknown"] += 1

    with pytest.raises(ArtifactValidationError, match="sample.*mode|mode.*count"):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(data_manifest=manifest)
        )


def test_partial_season_artifact_is_valid_but_cannot_promote(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    manifest = deepcopy(valid_artifact().data_manifest)
    manifest["sample_counts_by_mode"]["unknown"] += manifest[
        "sample_counts_by_mode"
    ]["winter"]
    manifest["sample_counts_by_mode"]["winter"] = 0
    registry.save_candidate(valid_artifact(data_manifest=manifest))

    with pytest.raises(ArtifactPromotionRefused, match="seasonal mode coverage"):
        registry.promote_candidate()


def test_tampered_accepted_sample_mode_vocabulary_is_quarantined(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    registry.save_candidate(valid_artifact())
    registry.promote_candidate()
    payload = json.loads(registry.accepted_path.read_text(encoding="utf-8"))
    payload["data_manifest"]["sample_counts_by_mode"]["monsoon"] = 1
    registry.accepted_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactUnavailable, match="quarantined"):
        registry.load_accepted()


def test_manifest_requires_exact_glazing_observation_bounds(tmp_path):
    manifest = deepcopy(valid_artifact().data_manifest)
    manifest["constraints"]["glazing_observation_bounds"][0][3] = False

    with pytest.raises(ArtifactValidationError, match="constraints"):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(data_manifest=manifest)
        )


def test_refused_candidate_does_not_replace_accepted_artifact(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    accepted = valid_artifact(code_revision="a" * 40)
    registry.save_candidate(accepted)
    registry.promote_candidate()

    metrics = deepcopy(valid_artifact().metrics)
    metrics["overall"]["model"]["air"]["24"]["mae"] = 2.0
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
                "action_provenance": {
                    "training": {
                        "confirmed": 1, "photosensor": 0,
                        "reconstructed": 0, "model_inferred": 0,
                        "unknown": 0,
                    },
                    "evaluation_targets": {
                        "confirmed": 1, "photosensor": 0,
                        "reconstructed": 0, "model_inferred": 0,
                        "unknown": 0,
                    },
                },
            }
        ],
        "metrics": {
            "mae": 0.5,
            "action_evidence": {
                "confirmed": {
                    "training_rows": 1,
                    "evaluation_targets": 1,
                    "disjoint_fold_count": 1,
                }
            },
        },
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

    mismatched = deepcopy(report)
    mismatched["metrics"]["action_evidence"]["confirmed"][
        "disjoint_fold_count"
    ] = 0
    with pytest.raises(ArtifactValidationError, match="action evidence"):
        registry.save_backtest_report(mismatched)
    assert registry.backtest_report_path.read_bytes() == first



def test_promotion_recomputes_provisional_gates_instead_of_trusting_flags(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    metrics = deepcopy(valid_artifact().metrics)
    metrics["scored_fold_count"] = 1
    metrics["overall"]["model"]["air"]["24"]["mae"] = 2.0
    metrics["overall"]["persistence"]["air"]["24"]["mae"] = 1.0
    assert all(metrics["promotion"]["gates"].values())
    assert metrics["promotion"]["eligible"] is True

    with pytest.raises(ArtifactPromotionRefused, match="does not match evidence"):
        registry.save_candidate(valid_artifact(metrics=metrics))
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
    with pytest.raises(ArtifactPromotionRefused, match="numeric types"):
        registry.save_candidate(valid_artifact(metrics=metrics))



def test_atomic_writer_uses_unique_temp_and_ignores_fixed_symlink(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    victim = tmp_path / "outside.json"
    victim.write_text("operator-owned", encoding="utf-8")
    fixed_temporary = registry.candidate_path.with_name("candidate.json.tmp")
    fixed_temporary.symlink_to(victim)

    registry.save_candidate(valid_artifact())

    assert victim.read_text(encoding="utf-8") == "operator-owned"
    assert registry.candidate_path.is_file()
    assert not list(tmp_path.glob(".candidate.json.tmp-*"))


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



def _artifact_with_metric(name, value):
    metrics = deepcopy(valid_artifact().metrics)
    if name in {"mae", "rmse", "count"}:
        metrics["overall"]["model"]["air"]["24"][name] = value
    elif name == "coverage":
        metrics["prediction_interval_coverage"]["air"]["24"]["fraction"] = value
    elif name == "timing":
        metrics["behavior"]["median_timing_error_minutes"] = value
    else:
        raise AssertionError(name)
    return valid_artifact(metrics=metrics)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("mae", -0.1),
        ("rmse", -0.1),
        ("coverage", 1.01),
        ("coverage", "not-a-number"),
        ("count", True),
        ("count", -1),
        ("timing", -5.0),
    ],
)
def test_metric_semantics_fail_closed_before_candidate_write(
    tmp_path, name, value
):
    registry = ArtifactRegistry(tmp_path)
    with pytest.raises(ArtifactValidationError):
        registry.save_candidate(_artifact_with_metric(name, value))
    assert not registry.candidate_path.exists()


@pytest.mark.parametrize("missing", [False, True])
def test_shadow_only_is_an_explicit_required_safety_invariant(tmp_path, missing):
    metrics = deepcopy(valid_artifact().metrics)
    if missing:
        metrics["promotion"].pop("shadow_only")
    else:
        metrics["promotion"]["shadow_only"] = False
    with pytest.raises(ArtifactValidationError, match="shadow"):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(metrics=metrics)
        )


def test_bool_coefficient_is_rejected_as_non_numeric(tmp_path):
    dynamics = stable_dynamics()
    glazing = dict(dynamics.glazing_observation_coefficients)
    glazing["intercept"] = True
    with pytest.raises(ArtifactValidationError, match="boolean"):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(
                dynamics=replace(
                    dynamics,
                    glazing_observation_coefficients=glazing,
                )
            )
        )


def test_manifest_requires_nonempty_canonical_provenance(tmp_path):
    manifest = deepcopy(valid_artifact().data_manifest)
    manifest["event_counts_by_source"] = {}
    with pytest.raises(ArtifactValidationError, match="provenance"):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(data_manifest=manifest)
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("fit_diagnostics", {"fitted_pairs": 1}),
        ("constraints", {"step_minutes": 5}),
    ],
)
def test_manifest_rejects_arbitrary_diagnostics_and_constraints(
    tmp_path, field, replacement
):
    manifest = deepcopy(valid_artifact().data_manifest)
    manifest[field] = replacement
    with pytest.raises(ArtifactValidationError, match=field.replace("_", " ")):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(data_manifest=manifest)
        )


def _malformed_behavior(probe):
    behavior = valid_artifact().behavior
    vocabulary = behavior.seasonal_vocabulary[0]
    if probe == "features":
        return replace(
            behavior,
            feature_names=("arbitrary",),
            transitions={name: () for name in TRANSITIONS},
        )
    if probe == "transitions":
        return replace(behavior, transitions={"invented_transition": ()})
    if probe == "action_state":
        vocabulary = replace(
            vocabulary,
            action_states=(("vent", ("ajar",)),),
        )
    elif probe == "airflow":
        vocabulary = replace(vocabulary, airflow_levels=("turbo",))
    elif probe == "window":
        vocabulary = replace(vocabulary, boosted_windows=((-1, 1500),))
    else:
        raise AssertionError(probe)
    return replace(behavior, seasonal_vocabulary=(vocabulary,))


@pytest.mark.parametrize(
    "probe", ["features", "transitions", "action_state", "airflow", "window"]
)
def test_behavior_contract_rejects_noncanonical_vocabulary(
    tmp_path, probe
):
    with pytest.raises(ArtifactValidationError):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(behavior=_malformed_behavior(probe))
        )


def _tamper_accepted(registry, probe):
    payload = json.loads(registry.accepted_path.read_text(encoding="utf-8"))
    if probe == "negative_mae":
        payload["metrics"]["overall"]["model"]["air"]["24"]["mae"] = -1.0
    elif probe == "shadow_only":
        payload["metrics"]["promotion"]["shadow_only"] = False
    elif probe == "schema":
        payload["schema"] = "earthship-thermal-model/v0"
    else:
        raise AssertionError(probe)
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    registry.accepted_path.write_bytes(raw)
    return raw


@pytest.mark.parametrize("probe", ["negative_mae", "shadow_only", "schema"])
def test_tampered_accepted_artifact_is_revalidated_and_quarantined(
    tmp_path, probe
):
    registry = ArtifactRegistry(tmp_path)
    registry.save_candidate(valid_artifact())
    registry.promote_candidate()
    raw = _tamper_accepted(registry, probe)

    with pytest.raises(ArtifactUnavailable, match="quarantined"):
        registry.load_accepted()

    quarantined = list(tmp_path.glob("accepted.json.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == raw
    assert not registry.accepted_path.exists()


def test_corrupt_current_restores_fully_validated_previous_generation(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    previous = valid_artifact(code_revision="a" * 40)
    current = valid_artifact(code_revision="b" * 40)
    registry.save_candidate(previous)
    registry.promote_candidate()
    registry.save_candidate(current)
    registry.promote_candidate()
    corrupt = b"{broken-current"
    registry.accepted_path.write_bytes(corrupt)

    loaded = registry.load_accepted()

    assert loaded.code_revision == "a" * 40
    assert registry.last_load_source == "previous_restored"
    assert "prior accepted generation" in registry.last_load_reason
    assert registry.load_accepted().code_revision == "a" * 40
    assert list(tmp_path.glob("accepted.json.corrupt-*"))[0].read_bytes() == corrupt


@pytest.mark.parametrize("probe", ["utf8", "type", "semantic"])
def test_invalid_previous_is_quarantined_and_cannot_mask_current_corruption(
    tmp_path, probe
):
    registry = ArtifactRegistry(tmp_path)
    registry.save_candidate(valid_artifact(code_revision="a" * 40))
    registry.promote_candidate()
    registry.save_candidate(valid_artifact(code_revision="b" * 40))
    registry.promote_candidate()
    if probe == "utf8":
        registry.previous_path.write_bytes(b"\xff\xfeinvalid")
    elif probe == "type":
        registry.previous_path.write_text("[]", encoding="utf-8")
    else:
        payload = json.loads(registry.previous_path.read_text(encoding="utf-8"))
        payload["schema"] = "earthship-thermal-model/v0"
        registry.previous_path.write_text(json.dumps(payload), encoding="utf-8")
    registry.accepted_path.write_bytes(b"{broken-current")

    with pytest.raises(ArtifactUnavailable, match="previous"):
        registry.load_accepted()

    assert not registry.accepted_path.exists()
    assert not registry.previous_path.exists()
    assert len(list(tmp_path.glob("accepted.json.corrupt-*"))) == 1
    assert len(list(tmp_path.glob("previous.json.corrupt-*"))) == 1


def test_failed_candidate_promotion_never_rotates_current_or_previous(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    registry.save_candidate(valid_artifact(code_revision="a" * 40))
    registry.promote_candidate()
    registry.save_candidate(valid_artifact(code_revision="b" * 40))
    registry.promote_candidate()
    prior_bytes = registry.previous_path.read_bytes()

    metrics = deepcopy(valid_artifact().metrics)
    metrics["overall"]["model"]["air"]["24"]["mae"] = 2.0
    metrics["promotion"]["eligible"] = False
    metrics["promotion"]["gates"]["air_24h_beats_persistence"] = False
    registry.save_candidate(
        valid_artifact(code_revision="c" * 40, metrics=metrics)
    )
    with pytest.raises(ArtifactPromotionRefused):
        registry.promote_candidate()

    assert registry.load_accepted().code_revision == "b" * 40
    assert registry.previous_path.read_bytes() == prior_bytes


def test_candidate_is_never_used_as_corruption_fallback(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    registry.save_candidate(valid_artifact(code_revision="a" * 40))
    registry.promote_candidate()
    registry.save_candidate(valid_artifact(code_revision="b" * 40))
    registry.accepted_path.write_bytes(b"{broken-current")

    with pytest.raises(ArtifactUnavailable, match="quarantined"):
        registry.load_accepted()

    assert registry.candidate_path.exists()
    assert not registry.accepted_path.exists()


def test_accepted_artifact_remains_loadable_after_later_candidate_regresses(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    accepted = valid_artifact(code_revision="a" * 40)
    registry.save_candidate(accepted)
    registry.promote_candidate()

    metrics = deepcopy(valid_artifact().metrics)
    metrics["overall"]["model"]["air"]["24"]["mae"] = 2.0
    metrics["promotion"]["eligible"] = False
    metrics["promotion"]["gates"]["air_24h_beats_persistence"] = False
    registry.save_candidate(
        valid_artifact(code_revision="b" * 40, metrics=metrics)
    )

    assert registry.load_accepted().code_revision == "a" * 40


def test_invalid_utf8_is_quarantined_without_losing_original_bytes(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    registry.directory.mkdir(parents=True, exist_ok=True)
    raw = b"\xff\xfe\x80not-json"
    registry.accepted_path.write_bytes(raw)

    with pytest.raises(ArtifactUnavailable, match="quarantined"):
        registry.load_accepted()

    quarantined = list(tmp_path.glob("accepted.json.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == raw


def test_two_concurrent_candidate_promoters_leave_one_complete_valid_artifact(
    tmp_path
):
    barrier = threading.Barrier(2)

    def writer(revision):
        registry = ArtifactRegistry(tmp_path)
        artifact = valid_artifact(code_revision=revision)
        barrier.wait(timeout=5)
        for _ in range(4):
            registry.save_candidate(artifact)
            registry.promote_candidate()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(writer, "a" * 40),
            executor.submit(writer, "b" * 40),
        ]
        for future in futures:
            future.result(timeout=15)

    registry = ArtifactRegistry(tmp_path)
    accepted = registry.load_accepted()
    assert accepted.code_revision in {"a" * 40, "b" * 40}
    assert registry.previous_path.exists()
    registry.accepted_path.write_bytes(b"{broken-after-concurrent-promotion")
    recovered = registry.load_accepted()
    assert recovered.code_revision in {"a" * 40, "b" * 40}
    assert registry.last_load_source == "previous_restored"
    assert not list(tmp_path.glob(".candidate.json.tmp-*"))
    assert not list(tmp_path.glob(".accepted.json.tmp-*"))
    assert not list(tmp_path.glob(".previous.json.tmp-*"))


def test_corrupt_reader_cannot_quarantine_newly_promoted_inode(
    tmp_path, monkeypatch
):
    reader = ArtifactRegistry(tmp_path)
    promoter = ArtifactRegistry(tmp_path)
    reader.save_candidate(valid_artifact(code_revision="a" * 40))
    reader.promote_candidate()
    promoter.save_candidate(valid_artifact(code_revision="b" * 40))
    reader.accepted_path.write_bytes(b"{broken")

    diagnosed = threading.Event()
    release = threading.Event()
    promoted = threading.Event()
    original_quarantine = reader._quarantine_accepted

    def paused_quarantine(*args, **kwargs):
        diagnosed.set()
        assert release.wait(timeout=5)
        return original_quarantine(*args, **kwargs)

    monkeypatch.setattr(reader, "_quarantine_accepted", paused_quarantine)

    def read_corrupt():
        with pytest.raises(ArtifactUnavailable):
            reader.load_accepted()

    def promote_valid():
        promoter.promote_candidate()
        promoted.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        read_future = executor.submit(read_corrupt)
        assert diagnosed.wait(timeout=5)
        promote_future = executor.submit(promote_valid)
        promoter_was_blocked = not promoted.wait(timeout=0.2)
        release.set()
        read_future.result(timeout=5)
        promote_future.result(timeout=5)

    assert promoter_was_blocked
    assert ArtifactRegistry(tmp_path).load_accepted().code_revision == "b" * 40
    quarantined = list(tmp_path.glob("accepted.json.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"{broken"


def test_quarantine_destination_is_reserved_with_o_excl(tmp_path, monkeypatch):
    registry = ArtifactRegistry(tmp_path)
    registry.directory.mkdir(parents=True, exist_ok=True)
    registry.accepted_path.write_bytes(b"{broken")
    observed_flags = []
    original_open = artifacts_module.os.open

    def tracking_open(path, flags, *args, **kwargs):
        if ".corrupt-" in str(path):
            observed_flags.append(flags)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(artifacts_module.os, "open", tracking_open)
    with pytest.raises(ArtifactUnavailable, match="quarantined"):
        registry.load_accepted()

    assert observed_flags
    assert all(flags & artifacts_module.os.O_EXCL for flags in observed_flags)


def test_behavior_seasonal_modes_use_canonical_order(tmp_path):
    behavior = valid_artifact().behavior
    warm = behavior.seasonal_vocabulary[0]
    winter = replace(warm, mode="winter")
    malformed = replace(
        behavior, seasonal_vocabulary=(winter, warm)
    )

    with pytest.raises(ArtifactValidationError, match="modes"):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(behavior=malformed)
        )



def test_promotion_requires_positive_model_and_persistence_24h_counts(tmp_path):
    for method in ("model", "persistence"):
        metrics = deepcopy(valid_artifact().metrics)
        metrics["overall"][method]["air"]["24"]["count"] = 0
        registry = ArtifactRegistry(tmp_path / method)

        with pytest.raises(ArtifactPromotionRefused, match="evidence|gate"):
            registry.save_candidate(valid_artifact(metrics=metrics))
        assert not registry.candidate_path.exists()


def test_bool_24h_evidence_count_is_rejected_without_coercion(tmp_path):
    metrics = deepcopy(valid_artifact().metrics)
    metrics["overall"]["persistence"]["air"]["24"]["count"] = True

    with pytest.raises(ArtifactPromotionRefused, match="numeric types"):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(metrics=metrics)
        )


def test_positive_24h_evidence_still_promotes(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    registry.save_candidate(valid_artifact())

    promoted = registry.promote_candidate()

    assert promoted.metrics["overall"]["model"]["air"]["24"]["count"] == 2
    assert registry.load_accepted() == promoted


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code_revision", 1234567),
        ("canonical_rows_sha256", int("1" * 64)),
    ],
)
def test_revision_and_digest_require_exact_string_types(tmp_path, field, value):
    changes = {}
    if field == "code_revision":
        changes[field] = value
    else:
        manifest = deepcopy(valid_artifact().data_manifest)
        manifest[field] = value
        changes["data_manifest"] = manifest

    with pytest.raises(ArtifactValidationError, match="string"):
        ArtifactRegistry(tmp_path).save_candidate(valid_artifact(**changes))


def test_valid_revision_and_digest_strings_round_trip(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    artifact = valid_artifact()
    registry.save_candidate(artifact)
    registry.promote_candidate()

    loaded = registry.load_accepted()
    assert loaded.code_revision == artifact.code_revision
    assert loaded.data_manifest["canonical_rows_sha256"] == "a" * 64


def _add_unknown_payload_key(payload, probe):
    if probe == "dynamics_container":
        payload["dynamics"]["invented"] = 1
    elif probe == "air_coefficient":
        payload["dynamics"]["air_coefficients"]["invented"] = 0.01
    elif probe == "behavior_container":
        payload["behavior"]["invented"] = 1
    elif probe == "behavior_transition":
        payload["behavior"]["transitions"]["invented"] = []
    elif probe == "seasonal_vocabulary":
        payload["behavior"]["seasonal_vocabulary"][0]["invented"] = 1
    elif probe == "metrics":
        payload["metrics"]["invented"] = 1
    else:
        raise AssertionError(probe)


@pytest.mark.parametrize(
    "probe",
    [
        "dynamics_container",
        "air_coefficient",
        "behavior_container",
        "behavior_transition",
        "seasonal_vocabulary",
        "metrics",
    ],
)
def test_unknown_nested_accepted_payload_keys_are_quarantined(tmp_path, probe):
    registry = ArtifactRegistry(tmp_path)
    registry.save_candidate(valid_artifact())
    registry.promote_candidate()
    payload = json.loads(registry.accepted_path.read_text(encoding="utf-8"))
    _add_unknown_payload_key(payload, probe)
    registry.accepted_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactUnavailable, match="quarantined"):
        registry.load_accepted()
    assert len(list(tmp_path.glob("accepted.json.corrupt-*"))) == 1


@pytest.mark.parametrize("probe", ["air_coefficient", "behavior_transition"])
def test_unknown_candidate_model_keys_are_rejected(tmp_path, probe):
    artifact = valid_artifact()
    if probe == "air_coefficient":
        coefficients = dict(artifact.dynamics.air_coefficients)
        coefficients["invented"] = 0.01
        artifact = replace(
            artifact,
            dynamics=replace(
                artifact.dynamics, air_coefficients=coefficients
            ),
        )
    else:
        transitions = dict(artifact.behavior.transitions)
        transitions["invented"] = ()
        artifact = replace(
            artifact,
            behavior=replace(artifact.behavior, transitions=transitions),
        )

    with pytest.raises(ArtifactValidationError):
        ArtifactRegistry(tmp_path).save_candidate(artifact)



def test_unknown_nested_metric_split_is_rejected_for_candidate(tmp_path):
    metrics = deepcopy(valid_artifact().metrics)
    metrics["by_regime"]["warm"]["invented"] = 1.0

    with pytest.raises(ArtifactValidationError, match="metric"):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(metrics=metrics)
        )


def test_unknown_nested_metric_split_is_quarantined_before_load(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    registry.save_candidate(valid_artifact())
    registry.promote_candidate()
    payload = json.loads(registry.accepted_path.read_text(encoding="utf-8"))
    payload["metrics"]["by_regime"]["warm"]["invented"] = 1.0
    registry.accepted_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactUnavailable, match="quarantined"):
        registry.load_accepted()



def test_unknown_threshold_baseline_leaf_is_rejected(tmp_path):
    metrics = deepcopy(valid_artifact().metrics)
    metrics["threshold_baseline"] = {
        "definition": {
            "close_up_tomorrow": "close",
            "vent_tonight": "vent",
            "none": "none",
        },
        "input": "held_out_outdoor_high_proxy",
        "class_counts": {
            "none": 1,
            "vent_tonight": 0,
            "close_up_tomorrow": 0,
            "invented": 0,
        },
        "comparison_target": "held_out_hallway_high_f >= 82",
        "precision": None,
        "recall": None,
        "count": 1,
    }

    with pytest.raises(ArtifactValidationError, match="threshold"):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(metrics=metrics)
        )



def test_manifest_count_vocabularies_are_exported_from_producer_strings():
    assert artifacts_module.CORE_REJECTED_COUNT_KEYS == frozenset(
        {"missing_required", "source_gap", "range", "jump"}
    )
    assert artifacts_module.AUXILIARY_EXCLUSION_COUNT_KEYS == frozenset(
        {
            "glazing_range",
            "glazing_jump",
            "glazing_source_gap",
            "glazing_non_finite",
            "glazing_missing",
        }
    )


@pytest.mark.parametrize(
    "field", ["rejected_counts", "auxiliary_exclusion_counts"]
)
def test_candidate_manifest_rejects_invented_count_reason(tmp_path, field):
    manifest = deepcopy(valid_artifact().data_manifest)
    manifest[field]["invented_reason"] = 1

    with pytest.raises(ArtifactValidationError, match="unknown"):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(data_manifest=manifest)
        )


@pytest.mark.parametrize(
    "field", ["rejected_counts", "auxiliary_exclusion_counts"]
)
def test_tampered_accepted_manifest_count_reason_is_quarantined(tmp_path, field):
    registry = ArtifactRegistry(tmp_path)
    registry.save_candidate(valid_artifact())
    registry.promote_candidate()
    payload = json.loads(registry.accepted_path.read_text(encoding="utf-8"))
    payload["data_manifest"][field]["invented_reason"] = 1
    registry.accepted_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactUnavailable, match="quarantined"):
        registry.load_accepted()
    assert len(list(tmp_path.glob("accepted.json.corrupt-*"))) == 1


@pytest.mark.parametrize(
    ("rejected", "auxiliary"),
    [
        ({}, {}),
        ({"jump": 2}, {"glazing_non_finite": 1}),
        (
            {"missing_required": 1, "source_gap": 2, "range": 3, "jump": 4},
            {
                "glazing_range": 1,
                "glazing_jump": 2,
                "glazing_source_gap": 3,
                "glazing_non_finite": 4,
                "glazing_missing": 5,
            },
        ),
    ],
)
def test_manifest_count_maps_allow_only_valid_subsets(
    tmp_path, rejected, auxiliary
):
    manifest = deepcopy(valid_artifact().data_manifest)
    manifest["rejected_counts"] = rejected
    manifest["auxiliary_exclusion_counts"] = auxiliary

    ArtifactRegistry(tmp_path).save_candidate(
        valid_artifact(data_manifest=manifest)
    )


@pytest.mark.parametrize("value", [True, -1])
@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("rejected_counts", "jump"),
        ("auxiliary_exclusion_counts", "glazing_jump"),
    ],
)
def test_manifest_count_map_values_are_nonnegative_non_bool(
    tmp_path, field, reason, value
):
    manifest = deepcopy(valid_artifact().data_manifest)
    manifest[field] = {reason: value}

    with pytest.raises(ArtifactValidationError):
        ArtifactRegistry(tmp_path).save_candidate(
            valid_artifact(data_manifest=manifest)
        )
