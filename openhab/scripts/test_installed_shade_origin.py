"""As-issued inputs, deterministic prediction and qualified later comparisons."""
from copy import deepcopy
from datetime import timedelta
import json
import pytest
import thermal_temperature_runtime as temperatures
from test_installed_shade_artifact import make_report, NOW, CODE
from test_installed_shade_inputs import snapshot, EPOCHS
from thermal_model.installed_shade_artifact import build_candidate_bundle, _digest
from thermal_model.forecast_history import select_origin_forecast_with_receipts, _window

ISSUE=NOW+timedelta(days=1)


def module():
    from thermal_model import installed_shade_origin
    return installed_shade_origin


@pytest.fixture(scope='module')
def candidate():
    runtime=dict(schema='earthship-thermal-runtime-binding/v1',code_revision='f'*64,
        observer_revision='e'*64,interpreter_sha256='d'*64,python_version='3.12.0',
        dependencies={'numpy':'2.0.0','scipy':'1.15.1','psycopg2':'2.9.10'},
        source_manifest={'thermal_intel.py':'c'*64,'thermal_model/origin_capture.py':'e'*64,
            'thermal_model/installed_shade_origin.py':'a'*64,
            'thermal_model/installed_shade_dynamics.py':'b'*64,
            'thermal_model/installed_shade_artifact.py':'c'*64,
            'thermal_model/forecast_history.py':'f'*64})
    inputs=snapshot(steps=864,rich_actions=True)
    bundle=build_candidate_bundle(inputs,make_report(inputs),code_revision=CODE,runtime_revision=_digest(runtime),created_at=NOW)
    return bundle,inputs,runtime


@pytest.fixture(scope='module')
def prepared(candidate):
    bundle,inputs,runtime=candidate
    return module().prepare_candidate(bundle,inputs,expected_runtime_revision=_digest(runtime),assessed_at=ISSUE)


def native(at):
    import test_thermal_sensor_epoch_origins as old
    saved=[]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(old,'NOW',at)
        selected=temperatures.shadow_temperatures_v2(at,old.native_grid(),sensor_epochs=EPOCHS,origin_observer=saved.append)
    return {role:value['current'] for role,value in selected.items()},saved[0]


def actions(at):
    def event(state,name):
        return dict(state=state,source='manual_dm',confidence=1.,effective_at=(at-timedelta(days=1)).isoformat(),received_at=(at-timedelta(days=1)).isoformat(),created_at=(at-timedelta(days=1)).isoformat(),event_id=name)
    return dict(source='thermal_intel_append_only_journal',origin=at.isoformat(),actions={name:event(state,name) for name,state in (('indoor_shade','open'),('outdoor_shade','installed'),('vent','closed'),('kiva','off'))},mode=event('warm','mode'),missing_actions=[],status='as_of_snapshot_not_outcome_confirmation')


def weather(at,hours=24):
    _,targets=_window(at,hours);records=[]
    for index,target in enumerate(targets):
        for metric,value in (('temperature_f',59+index/10),('radiation_wm2',100),('wind_mph',2),('weather_code',0)):
            records.append((at-timedelta(hours=1),at-timedelta(minutes=20),target,metric,value))
    return select_origin_forecast_with_receipts(records,origin=at,horizon_hours=hours)


@pytest.fixture(scope='module')
def original(prepared,candidate):
    current,proof=native(ISSUE)
    return module().build_issued_capture(prepared,issued_at=ISSUE,published_at=ISSUE+timedelta(seconds=2),inputs_available_at=ISSUE,
        runtime=candidate[2],forecast=weather(ISSUE),current=current,origin_temperatures=proof,action_snapshot=actions(ISSUE))


def test_original_forecast_and_native_state_are_retained_and_predictions_replay(original):
    m=module();m.validate_issued_capture(original)
    assert original['schema']=='earthship-installed-shade-origin/v1'
    assert original['output']['status']=='shadow' and original['output']['release_authorized'] is False
    assert len(original['output']['trajectory'])==24
    assert original['output']['prediction_intervals'] is None and original['output']['advice']==[]
    assert original['source_epochs']==EPOCHS
    assert original['output']['initial']['air_f']==74
    assert original['forecast']['source']=='open_meteo_openhab'


@pytest.mark.parametrize('damage',['future_weather','stale_weather','missing_weather','future_action','removed','heat','expired','phase','initial','runtime'])
def test_bad_origin_inputs_never_create_prediction(prepared,candidate,damage):
    current,proof=native(ISSUE);forecast=weather(ISSUE);knowledge=actions(ISSUE);runtime=deepcopy(candidate[2]);published=ISSUE+timedelta(seconds=2)
    if damage=='future_weather':forecast['captured_at']=ISSUE+timedelta(seconds=1)
    elif damage=='stale_weather':forecast['issued_at']=ISSUE-timedelta(hours=7)
    elif damage=='missing_weather':forecast['rows'].pop()
    elif damage=='future_action':knowledge['actions']['vent']['created_at']=(ISSUE+timedelta(seconds=1)).isoformat()
    elif damage=='removed':knowledge['actions']['outdoor_shade']['state']='removed'
    elif damage=='heat':knowledge['actions']['kiva']['state']='on'
    elif damage=='expired':published=ISSUE+timedelta(minutes=3)
    elif damage=='phase':proof['roles']['air']['identity']['sensor_epoch']=EPOCHS['mass']
    elif damage=='initial':current['air']['value']=99
    else:runtime['dependencies']['numpy']='9.0.0'
    with pytest.raises(ValueError):module().build_issued_capture(prepared,issued_at=ISSUE,published_at=published,inputs_available_at=ISSUE,runtime=runtime,forecast=forecast,current=current,origin_temperatures=proof,action_snapshot=knowledge)


