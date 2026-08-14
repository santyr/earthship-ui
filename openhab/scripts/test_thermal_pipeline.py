from datetime import datetime, timedelta, timezone
import json
import math
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from thermal_model.artifacts import ArtifactPromotionRefused, ArtifactUnavailable
from thermal_model.behavior import FEATURE_NAMES, TRANSITIONS, baseline_schedule
from thermal_model.pipeline import (
    TrainingRefused,
    build_shadow_output,
    interpolate_hourly_forecast,
    run_backtest,
    run_shadow,
    run_training,
    write_shadow_output,
)
import thermal_model.pipeline as thermal_pipeline
from thermal_model.schema import (
    ActionEvent,
    BehaviorModel,
    DynamicsModel,
    ModeEvent,
    SeasonalActionVocabulary,
    THERMAL_ITEMS,
    ThermalSample,
    validate_shadow_output,
)


UTC = timezone.utc
LOCAL = ZoneInfo("America/Denver")
NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
STEP = timedelta(minutes=5)


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
        glazing_observation_coefficients={},
    )


def warm_behavior():
    return BehaviorModel(
        version=1,
        feature_names=FEATURE_NAMES,
        transitions={name: () for name in TRANSITIONS},
        seasonal_vocabulary=(
            SeasonalActionVocabulary(
                mode="warm",
                action_states=(
                    ("indoor_shade", ("closed", "open")),
                    ("outdoor_shade", ("absent", "present")),
                    ("vent", ("closed", "open")),
                ),
                transitions=(),
                airflow_levels=("closed", "baseline"),
                boosted_windows=(),
            ),
        ),
    )


def accepted_artifact(
    *, confirmed_training=False, confirmed_evaluation=False, disjoint_confirmed=None
):
    training_counts = {"historical_reconstruction": 20}
    if confirmed_training or confirmed_evaluation:
        training_counts["nostr_confirmed"] = 4
    if disjoint_confirmed is None:
        disjoint_confirmed = confirmed_training and confirmed_evaluation
    evaluation_split = "confirmed" if confirmed_evaluation else "reconstructed"
    summary = {
        "count": 3,
        "mae": 0.8,
        "rmse": 1.0,
        "bias": 0.1,
    }
    return SimpleNamespace(
        created_at="2026-08-13T10:00:00Z",
        trained_through="2026-08-13T09:00:00Z",
        code_revision="0123456789abcdef0123456789abcdef01234567",
        dynamics=stable_dynamics(),
        behavior=warm_behavior(),
        metrics={
            "overall": {"model": {"air": {"24": summary}}},
            "by_provenance": {
                evaluation_split: {"air": {"24": summary}},
            },
            "action_evidence": {
                "confirmed": {
                    "training_rows": 4 if confirmed_training else 0,
                    "evaluation_targets": 3 if confirmed_evaluation else 0,
                    "disjoint_fold_count": 1 if disjoint_confirmed else 0,
                }
            },
            "prediction_interval_coverage": {
                "air": {
                    "24": {
                        "nominal": 0.9,
                        "count": 3,
                        "covered": 2,
                        "fraction": 2 / 3,
                    }
                }
            },
        },
        data_manifest={"event_counts_by_source": training_counts},
    )


class AcceptedRegistry:
    def __init__(self, artifact=None, error=None):
        self.artifact = artifact or accepted_artifact()
        self.error = error

    def load_accepted(self):
        if self.error is not None:
            raise self.error
        return self.artifact


def current_states(**ages):
    def reading(value, role):
        return {"value": value, "at": NOW - timedelta(minutes=ages.get(role, 2))}

    return {
        "air": reading(74.1, "air"),
        "mass": reading(72.8, "mass"),
        "glazing": reading(75.0, "glazing"),
        "outdoor": reading(65.0, "outdoor"),
        "radiation": reading(100.0, "radiation"),
        "observed": [
            {
                "at": NOW - timedelta(minutes=index * 5),
                "hallwayF": 74.1 - index * 0.02,
                "massF": 72.8 - index * 0.01,
            }
            for index in range(30)
        ],
    }


def forecast_hours(hours=72):
    rows = []
    for index in range(hours + 1):
        at = NOW.astimezone(LOCAL) + timedelta(hours=index)
        local_hour = at.hour
        night = local_hour >= 20 or local_hour < 8
        rows.append(
            {
                "at": at,
                "tempF": 62.0 if night else 86.0,
                "radiationWm2": (
                    max(0.0, 700.0 * math.sin(math.pi * (local_hour - 6) / 12.0))
                    if 6 <= local_hour <= 18
                    else 0.0
                ),
                "weatherCode": 1 if night else 0,
                "windMph": 7.0 if night else 3.0,
                "mode": "warm",
            }
        )
    return rows


