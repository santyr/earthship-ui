"""Explicit native-v2 origin and outcome contracts; original source receipts retained."""
from copy import deepcopy
from datetime import timedelta
from dataclasses import replace
import json
import pytest
from test_thermal_origin_capture import NOW,capture_inputs,VALUES
from test_thermal_sensor_epoch_history import EPOCHS
from test_thermal_sensor_epoch_training import sensor_artifact
from thermal_model.temperature_history import STREAMS,POLICY
from weather_temperature_evidence import TemperaturePolicy,MODELS
from weather_temperature_receiver import TemperatureCollector
from weather_temperature_reader import select_temperature_grid_v2
import thermal_temperature_runtime as runtime
import thermal_model.origin_capture as origins
import thermal_model.graduation_evidence as evidence


def native_grid():
    policies={stream:TemperaturePolicy(model,sensor,**POLICY) for stream,model,sensor in STREAMS.values()}
    phases={identity[0]:EPOCHS[role] for role,identity in STREAMS.items()}
    first=NOW-timedelta(minutes=5*287);clock={'at':first,'tick':1000,'pid':1}
    source=TemperatureCollector(policies,sensor_epochs=phases,clock=lambda:clock['at'],monotonic=lambda:clock['tick'],process_id=lambda:clock['pid'])
    rows=[]
    for index in range(288):
        at=first+timedelta(minutes=5*index)
        clock.update(at=at-timedelta(seconds=30),tick=1000+index*300,pid=1 if index<144 else 2)
        for stream,policy in policies.items():source.observe({'model':policy.model,'id':str(policy.sensor_id),MODELS[policy.model][1]:str(VALUES[stream])})
        rows.append((at-timedelta(seconds=20),json.dumps(source.snapshot())))
    def read(stream,targets,assessed):
        role=next(role for role,identity in STREAMS.items() if identity[0]==stream)
        return select_temperature_grid_v2(rows,targets=targets,assessed_at=assessed,history_start=targets[0]-timedelta(seconds=120),stream=stream,policy=policies[stream],sensor_epoch=EPOCHS[role])
    return read


def sensor_inputs():
    data=capture_inputs();saved=[]
    selected=runtime.shadow_temperatures_v2(NOW,native_grid(),sensor_epochs=EPOCHS,origin_observer=saved.append)
    data['origin_temperatures']=saved[0];data['current']={role:row['current'] for role,row in selected.items()}
    data['artifact']=sensor_artifact()
    return data


def sensor_case(tmp_path):
    data=sensor_inputs();record=origins.build_sensor_origin_capture(**data)
    path=origins.write_sensor_origin_capture(tmp_path,record)
    target=NOW+timedelta(hours=1)
    def receipt(at,value,index):
        return dict(temperatureF=value,receivedAt=(at-timedelta(seconds=30)).isoformat(),storedAt=(at-timedelta(seconds=20)).isoformat(),validUntil=(at+timedelta(seconds=90)).isoformat(),streamEpoch=f'{index:08x}-99ee-4b7a-b5fc-e6a96e7274d8',snapshotSha256='a'*64,sensorEpoch=EPOCHS['air'],receiptVersion=2)
    cycles=[]
    for lag in range(1,8):
        start=NOW-timedelta(days=lag);end=target-timedelta(days=lag)
        cycles.extend([[start.isoformat(),receipt(start,70,lag)],[end.isoformat(),receipt(end,71,lag+10)]])
    return dict(origin_path=path,publication=dict(time=int((NOW+timedelta(seconds=2)).timestamp()*1000),state=json.dumps(record['output'])),horizon_hours=1,outcome=dict(target_at=target.isoformat(),receipt=receipt(target,74,20)),recent_cycle_grid=cycles,assessed_at=target+timedelta(minutes=10))


def test_v2_shadow_origin_preserves_sessions_but_declares_stable_hardware():
    data=sensor_inputs();proof=data['origin_temperatures']
    assert proof['schema']=='earthship-thermal-origin-temperatures/v2'
    for role,details in proof['roles'].items():
        assert details['identity']['sensor_epoch']==EPOCHS[role]
        assert len({value['streamEpoch'] for _,value in details['grid']})==2
        assert {value['sensorEpoch'] for _,value in details['grid']}=={EPOCHS[role]}
    with pytest.raises(ValueError):runtime.shadow_temperatures(NOW,native_grid())


def test_sensor_origin_roundtrip_is_typed_and_old_reader_refuses(tmp_path):
    tmp_path.chmod(0o700);data=sensor_inputs();record=origins.build_sensor_origin_capture(**data)
    assert record['schema']=='earthship-thermal-origin-capture/v3' and record['source_epochs']==EPOCHS
    path=origins.write_sensor_origin_capture(tmp_path,record)
    assert path.name.endswith('-origin-v3.json.gz') and path.stat().st_mode&0o777==0o600
    assert origins.read_sensor_origin_capture(path)==record
    assert origins.read_observed_origin_capture(path)==record
    with pytest.raises(ValueError):origins.read_origin_capture(path)
    with pytest.raises(ValueError):origins.build_origin_capture(**data)