def test_rehashed_prediction_tamper_fails_exact_original_replay(original):
    record=deepcopy(original);record['output']['trajectory'][-1]['air_f']+=1
    record['capture_sha256']=_digest({key:value for key,value in record.items() if key!='capture_sha256'})
    with pytest.raises(ValueError):module().validate_issued_capture(record)


def test_private_capture_roundtrip_preserves_exact_issued_output(tmp_path,original):
    m=module();tmp_path.chmod(0o700);path=m.write_issued_capture(tmp_path,original)
    assert path.stat().st_mode&0o777==0o600
    assert m.read_issued_capture(path)==original
    assert m.write_issued_capture(tmp_path,original)==path


def test_november_default_remains_closed_until_new_confirmed_operator_entry():
    m=module();at=ISSUE.replace(month=11,day=1);known=actions(at)
    known['actions'].pop('vent');known['missing_actions']=['vent']
    values=m._origin_actions(known,at)
    assert values['vent_open']==0 and values['vent_provenance']=='operator_default_no_vent'
    known['actions']['vent']={**actions(at)['actions']['vent'],'state':'open'};known['missing_actions']=[]
    assert m._origin_actions(known,at)['vent_open']==0
    for key in ('received_at','effective_at','created_at'):known['actions']['vent'][key]=at.isoformat()
    assert m._origin_actions(known,at)['vent_open']==1


def outcome(at,value=75):
    return dict(temperatureF=value,receivedAt=(at-timedelta(seconds=30)).isoformat(),storedAt=(at-timedelta(seconds=20)).isoformat(),validUntil=(at+timedelta(seconds=90)).isoformat(),streamEpoch='66666666-99ee-4b7a-b5fc-e6a96e7274d8',snapshotSha256='a'*64,sensorEpoch=EPOCHS['air'],receiptVersion=2)


def cycles(hours):
    rows={}
    for lag in range(1,9 if hours==24 else 8):
        begin=ISSUE-timedelta(days=lag);end=begin+timedelta(hours=hours)
        rows[begin]=outcome(begin,74)
        if end<ISSUE:rows[end]=outcome(end,74 if hours==24 else 75)
    # Preserve the existing strictly-historical policy: 24h uses lags2..8.
    # The cycle ending exactly at issue is excluded, not counted as a seventh.
    return [[at.isoformat(),value] for at,value in sorted(rows.items())]


@pytest.mark.parametrize('hours',[1,6,12,24])
def test_original_publication_and_qualified_outcome_score_all_required_horizons(original,hours):
    m=module();target=ISSUE+timedelta(hours=hours)
    publication=dict(time=int((ISSUE+timedelta(seconds=2)).timestamp()*1000),state=json.dumps(original['output']))
    result=m.score_issued_capture(original,publication=publication,horizon_hours=hours,outcome=dict(target_at=target.isoformat(),receipt=outcome(target)),recent_cycle_grid=cycles(hours),assessed_at=target+timedelta(minutes=10))
    assert result['schema']=='earthship-installed-shade-source-scored-pair/v1'
    assert result['scored_pair']['persistence_error_f']==-1
    assert result['scored_pair']['sensor_epochs']==EPOCHS and result['release_authorized'] is False
    assert result['scored_pair']['artifact_sha256']==original['candidate']['artifact_sha256']


@pytest.mark.parametrize('damage',['publication','phase','future_outcome','cycles'])
def test_scoring_refuses_revised_publication_or_unqualified_outcomes(original,damage):
    target=ISSUE+timedelta(hours=1);publication=dict(time=int((ISSUE+timedelta(seconds=2)).timestamp()*1000),state=json.dumps(original['output']));receipt=outcome(target);grid=cycles(1)
    if damage=='publication':publication['state']=json.dumps({**original['output'],'status':'forecast_active'})
    elif damage=='phase':receipt['sensorEpoch']=EPOCHS['mass']
    elif damage=='future_outcome':receipt['storedAt']=(target+timedelta(seconds=1)).isoformat()
    else:grid.pop()
    with pytest.raises(ValueError):module().score_issued_capture(original,publication=publication,horizon_hours=1,outcome=dict(target_at=target.isoformat(),receipt=receipt),recent_cycle_grid=grid,assessed_at=target+timedelta(minutes=10))



def test_late_persisted_publication_cannot_claim_the_earlier_captured_issue(original):
    target=ISSUE+timedelta(hours=1)
    publication=dict(time=int((ISSUE+timedelta(minutes=10)).timestamp()*1000),state=json.dumps(original['output']))
    with pytest.raises(ValueError):module().score_issued_capture(original,publication=publication,horizon_hours=1,outcome=dict(target_at=target.isoformat(),receipt=outcome(target)),recent_cycle_grid=cycles(1),assessed_at=target+timedelta(minutes=10))


@pytest.mark.parametrize('damage',['actions','event'])
def test_malformed_action_inputs_refuse_cleanly(damage):
    known=actions(ISSUE)
    if damage=='actions':known['actions']=None
    else:known['actions']['vent']=None
    with pytest.raises(ValueError):module()._origin_actions(known,ISSUE)



def test_archive_hash_must_bind_original_weather_values(prepared,candidate):
    current,proof=native(ISSUE);forecast=weather(ISSUE)
    forecast['rows'][0]['tempF']+=1
    with pytest.raises(ValueError):module().build_issued_capture(prepared,issued_at=ISSUE,published_at=ISSUE+timedelta(seconds=2),inputs_available_at=ISSUE,runtime=candidate[2],forecast=forecast,current=current,origin_temperatures=proof,action_snapshot=actions(ISSUE))
