"""Marginal labels retain actual acquisition and original measurement meaning."""
from datetime import timedelta
import importlib.util,json
from dataclasses import replace
import pytest
from learning_fixtures import T,EPOCH,receipt
from weather_learning.contracts import identity


def api():
    assert importlib.util.find_spec('weather_learning.marginal_outcomes'), 'Task7 original marginal outcome adapters missing'
    from weather_learning import marginal_outcomes
    return marginal_outcomes


def temp(at=T,acquired=None,**kw):
    return api().temperature_observation(receipt(at),target=at,acquired_at=at+timedelta(minutes=2) if acquired is None else acquired,sensor_epoch=EPOCH,observation_policy_sha256='a'*64,**kw)


def test_temperature_outcome_preserves_original_receipt_and_actual_late_capture():
    at=T;acquired=at+timedelta(days=2);value=temp(at,acquired).to_dict()
    assert value['available_at']==acquired.isoformat()
    assert value['target_start']==value['target_end']==at.isoformat()
    assert value['value']==pytest.approx(12.) and value['measurement_health_qualified'] is True
    assert value['original']['snapshotSha256']==receipt(at)['snapshotSha256']
    assert api().load_observation(value).to_dict()==value


def test_temperature_label_refuses_wrong_epoch_and_before_maturity():
    with pytest.raises(ValueError):temp(acquired=T-timedelta(seconds=1))
    point=receipt(T,epoch='00000000-0000-4000-8000-000000000099')
    with pytest.raises(ValueError):api().temperature_observation(point,target=T,acquired_at=T+timedelta(minutes=2),sensor_epoch=EPOCH,observation_policy_sha256='a'*64)


def test_rehashed_changed_observation_value_is_refused_by_literal_source_replay():
    value=temp().to_dict();value['value']=99;value['observation_sha256']=identity({k:v for k,v in value.items() if k!='observation_sha256'})
    with pytest.raises(ValueError,match='original|replay'):api().load_observation(value)


def test_wind_zero_and_units_are_replayed_without_measurement_health_claim():
    from weather_learning.correction_monitor import wind_outcome
    start=T.replace(minute=0,second=0,microsecond=0);end=start+timedelta(hours=1);acquired=end+timedelta(minutes=2)
    rows=[(start+timedelta(minutes=i),0. if i<30 else 10.) for i in range(61)]
    raw=wind_outcome(rows,start=start,assessed_at=acquired,source_available_at=acquired,unit='mph')
    obj=api().wind_observation(raw,acquired_at=acquired,observation_policy_sha256='a'*64);body=obj.to_dict()
    assert body['kind']=='wind' and body['measurement_health_qualified'] is False
    assert body['value']==pytest.approx(raw['value']) and body['unit']=='m_s'
    assert api().load_observation(body).to_dict()==body
    changed=dict(raw,value=raw['value']+1)
    with pytest.raises(ValueError,match='original|wind'):api().wind_observation(changed,acquired_at=acquired,observation_policy_sha256='a'*64)


def test_solar_hour_is_the_original_reported_proxy_not_physical_irradiance():
    from test_solar_shadow import source
    from weather_learning.solar_shadow import capture_solar_window
    raw=capture_solar_window(**source(values=(0,0)));at=__import__('datetime').datetime.fromisoformat(raw['start']);acquired=__import__('datetime').datetime.fromisoformat(raw['assessed_at'])
    body=api().solar_observation(raw,start=at,acquired_at=acquired,observation_policy_sha256='a'*64).to_dict()
    assert body['kind']=='solar_proxy' and body['value']==0 and body['physical_calibration_qualified'] is False
    assert body['target_end']==(at+timedelta(hours=1)).isoformat()
    assert api().load_observation(body).to_dict()==body


def test_first_actual_capture_is_reused_for_repeated_forecast_origins(tmp_path):
    from weather_learning.shadow import ShadowStore
    state=ShadowStore(tmp_path/'state');at=T;now=T+timedelta(minutes=2);work=dict(kind='temperature',start=at.isoformat(),end=at.isoformat());calls=[]
    def read(w,a):calls.append(w);return temp(at,now)
    first=api().captured_observations(state,[work],now=now,observation_policy_sha256='a'*64,read=read,apply=True,clock=lambda:now)
    again=api().captured_observations(state,[work],now=now+timedelta(days=1),observation_policy_sha256='a'*64,read=lambda *a:pytest.fail('first capture reused'),apply=True,clock=lambda:now+timedelta(days=1))
    assert len(calls)==1 and list(first.values())[0].to_dict()==list(again.values())[0].to_dict()


def test_preview_capture_is_pure_and_unknown_old_acquisition_cannot_be_backdated(tmp_path):
    from weather_learning.shadow import ShadowStore
    state=ShadowStore(tmp_path/'state');now=T+timedelta(minutes=2);work=dict(kind='temperature',start=T.isoformat(),end=T.isoformat());before=set(state.root.rglob('*'))
    result=api().captured_observations(state,[work],now=now,observation_policy_sha256='a'*64,read=lambda *a:temp(T,now),apply=False,clock=lambda:now)
    assert len(result)==1 and set(state.root.rglob('*'))==before
    with pytest.raises(ValueError,match='acquisition|capture'):
        api().captured_observations(state,[work],now=now+timedelta(days=2),observation_policy_sha256='a'*64,read=lambda *a:temp(T,now),apply=True,clock=lambda:now+timedelta(days=2))


def test_actual_http_wind_original_is_replayed_and_unit_changes_refused():
    from weather_learning.correction_monitor import wind_outcome
    from weather_learning.wind_history import ITEM
    start=T.replace(minute=0,second=0,microsecond=0);end=start+timedelta(hours=1);ready=end+timedelta(minutes=2)
    rows=[(start+timedelta(minutes=i),10.) for i in range(61)]
    raw=wind_outcome(rows,start=start,assessed_at=ready,source_available_at=ready,unit='mph')
    original=dict(schema='earthship-station-wind-http-source/v1',item=ITEM,unit='mph',query_start=(start-timedelta(seconds=120)).isoformat(),query_end=end.isoformat(),assessment_started_at=(ready-timedelta(seconds=2)).isoformat(),requested_at=(ready-timedelta(seconds=1)).isoformat(),received_at=ready.isoformat(),raw=json.dumps(dict(name=ITEM,unit='mph',data=[dict(time=at.timestamp()*1000,state=str(value)+' mph') for at,value in rows])),automatic_actuation=False)
    raw.update(original=original,source_sha256=identity(original),unit='m_s')
    body=api().wind_observation(raw,acquired_at=ready+timedelta(seconds=1),observation_policy_sha256='a'*64).to_dict()
    assert body['value']==pytest.approx(4.4704) and api().load_observation(body).to_dict()==body
    altered=dict(original,raw=original['raw'].replace('"unit": "mph"','"unit": "m/s"'))
    with pytest.raises(ValueError,match='wind'):
        api().wind_observation(dict(raw,original=altered,source_sha256=identity(altered)),acquired_at=ready+timedelta(seconds=1),observation_policy_sha256='a'*64)


def test_temperature_scoring_quality_matches_known_issuance_context():
    from weather_learning.probabilistic_issue import temperature_context
    expected=temperature_context(receipt(T),sampled_at=T,acquired_at=T,sensor_epoch=EPOCH).quality_at(T)
    assert temp().to_dict()['quality']==expected