def test_forecast_interpolation_is_aware_linear_and_holds_categories():
    start = datetime(2026, 11, 1, 0, 0, tzinfo=LOCAL)
    rows = [
        {
            "at": start,
            "tempF": 60.0,
            "radiationWm2": 0.0,
            "weatherCode": 3,
            "windMph": 5.0,
            "mode": "warm",
        },
        {
            "at": start + timedelta(hours=1),
            "tempF": 72.0,
            "radiationWm2": 120.0,
            "weatherCode": 1,
            "windMph": 9.0,
            "mode": "warm",
        },
    ]

    result = interpolate_hourly_forecast(rows, start=start, end=rows[-1]["at"])

    assert len(result) == 13
    assert result[1]["outdoor_f"] == pytest.approx(61.0)
    assert result[1]["radiation_wm2"] == pytest.approx(10.0)
    assert result[1]["weather_code"] == 3
    assert result[1]["wind_mph"] == 5.0
    assert result[-1]["weather_code"] == 1
    assert all(row["at"].tzinfo is not None for row in result)


def test_forecast_interpolation_preserves_every_five_minutes_across_dst_fallback():
    start_utc = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)
    rows = [
        {
            "at": (start_utc + timedelta(hours=index)).astimezone(LOCAL),
            "tempF": 60.0 + index,
            "radiationWm2": 0.0,
            "weatherCode": index,
            "windMph": 5.0,
            "mode": "fall_charge",
        }
        for index in range(4)
    ]

    result = interpolate_hourly_forecast(rows, start=rows[0]["at"], end=rows[-1]["at"])

    assert len(result) == 37
    assert all(
        right["at"].astimezone(UTC) - left["at"].astimezone(UTC) == STEP
        for left, right in zip(result, result[1:])
    )
    repeated = [row["at"].astimezone(LOCAL) for row in result if row["at"].astimezone(LOCAL).hour == 1]
    assert {at.fold for at in repeated} == {0, 1}


def test_forecast_interpolation_rejects_extrapolation_naive_and_missing_numeric():
    rows = forecast_hours(2)
    with pytest.raises(ValueError, match="extrapolate"):
        interpolate_hourly_forecast(
            rows,
            start=rows[0]["at"] - STEP,
            end=rows[-1]["at"],
        )
    with pytest.raises(ValueError, match="timezone"):
        interpolate_hourly_forecast(
            [{**row, "at": row["at"].replace(tzinfo=None)} for row in rows],
            start=rows[0]["at"],
            end=rows[-1]["at"],
        )
    broken = [dict(row) for row in rows]
    broken[1]["tempF"] = None
    with pytest.raises(ValueError, match="temperature"):
        interpolate_hourly_forecast(
            broken,
            start=broken[0]["at"],
            end=broken[-1]["at"],
        )


def test_shadow_output_is_bounded_versioned_and_never_advisory():
    output = run_shadow(
        registry=AcceptedRegistry(),
        current=current_states(),
        forecast=forecast_hours(),
        now=NOW,
    )

    assert set(output) == {
        "version", "status", "generatedAt", "model", "current", "forecast",
        "schedule", "confidence", "provenance", "reasons",
    }
    assert output["status"] == "shadow"
    assert output["version"] == 1
    assert len(json.dumps(output, separators=(",", ":")).encode()) < 16 * 1024
    assert "commands" not in json.dumps(output).lower()
    assert "advisory" not in json.dumps(output).lower()
    assert output["forecast"]["hallwayHighF"] is not None
    assert output["forecast"]["availableHours"] == 72
    assert len(output["forecast"]["trajectory"]) <= 73
    assert len(output["forecast"]["observed"]) == 25
    assert all(
        datetime.fromisoformat(row["at"]).astimezone(LOCAL).minute == 0
        for row in output["forecast"]["trajectory"]
    )
    allowed = {
        "vent_open", "vent_close", "indoor_shade_open", "indoor_shade_close",
        "outdoor_shade_installed", "outdoor_shade_removed",
    }
    assert all(
        set(row["actions"]) <= allowed
        for row in output["forecast"]["trajectory"]
    )
    assert output["confidence"]["grade"] == "low"
    markers = [marker for row in output["forecast"]["trajectory"] for marker in row["actions"]]
    assert markers.count("vent_open") >= 3
    assert output["schedule"]["baseline"]["ventOpenAt"] is not None
    assert output["schedule"]["baseline"]["ventCloseAt"] is not None
    assert "caus" not in json.dumps(output).lower()


def test_build_shadow_output_is_an_alias_for_validated_shadow_construction():
    output = build_shadow_output(
        registry=AcceptedRegistry(),
        current=current_states(),
        forecast=forecast_hours(24),
        now=NOW,
    )
    assert output["forecast"]["availableHours"] == 24
    assert output["status"] == "shadow"


