"""Synthetic Google/local pairs. No live forecasts, credentials or legacy state."""
from datetime import datetime,timedelta,timezone
from weather_learning.config import Site,COLLECTIONS
from weather_learning.contracts import identity
from weather_learning.weathernext_ee import parse_collection_response,make_snapshot

T=datetime(2026,1,1,tzinfo=timezone.utc)
SITE=Site(38.3739919,-105.7744609,'America/Denver')
EPOCH='00000000-0000-4000-8000-000000000001'
REVISION='a'*40

def native_snapshot(day=0,mean_c=10,hours=2):
    init=T+timedelta(days=day)
    bands=['station_head_temperature_2m_mean','station_head_temperature_2m_p10','station_head_temperature_2m_p90']
    raw={'metadata':[],'region':[['id','longitude','latitude','time',*bands]]}
    for hour in range(1,hours+1):
        valid=init+timedelta(hours=hour)
        raw['metadata'].append({'system:index':f'fixture{hour}','start_time':init.isoformat(),'end_time':valid.isoformat(),'forecast_hour':hour,'ingestion_time_utc':init.timestamp()+900})
        raw['region'].append([f'fixture{hour}',-105.75,38.35,valid.timestamp()*1000,mean_c+273.15,mean_c+271.15,mean_c+275.15])
    source,points=parse_collection_response(raw,collection=COLLECTIONS['station'],bands=bands,site=SITE,initialized_at=init,horizon=hours)
    return make_snapshot([(source,points)],site=SITE,initialized_at=init,first_seen_at=init+timedelta(minutes=20),completed_at=init+timedelta(minutes=21))

def receipt(target,celsius=12,epoch=EPOCH):
    return dict(temperatureF=celsius*9/5+32,receivedAt=target-timedelta(seconds=10),storedAt=target-timedelta(seconds=5),validUntil=target+timedelta(seconds=110),streamEpoch='00000000-0000-4000-8000-000000000002',snapshotSha256=identity({'synthetic':True,'target':target.isoformat(),'value':celsius}),receiptVersion=2,sensorEpoch=epoch)

def pair(day=0,mean_c=10,actual_c=12,epoch=EPOCH,hour=2):
    from weather_learning.features import temperature_targets,local_temperature_outcome,training_pair
    snapshot=native_snapshot(day,mean_c,hours=hour)
    issued=T+timedelta(days=day,minutes=30)
    target=temperature_targets(snapshot,issued_at=issued)[-1]
    outcome=local_temperature_outcome(receipt(target.target_at,actual_c,epoch),target_at=target.target_at,assessed_at=target.target_at+timedelta(minutes=1),sensor_epoch=epoch)
    return training_pair(target,outcome)


def full_snapshot(init=T,hours=80):
    collections=[]
    for collection,bands,values in [
        (COLLECTIONS['station'],['station_head_temperature_2m_mean'],[283.15]),
        (COLLECTIONS['gridded'],['surface_solar_radiation_downwards_1hr_mean','total_sky_direct_solar_radiation_at_surface_1hr_mean','total_precipitation_1hr_mean','wind_speed_10m_mean','total_cloud_cover_mean'],[360000,180000,.001,1,.5])]:
        raw={'metadata':[],'region':[['id','longitude','latitude','time',*bands]]}
        for hour in range(1,hours+1):
            valid=init+timedelta(hours=hour)
            raw['metadata'].append({'system:index':f'fixture{hour}','start_time':init.isoformat(),'end_time':valid.isoformat(),'forecast_hour':hour,'ingestion_time_utc':init.timestamp()+900})
            raw['region'].append([f'fixture{hour}',-105.75,38.35,valid.timestamp()*1000,*values])
        collections.append(parse_collection_response(raw,collection=collection,bands=bands,site=SITE,initialized_at=init,horizon=hours))
    return make_snapshot(collections,site=SITE,initialized_at=init,first_seen_at=init+timedelta(minutes=20),completed_at=init+timedelta(minutes=21))
