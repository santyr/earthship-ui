"""Atmospheric fields retain native source semantics without forecast authority."""
from datetime import timedelta
import importlib
import pytest
from native_solar_fixtures import T,SITE
from weather_learning.config import COLLECTIONS
from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
from weather_learning.contracts import canonical

DECISION=T+timedelta(minutes=30);TARGET=T+timedelta(hours=1)
def api():return importlib.import_module('weather_learning.atmospheric_context')
def source(*,station=True,u=None,v=None,dew=283.15,temp=293.15,layer=.8,latitude=40.,completed=21):
    if station:
        bands=['station_head_temperature_2m_mean','station_head_dewpoint_temperature_2m_mean'];values=[temp,dew];grid='station'
    else:
        bands=['mean_sea_level_pressure_mean','wind_speed_10m_mean','total_cloud_cover_mean'];values=[101325.,5.,.25];grid='gridded'
        if u is not None or v is not None:
            bands+=['u_component_of_wind_10m_mean','v_component_of_wind_10m_mean','high_cloud_cover_mean','medium_cloud_cover_mean','low_cloud_cover_mean'];values +=[u,v,layer,layer,layer]
    raw=dict(metadata=[{'system:index':'a1','start_time':T.isoformat(),'end_time':TARGET.isoformat(),'forecast_hour':1,'ingestion_time_utc':T.timestamp()+900}],
        region=[['id','longitude','latitude','time',*bands],['a1',-105.,latitude,TARGET.timestamp()*1000,*values]])
    result=parse_collection_response(raw,collection=COLLECTIONS[grid],bands=bands,site=SITE,initialized_at=T,horizon=1)
    return make_snapshot([result],site=SITE,initialized_at=T,first_seen_at=T+timedelta(minutes=20),completed_at=T+timedelta(minutes=completed))

def context(values=None):return api().build_atmospheric_context([source(),source(station=False,u=1.,v=0.)] if values is None else values,decision=DECISION,target=TARGET,site=SITE)


@pytest.mark.parametrize('u,v,want',[(1,0,270),(0,-1,0),(-1,0,90),(0,1,180),(1,1,225)])
def test_wind_from_cardinal_directions(u,v,want):
    assert api().wind_from(u,v)['from_degrees']==pytest.approx(want)


def test_calm_or_missing_vector_does_not_fabricate_direction():
    for u,v in [(0,0),(None,1),(1,None),(float('nan'),1)]:assert api().wind_from(u,v)['from_degrees'] is None


def test_native_scalars_are_separate_from_vector_mean_and_layer_overlap():
    r=context()
    assert r['wind']['scalar_speed']['value']==5
    assert r['wind']['vector']['magnitude_m_s']==1 and r['wind']['vector']['from_degrees']==270
    assert r['wind']['quantity_semantics']=='scalar_mean_speed_and_mean_vector_are_distinct; neither_is_gust'
    assert r['clouds']['total']['value']==25
    assert [r['clouds'][k]['value'] for k in ('high','medium','low')]==[80,80,80]
    assert 'layer_sum' not in r['clouds']
    assert r['automatic_actuation'] is False and r['temperature_model_uses_fields'] is False


def test_temperature_dewpoint_rh_and_sea_level_pressure_have_explicit_units_and_scope():
    r=context()
    assert r['dewpoint']['value']==10 and r['temperature']['value']==20
    assert r['relative_humidity']['value_pct']==pytest.approx(52.5,abs=.1)
    assert r['relative_humidity']['scope']=='diagnostic_from_mean_T_and_mean_Td_not_ensemble_mean_RH'
    assert r['pressure']['value']==1013.25 and r['pressure']['unit']=='hPa'
    assert r['pressure']['basis']=='mean_sea_level'
    assert r['relative_humidity']['locally_calibrated'] is False


def test_incompatible_station_cells_cannot_be_paired_into_a_humidity_diagnostic():
    values=[source(dew=None),source(temp=None,latitude=40.02)]
    r=context(values)
    assert r['dewpoint']['value']==10 and r['relative_humidity']['value_pct'] is None
    assert r['relative_humidity']['reason']=='compatible_station_pair_unavailable'


def test_missing_optional_components_preserve_scalar_and_core_fields():
    r=context([source(),source(station=False)])
    assert r['wind']['scalar_speed']['value']==5 and r['wind']['vector']['from_degrees'] is None
    assert r['clouds']['total']['value']==25 and r['clouds']['high'] is None
    assert r['dewpoint']['value']==10


def test_later_acquisition_cannot_rewrite_earlier_fields_or_enter_the_context():
    a=source(station=False,u=1.,v=0.,completed=31);before=canonical(a)
    r=context([source(),a])
    assert r['wind']['vector']['from_degrees'] is None and r['dewpoint']['value']==10
    assert canonical(a)==before


def test_sea_level_pressure_cannot_be_compared_with_station_pressure_or_unknown_basis():
    f=context()['pressure']
    assert api().compare_pressure(f,observed_hpa=800.,observed_basis='station')['difference_hpa'] is None
    assert api().compare_pressure(f,observed_hpa=1000.,observed_basis='unknown')['difference_hpa'] is None
    assert api().compare_pressure(f,observed_hpa=1000.,observed_basis='mean_sea_level')['difference_hpa']==13.25


def test_derived_rh_does_not_silently_clip_substantially_crossed_mean_temperatures():
    r=context([source(dew=298.15),source(station=False)])
    assert r['dewpoint']['value']==25 and r['relative_humidity']['value_pct'] is None
    assert r['relative_humidity']['reason']=='dewpoint_above_temperature'