def test_shadow_emits_no_candidate_for_actual_minimum_improvement_result():
    artifact = accepted_artifact()
    artifact.dynamics.air_coefficients["vent_exchange"] = 0.0

    output = run_shadow(
        registry=AcceptedRegistry(artifact),
        current=current_states(),
        forecast=forecast_hours(24),
        now=NOW,
    )

    assert output["schedule"]["candidate"] is None
    assert output["schedule"]["effect"] == {
        "morningMassDeltaF": 0.0, "hallwayPeakDeltaF": 0.0
    }
    assert "minimum modeled improvement" in output["reasons"][0]


def test_shadow_emits_no_candidate_for_winter_protocol_constraint():
    forecast = forecast_hours(24)
    for row in forecast:
        row.update(
            {"mode": "winter", "tempF": 25.0, "radiationWm2": 25.0}
        )

    output = run_shadow(
        registry=AcceptedRegistry(),
        current=current_states(),
        forecast=forecast,
        now=NOW,
    )

    assert output["schedule"]["candidate"] is None
    assert output["schedule"]["effect"] == {
        "morningMassDeltaF": 0.0, "hallwayPeakDeltaF": 0.0
    }
    assert "protocol constraint" in output["reasons"][0]


def test_shadow_omits_structurally_equal_nonimproving_candidate(monkeypatch):
    def equal_search(*, behavior, dynamics, forecast):
        del dynamics
        baseline = baseline_schedule(behavior, forecast)
        return SimpleNamespace(
            baseline=baseline,
            candidate=dict(baseline),
            modeled_difference={
                "selectionReason": "minimum_improvement_not_met",
                "scoreImprovement": 0.0,
            },
        )

    monkeypatch.setattr(
        "thermal_model.pipeline.search_candidate_schedule", equal_search
    )

    output = run_shadow(
        registry=AcceptedRegistry(),
        current=current_states(),
        forecast=forecast_hours(24),
        now=NOW,
    )

    assert output["schedule"]["candidate"] is None
    assert output["schedule"]["effect"] == {
        "morningMassDeltaF": 0.0,
        "hallwayPeakDeltaF": 0.0,
    }
    assert "minimum modeled improvement" in output["reasons"][0]


@pytest.mark.parametrize("role", ["air", "mass", "outdoor", "radiation"])
def test_stale_critical_input_emits_unavailable_without_candidate_schedule(role):
    output = run_shadow(
        registry=AcceptedRegistry(),
        current=current_states(**{role: 31}),
        forecast=forecast_hours(),
        now=NOW,
    )

    labels = {
        "air": "hallway temperature",
        "mass": "mass temperature",
        "outdoor": "outdoor temperature",
        "radiation": "solar radiation",
    }
    assert output["confidence"]["grade"] == "unavailable"
    assert output["schedule"] == {}
    assert f"stale {labels[role]}" in output["reasons"]


@pytest.mark.parametrize(
    ("role", "value", "reason"),
    [
        ("air", 141.0, "hallway temperature is outside"),
        ("mass", -41.0, "mass temperature is outside"),
        ("outdoor", 141.0, "outdoor temperature is outside"),
        ("radiation", -1.0, "solar radiation is outside"),
    ],
)
def test_out_of_range_current_forcing_fails_soft(role, value, reason):
    current = current_states()
    current[role]["value"] = value

    output = run_shadow(
        registry=AcceptedRegistry(), current=current, forecast=forecast_hours(24), now=NOW
    )

    assert output["confidence"]["grade"] == "unavailable"
    assert output["schedule"] == {}
    assert reason in output["reasons"][0]


def test_out_of_range_forecast_forcing_fails_soft():
    forecast = forecast_hours(24)
    forecast[3]["radiationWm2"] = 1601.0

    output = run_shadow(
        registry=AcceptedRegistry(), current=current_states(), forecast=forecast, now=NOW
    )

    assert output["confidence"]["grade"] == "unavailable"
    assert output["schedule"] == {}
    assert "forecast solar radiation is outside" in output["reasons"][0]


def test_optional_glazing_may_be_null():
    current = current_states()
    current["glazing"] = {"value": None, "at": NOW - timedelta(minutes=2)}
    output = run_shadow(
        registry=AcceptedRegistry(), current=current, forecast=forecast_hours(), now=NOW
    )
    assert output["confidence"]["grade"] == "low"
    assert output["current"]["glazingF"] is None


