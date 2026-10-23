"""Moisture context consumes existing original-bound sensor quality contracts."""
from datetime import timedelta
from hashlib import sha256
import importlib
import pytest
from test_atmospheric_context import context,DECISION
from household.codec import canonical
from household.sensor_observations import prepare_sensor_observations
from services.observations.registry import Registry
from services.observations.contract import normalize
from services.lorawan.tests.test_core import config


def indoor(*,quality=True,synthetic=False,zone='room',skew=0,stale_seconds=120,age=10):
    cfg=config(radio_verified=True,source_verified=True,transport='wired',decoder=None,device_id='indoor-fixture',sensor_id='indoor_01',zone=zone,state_stale_seconds=stale_seconds,offline_seconds=max(300,stale_seconds*2),
        device_type='environment',capabilities=['air_temperature','relative_humidity'],observation_types=['air_temperature','relative_humidity'],units={'air_temperature':'degC','relative_humidity':'percent'})
    cfg['environment']='production';registry=Registry(cfg);sensor=registry.devices['indoor_01'];sources={}
    for kind,value,unit in [('air_temperature',22.,'degC'),('relative_humidity',60.,'percent')]:
        at=DECISION-timedelta(seconds=age+(skew if kind=='air_temperature' else 0))
        point=normalize(sensor=sensor,kind=kind,value=value,unit=unit,observed_at=at,received_at=at,valid_until=at+timedelta(seconds=stale_seconds),
            source_identity='wired/fixture',raw_sha256='a'*64,source_epoch=sensor['hardware_epoch'],timestamp_basis='provider_receipt',synthetic=synthetic,qualified=quality and not synthetic)
        raw=canonical(point).decode();sources['indoor_01:'+kind]=dict(raw=raw,sha256=sha256(raw.encode()).hexdigest(),available_at=at.isoformat(),expected_source_epoch=sensor['hardware_epoch'])
    raw=canonical(registry.config).decode()
    return prepare_sensor_observations(registry_raw=raw,registry_sha256=sha256(raw.encode()).hexdigest(),sources=sources,as_of=DECISION)


def api():return importlib.import_module('weather_learning.moisture_context')
def build(prepared=None,**kwargs):
    args=dict(outdoor=context(),indoor=prepared,zone='room',decision=DECISION);args.update(kwargs)
    return api().build_moisture_context(**args)


def test_missing_indoor_evidence_keeps_outdoor_moisture_without_ventilation_permission():
    r=build()
    assert r['mode']=='outdoor_only' and r['outdoor_vapor_pressure_hpa']>12
    assert r['comparison'] is None and r['condensation_assessed'] is False and r['automatic_actuation'] is False
    assert 'qualified_indoor_temperature_and_relative_humidity' in r['missing_dependencies']


def test_qualified_same_zone_measurements_allow_only_a_source_expiring_diagnostic():
    r=build(indoor())
    assert r['mode']=='qualified_comparison' and r['comparison']=='forecast_air_drier'
    assert r['indoor_temperature_c']==22 and r['indoor_relative_humidity_pct']==60
    assert r['valid_until']==(DECISION+timedelta(seconds=110)).isoformat()
    assert r['release_authorized'] is False and r['condensation_assessed'] is False
    assert len(r['indoor_evidence_sha256s'])==2


@pytest.mark.parametrize('kwargs',[{'quality':False},{'synthetic':True},{'zone':'different_room'}])
def test_unqualified_synthetic_or_wrong_zone_readings_never_authorize_a_comparison(kwargs):
    r=build(indoor(**kwargs))
    assert r['mode']=='outdoor_only' and r['comparison'] is None


def test_prepared_sources_are_reassessed_at_current_clock_without_renewing_them():
    p=indoor();before=p.content
    r=build(p,decision=DECISION+timedelta(seconds=111))
    assert r['mode']=='outdoor_only' and r['comparison'] is None and p.content==before


def test_raw_observation_dictionary_cannot_impersonate_the_qualified_adapter():
    with pytest.raises(ValueError):build(indoor().to_dict())


def test_current_context_does_not_use_a_long_registry_ttl_to_treat_old_indoor_air_as_current():
    r=build(indoor(stale_seconds=600,age=121))
    assert r['mode']=='outdoor_only' and r['comparison'] is None
    fresh=build(indoor(stale_seconds=600))
    assert fresh['valid_until']==(DECISION+timedelta(seconds=110)).isoformat()
    assert len(fresh['indoor_context_sha256'])==64
