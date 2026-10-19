"""Synthetic original-shaped Google forcing for model tests, never live data."""
from copy import deepcopy
from datetime import timedelta
from weather_learning.tests.learning_fixtures import SITE,full_snapshot
from weather_learning.contracts import instant
from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
from weather_learning.native_forecast import make_native_forecast


def forecast(origin,horizon_hours=24,*,available_by=None,temperature_f=59.,radiation_wm2=0.,wind_mph=2.,temperature_step_f=0.,radiation_step_wm2=0.):
    first=origin.replace(minute=0,second=0,microsecond=0);init=first-timedelta(hours=8)
    end=origin+timedelta(hours=horizon_hours);last=end.replace(minute=0,second=0,microsecond=0)
    if last<end:last+=timedelta(hours=1)
    count=int((last-init).total_seconds()/3600)
    source=full_snapshot(init,hours=count);collections=[]
    for original in source['source_originals']:
        raw=deepcopy(original['payload']);bands=raw['region'][0][4:]
        times={m['system:index']:instant(m['end_time']) for m in raw['metadata']}
        for row in raw['region'][1:]:
            at=times[row[0]]
            index=(at-first).total_seconds()/3600
            for offset,band in enumerate(bands,4):
                if band=='station_head_temperature_2m_mean':row[offset]=(temperature_f+index*temperature_step_f-32)*5/9+273.15
                elif band=='surface_solar_radiation_downwards_1hr_mean':row[offset]=max(0.,radiation_wm2+index*radiation_step_wm2)*3600
                elif band=='total_sky_direct_solar_radiation_at_surface_1hr_mean':row[offset]=max(0.,radiation_wm2+index*radiation_step_wm2)*1800
                elif band=='wind_speed_10m_mean':row[offset]=wind_mph*.44704
        collections.append(parse_collection_response(raw,collection=original['collection'],bands=bands,site=SITE,initialized_at=init,horizon=count))
    snapshot=make_snapshot(collections,site=SITE,initialized_at=init,first_seen_at=instant(source['first_seen_at']),completed_at=instant(source['ingestion_completed_at']))
    return make_native_forecast(snapshot,origin=origin,available_by=origin-timedelta(minutes=20) if available_by is None else available_by,horizon_hours=horizon_hours,site=SITE)


from functools import lru_cache


@lru_cache(maxsize=1)
def native_originals():
    """Reuse one synthetic fit, as the existing module-scoped pytest fixture does."""
    from test_native_thermal_artifact import originals
    return originals.__wrapped__()