def test_missing_invalid_or_short_inputs_fail_soft_without_schedule():
    missing_artifact = run_shadow(
        registry=AcceptedRegistry(error=ArtifactUnavailable("corrupt artifact")),
        current=current_states(),
        forecast=forecast_hours(),
        now=NOW,
    )
    short_forecast = run_shadow(
        registry=AcceptedRegistry(),
        current=current_states(),
        forecast=forecast_hours(23),
        now=NOW,
    )
    broken_forecast = forecast_hours()
    broken_forecast[2]["radiationWm2"] = None
    invalid_forecast = run_shadow(
        registry=AcceptedRegistry(),
        current=current_states(),
        forecast=broken_forecast,
        now=NOW,
    )

    for output in (missing_artifact, short_forecast, invalid_forecast):
        assert output["confidence"]["grade"] == "unavailable"
        assert output["schedule"] == {}
        assert output["forecast"].get("trajectory", []) == []
        assert output["reasons"]


@pytest.mark.parametrize(
    ("confirmed_training", "confirmed_evaluation", "disjoint_folds", "expected"),
    [
        (False, True, 0, "reconstructed"),
        (True, False, 0, "reconstructed"),
        (True, True, 1, "confirmed"),
        (True, True, 0, "reconstructed"),
    ],
)
def test_action_label_requires_disjoint_confirmed_training_and_evaluation(
    confirmed_training, confirmed_evaluation, disjoint_folds, expected
):
    output = run_shadow(
        registry=AcceptedRegistry(
            accepted_artifact(
                confirmed_training=confirmed_training,
                confirmed_evaluation=confirmed_evaluation,
                disjoint_confirmed=bool(disjoint_folds),
            )
        ),
        current=current_states(),
        forecast=forecast_hours(24),
        now=NOW,
    )

    assert output["confidence"] == {
        "grade": "low", "actionLabels": expected
    }


def test_shadow_discloses_verified_prior_accepted_generation_fallback():
    class FallbackRegistry(AcceptedRegistry):
        def load_accepted(self):
            artifact = super().load_accepted()
            self.last_load_source = "previous_restored"
            self.last_load_reason = (
                "accepted model recovered from verified prior accepted generation"
            )
            return artifact

    output = run_shadow(
        registry=FallbackRegistry(),
        current=current_states(),
        forecast=forecast_hours(24),
        now=NOW,
    )

    assert (
        "accepted model recovered from verified prior accepted generation"
        in output["reasons"]
    )


def test_older_valid_artifact_remains_shadow_and_discloses_ages():
    artifact = accepted_artifact()
    artifact.created_at = "2026-08-10T12:00:00Z"
    artifact.trained_through = "2026-08-09T12:00:00Z"

    output = run_shadow(
        registry=AcceptedRegistry(artifact),
        current=current_states(),
        forecast=forecast_hours(24),
        now=NOW,
    )

    assert output["confidence"]["grade"] == "low"
    assert output["provenance"]["modelAgeHours"] == 72.0
    assert output["provenance"]["trainingDataAgeHours"] == 96.0
    assert "accepted model daily training cadence missed" in output["reasons"]


@pytest.mark.parametrize("field", ["created_at", "trained_through"])
def test_future_dated_artifact_fails_soft(field):
    artifact = accepted_artifact()
    setattr(artifact, field, "2026-08-13T12:05:00Z")

    output = run_shadow(
        registry=AcceptedRegistry(artifact),
        current=current_states(),
        forecast=forecast_hours(24),
        now=NOW,
    )

    assert output["confidence"]["grade"] == "unavailable"
    assert output["schedule"] == {}
    assert any("future" in reason for reason in output["reasons"])


def training_samples():
    return [
        ThermalSample(
            at=NOW - timedelta(minutes=(3 - index) * 5),
            air_f=72.0 + index * 0.1,
            mass_f=70.0 + index * 0.02,
            glazing_f=None,
            outdoor_f=62.0 + index,
            radiation_wm2=100.0 + index * 10,
            vent_open=1.0,
            vent_confidence=0.35,
            indoor_shade_closed=0.0,
            indoor_shade_confidence=0.35,
            outdoor_shade_present=1.0,
            outdoor_shade_confidence=0.35,
            action_confidence=0.35,
            passive_fit_allowed=True,
            mode="warm",
        )
        for index in range(4)
    ]


def action_event():
    return ActionEvent(
        event_id="event-1",
        idempotency_key="receipt-1",
        received_at=NOW - timedelta(days=1),
        effective_at=NOW - timedelta(days=1),
        action="vent",
        state="open",
        source="historical_reconstruction",
        confidence=0.35,
    )


def mode_event():
    return ModeEvent(
        event_id="mode-1",
        idempotency_key="receipt-1",
        received_at=NOW - timedelta(days=1),
        effective_at=NOW - timedelta(days=1),
        mode="warm",
        source="historical_reconstruction",
        confidence=0.35,
    )


