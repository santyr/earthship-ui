"""Synthetic source/array fixtures; no household coordinates or measurements."""
from datetime import datetime,timedelta,timezone
from weather_learning.config import Site,COLLECTIONS
from weather_learning.weathernext_ee import parse_collection_response,make_snapshot

T=datetime(2026,6,21,12,tzinfo=timezone.utc)
SITE=Site(40.,-105.,'UTC')
ARRAY=dict(module_count=1,module_nameplate_w=1000.,dc_nameplate_w=1000.,surface_azimuth_degrees=180.,surface_tilt_degrees=30.)
HORIZON=[dict(azimuth_degrees=7.5*i,elevation_degrees=0.) for i in range(48)]

def snapshot(*,hours=8,total_j=1800000.,direct_j=1080000.,temperature_k=None):
    result=[]
    for grid,bands,values in [
        ('station',['station_head_temperature_2m_mean'],[293.15]),
        ('gridded',['surface_solar_radiation_downwards_1hr_mean','total_sky_direct_solar_radiation_at_surface_1hr_mean','wind_speed_10m_mean'],[total_j,direct_j,2.]),
    ]:
        raw=dict(metadata=[],region=[['id','longitude','latitude','time',*bands]])
        for hour in range(1,hours+1):
            at=T+timedelta(hours=hour)
            raw['metadata'].append({'system:index':f'synthetic{hour}','start_time':T.isoformat(),'end_time':at.isoformat(),
                'forecast_hour':hour,'ingestion_time_utc':T.timestamp()+900})
            hour_values=[temperature_k(hour)] if grid=='station' and temperature_k is not None else values
            raw['region'].append([f'synthetic{hour}',SITE.longitude,SITE.latitude,at.timestamp()*1000,*hour_values])
        result.append(parse_collection_response(raw,collection=COLLECTIONS[grid],bands=bands,site=SITE,initialized_at=T,horizon=hours))
    return make_snapshot(result,site=SITE,initialized_at=T,first_seen_at=T+timedelta(minutes=20),completed_at=T+timedelta(minutes=21))

def geometry(*,start=T,count=36,elevation=30.):
    return [dict(at=(start+timedelta(minutes=5*i)).isoformat(),elevation_degrees=elevation if not callable(elevation) else elevation(i),azimuth_degrees=180.) for i in range(1,count+1)]
