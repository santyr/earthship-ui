import copy
from datetime import datetime, timezone

import pytest

import completed_trough_score as adapter
import forecast_intel as fi
from test_advisory_capture import run_main
from test_forecast_intel import _run_main, _scoring_state


def forbidden(*args, **kwargs):
    pytest.fail("unexpected dependency")


@pytest.mark.parametrize("flag", [None, "", "0", "true"])
def test_disabled_does_not_import_assessor_or_read_credentials(flag):
    logs, unknown = [], []
    result = adapter.update_completed_trough_score(diagnostics=logs, token_provider=forbidden,
        put_unknown=lambda: unknown.append(True), environ={"ADVISORY_ASSESS_ENABLED":flag},
        assessor=forbidden, publisher=forbidden, clock=forbidden)
    assert result == "disabled" and unknown == [True]


@pytest.mark.parametrize("report", [None, {"status":"unavailable"},
    {"status":"time_budget_exhausted"}, {"status":"decision_limit_exceeded"}])
def test_failed_or_partial_assessment_clears_diagnostic_without_publisher(report):
    unknown = []
    assert adapter.update_completed_trough_score(diagnostics=[], token_provider=forbidden,
        put_unknown=lambda: unknown.append(True), environ={"ADVISORY_ASSESS_ENABLED":"1"},
        assessor=lambda _: report, publisher=forbidden) == "assessment_unavailable"
    assert unknown == [True]


def test_publication_failure_never_retries_or_clears_after_ambiguous_write():
    calls, logs = [], []
    def publish(*args, **kwargs):
        calls.append(True)
        raise RuntimeError("PRIVATE-ERROR")
    result = adapter.update_completed_trough_score(diagnostics=logs, token_provider=lambda: "test",
        put_unknown=forbidden, environ={"ADVISORY_ASSESS_ENABLED":"1"},
        assessor=lambda _: {"status":"complete"}, publisher=publish)
    assert result == "publication_unknown" and calls == [True]
    assert "PRIVATE" not in str(logs)


@pytest.mark.parametrize("highs", [[98,83,83], [93,83,83], [92,83,83]])
@pytest.mark.parametrize("low_resource,suppressed", [(False,False), (True,False), (True,True)])
@pytest.mark.parametrize("mode", ["disabled", "accepted", "failed"])
def test_score_integration_preserves_predictions_capture_and_notification_behavior(monkeypatch, tmp_path, highs, low_resource, suppressed, mode):
    # Baseline omits only the diagnostic adapter; both paths execute real main().
    original = adapter.update_completed_trough_score
    monkeypatch.setattr(adapter, "update_completed_trough_score", lambda **kwargs: None)
    args = dict(active=True, highs=highs, low_resource=low_resource, suppressed=suppressed)
    before = run_main(monkeypatch, tmp_path, **args)
    monkeypatch.setattr(adapter, "update_completed_trough_score", original)
    monkeypatch.setenv("ADVISORY_ASSESS_ENABLED", "0" if mode == "disabled" else "1")
    calls = []
    def assess(env):
        calls.append("assess")
        return {"status":"complete" if mode == "accepted" else "time_budget_exhausted"}
    def publish(report, **kwargs):
        calls.append("publish")
        return {"sample_count":1}
    monkeypatch.setattr(adapter, "_assess", assess)
    monkeypatch.setattr(adapter, "_publish", publish)
    monkeypatch.setattr(fi, "auth_token", lambda: "test-token")
    after = run_main(monkeypatch, tmp_path, **args)
    assert before[0] == after[0]  # model, predictions, DM markers unchanged
    assert before[2] == after[2]  # exact notification command/content/options
    assert before[1] == [p for p in after[1] if p[0] != "Forecast_Trough_Error_7d"]
    if mode != "accepted":
        assert after[1][-1] == ("Forecast_Trough_Error_7d", "UNDEF")
    assert calls == ([] if mode == "disabled" else ["assess", "publish"] if mode == "accepted" else ["assess"])


@pytest.mark.parametrize("month,day", [(1,15), (7,15), (3,8), (11,1)])
def test_main_preserves_legacy_scores_and_does_not_consume_incomplete_night(monkeypatch, tmp_path, month, day):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, month, day, 6, 40, tzinfo=fi.MOUNTAIN)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)
    class Day(fi.date):
        @classmethod
        def today(cls): return cls(2026, month, day)
    monkeypatch.setattr(fi, "datetime", Clock)
    monkeypatch.setattr(fi, "date", Day)
    monkeypatch.setenv("ADVISORY_ASSESS_ENABLED", "0")
    ykey = (fi.date.today() - fi.timedelta(days=1)).isoformat()
    state = _scoring_state(ykey)
    state["trough_errors"] = [4.2, 8.1]
    original = copy.deepcopy(state["trough_errors"])
    result, puts = _run_main(monkeypatch, tmp_path, state, {"BMS_SOC":[85]})
    assert result["trough_errors"] == original
    assert "trough" not in result.get("scored", {}).get(ykey, [])
    assert puts.count("Forecast_Trough_Error_7d") == 1


def test_enabled_adapter_forwards_one_complete_report_after_assessment():
    report, calls = {"status":"complete"}, []
    now = datetime(2026,9,10,tzinfo=timezone.utc)
    def assess(env):
        calls.append("assess"); return report
    def publish(value, **kwargs):
        assert value is report and kwargs == {"token":"test", "now":now}
        calls.append("publish"); return {"sample_count":1}
    logs = []
    assert adapter.update_completed_trough_score(diagnostics=logs, token_provider=lambda:"test",
        put_unknown=forbidden, environ={"ADVISORY_ASSESS_ENABLED":"1"},
        assessor=assess, publisher=publish, clock=lambda:now) == "accepted"
    assert calls == ["assess", "publish"] and "samples=1" in logs[0]