def backtest_report(*, eligible=False):
    model_summary = {"count": 2, "mae": 0.5, "rmse": 0.6, "bias": 0.0}
    persistence_summary = {"count": 2, "mae": 1.0, "rmse": 1.1, "bias": 0.0}
    gates = {
        "physics_valid": True,
        "finite_metrics": True,
        "at_least_two_folds": True,
        "air_24h_beats_persistence": eligible,
    }
    return {
        "schema": "earthship-thermal-backtest/v1",
        "generated_at": NOW.isoformat().replace("+00:00", "Z"),
        "data_range": {
            "start": (NOW - timedelta(days=30)).isoformat().replace("+00:00", "Z"),
            "end": NOW.isoformat().replace("+00:00", "Z"),
        },
        "folds": [],
        "prediction_records": [],
        "metrics": {
            "fold_count": 2,
            "scored_fold_count": 2,
            "overall": {
                "model": {"air": {"24": model_summary}},
                "persistence": {"air": {"24": persistence_summary}},
            },
            "by_regime": {},
            "by_horizon": {},
            "by_provenance": {},
            "promotion": {
                "eligible": eligible,
                "shadow_only": True,
                "gates": gates,
                "graduation_thresholds": None,
            },
        },
    }


class FakeJournal:
    def __init__(self, calls):
        self.calls = calls

    def effective_events(self, start, end):
        self.calls.append(("events", start, end))
        return (action_event(),)

    def effective_modes(self, start, end):
        self.calls.append(("modes", start, end))
        return (mode_event(),)


class RecordingRegistry:
    def __init__(self, *, refuse=False):
        self.calls = []
        self.report = None
        self.artifact = None
        self.refuse = refuse

    def save_backtest_report(self, report):
        self.calls.append("report")
        self.report = report

    def save_candidate(self, artifact):
        self.calls.append("candidate")
        self.artifact = artifact

    def promote_candidate(self):
        self.calls.append("promote")
        if self.refuse:
            raise ArtifactPromotionRefused(
                "candidate promotion refused: air_24h_beats_persistence"
            )
        return self.artifact


def orchestration_dependencies(calls, *, eligible=False):
    def series_reader(item, start, end):
        calls.append(("series", item, start, end))
        return [(NOW - STEP, 1.0)]

    return {
        "series_reader": series_reader,
        "forecast_reader": lambda: calls.append("forecast") or forecast_hours(),
        "clock": lambda: NOW,
        "revision_reader": lambda: "a" * 40,
        "site_settings_loader": lambda: calls.append("site"),
        "sample_builder": lambda series, events, modes, start, end: training_samples(),
        "dynamics_fitter": lambda rows: stable_dynamics(),
        "behavior_fitter": lambda rows: warm_behavior(),
        "evaluator": lambda rows, fit: backtest_report(eligible=eligible),
        "artifact_validator": lambda artifact: artifact,
    }


def test_training_assembles_exact_manifest_persists_report_then_refuses():
    calls = []
    registry = RecordingRegistry(refuse=True)
    start = NOW - timedelta(days=30)

    with pytest.raises(TrainingRefused, match="air_24h_beats_persistence") as exc:
        run_training(
            start=start,
            end=NOW,
            registry=registry,
            journal=FakeJournal(calls),
            **orchestration_dependencies(calls, eligible=False),
        )

    assert exc.value.reasons == ("air_24h_beats_persistence",)
    assert registry.calls == ["report", "candidate", "promote"]
    assert registry.report is not None
    assert set(registry.artifact.data_manifest) == {
        "start", "end", "sample_count", "rejected_counts",
        "auxiliary_exclusion_counts", "event_counts_by_source", "items", "units",
        "canonical_rows_sha256", "fit_diagnostics", "constraints",
    }
    assert registry.artifact.data_manifest["items"] == THERMAL_ITEMS
    assert registry.artifact.metrics is registry.report["metrics"]
    assert calls[0] == "site"
    assert [call[1] for call in calls if isinstance(call, tuple) and call[0] == "series"] == list(THERMAL_ITEMS.values())
    assert "forecast" not in calls


def test_training_promotes_only_after_report_and_candidate():
    calls = []
    registry = RecordingRegistry()
    result = run_training(
        start=NOW - timedelta(days=30),
        end=NOW,
        registry=registry,
        journal=FakeJournal(calls),
        **orchestration_dependencies(calls, eligible=True),
    )

    assert registry.calls == ["report", "candidate", "promote"]
    assert result.promoted is True
    assert result.artifact is registry.artifact


def test_backtest_reads_authorities_and_persists_only_report():
    calls = []
    registry = RecordingRegistry()
    report = run_backtest(
        start=NOW - timedelta(days=30),
        end=NOW,
        registry=registry,
        journal=FakeJournal(calls),
        **orchestration_dependencies(calls, eligible=False),
    )

    assert registry.calls == ["report"]
    assert report is registry.report


