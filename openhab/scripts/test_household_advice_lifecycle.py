"""Retained as-issued advice, correction semantics and conservative outcomes."""
from datetime import timedelta
from copy import deepcopy
import importlib
import pytest
from test_household_advice_contract import run,policy
from local_measurement_test_support import NOW


def api():return importlib.import_module('household.advice.lifecycle')


def test_equivalent_refresh_keeps_episode_but_material_state_changes_it():
    first=run();later=run(now=NOW+timedelta(seconds=1))
    assert first['recommendations'][0]['episode_id']==later['recommendations'][0]['episode_id']
    assert first['report_id']!=later['report_id']


def test_dismiss_and_snooze_survive_refresh_and_undo_restores():
    first=run();rec=first['recommendations'][0]
    events=[dict(event_id='one',episode_id=rec['episode_id'],kind='dismiss',at=NOW.isoformat(),snooze_until=None,corrects=None)]
    assert api().feedback_status(rec,events,now=NOW)=='dismissed'
    events.append(dict(event_id='two',episode_id=rec['episode_id'],kind='undo',at=NOW.isoformat(),snooze_until=None,corrects='one'))
    assert api().feedback_status(rec,events,now=NOW)=='unseen'
    events=[dict(event_id='three',episode_id=rec['episode_id'],kind='snooze',at=NOW.isoformat(),snooze_until=(NOW+timedelta(seconds=30)).isoformat(),corrects=None)]
    assert api().feedback_status(rec,events,now=NOW)=='snoozed'
    assert api().feedback_status(rec,events,now=NOW+timedelta(seconds=31))=='unseen'


def test_seen_and_action_reported_are_not_observed_target_or_effect():
    rec=run()['recommendations'][0]
    event=dict(event_id='one',episode_id=rec['episode_id'],kind='report_action_taken',at=NOW.isoformat(),snooze_until=None,corrects=None)
    assert api().feedback_status(rec,[event],now=NOW)=='action_self_reported'
    assert api().evaluate_usefulness([run()],[event],[])['causal_benefit_qualified'] is False


def test_history_retains_originals_and_rejects_altered_report(tmp_path):
    store=api().AdviceHistory(tmp_path/'advice.sqlite');r=run()
    store.retain(r,inputs={'fixture':'frozen input'},runtime={'advice':'a'*64})
    assert api().AdviceHistory(tmp_path/'advice.sqlite').reports()==[r]
    bad=deepcopy(r);bad['recommendations'][0]['reason']='Changed'
    with pytest.raises(ValueError):store.retain(bad,inputs={},runtime={})


def test_later_outcomes_do_not_become_original_features_or_causal_labels():
    r=run();report=api().evaluate_usefulness([r],[],[dict(observed_at=(NOW+timedelta(hours=1)).isoformat(),temperature_f=72.)])
    assert report['recommendation_count']==len(r['recommendations'])
    assert report['observed_outcome_count']==1
    assert report['unchosen_alternatives_observed'] is False
    assert report['causal_benefit_qualified'] is False


def test_observed_target_is_per_member_stopped_and_deduplicated(tmp_path):
    from test_shade_position_observations import event
    store=api().AdviceHistory(tmp_path/'advice.sqlite');report=run();store.retain(report,inputs={},runtime={})
    at=NOW+timedelta(seconds=1)
    row=event(position=0.,observed_at=at.isoformat(),received_at=at.isoformat(),available_at=at.isoformat())
    records=store.observe_targets([row],now=at)
    assert len(records)==1 and records[0]['kind']=='target_observed'
    assert records[0]['user_motivation_known'] is False and records[0]['thermal_benefit_verified'] is False
    assert store.observe_targets([row],now=at+timedelta(seconds=1))==records
    late=NOW+timedelta(hours=1)
    row=event(seq=2,position=0.,observed_at=late.isoformat(),received_at=late.isoformat(),available_at=late.isoformat())
    assert store.observe_targets([row],now=late)==[]


def test_recent_evaluation_window_is_bounded_and_originals_stay_retained(tmp_path):
    store=api().AdviceHistory(tmp_path/'advice.sqlite')
    originals=[run(now=NOW+timedelta(seconds=i)) for i in range(3)]
    for report in originals:store.retain(report,inputs={},runtime={})
    assert store.recent_reports(2)==originals[-2:]
    assert store.reports()==originals
    with pytest.raises(ValueError):store.recent_reports(129)
