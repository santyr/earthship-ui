"""Forecast-only atmospheric ablations preserve native payload and time support."""
from copy import deepcopy
from datetime import timedelta
import importlib
import pytest
from learning_fixtures import T,SITE
from weather_learning.config import COLLECTIONS
from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
from weather_learning.contracts import identity


def source(*,historical=True,missing=(),u=1.,v=0.):
    parsed=[]
    for grid,bands in [('station',['station_head_temperature_2m_mean','station_head_dewpoint_temperature_2m_mean']),
            ('gridded',['mean_sea_level_pressure_mean','wind_speed_10m_mean','u_component_of_wind_10m_mean','v_component_of_wind_10m_mean','high_cloud_cover_mean','medium_cloud_cover_mean','low_cloud_cover_mean'])]:
        raw=dict(metadata=[],region=[['id','longitude','latitude','time',*bands]])
        for h in range(1,13):
            at=T+timedelta(hours=h);values=([293.15,273.15+h] if grid=='station' else [100000+100*h,5.,u,v,.8,.8,.8])
            values=[None if (band,h) in missing else value for band,value in zip(bands,values)]
            raw['metadata'].append({'system:index':f'a{h}','start_time':T.isoformat(),'end_time':at.isoformat(),'forecast_hour':h,'ingestion_time_utc':T.timestamp()+900})
            raw['region'].append([f'a{h}',-105.75,38.35,at.timestamp()*1000,*values])
        parsed.append(parse_collection_response(raw,collection=COLLECTIONS[grid],bands=bands,site=SITE,initialized_at=T,horizon=12))
    first=T+timedelta(days=5) if historical else T+timedelta(minutes=20)
    return make_snapshot(parsed,site=SITE,initialized_at=T,first_seen_at=first,completed_at=first+timedelta(minutes=1),historical=historical)


def prepare(snapshot=None,**kwargs):
    args=dict(snapshots=[source() if snapshot is None else snapshot],site=SITE,assessed_at=T+timedelta(days=6),availability_basis='retrospective_assumed_full_cycle_9h')
    args.update(kwargs)
    return importlib.import_module('weather_learning.atmospheric_features').prepare_atmospheric_features(**args)


def test_point_features_replay_native_units_and_keep_clouds_and_scalar_wind_distinct():
    result=prepare().features(kind='temperature',origin=T+timedelta(hours=9),target=T+timedelta(hours=10))
    assert result['groups']=={'dewpoint':[10.], 'pressure':[1010.], 'wind_direction':[1.,0.], 'cloud_layers':[.8,.8,.8]}
    assert result['automatic_actuation'] is False and result['as_issued_forecast'] is False
    assert result['source_class']=='historical_assumed_availability'
    assert result['actual_source_available_at']==(T+timedelta(days=5,minutes=1)).isoformat()
    assert result['feature_sha256']==identity({k:v for k,v in result.items() if k!='feature_sha256'})


def test_wind_uses_adjacent_native_instants_not_future_observed_weather():
    result=prepare().features(kind='wind',origin=T+timedelta(hours=9),target=T+timedelta(hours=11))
    assert result['groups']['pressure']==[1010.5] and result['groups']['dewpoint']==[10.5]
    assert result['window_start']==(T+timedelta(hours=10)).isoformat()


def test_fractional_thermal_window_uses_exact_complete_linear_forecast_time_average():
    result=prepare().features(kind='thermal',origin=T+timedelta(hours=9,minutes=15),target=T+timedelta(hours=10,minutes=45))
    assert result['groups']['pressure']==pytest.approx([1010.])
    assert result['groups']['dewpoint']==pytest.approx([10.])
    assert result['groups']['wind_direction']==[1.,0.]


def test_missing_internal_native_hour_never_gets_interpolated_across_or_zero_filled():
    missing=[('mean_sea_level_pressure_mean',10),('low_cloud_cover_mean',10)]
    result=prepare(source(missing=missing)).features(kind='thermal',origin=T+timedelta(hours=9),target=T+timedelta(hours=11))
    assert result['groups']['pressure'] is None and result['groups']['cloud_layers'] is None
    assert result['groups']['dewpoint']==[10.] and result['groups']['wind_direction']==[1.,0.]
    assert result['withheld']['pressure']=='missing_complete_native_quantity_support'


def test_cancelling_or_calm_mean_vector_withholds_only_direction():
    result=prepare(source(u=0.,v=0.)).features(kind='wind',origin=T+timedelta(hours=9),target=T+timedelta(hours=11))
    assert result['groups']['wind_direction'] is None
    assert result['withheld']['wind_direction']=='calm_or_cancelling_mean_vector'
    assert result['groups']['pressure']==[1010.5]


def test_forecast_originals_cannot_be_relabelled_or_used_before_declared_readiness():
    with pytest.raises(ValueError):prepare(source(historical=False))
    adapter=prepare()
    with pytest.raises(ValueError):adapter.features(kind='temperature',origin=T+timedelta(hours=8),target=T+timedelta(hours=10))
    with pytest.raises(ValueError):adapter.features(kind='thermal',origin=T+timedelta(hours=9),target=T+timedelta(hours=13))


def test_recorded_profile_keeps_actual_clocks_and_cannot_enter_earlier_decisions():
    frame=source(historical=False)
    adapter=prepare(frame,availability_basis='retrospective_recorded_ingestion_next_whole_hour')
    result=adapter.features(kind='temperature',origin=T+timedelta(hours=9),target=T+timedelta(hours=10))
    assert result['source_class']=='recorded_ingestion_availability' and result['actual_source_available_at']==frame['ingestion_completed_at']
    with pytest.raises(ValueError):adapter.features(kind='temperature',origin=T+timedelta(minutes=15),target=T+timedelta(hours=10))


def test_normalized_field_mutation_cannot_replace_actual_provider_original():
    bad=deepcopy(source());bad['points'][0]['value']+=1
    with pytest.raises(ValueError):prepare(bad)


def test_distinct_runs_cannot_be_borrowed_even_when_the_missing_group_would_be_useful():
    from learning_fixtures import native_snapshot
    first=source();later=native_snapshot(day=1,hours=12)
    with pytest.raises(ValueError):prepare(snapshots=[first,later])


def test_compiled_forecast_features_are_immutable_and_do_not_refresh_original_clocks():
    from dataclasses import FrozenInstanceError
    adapter=prepare();result=adapter.features(kind='temperature',origin=T+timedelta(hours=9),target=T+timedelta(hours=10))
    result['groups']['pressure'][0]=0
    again=adapter.features(kind='temperature',origin=T+timedelta(hours=9),target=T+timedelta(hours=10))
    assert again['groups']['pressure']==[1010.] and again['actual_source_available_at']==result['actual_source_available_at']
    with pytest.raises(FrozenInstanceError):adapter.ready_at=T