def test_shadow_output_write_is_atomic_and_compact(tmp_path):
    destination = tmp_path / "nested" / "shadow.json"
    output = run_shadow(
        registry=AcceptedRegistry(),
        current=current_states(),
        forecast=forecast_hours(24),
        now=NOW,
    )

    write_shadow_output(destination, output)

    assert json.loads(destination.read_text(encoding="utf-8")) == output
    assert len(destination.read_bytes()) < 16 * 1024
    assert not list(destination.parent.glob(".shadow.json.tmp-*"))


def test_cli_jdbc_reader_selects_the_jdbc_persistence_service(monkeypatch):
    import thermal_intel

    paths = []
    monkeypatch.setattr(
        thermal_intel.forecast_intel,
        "oh_get",
        lambda path: paths.append(path) or {
            "data": [{"time": int((NOW - timedelta(minutes=1)).timestamp() * 1000), "state": "74.5 °F"}]
        },
    )

    assert thermal_intel._jdbc_series("Hallway", NOW - STEP, NOW) == [(NOW - timedelta(minutes=1), 74.5)]
    assert "serviceId=jdbc" in paths[0]


def test_cli_forecast_mode_is_evidence_backed_across_calendar_boundary():
    import thermal_intel

    start = datetime(2026, 8, 31, 23, 0, tzinfo=UTC)
    rows = [
        {
            "at": start + timedelta(hours=index),
            "tempF": 70.0,
            "radiationWm2": 0.0,
            "weatherCode": 0,
            "windMph": 2.0,
        }
        for index in range(4)
    ]
    prior = ModeEvent(
        event_id="mode-warm-prior",
        idempotency_key="mode-warm-prior-receipt",
        received_at=start - timedelta(days=10),
        effective_at=start - timedelta(days=10),
        mode="warm",
        source="manual_dm",
        confidence=1.0,
    )

    projected = thermal_intel._apply_mode_timeline(rows, (prior,), start)

    assert [row["mode"] for row in projected] == ["warm"] * 4


def test_cli_forecast_mode_projects_only_explicit_journal_transition():
    import thermal_intel

    start = datetime(2026, 10, 31, 23, 0, tzinfo=UTC)
    transition_at = start + timedelta(hours=1, minutes=30)
    rows = [
        {
            "at": start + timedelta(hours=index),
            "tempF": 70.0,
            "radiationWm2": 0.0,
            "weatherCode": 0,
            "windMph": 2.0,
        }
        for index in range(4)
    ]
    modes = (
        ModeEvent(
            event_id="mode-fall-prior",
            idempotency_key="mode-fall-prior-receipt",
            received_at=start - timedelta(days=1),
            effective_at=start - timedelta(days=1),
            mode="fall_charge",
            source="manual_dm",
            confidence=1.0,
        ),
        ModeEvent(
            event_id="mode-winter-transition",
            idempotency_key="mode-winter-transition-receipt",
            received_at=transition_at,
            effective_at=transition_at,
            mode="winter",
            source="manual_dm",
            confidence=1.0,
        ),
    )

    projected = thermal_intel._apply_mode_timeline(rows, modes, start)
    interpolated = interpolate_hourly_forecast(
        projected, start=start, end=start + timedelta(hours=3)
    )

    assert next(row for row in interpolated if row["at"] == transition_at)["mode"] == "winter"
    assert next(
        row for row in interpolated if row["at"] == transition_at - STEP
    )["mode"] == "fall_charge"


def test_cli_forecast_mode_is_unavailable_without_active_journal_evidence():
    import thermal_intel

    start = datetime(2026, 8, 31, 23, 0, tzinfo=UTC)
    rows = [{"at": start, "tempF": 70.0, "radiationWm2": 0.0, "weatherCode": 0, "windMph": 2.0}]

    with pytest.raises(ValueError, match="evidence-backed active thermal mode"):
        thermal_intel._apply_mode_timeline(rows, (), start)


def test_cli_observed_history_buckets_independent_item_updates_without_invention():
    import thermal_intel

    base = datetime(2026, 8, 13, 11, 0, tzinfo=UTC)
    histories = {
        "air": (
            (base + timedelta(seconds=2, milliseconds=100), 70.0),
            (base + timedelta(minutes=4, seconds=59), 71.0),
            (base + timedelta(minutes=4, seconds=59), 70.5),
            (base + timedelta(minutes=10, seconds=2), 72.0),
        ),
        "mass": (
            (base + timedelta(seconds=47, milliseconds=900), 68.0),
            (base + timedelta(minutes=5, seconds=31), 68.5),
            (base + timedelta(minutes=10, seconds=59), 69.0),
        ),
    }

    observed = thermal_intel._aligned_observed_history(histories)

    assert observed == [
        {"at": base, "hallwayF": 71.0, "massF": 68.0},
        {"at": base + timedelta(minutes=10), "hallwayF": 72.0, "massF": 69.0},
    ]
    assert base + timedelta(minutes=5) not in {row["at"] for row in observed}


