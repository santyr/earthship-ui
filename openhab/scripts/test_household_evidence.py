"""Synthetic exact-source adaptation; no live household readers."""
from dataclasses import FrozenInstanceError
from datetime import timedelta
from hashlib import sha256
import importlib
import json
import pytest
from test_forecast_pre_dusk import evidence as bms_raw, NOW
from test_pv_day_evidence import receipt as pv_receipt, EPOCH
from test_weather_temperature_sources import case
from weather_temperature_sources import build_temperature_source


def api():
    assert importlib.util.find_spec('household') is not None, 'shared household evidence package missing'
    return importlib.import_module('household.adapters')


def args(raw, now=NOW, epoch=EPOCH):
    return dict(raw=raw, expected_sha256=sha256(raw.encode()).hexdigest(),
                source_identity='synthetic-original', expected_epoch=epoch,
                persisted_at=now, as_of=now)


def test_bms_preserves_original_bytes_clocks_epoch_and_immutability():
    raw=bms_raw();kwargs=args(raw,epoch='00000000-0000-0000-0000-000000000001')
    value=api().battery_soc(**kwargs)
    assert value.value==100 and value.unit=='percent' and value.ref.quality=='qualified'
    assert value.ref.digest==sha256(raw.encode()).hexdigest()
    assert value.ref.source_epoch==kwargs['expected_epoch']
    assert value.ref.observed_at==NOW-timedelta(seconds=20)
    with pytest.raises(FrozenInstanceError):value.value=0


@pytest.mark.parametrize('damage',['digest','epoch','future','expired','malformed'])
def test_bms_bad_original_never_becomes_current(damage):
    raw=bms_raw();kwargs=args(raw,epoch='00000000-0000-0000-0000-000000000001')
    if damage=='digest':
        kwargs['expected_sha256']='a'*64
        with pytest.raises(ValueError):api().battery_soc(**kwargs)
        return
    if damage=='epoch':kwargs['expected_epoch']=EPOCH
    elif damage=='future':kwargs['as_of']=NOW-timedelta(minutes=1)
    elif damage=='expired':kwargs['as_of']=NOW+timedelta(minutes=3)
    else:
        kwargs['raw']='{}';kwargs['expected_sha256']=sha256(b'{}').hexdigest()
    result=api().battery_soc(**kwargs)
    assert result.value is None and result.ref.quality=='unavailable' and result.ref.reason


def test_pv_counter_is_not_relabelled_as_power_or_completed_day():
    raw=json.dumps(pv_receipt(NOW,1,wh=1234));result=api().pv_day_counter(**args(raw))
    assert result.value==1234 and result.unit=='Wh' and result.ref.source_role=='pv_day_wh'
    assert result.ref.quality=='qualified'
    assert api().pv_day_counter(**{**args(raw),'as_of':NOW+timedelta(seconds=90)}).value is None


@pytest.mark.parametrize('role,stream,epoch_key',[('air_temperature','indoor','air'),('outdoor_temperature','outdoor','outdoor')])
def test_native_thermal_and_weather_replay_original_query_packet(tmp_path,monkeypatch,role,stream,epoch_key):
    from test_thermal_sensor_epoch_history import EPOCHS
    source=case(tmp_path,monkeypatch);source.update(rows=source['rows'][:1],targets=source['targets'][:1],stream=stream,sensor_epoch=EPOCHS[epoch_key])
    from thermal_model.temperature_history import STREAMS,POLICY
    from weather_temperature_evidence import TemperaturePolicy
    source['policy']=TemperaturePolicy(STREAMS[epoch_key][1],STREAMS[epoch_key][2],**POLICY)
    at=source['targets'][0];source['assessed_at']=at
    raw=json.dumps(build_temperature_source(**source));kwargs=args(raw,now=at,epoch=EPOCHS[epoch_key]);kwargs.pop('persisted_at')
    result=api().native_temperature(role=role,**kwargs)
    assert result.value==70 and result.unit=='degF' and result.ref.hardware_epoch==EPOCHS[epoch_key]
    assert result.ref.observed_at is None and result.ref.received_at is not None
    assert result.ref.parent_digests and result.ref.digest==sha256(raw.encode()).hexdigest()
    assert api().native_temperature(role=role,**{**kwargs,'expected_epoch':EPOCHS['mass']}).value is None
    assert api().native_temperature(role=role,**{**kwargs,'as_of':at+timedelta(minutes=3)}).value is None


def test_missing_is_explicit_and_independent_dates_are_not_inferred():
    m=api();result=m.battery_soc(raw=None,expected_sha256=None,source_identity='missing-source',expected_epoch=EPOCH,persisted_at=NOW,as_of=NOW)
    assert result.value is None and result.ref.reason=='missing_source' and result.ref.digest is None
    assert not hasattr(result.ref,'independent_samples')


def test_native_query_assessed_after_snapshot_cannot_supply_past_currentness(tmp_path,monkeypatch):
    source=case(tmp_path,monkeypatch);source.update(rows=source['rows'][:1],targets=source['targets'][:1])
    at=source['targets'][0];source['assessed_at']=at+timedelta(seconds=30)
    raw=json.dumps(build_temperature_source(**source));kwargs=args(raw,now=at,epoch=source['sensor_epoch']);kwargs.pop('persisted_at')
    value=api().native_temperature(role='air_temperature',**kwargs)
    assert value.value is None and value.ref.reason=='future_source'


def test_bms_source_specific_unavailable_reason_is_retained():
    raw=bms_raw(status='unavailable');kwargs=args(raw,epoch='00000000-0000-0000-0000-000000000001')
    value=api().battery_soc(**kwargs)
    assert value.value is None and value.ref.reason=='input_stale'


def test_native_packet_cannot_choose_another_sensor_for_household_air_role():
    from test_thermal_sensor_epoch_history import EPOCHS
    from test_weather_temperature_reader import AT
    from weather_temperature_receiver import TemperatureCollector
    from weather_temperature_evidence import TemperaturePolicy
    from thermal_model.temperature_history import STREAMS,POLICY
    policy=TemperaturePolicy(STREAMS['mass'][1],STREAMS['mass'][2],**POLICY)
    collector=TemperatureCollector({'indoor':policy},sensor_epochs={'indoor':EPOCHS['air']},clock=lambda:AT,process_id=lambda:1,monotonic=lambda:0)
    collector.observe({'model':policy.model,'id':str(policy.sensor_id),'tempinf':'70'})
    target=AT+timedelta(seconds=60)
    packet=build_temperature_source(rows=[(AT,json.dumps(collector.snapshot()))],targets=[target],assessed_at=target,stream='indoor',policy=policy,sensor_epoch=EPOCHS['air'])
    raw=json.dumps(packet);kwargs=args(raw,now=target,epoch=EPOCHS['air']);kwargs.pop('persisted_at')
    with pytest.raises(ValueError):api().native_temperature(role='air_temperature',**kwargs)


@pytest.mark.parametrize('field,value',[('minimum_f',-100),('maximum_f',200),('validity_seconds',300)])
def test_native_source_policy_cannot_widen_household_acceptance(tmp_path,monkeypatch,field,value):
    source=case(tmp_path,monkeypatch);source.update(rows=source['rows'][:1],targets=source['targets'][:1])
    at=source['targets'][0];source['assessed_at']=at
    packet=build_temperature_source(**source);packet['policy'][field]=value
    raw=json.dumps(packet);kwargs=args(raw,now=at,epoch=source['sensor_epoch']);kwargs.pop('persisted_at')
    with pytest.raises(ValueError):api().native_temperature(role='air_temperature',**kwargs)
