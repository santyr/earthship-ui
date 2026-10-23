"""Cold/warm/no-change decisions and bounded ventilation without safety claims."""
from datetime import timedelta
from copy import deepcopy
from test_household_advice_contract import run,policy,state,snapshot
from household.snapshot import HouseholdSnapshot
from household.codec import canonical
from local_measurement_test_support import NOW


def temperatures(air,out=50.):
    s=snapshot().to_dict();s.pop('snapshot_id');s['domains']['thermal']['air_temperature']['value']=air;s['domains']['weather']['outdoor_temperature']['value']=out
    return HouseholdSnapshot(canonical(s))


def thermal(air,out=50.,shade=0.,opening='closed',**changes):
    snap=temperatures(air,out);s=state();s['snapshot_id']=snap.snapshot_id;s['declarations'][0]['value']=shade;s['declarations'][1]['value']=opening
    for key in ('rain','wind','security','smoke'):s['checks'][key]=dict(clear=True,observed_at=NOW.isoformat(),valid_until=(NOW+timedelta(seconds=100)).isoformat(),source_ref='e'*64)
    args=dict(snapshot=snap,action_state=s);args.update(changes);return run(**args)


def test_cold_sunny_open_warm_sunny_close_and_comfortable_hold():
    cold=thermal(60.);warm=thermal(85.,shade=100.)
    assert any('to 100%' in r['action'] for r in cold['recommendations'])
    assert any('to 0%' in r['action'] for r in warm['recommendations'])
    assert thermal(72.)['domains']['shades']['status']=='no_change_recommended'
    assert all(r['effects']['thermal_f'] is None for r in cold['recommendations']+warm['recommendations'])


def test_privacy_can_defeat_solar_heat_capture():
    p=policy();p['shades']['privacy_required']=True
    assert thermal(60.,shade=0.,policy=p)['domains']['shades']['reason']=='target_already_observed'


def test_unsupported_partial_advice_is_not_invented():
    r=thermal(85.,shade=37.5)
    assert next(r for r in r['recommendations'] if r['kind']=='SHADE_POSITION')['action'].endswith('0% open')


def test_favorable_ventilation_has_explicit_end_review_and_no_air_safety_claim():
    r=thermal(85.,out=70.)
    vent=next(r for r in r['recommendations'] if r['kind']=='VENTILATION_WINDOW')
    assert vent['end_at']==(NOW+timedelta(minutes=15)).isoformat()
    assert vent['review_at']<=vent['valid_until']
    assert 'does not establish clean air' in vent['reason']


def test_unresolved_conditions_are_conditional_and_adverse_wind_withholds_opening():
    snap=temperatures(85.,70.);s=state();s['snapshot_id']=snap.snapshot_id
    r=run(snapshot=snap,action_state=s);assert r['domains']['ventilation']['status']=='conditional'
    assert len(next(r for r in r['recommendations'] if r['kind']=='VENTILATION_WINDOW')['conditions'])==4
    s['checks']['wind']=dict(clear=False,observed_at=NOW.isoformat(),valid_until=(NOW+timedelta(seconds=100)).isoformat(),source_ref='e'*64)
    r=run(snapshot=snap,action_state=s);assert not any(r['kind']=='VENTILATION_WINDOW' for r in r['recommendations'])


def test_outside_warmer_or_overcooling_risk_do_not_recommend_opening():
    for out in (90.,40.):assert thermal(85.,out=out)['domains']['ventilation']['status']=='no_change_recommended'


def test_open_vent_gets_close_or_reassessment_when_conditions_turn():
    r=thermal(72.,out=40.,opening='open')
    assert any(r['action'].startswith('Close living-window') for r in r['recommendations'])