@pytest.mark.parametrize('damage',['phase','receipt_version','legacy_model','expired','future_source','partial','initial','declared_phase'])
def test_sensor_origin_refuses_incompatible_or_stale_source(damage):
    data=sensor_inputs()
    if damage=='phase':data['origin_temperatures']['roles']['air']['grid'][0][1]['sensorEpoch']=EPOCHS['mass']
    elif damage=='receipt_version':data['origin_temperatures']['roles']['mass']['grid'][0][1]['receiptVersion']=1
    elif damage=='legacy_model':data['artifact']=replace(data['artifact'],schema='earthship-thermal-model/v5')
    elif damage=='expired':data['published_at']=NOW+timedelta(minutes=3)
    elif damage=='future_source':data['origin_temperatures']['roles']['air']['grid'][-1][1]['storedAt']=NOW+timedelta(seconds=1)
    elif damage=='partial':data['origin_temperatures']['roles']['outdoor']['grid'].pop()
    elif damage=='initial':data['current']['air']['value']=99
    else:data['origin_temperatures']['roles']['air']['identity']['sensor_epoch']=EPOCHS['mass']
    with pytest.raises(ValueError):origins.build_sensor_origin_capture(**data)


def test_v2_source_scoring_accepts_fresh_sessions_with_one_declared_phase(tmp_path):
    tmp_path.chmod(0o700);result=evidence.score_qualified_origin(**sensor_case(tmp_path))
    assert result['schema']=='earthship-thermal-source-scored-pair/v2'
    assert result['scored_pair']['sensor_epochs']==EPOCHS
    assert result['scored_pair']['model_error_f']==1 and result['scored_pair']['recent_cycle_error_f']==1
    assert result['release_authorized'] is False and result['action_response_qualification_claimed'] is False


@pytest.mark.parametrize('damage',['outcome_phase','cycle_phase','old_outcome','old_cycle','future_outcome','missing_cycles'])
def test_v2_source_scoring_refuses_wrong_phase_or_legacy_receipts(tmp_path,damage):
    tmp_path.chmod(0o700);data=sensor_case(tmp_path)
    if damage=='outcome_phase':data['outcome']['receipt']['sensorEpoch']=EPOCHS['mass']
    elif damage=='cycle_phase':data['recent_cycle_grid'][0][1]['sensorEpoch']=EPOCHS['mass']
    elif damage=='old_outcome':
        data['outcome']['receipt'].pop('sensorEpoch');data['outcome']['receipt'].pop('receiptVersion')
    elif damage=='old_cycle':
        data['recent_cycle_grid'][0][1].pop('sensorEpoch');data['recent_cycle_grid'][0][1].pop('receiptVersion')
    elif damage=='future_outcome':data['outcome']['receipt']['storedAt']=(NOW+timedelta(hours=1,seconds=1)).isoformat()
    else:data['recent_cycle_grid']=data['recent_cycle_grid'][:-2]
    with pytest.raises(ValueError):evidence.score_qualified_origin(**data)


def test_configured_shadow_v2_binds_fixed_policy_to_worker(tmp_path,monkeypatch):
    from test_thermal_sensor_epoch_history import sources
    policy,_=sources(tmp_path,monkeypatch);calls=[];saved=[]
    env=dict(THERMAL_TEMP_SHADOW_QUALIFIED_ENABLE='1',THERMAL_TEMP_POLICY=str(policy),THERMAL_TEMP_DB_CONFIG='/private/db.json')
    def configured(value,*,budget,sensor_epochs):
        assert value==env and budget==90 and sensor_epochs==EPOCHS
        calls.append('configured');return native_grid()
    monkeypatch.setattr(runtime,'_configured_grid_reader',configured)
    selected=runtime.configured_shadow_temperatures_v2(NOW,environ=env,origin_observer=saved.append)
    assert calls==['configured'] and saved[0]['schema']=='earthship-thermal-origin-temperatures/v2'
    assert selected['air']['current']['value']==74


def test_sensor_origin_refuses_model_hardware_mismatch_even_with_valid_model():
    data=sensor_inputs();artifact=data['artifact'];manifest=deepcopy(artifact.data_manifest)
    manifest['temperature_evidence']['roles']['air']['sensor_epoch']=EPOCHS['mass']
    data['artifact']=replace(artifact,data_manifest=manifest)
    with pytest.raises(ValueError,match='hardware phase'):origins.build_sensor_origin_capture(**data)


def test_v2_shadow_refuses_partial_role_without_observer_output():
    saved=[];real=native_grid()
    def missing(stream,targets,assessed):
        rows=real(stream,targets,assessed)
        if stream=='outdoor':rows[-1]=(rows[-1][0],None)
        return rows
    with pytest.raises(ValueError):runtime.shadow_temperatures_v2(NOW,missing,sensor_epochs=EPOCHS,origin_observer=saved.append)
    assert saved==[]
