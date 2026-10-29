"""Decision behavior from real frozen inputs, without any physical transport."""
from datetime import timedelta
from copy import deepcopy
import importlib
import pytest
from test_household_planning import setup
from local_measurement_test_support import NOW


def api():
    return importlib.import_module('household.advice')


def snapshot():
    original,_=setup();body=original.to_dict();body.pop("snapshot_id")
    ref=body["domains"]["energy"]["battery_soc"]["evidence"]
    for domain,role,value in (("thermal","air_temperature",60.),("weather","outdoor_temperature",50.)):
        body["domains"][domain][role]=dict(value=value,unit="degF",reason=None,evidence={**ref,"source_role":role})
        body["temporal_policy"]["max_age_seconds"][role]=120
    from household.snapshot import HouseholdSnapshot
    from household.codec import canonical
    return HouseholdSnapshot(canonical(body))


def policy():
    return dict(schema='earthship-household-advice-policy/v1',version='operator-fixture-1',timezone='America/Denver',
        valid_until=(NOW+timedelta(days=1)).isoformat(),comfort_min_f=65.,comfort_max_f=80.,
        validity_seconds=120,review_seconds=60,minimum_temperature_delta_f=2.,manual_hold_seconds=600,
        shades=dict(target='living',shade_ids=['shade-9'],privacy_required=False),
        ventilation=dict(target='living-window',window_minutes=15,allowed=True,required_checks=['rain','wind','security','smoke']),
        energy=dict(reserve_soc_pct=20.,minimum_benefit_soc_pct=1.,loads=[]))


def state():
    snap=snapshot()
    return dict(schema='earthship-household-action-state/v1',snapshot_id=snap.snapshot_id,
        declarations=[dict(target='living',kind='shade',value=0.,reported_at=NOW.isoformat(),
          valid_until=(NOW+timedelta(minutes=30)).isoformat(),source='operator',revision='1'),
          dict(target='living-window',kind='opening',value='closed',reported_at=NOW.isoformat(),
          valid_until=(NOW+timedelta(minutes=30)).isoformat(),source='operator',revision='1')],shade_reports=[],shade_movements=[],checks={})


def run(**changes):
    snap=changes.get('snapshot',snapshot())
    args=dict(snapshot=snap,projections={'solar':dict(snapshot_id=snap.snapshot_id,source_ref='d'*64,available_at=NOW.isoformat(),valid_until=(NOW+timedelta(seconds=120)).isoformat(),direct_gain_available=True)},policy=policy(),action_state=state(),now=NOW)
    args.update(changes)
    return api().evaluate_advice(**args)


def test_missing_policy_is_precise_and_does_not_invent_preferences():
    report=run(policy=None)
    assert {d['reason'] for d in report['domains'].values()}=={'operator_policy_missing'}
    assert report['recommendations']==[]


def test_current_report_is_deterministic_human_only_and_closed():
    a=run();assert a==run()
    assert a['automatic_actuation'] is False and a['human_action_only'] is True
    assert api().validate_report(a)==a
    damaged=deepcopy(a);damaged['command']='ON'
    with pytest.raises(ValueError):api().validate_report(damaged)


def test_missing_shade_state_is_not_a_no_change_decision():
    s=state();s['declarations']=[]
    r=run(action_state=s)
    assert r['domains']['shades']['status']=='insufficient_evidence'
    assert r['domains']['shades']['reason']=='shade_state_unknown'


def test_future_declaration_and_snapshot_mismatch_are_refused():
    s=state();s['declarations'][0]['reported_at']=(NOW+timedelta(seconds=1)).isoformat()
    assert run(action_state=s)['domains']['shades']['status']=='insufficient_evidence'
    s=state();s['snapshot_id']='f'*64
    with pytest.raises(ValueError):run(action_state=s)


def test_stale_battery_does_not_block_independent_shade_path():
    snap=snapshot();body=snap.to_dict();body['domains']['energy']['battery_soc']['reason']='source_stale'
    body['domains']['thermal']['air_temperature']['value']=60.
    from household.snapshot import HouseholdSnapshot
    from household.codec import canonical
    body.pop('snapshot_id');snap=HouseholdSnapshot(canonical(body));s=state();s['snapshot_id']=snap.snapshot_id
    r=run(snapshot=snap,action_state=s)
    assert r['domains']['shades']['status']=='recommendation_available'
    assert r['recommendations'][0]['effects']['thermal_f'] is None


def test_bad_policy_fails_closed_without_cross_domain_defaults():
    p=policy();p['comfort_min_f']=100.
    with pytest.raises(ValueError):run(policy=p)


@pytest.mark.parametrize('damage',['rule_effect','private_baseline','partial_rule','no_comparison'])
def test_issued_advice_rejects_unsupported_effect_or_private_baseline(damage):
    from household.codec import identity
    report=run();rec=report['recommendations'][0]
    if damage=='rule_effect':rec['effects']['thermal_f']=-5.
    elif damage=='private_baseline':rec['baseline']['state']={'private_path':'private'}
    elif damage=='partial_rule':rec['action_spec']['position_open_pct']=47.5
    else:rec['comparison']=[]
    rec['recommendation_id']=identity({k:v for k,v in rec.items() if k!='recommendation_id'})
    report['report_id']=identity({k:v for k,v in report.items() if k!='report_id'})
    with pytest.raises(ValueError):api().validate_report(report)


def test_no_change_evaluation_keeps_its_own_relevant_source_expiry():
    from test_household_advice_thermal import thermal
    report=thermal(72.)
    assert report['domains']['shades']['status']=='no_change_recommended'
    assert report['domains']['shades']['valid_until']<=report['valid_until']
    assert report['domains']['shades']['valid_until']==snapshot().to_dict()['domains']['thermal']['air_temperature']['evidence']['valid_until']
