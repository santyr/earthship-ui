"""Explicit v2 raw forcing contract; v1 numerical/row meanings stay separate."""
from datetime import timedelta
import sqlite3
from household_job_budget import AdmissionDeferred
from .config import Site,COLLECTIONS
from .contracts import canonical,identity,instant
from .evidence import utc
from .features import prospective_snapshot

SCHEMA='earthship-weathernext-native-forecast/v2'
SOLAR_CONTRACT='native-SSRD-FDIR-horizontal-energy/v1'
TOTAL='surface_solar_radiation_downwards_1hr'
DIRECT='total_sky_direct_solar_radiation_at_surface_1hr'
REQUIRED=frozenset({'station_head_temperature_2m',TOTAL,'wind_speed_10m'})

def window(origin,hours):
    origin=utc(origin)
    if type(hours) is not int or not 1<=hours<=336:raise ValueError('bounded v2 forcing horizon required')
    first=origin.replace(minute=0,second=0,microsecond=0)
    last=(origin+timedelta(hours=hours)).replace(minute=0,second=0,microsecond=0)
    if last<origin+timedelta(hours=hours):last+=timedelta(hours=1)
    return tuple(first+timedelta(hours=i) for i in range(int((last-first).total_seconds()/3600)+1))

def solar_pair(points,at):
    """Extract matching native means, retaining absent/inconsistent direct data."""
    total=points.get((TOTAL,at));direct=points.get((DIRECT,at))
    if total is None or total['value'] is None:raise ValueError('native total solar mean required')
    for point in (total,direct):
        if point is None:continue
        if (point['statistic']!='mean' or point['raw_unit']!='J m**-2' or point['unit']!='W m-2' or point['period_seconds']!=3600 or
                not point['source_ref'].startswith(COLLECTIONS['gridded']+'/')):
            raise ValueError('matching native gridded one-hour mean energies required')
    if direct is not None and any(direct[k]!=total[k] for k in ('source_digest','latitude','longitude','valid_at')):
        raise ValueError('solar components differ in native source cell or interval')
    return dict(schema='earthship-native-hourly-solar/v1',start=(at-timedelta(hours=1)).isoformat(),end=at.isoformat(),
        total_j_m2=total['raw_value'],direct_j_m2=None if direct is None else direct['raw_value'],period_seconds=3600,statistic='mean',
        source_digest=total['source_digest'],grid_sha256=identity(dict(collection=COLLECTIONS['gridded'],latitude=total['latitude'],longitude=total['longitude'])))

def derive(snapshot,*,origin,available_by,horizon_hours,site):
    origin,known=map(utc,(origin,available_by));targets=window(origin,horizon_hours)
    if known>origin or not isinstance(site,Site):raise ValueError('authoritative causally available v2 context required')
    source=prospective_snapshot(snapshot,issued_at=known);prospective_snapshot(source,issued_at=origin)
    if source['site']!=dict(latitude=site.latitude,longitude=site.longitude,timezone=site.timezone):raise ValueError('v2 native source site differs')
    points={(p['variable'],instant(p['valid_at'])):p for p in source['points'] if p['statistic']=='mean'}
    rows=[]
    for at in targets:
        values=[points.get((name,at),{}).get('value') for name in ('station_head_temperature_2m',TOTAL,'wind_speed_10m')]
        if any(v is None for v in values):raise ValueError('complete original v2 weather brackets required')
        temp,ghi,wind=values;temp=temp*9/5+32
        if not -40<=temp<=140 or not 0<=ghi<=1600 or wind<0:raise ValueError('v2 weather outside original physical bounds')
        rows.append(dict(at=at.isoformat(),tempF=temp,radiationWm2=ghi,windMph=wind/.44704,weatherCode=None,solar=solar_pair(points,at)))
    return source,rows

def make_component_forecast(snapshot,*,origin,available_by,horizon_hours,site):
    from .native_forecast import _snapshot,_encode,MAX_CAPSULE_BYTES
    source,rows=derive(snapshot,origin=origin,available_by=available_by,horizon_hours=horizon_hours,site=site)
    original={k:v for k,v in source.items() if k not in ('points','snapshot_sha256')}
    if identity(_snapshot(original))!=source['snapshot_sha256']:raise ValueError('v2 original normalized source differs')
    value=dict(schema=SCHEMA,source='weathernext3',solar_input_contract=SOLAR_CONTRACT,
        origin=utc(origin).isoformat(),horizon_hours=horizon_hours,issued_at=source['initialized_at'],
        captured_at=source['ingestion_completed_at'],available_by=utc(available_by).isoformat(),site=source['site'],
        rows=rows,rows_sha256=identity(rows),snapshot_sha256=source['snapshot_sha256'],source_original=_encode(original),
        release_authorized=False,automatic_actuation=False)
    value['forecast_sha256']=identity(value)
    if len(canonical(value))>MAX_CAPSULE_BYTES:raise ValueError('v2 native packet exceeds unchanged byte limit')
    return value

def validate_component_forecast(value):
    from .native_forecast import FIELDS,_decode,_snapshot,MAX_CAPSULE_BYTES
    if (not isinstance(value,dict) or set(value)!=FIELDS|{'solar_input_contract'} or value['schema']!=SCHEMA or
            value['source']!='weathernext3' or value['solar_input_contract']!=SOLAR_CONTRACT or
            value['release_authorized'] is not False or value['automatic_actuation'] is not False or
            len(canonical(value))>MAX_CAPSULE_BYTES or value['forecast_sha256']!=identity({k:v for k,v in value.items() if k!='forecast_sha256'})):
        raise ValueError('closed original v2 solar forcing required')
    body=_decode(value['source_original']);snapshot=_snapshot(body)
    if identity(snapshot)!=value['snapshot_sha256']:raise ValueError('v2 source identity differs')
    source,rows=derive(snapshot,origin=instant(value['origin']),available_by=instant(value['available_by']),
        horizon_hours=value['horizon_hours'],site=Site(**value['site']))
    if (source['initialized_at']!=value['issued_at'] or source['ingestion_completed_at']!=value['captured_at'] or
            canonical(rows)!=canonical(value['rows']) or identity(rows)!=value['rows_sha256']):
        raise ValueError('v2 rows, energies or original availability differ')
    return value

def load_component_forecast(archive,*,origin,available_by,horizon_hours,site):
    try:
        targets=window(origin,horizon_hours)
        source=archive.eligible_snapshot(utc(available_by),targets[-1],required_variables=REQUIRED)
        if source is None:return None
        return make_component_forecast(source,origin=origin,available_by=available_by,horizon_hours=horizon_hours,site=site)
    except (TimeoutError,AdmissionDeferred,MemoryError):raise
    except (ValueError,KeyError,TypeError,OverflowError,OSError,sqlite3.Error):return None