class _ModeJournal:
    def __init__(self, modes):
        self.modes = tuple(modes)
        self.calls = []

    def effective_modes(self, start, end):
        self.calls.append((start, end))
        return self.modes


def test_cli_shadow_queries_journal_for_effective_mode_timeline(tmp_path, monkeypatch):
    import thermal_intel

    destination = tmp_path / "shadow.json"
    rows = [{key: value for key, value in row.items() if key != "mode"} for row in forecast_hours(24)]
    prior = ModeEvent(
        event_id="shadow-mode-warm",
        idempotency_key="shadow-mode-warm-receipt",
        received_at=NOW - timedelta(days=1),
        effective_at=NOW - timedelta(days=1),
        mode="warm",
        source="manual_dm",
        confidence=1.0,
    )
    journal = _ModeJournal((prior,))
    monkeypatch.setattr(thermal_intel.forecast_intel, "load_site_settings", lambda: {})
    monkeypatch.setattr(thermal_intel, "_current_states", lambda now: current_states())
    monkeypatch.setattr(thermal_intel.forecast_intel, "fetch_forecast", lambda: {})
    monkeypatch.setattr(thermal_intel, "_forecast_rows", lambda snapshot, now: rows)
    monkeypatch.setattr(thermal_intel, "ArtifactRegistry", lambda path: AcceptedRegistry())

    status = thermal_intel._shadow(
        SimpleNamespace(output=destination, publish=False), NOW, journal=journal
    )

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert status == 0
    assert payload["confidence"]["grade"] != "unavailable"
    assert journal.calls == [(NOW, rows[-1]["at"] + timedelta(microseconds=1))]


def test_cli_shadow_missing_effective_mode_fails_soft_without_candidate(tmp_path, monkeypatch):
    import thermal_intel

    destination = tmp_path / "shadow.json"
    rows = [{key: value for key, value in row.items() if key != "mode"} for row in forecast_hours(24)]
    monkeypatch.setattr(thermal_intel.forecast_intel, "load_site_settings", lambda: {})
    monkeypatch.setattr(thermal_intel, "_current_states", lambda now: current_states())
    monkeypatch.setattr(thermal_intel.forecast_intel, "fetch_forecast", lambda: {})
    monkeypatch.setattr(thermal_intel, "_forecast_rows", lambda snapshot, now: rows)
    monkeypatch.setattr(thermal_intel, "ArtifactRegistry", lambda path: AcceptedRegistry())

    status = thermal_intel._shadow(
        SimpleNamespace(output=destination, publish=False),
        NOW,
        journal=_ModeJournal(()),
    )

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert status == 1
    assert payload["confidence"]["grade"] == "unavailable"
    assert payload["schedule"] == {}
    assert any("evidence-backed active thermal mode" in reason for reason in payload["reasons"])


@pytest.mark.parametrize("failure", ["current", "forecast", "artifact"])
def test_cli_shadow_reader_failures_replace_stale_output_with_unavailable(
    tmp_path, monkeypatch, failure
):
    import thermal_intel

    destination = tmp_path / "shadow.json"
    destination.write_text("stale-prior-output", encoding="utf-8")
    monkeypatch.setattr(thermal_intel.forecast_intel, "load_site_settings", lambda: {})
    monkeypatch.setattr(thermal_intel, "_current_states", lambda now: current_states())
    monkeypatch.setattr(thermal_intel.forecast_intel, "fetch_forecast", lambda: {})
    monkeypatch.setattr(
        thermal_intel, "_forecast_rows", lambda snapshot, now: forecast_hours(24)
    )
    monkeypatch.setattr(
        thermal_intel, "ArtifactRegistry", lambda path: AcceptedRegistry()
    )
    if failure == "current":
        monkeypatch.setattr(
            thermal_intel, "_current_states",
            lambda now: (_ for _ in ()).throw(OSError("jdbc unavailable")),
        )
    elif failure == "forecast":
        monkeypatch.setattr(
            thermal_intel.forecast_intel, "fetch_forecast",
            lambda: (_ for _ in ()).throw(RuntimeError("forecast unavailable")),
        )
    else:
        monkeypatch.setattr(
            thermal_intel, "ArtifactRegistry",
            lambda path: AcceptedRegistry(
                error=ArtifactUnavailable("accepted artifact unavailable")
            ),
        )

    status = thermal_intel._shadow(SimpleNamespace(output=destination), NOW)

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert status == 1
    assert validate_shadow_output(payload) is payload
    assert payload["confidence"]["grade"] == "unavailable"
    assert payload["schedule"] == {}
    assert payload["reasons"]
    assert "publish" not in json.dumps(payload).lower()


