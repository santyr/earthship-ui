"""Frozen mappings from observed WeatherNext native units and intervals."""
from datetime import date,datetime,time,timedelta,timezone
import math
from zoneinfo import ZoneInfo
from .contracts import digest,finite,instant
from .config import Site

# Values are (native unit, normalized unit, factor, offset, interval seconds).
VARIABLES={
 'temperature_2m':('K','degC',1.,-273.15,0),
 'station_head_temperature_2m':('K','degC',1.,-273.15,0),
 'dewpoint_temperature_2m':('K','degC',1.,-273.15,0),
 'station_head_dewpoint_temperature_2m':('K','degC',1.,-273.15,0),
 'surface_solar_radiation_downwards_1hr':('J m**-2','W m-2',1/3600.,0.,3600),
 'total_sky_direct_solar_radiation_at_surface_1hr':('J m**-2','W m-2',1/3600.,0.,3600),
 'total_precipitation_1hr':('m','mm',1000.,0.,3600),
 'mean_sea_level_pressure':('Pa','hPa',.01,0.,0),
 'total_cloud_cover':('(0 - 1)','percent',100.,0.,0),
 'wind_speed_10m':('m s**-1','m s-1',1.,0.,0),
 'u_component_of_wind_10m':('m s**-1','m s-1',1.,0.,0),
 'v_component_of_wind_10m':('m s**-1','m s-1',1.,0.,0),
}

def normalize_point(variable,raw_value,raw_unit,*,valid_at,source_ref,source_digest,latitude,longitude,statistic='mean'):
    if variable not in VARIABLES:raise ValueError('unmapped native WeatherNext variable')
    native,unit,factor,offset,period=VARIABLES[variable]
    if raw_unit!=native:raise ValueError('native unit/schema differs')
    if statistic not in ('mean','p10','p25','p50','p75','p90'):raise ValueError('native statistic required')
    if raw_value is not None:
        if not finite(raw_value):raise ValueError('finite source value required')
        if period and raw_value<0:raise ValueError('negative native accumulation refused')
        if variable=='total_cloud_cover' and not 0<=raw_value<=1:raise ValueError('cloud fraction outside native domain')
    digest(source_digest);valid=instant(valid_at);Site(latitude,longitude,'UTC')
    if not isinstance(source_ref,str) or not source_ref.startswith('projects/gcp-public-data-weathernext/assets/') or len(source_ref)>512:
        raise ValueError('WeatherNext source asset required')
    return dict(variable=variable,statistic=statistic,valid_at=valid.isoformat(),
        value=None if raw_value is None else raw_value*factor+offset,unit=unit,raw_value=raw_value,raw_unit=raw_unit,
        period_seconds=period,source_ref=source_ref,source_digest=source_digest,latitude=latitude,longitude=longitude)


def nearest_cell(latitudes,longitudes,site):
    if not isinstance(site,Site):raise ValueError('authoritative site required')
    for values in (latitudes,longitudes):
        if not isinstance(values,(tuple,list)) or not 1<=len(values)<=10000 or any(not finite(v) for v in values):
            raise ValueError('bounded finite native grid required')
    lat=min(range(len(latitudes)),key=lambda i:(abs(latitudes[i]-site.latitude),i))
    lon=min(range(len(longitudes)),key=lambda i:(abs((longitudes[i]-site.longitude+180)%360-180),i))
    return lat,lon


def daily_solar_energy(points,local_date,timezone_name,*,variable='surface_solar_radiation_downwards_1hr'):
    """kWh/m2 from a complete mean series; missing intervals remain unavailable."""
    if not isinstance(local_date,date) or isinstance(local_date,datetime):raise ValueError('local date required')
    if variable not in ('surface_solar_radiation_downwards_1hr','total_sky_direct_solar_radiation_at_surface_1hr'):
        raise ValueError('explicit solar field required')
    if not isinstance(points,(list,tuple)) or len(points)>360*128:raise ValueError('bounded point series required')
    zone=ZoneInfo(timezone_name)
    start=datetime.combine(local_date,time.min,zone).astimezone(timezone.utc)
    end=datetime.combine(local_date+timedelta(days=1),time.min,zone).astimezone(timezone.utc)
    selected={}
    for row in points:
        if row['variable']!=variable:continue
        if row['statistic']!='mean':raise ValueError('daily marginal quantile summation is unsupported')
        at=instant(row['valid_at'])
        if not start<at<=end:continue
        if row['period_seconds']!=3600 or row['raw_unit']!='J m**-2' or row['unit']!='W m-2':
            raise ValueError('one-hour native solar interval required')
        if at in selected:raise ValueError('duplicate solar interval refused')
        selected[at]=row['raw_value']
    at=start+timedelta(hours=1);energy=0.
    while at<=end:
        value=selected.get(at)
        if value is None:return None
        if not finite(value) or value<0:raise ValueError('finite nonnegative solar accumulation required')
        energy+=value;at+=timedelta(hours=1)
    return energy/3600000.
