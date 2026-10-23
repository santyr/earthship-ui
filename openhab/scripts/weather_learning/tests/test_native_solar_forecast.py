"""Explicit v2 solar data, with frozen v1 source/row meanings preserved."""
from copy import deepcopy
from datetime import timedelta
import importlib
import pytest
from native_solar_fixtures import T,SITE,snapshot
from weather_learning import native_forecast as native
from weather_learning.contracts import canonical,identity

def make(source=None,**kwargs):
    return native.make_native_component_forecast(snapshot() if source is None else source,
        origin=T+timedelta(hours=1,minutes=15),available_by=T+timedelta(hours=1),horizon_hours=kwargs.get('horizon_hours',1),site=SITE)

def test_v1_rows_and_original_codec_remain_frozen_on_synthetic_source():
    value=native.make_native_forecast(snapshot(),origin=T+timedelta(hours=1,minutes=15),available_by=T+timedelta(hours=1),horizon_hours=1,site=SITE)
    assert value['schema']=='earthship-weathernext-native-forecast/v1'
    assert value['rows_sha256']=='10c536e3877d0d64c64e3bde26f5576cfeeca31e4c511c24ecbeff7be1845039'
    assert value['source_original']['uncompressed_sha256']=='f008e7748cb746f99212cec6374295e4a70e595cc40be71e2ae832d1cdbaef74'
    assert all(set(row)=={'at','tempF','radiationWm2','windMph','weatherCode'} for row in value['rows'])
    assert native.validate_native_forecast(value)==value

def test_v2_preserves_mean_total_direct_energy_and_original_grid_interval():
    source=snapshot();before=canonical(source);value=make(source)
    assert value['schema']=='earthship-weathernext-native-forecast/v2'
    assert value['solar_input_contract']=='native-SSRD-FDIR-horizontal-energy/v1'
    first=value['rows'][0];solar=first['solar']
    assert first['radiationWm2']==500 and first['tempF']==68
    assert solar['total_j_m2']==1800000 and solar['direct_j_m2']==1080000
    assert solar['period_seconds']==3600 and solar['statistic']=='mean'
    assert solar['start']==T.isoformat() and solar['end']==(T+timedelta(hours=1)).isoformat()
    assert len(solar['grid_sha256'])==64 and len(solar['source_digest'])==64
    assert value['release_authorized'] is False and value['automatic_actuation'] is False
    assert native.validate_native_forecast(value)==value and canonical(source)==before

def test_optional_direct_absence_and_inconsistency_do_not_mutate_total_means():
    for direct in (None,2000000):
        value=make(snapshot(direct_j=direct));solar=value['rows'][0]['solar']
        assert solar['direct_j_m2']==direct and solar['total_j_m2']==1800000
        assert value['rows'][0]['radiationWm2']==500
        assert native.validate_native_forecast(value)==value

@pytest.mark.parametrize('field',['total_j_m2','direct_j_m2','grid_sha256','source_digest','period_seconds','end'])
def test_rehashed_v2_row_cannot_change_original_solar_values_or_binding(field):
    value=make();solar=value['rows'][0]['solar']
    solar[field]=123 if field.endswith('j_m2') or field=='period_seconds' else 'a'*64 if field.endswith('sha256') or field=='source_digest' else (T+timedelta(hours=2)).isoformat()
    value['rows_sha256']=identity(value['rows']);value['forecast_sha256']=identity({k:v for k,v in value.items() if k!='forecast_sha256'})
    with pytest.raises(ValueError):native.validate_native_forecast(value)

def test_daily_range_v2_remains_bounded_while_v1_horizon_limit_is_unchanged():
    value=make(snapshot(hours=250),horizon_hours=240)
    assert len(value['rows'])==242 and native.validate_native_forecast(value)==value
    with pytest.raises(ValueError):native.make_native_forecast(snapshot(hours=250),origin=T+timedelta(hours=1,minutes=15),available_by=T+timedelta(hours=1),horizon_hours=240,site=SITE)
    with pytest.raises(ValueError):make(snapshot(hours=360),horizon_hours=337)

def test_original_packet_is_required_for_v2_and_future_availability_is_refused():
    value=make();value['source_original']['data']='AA=='
    value['forecast_sha256']=identity({k:v for k,v in value.items() if k!='forecast_sha256'})
    with pytest.raises(ValueError):native.validate_native_forecast(value)
    source=snapshot();source['ingestion_completed_at']=(T+timedelta(hours=2)).isoformat()
    with pytest.raises(ValueError):make(source)
