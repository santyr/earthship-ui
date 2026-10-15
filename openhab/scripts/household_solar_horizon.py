"""Original location-bound terrain skyline; no maps, astronomy, fitting or actions."""
from hashlib import sha256
from math import isfinite
import re
from household.codec import loads,canonical,identity
from household.control_contracts import instant
from household.evidence import utc

IDENTITY='earthship-ui/openhab/household-solar-horizon.json'
MAX_BYTES=16384
FIELDS={'schema','recorded_at','site_sha256','timezone','source','basis','azimuth_convention','angular_step_degrees','profile',
    'terrain_resolution_m_approximate','validation_status','nearby_obstructions_included','diffuse_sky_view_modeled',
    'physical_calibration_qualified','automatic_actuation'}


def prepare_horizon_source(raw,*,available_at):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_BYTES:raise ValueError('bounded original horizon source required')
    text=raw.decode('utf-8');loads(text)
    return dict(schema='earthship-household-solar-horizon-source/v1',source_identity=IDENTITY,raw=text,
        sha256=sha256(raw).hexdigest(),available_at=utc(available_at).isoformat())


def _profile(rows):
    if not isinstance(rows,list) or len(rows)!=48:raise ValueError('complete original 7.5 degree horizon required')
    for i,row in enumerate(rows):
        if (not isinstance(row,dict) or set(row)!={'azimuth_degrees','elevation_degrees'} or
            type(row['azimuth_degrees']) not in (int,float) or row['azimuth_degrees']!=7.5*i or
            type(row['elevation_degrees']) not in (int,float) or not isfinite(row['elevation_degrees']) or
            not 0<=row['elevation_degrees']<=90):raise ValueError('ordered bounded skyline samples required')
    return rows


def horizon_configuration(source,*,origin,site,timezone_name):
    if source is None:return None,'solar_horizon_unavailable'
    if (not isinstance(source,dict) or set(source)!={'schema','source_identity','raw','sha256','available_at'} or
        source['schema']!='earthship-household-solar-horizon-source/v1' or source['source_identity']!=IDENTITY):
        raise ValueError('closed original horizon source required')
    raw=source['raw']
    if (not isinstance(raw,str) or not 1<=len(raw.encode())<=MAX_BYTES or sha256(raw.encode()).hexdigest()!=source['sha256'] or
        instant(source['available_at'])>utc(origin)):raise ValueError('horizon source bytes or original availability differ')
    try:
        body=loads(raw)
        if not isinstance(body,dict) or set(body)!=FIELDS or body['schema']!='earthship-household-solar-horizon/v1':raise ValueError()
        original=body['source']
        if (not isinstance(original,dict) or set(original)!={'provider','api_version','tool','response_sha256','retrieved_at'} or
            original['provider']!='European_Commission_JRC_PVGIS' or original['api_version']!='5.3' or original['tool']!='printhorizon' or
            not isinstance(original['response_sha256'],str) or re.fullmatch('[a-f0-9]{64}',original['response_sha256']) is None or
            not instant(original['retrieved_at'])<=instant(body['recorded_at'])<=instant(source['available_at']) or
            body['basis']!='DEM_calculated' or body['azimuth_convention']!='clockwise_from_true_north' or
            type(body['angular_step_degrees']) not in (int,float) or body['angular_step_degrees']!=7.5 or
            type(body['terrain_resolution_m_approximate']) not in (int,float) or body['terrain_resolution_m_approximate']!=90 or
            body['validation_status']!='unvalidated_map_estimate' or any(body[k] is not False for k in
                ('nearby_obstructions_included','diffuse_sky_view_modeled','physical_calibration_qualified','automatic_actuation'))):raise ValueError()
        _profile(body['profile'])
        if body['timezone']!=timezone_name or body['site_sha256']!=identity({k:site[k] for k in ('latitude','longitude')}):
            return None,'solar_horizon_site_mismatch'
        return loads(canonical(body)),None
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):
        return None,'unsupported_solar_horizon_configuration'


def horizon_height(profile,azimuth_degrees):
    rows=_profile(profile)
    if type(azimuth_degrees) not in (int,float) or not isfinite(azimuth_degrees) or not 0<=azimuth_degrees<=360:
        raise ValueError('finite original solar azimuth required')
    az=azimuth_degrees%360;index=min(47,int(az//7.5));left=rows[index];right=rows[(index+1)%48]
    weight=(az-left['azimuth_degrees'])/7.5
    return left['elevation_degrees']*(1-weight)+right['elevation_degrees']*weight