@pytest.mark.parametrize(
    "error",
    [
        OSError(),
        OSError(("secret\n\x00\t" + "🌡" * 8192) + "\rtrailing"),
    ],
)
def test_cli_shadow_sanitizes_reader_failures_and_always_replaces_stale_output(
    tmp_path, monkeypatch, error
):
    import thermal_intel

    destination = tmp_path / "shadow.json"
    destination.write_text("stale-prior-output", encoding="utf-8")
    monkeypatch.setattr(thermal_intel.forecast_intel, "load_site_settings", lambda: {})
    monkeypatch.setattr(
        thermal_intel,
        "_current_states",
        lambda now: (_ for _ in ()).throw(error),
    )

    status = thermal_intel._shadow(SimpleNamespace(output=destination), NOW)

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert status == 1
    assert validate_shadow_output(payload) is payload
    assert payload["confidence"]["grade"] == "unavailable"
    assert payload["schedule"] == {}
    assert payload["reasons"]
    assert len(destination.read_bytes()) < 16 * 1024
    assert all(
        "\n" not in reason and "\r" not in reason and "\x00" not in reason
        for reason in payload["reasons"]
    )
    if not str(error):
        assert payload["reasons"] == ["current state input unavailable"]
    assert "publish" not in json.dumps(payload).lower()


def test_empty_artifact_reader_failure_names_the_failed_input_class():
    output = run_shadow(
        registry=AcceptedRegistry(error=ArtifactUnavailable()),
        current=current_states(),
        forecast=forecast_hours(24),
        now=NOW,
    )

    assert output["confidence"]["grade"] == "unavailable"
    assert output["schedule"] == {}
    assert output["reasons"] == ["accepted artifact input unavailable"]


def test_pipeline_applies_nonwinter_shade_transitions_and_emits_matching_markers():
    hourly = forecast_hours(30)
    rows = interpolate_hourly_forecast(
        hourly, start=hourly[0]["at"], end=hourly[-1]["at"]
    )
    schedule = baseline_schedule(warm_behavior(), rows)

    thermal_pipeline._validate_internal_schedule(
        schedule, horizon_start=rows[0]["at"], horizon_end=rows[-1]["at"]
    )
    forcings = thermal_pipeline._schedule_forcings(rows, schedule)
    by_local_hour = {
        row["at"].astimezone(LOCAL).hour: forcing["indoor_shade_closed"]
        for row, forcing in zip(rows[1:24 * 12 + 1], forcings)
    }
    assert by_local_hour[12] == 1.0
    assert by_local_hour[23] == 0.0

    expected = [
        (item["at"], f'indoor_shade_{"open" if item["state"] == "open" else "close"}')
        for item in schedule["shadeTransitions"]
    ]
    actual = [
        item for item in thermal_pipeline._action_events(schedule)
        if item[1].startswith("indoor_shade_")
    ]
    assert actual == expected


def test_pipeline_fall_charge_forcing_keeps_shades_open_without_markers():
    hourly = [{**row, "mode": "fall_charge"} for row in forecast_hours(30)]
    rows = interpolate_hourly_forecast(
        hourly, start=hourly[0]["at"], end=hourly[-1]["at"]
    )
    schedule = baseline_schedule(warm_behavior(), rows)

    assert all(
        forcing["indoor_shade_closed"] == 0.0
        for forcing in thermal_pipeline._schedule_forcings(rows, schedule)
    )
    assert not any(
        marker.startswith("indoor_shade_")
        for _, marker in thermal_pipeline._action_events(schedule)
    )


def test_internal_schedule_rejects_boosted_segment_outside_owning_vent_window():
    horizon_start = NOW
    horizon_end = NOW + timedelta(hours=24)
    schedule = {
        "mode": "warm",
        "ventOpenAt": NOW + timedelta(hours=8),
        "ventCloseAt": NOW + timedelta(hours=14),
        "shadeOpenAt": None,
        "shadeCloseAt": None,
        "airflowSegments": (
            {
                "startAt": NOW + timedelta(hours=8),
                "endAt": NOW + timedelta(hours=14),
                "level": "baseline",
            },
            {
                "startAt": NOW + timedelta(hours=7),
                "endAt": NOW + timedelta(hours=9),
                "level": "boosted",
            },
        ),
    }

    with pytest.raises(ValueError, match="boosted.*vent"):
        thermal_pipeline._validate_internal_schedule(
            schedule, horizon_start=horizon_start, horizon_end=horizon_end
        )


def test_cli_keeps_only_the_existing_commands_and_adds_explicit_shadow_publish():
    import thermal_intel

    parser = thermal_intel._build_parser()
    help_text = parser.format_help()
    assert all(name in help_text for name in ("journal", "train", "backtest", "shadow"))
    assert parser.parse_args(["shadow"]).publish is False
    assert parser.parse_args(["shadow", "--publish"]).publish is True
