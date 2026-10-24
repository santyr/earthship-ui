"""Approved provisional comparisons use real evidence, never invented device state."""
from copy import deepcopy
from datetime import timedelta
from test_household_advice_contract import snapshot, state, api, NOW
from household.snapshot import HouseholdSnapshot
from household.codec import canonical,identity


def evaluate(air=80,out=60,solar=True,stale=False):
 body=snapshot().to_dict();body.pop('snapshot_id');body['domains']['thermal']['air_temperature']['value']=air;body['domains']['weather']['outdoor_temperature']['value']=out
 if stale:body['domains']['thermal']['air_temperature']['evidence']['valid_until']=(NOW-timedelta(seconds=1)).isoformat()
 snap=HouseholdSnapshot(canonical(body));action=state();action['snapshot_id']=snap.snapshot_id;action['declarations']=[]
 projections={'provisional_preferences':dict(schema='earthship-provisional-advice-preferences/v1',enabled=True,comfort_min_f=70,comfort_max_f=76,timezone='America/Denver'),'solar':dict(snapshot_id=snap.snapshot_id,source_ref='a'*64,available_at=NOW.isoformat(),valid_until=(NOW+timedelta(minutes=2)).isoformat(),direct_gain_available=solar)}
 return api().evaluate_advice(snapshot=snap,policy=None,projections=projections,action_state=action,now=NOW),snap


def test_approved_band_yields_readable_cooling_and_shading_without_fake_states():
 report,_=evaluate()
 assert report['domains']['ventilation']['status']=='conditional'
 assert report['domains']['ventilation']['comparison'][1]['alternative']=='Ventilate briefly'
 assert report['domains']['shades']['comparison'][1]['alternative']=='Reduce solar heat gain'
 assert report['recommendations']==[] and report['automatic_actuation'] is False
 assert '70–76' in report['domains']['ventilation']['comparison'][1]['outcome']
 assert report['policy_sha256'] is not None


def test_cold_indoor_air_does_not_get_a_cooling_suggestion():
 report,_=evaluate(air=65,out=50)
 assert report['domains']['ventilation']['comparison'][1]['alternative']=='Keep heat in'
 assert report['domains']['shades']['comparison'][1]['alternative']=='Use available solar heat'


def test_provisional_comparisons_expire_with_the_original_evidence():
 report,snap=evaluate()
 from household.control_contracts import instant
 for domain in ['shades','ventilation']:
  deadline=instant(report['domains'][domain]['valid_until'])
  assert deadline<=instant(snap.to_dict()['domains']['thermal']['air_temperature']['evidence']['valid_until'])
 report,_=evaluate(stale=True)
 assert report['domains']['ventilation']['comparison']==[]
 assert report['domains']['shades']['comparison']==[]


def test_no_invented_discretionary_load_or_night_override_advice():
 report,_=evaluate()
 assert report['domains']['energy']['comparison']==[]
 assert report['domains']['energy']['reason']=='approved_flexible_task_missing'


def test_malformed_optional_solar_does_not_hide_ventilation(monkeypatch):
 import household.advice.provisional as provisional
 original=provisional.evaluate
 def damaged(report,snap,projections,action,now):
  broken=deepcopy(projections);broken['solar'].pop('valid_until')
  return original(report,snap,broken,action,now)
 monkeypatch.setattr(provisional,'evaluate',damaged)
 report,_=evaluate()
 assert report['domains']['ventilation']['comparison'][1]['alternative']=='Ventilate briefly'
 assert report['domains']['shades']['comparison']==[]


def test_invalid_provisional_band_is_rejected():
 import pytest
 from household.advice.provisional import validate_preferences
 with pytest.raises(ValueError):validate_preferences(dict(schema='earthship-provisional-advice-preferences/v1',enabled=True,comfort_min_f=80,comfort_max_f=70,timezone='America/Denver'))


def test_recent_setting_comparison_expires_at_the_end_of_the_hold(monkeypatch):
 import household.advice.provisional as provisional
 original=provisional.evaluate
 def recent(report,snap,projections,action,now):
  action=deepcopy(action);action['shade_movements']=[dict(shade_id='shade-9',epoch='installation-1',stop_observed_at=(NOW-timedelta(seconds=590)).isoformat(),event_refs=['d'*64])]
  return original(report,snap,projections,action,now)
 monkeypatch.setattr(provisional,'evaluate',recent)
 report,_=evaluate()
 from household.control_contracts import instant
 assert report['domains']['shades']['comparison'][1]['alternative']=='Keep the recent shade setting'
 assert instant(report['domains']['shades']['valid_until'])<=NOW+timedelta(seconds=10)
