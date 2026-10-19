import copy
from datetime import datetime, timezone

import pytest

import completed_trough_score as adapter


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


def qualified_report(now):
    from datetime import timedelta
    from uuid import UUID
    from earthship_energy.trough_runtime import REPORT_FIELDS
    from earthship_energy.trough_selection import SELECTION_VERSION
    from earthship_energy.trough_assessment import ASSESSMENT_VERSION
    start=(now-timedelta(days=3)).date().isoformat()
    end=(now-timedelta(days=1)).date().isoformat()
    projection=dict(schema_version=1, diagnostic_version=SELECTION_VERSION,
        assessment_version=ASSESSMENT_VERSION, bank_epoch='fixture-bank',
        generated_at=now.isoformat(), target_start_day=start, target_end_day_exclusive=end,
        status='available', sample_count=1, mean_absolute_error_pct_points=3.5,
        item_value=3.5, samples=[dict(prediction_day=start,decision_id=str(UUID(int=1)),
            evidence_digest='a'*64,coverage=.99,signed_residual_pct_points=-3.5)],
        missing_outcome_dates=[],insufficient_dates=[],pending_dates=[],bandit_eligible=False)
    report={key:0 for key in REPORT_FIELDS}
    report.update(status='complete',generated_at=now.isoformat(),target_start_day=start,
        target_end_day_exclusive=end,projection=projection,causal_reward_proven=False)
    return report


def test_same_validated_prospective_projection_is_retained_without_another_assessment():
    now=datetime(2026,9,23,12,tzinfo=timezone.utc);report=qualified_report(now)
    retained={};calls=[]
    def assess(_):calls.append('assess');return report
    def publish(value,**kwargs):
        calls.append('publish');assert value is report
        return {'sample_count':1}
    result=adapter.update_completed_trough_score(diagnostics=[],token_provider=lambda:'fixture',
        put_unknown=forbidden,environ={'ADVISORY_ASSESS_ENABLED':'1'},assessor=assess,
        publisher=publish,clock=lambda:now,evidence_sink=retained)
    assert result=='accepted' and calls==['assess','publish']
    assert retained['projection']==report['projection']
    assert retained['release_authority'] is False
    assert retained['causal_reward_proven'] is False
    report['projection']['samples'][0]['coverage']=.1
    assert retained['projection']['samples'][0]['coverage']==.99


@pytest.mark.parametrize('damage',['mean','future','stale','duplicate','bank'])
def test_unverified_prospective_projection_never_reaches_sink_or_publisher(damage):
    from datetime import timedelta
    now=datetime(2026,9,23,12,tzinfo=timezone.utc);report=qualified_report(now)
    if damage=='mean':report['projection']['mean_absolute_error_pct_points']=1
    if damage=='future':report['generated_at']=(now+timedelta(seconds=1)).isoformat()
    if damage=='stale':report['generated_at']=(now-timedelta(seconds=301)).isoformat()
    if damage=='duplicate':report['projection']['samples']*=2;report['projection']['sample_count']=2
    if damage=='bank':report['projection']['bank_epoch']=''
    retained={};unknown=[]
    result=adapter.update_completed_trough_score(diagnostics=[],token_provider=forbidden,
        put_unknown=lambda:unknown.append(True),environ={'ADVISORY_ASSESS_ENABLED':'1'},
        assessor=lambda _:report,publisher=forbidden,clock=lambda:now,evidence_sink=retained)
    assert result=='assessment_unavailable' and unknown==[True] and retained=={}


def test_valid_assessment_is_retained_when_diagnostic_delivery_is_unknown():
    now=datetime(2026,9,23,12,tzinfo=timezone.utc);retained={}
    def ambiguous(*args,**kwargs):raise RuntimeError('private transport error')
    assert adapter.update_completed_trough_score(diagnostics=[],token_provider=lambda:'fixture',
        put_unknown=forbidden,environ={'ADVISORY_ASSESS_ENABLED':'1'},assessor=lambda _:qualified_report(now),
        publisher=ambiguous,clock=lambda:now,evidence_sink=retained)=='publication_unknown'
    assert retained['projection']['sample_count']==1




def test_delayed_token_read_does_not_extend_diagnostic_freshness():
    from datetime import timedelta
    from earthship_energy.trough_publish import diagnostic_state
    now=[datetime(2026,9,23,12,tzinfo=timezone.utc)];report=qualified_report(now[0]);retained={}
    def token():now[0]+=timedelta(seconds=301);return 'fixture'
    def publish(value,**kwargs):
        diagnostic_state(value,now=kwargs['now'])
        return {'sample_count':1}
    result=adapter.update_completed_trough_score(diagnostics=[],token_provider=token,
        put_unknown=forbidden,environ={'ADVISORY_ASSESS_ENABLED':'1'},assessor=lambda _:report,
        publisher=publish,clock=lambda:now[0],evidence_sink=retained)
    assert result=='publication_unknown'
    assert retained['generated_at']==report['generated_at']
