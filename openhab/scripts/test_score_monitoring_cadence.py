"""Current-model reports must refresh before their existing 15-minute expiry."""
from datetime import datetime,timedelta,timezone
import pytest


def test_daily_cadence_keeps_current_fresh_without_more_jobs():
    import household_forecast_score as score
    begin=datetime(2026,10,14,tzinfo=timezone.utc)
    history=[dict(stage='/archive/'+str(i),deployment_sha256=format(i,'064x')) for i in range(31)]
    roles={name:[] for name in ['current','historical','legacy','reserved']};selected=[]
    for minute in range(24*60):
        at=begin+timedelta(minutes=minute);role=score.score_role(at);roles[role].append(minute)
        if role in ('current','historical'):
            target=score.native_score_selection(dict(historical=history),at)
            if role=='current':assert target=='current'
            else:selected.append(target['stage'])
    assert len(roles['current'])==144
    assert len(roles['historical'])==len(roles['legacy'])==72
    assert all(b-a==10 for a,b in zip(roles['current'],roles['current'][1:]))
    assert set(selected)=={row['stage'] for row in history}
    assert sorted(roles['current']+roles['historical']+roles['legacy'])==list(range(1,24*60,5))
    assert all(minute%5 not in (3,4) for minute in roles['current']+roles['historical']+roles['legacy'])


def test_history_slot_without_history_refreshes_current_report():
    import household_forecast_score as score
    at=datetime(2026,10,14,20,16,tzinfo=timezone.utc)
    assert score.native_score_selection(dict(historical=[]),at)=='current'
    with pytest.raises(ValueError):score.native_score_selection(dict(historical=[]),at+timedelta(minutes=1))


def test_family_records_new_roles_without_changing_old_family_or_timer(tmp_path,monkeypatch):
    import household_native_family as family
    from test_native_serving_upgrade import fixture
    monkeypatch.setattr(family,'_extended_score_window',lambda stage:True)
    monkeypatch.setattr(family,'_frequent_current_scores',lambda stage:stage.name=='new-stage')
    deploy,handoff,new,kwargs,targets,old=fixture(tmp_path,monkeypatch)
    assert family.verify(old,guard=lambda:None)['score_slot_roles']==dict(current=[1],legacy=[6],period_minutes=10)
    assert family.verify(new,guard=lambda:None)['score_slot_roles']==dict(current=[1,11],historical=[16],legacy=[6],period_minutes=20)
    assert (new/'score-timer.conf').read_bytes()==(old/'score-timer.conf').read_bytes()
    handoff.prepare(new,**kwargs)
