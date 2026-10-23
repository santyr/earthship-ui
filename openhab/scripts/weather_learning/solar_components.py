"""Versioned native horizontal-energy reconstruction; pure and advisory.

FDIR is horizontal energy, not DNI. A constant nonnegative daylight DNI shape
is normalized over complete retained five-minute geometry bins. Raw interval
energies are conserved before the existing skyline removes the direct beam.
Legacy total-only functions are independent and remain the explicit fallback.
"""
from datetime import timedelta
from math import fsum,radians,sin
from .contracts import finite,identity,instant
from .evidence import utc

METHOD='native_fdir_ssrd_constant_daylight_dni_5min/v1'
RELATIVE_TOLERANCE=1e-9
ABSOLUTE_TOLERANCE_J_M2=1e-6
MAX_DNI_W_M2=2000.
MAX_GHI_W_M2=2000.
MAX_GEOMETRY_POINTS=3000
BIN=timedelta(minutes=5)

def _energy(value):
    if not finite(value) or not 0<=value<=7200000:raise ValueError('finite bounded nonnegative native hourly energy required')
    return float(value)

def _geometry(positions,start,end):
    if not isinstance(positions,list) or len(positions)>MAX_GEOMETRY_POINTS:raise ValueError('bounded retained native geometry required')
    times=[];rows=[]
    for p in positions:
        if not isinstance(p,dict) or set(p)!={'at','elevation_degrees','azimuth_degrees'}:
            raise ValueError('closed original geometry point required')
        at=instant(p['at']);elev=p['elevation_degrees'];az=p['azimuth_degrees']
        if not finite(elev) or not -90<=elev<=90 or not finite(az) or not 0<=az<=360:
            raise ValueError('finite native solar angles required')
        if times and at-times[-1]<BIN:raise ValueError('ordered nonoverlapping native five-minute bins required')
        times.append(at)
        left,right=max(start,at-BIN),min(end,at)
        if left<right:rows.append(dict(start=left.isoformat(),end=right.isoformat(),elevation_degrees=elev,azimuth_degrees=az))
    cursor=start
    for row in rows:
        if instant(row['start'])!=cursor:return None
        cursor=instant(row['end'])
    return rows if cursor==end else None

def reconstruct_hour(*,start,end,total_j_m2,direct_j_m2,positions,horizon_profile=None):
    """Reconstruct one complete trailing UTC hour, retaining explicit failures.

    Geometry may use an origin-offset five-minute grid: intersect each retained
    bin with the exact source hour. Missing prefixes/tails never justify scaling
    an incomplete hour as though its energy applied only to the remaining part.
    """
    start,end=map(utc,(start,end));total=_energy(total_j_m2)
    if end-start!=timedelta(hours=1) or any((start.minute,start.second,start.microsecond,end.minute,end.second,end.microsecond)):
        raise ValueError('one complete ending-hour native interval required')
    direct=None if direct_j_m2 is None else _energy(direct_j_m2)
    value=dict(schema='earthship-native-solar-components/v1',method=METHOD,start=start.isoformat(),end=end.isoformat(),
        status='total_only_fallback',reason=None,raw_total_j_m2=total,raw_direct_j_m2=direct,
        mean_ghi_w_m2=total/3600,mean_bhi_w_m2=None,mean_dhi_w_m2=None,
        roundoff_adjustment_j_m2=0.,geometry_sha256=None,segments=[],
        terrain_rule='direct_beam_mask_diffuse_sky_view_unmodeled',physical_calibration_qualified=False,automatic_actuation=False)
    def fallback(reason):value['reason']=reason;return value
    if direct is None:return fallback('native_direct_unavailable')
    tolerance=max(ABSOLUTE_TOLERANCE_J_M2,RELATIVE_TOLERANCE*max(total,direct))
    if direct-total>tolerance:return fallback('direct_exceeds_total')
    effective=min(total,direct);diffuse=total-effective
    value.update(mean_bhi_w_m2=effective/3600,mean_dhi_w_m2=diffuse/3600,roundoff_adjustment_j_m2=effective-direct)
    rows=_geometry(positions,start,end)
    if rows is None:return fallback('incomplete_hour_geometry')
    value['geometry_sha256']=identity(rows)
    seconds=[(instant(r['end'])-instant(r['start'])).total_seconds() for r in rows]
    projection=[max(0.,sin(radians(r['elevation_degrees']))) for r in rows]
    daylight=fsum(dt for dt,p in zip(seconds,projection) if p>0)
    if daylight==0 and total>0:return fallback('no_daylight_support')
    denominator=fsum(dt*p for dt,p in zip(seconds,projection))
    if effective>0 and denominator<=0:return fallback('no_direct_projection_support')
    dni=0. if effective==0 else effective/denominator
    if not finite(dni) or dni>MAX_DNI_W_M2:return fallback('reconstructed_dni_outside_bound')
    dhi=0. if diffuse==0 else diffuse/daylight
    if not finite(dhi) or dhi>MAX_GHI_W_M2:return fallback('reconstructed_diffuse_outside_bound')
    from household_solar_horizon import horizon_height
    segments=[]
    for row,p in zip(rows,projection):
        light=p>0;raw_dni=dni if light else 0.;raw_dhi=dhi if light else 0.;raw_bhi=raw_dni*p
        skyline=0. if horizon_profile is None else horizon_height(horizon_profile,row['azimuth_degrees'])
        visible=light and row['elevation_degrees']>skyline
        beam=raw_dni if visible else 0.;horizontal=beam*p
        segments.append(dict(row,raw_dni_w_m2=raw_dni,raw_bhi_w_m2=raw_bhi,raw_dhi_w_m2=raw_dhi,
            raw_ghi_w_m2=raw_bhi+raw_dhi,dni_w_m2=beam,bhi_w_m2=horizontal,dhi_w_m2=raw_dhi,
            ghi_w_m2=horizontal+raw_dhi,direct_beam_visible=visible,
            terrain_blocked=horizon_profile is not None and light and not visible))
    if any(row['raw_ghi_w_m2']>MAX_GHI_W_M2 for row in segments):return fallback('reconstructed_ghi_outside_bound')
    for key,expected in (('raw_bhi_w_m2',effective),('raw_dhi_w_m2',diffuse),('raw_ghi_w_m2',total)):
        actual=fsum(row[key]*dt for row,dt in zip(segments,seconds))
        if abs(actual-expected)>tolerance:raise ValueError('native interval energy conservation failed')
    value.update(status='native_components',reason=None,segments=segments,
        terrain_blocked_direct_j_m2=fsum((r['raw_bhi_w_m2']-r['bhi_w_m2'])*dt for r,dt in zip(segments,seconds)))
    return value

def slice_hour(value,*,start,end):
    """Intersect a reconstructed original with a fractional requested window."""
    start,end=map(utc,(start,end))
    if (value.get('schema')!='earthship-native-solar-components/v1' or value.get('method')!=METHOD or
            value.get('status')!='native_components' or not instant(value['start'])<=start<end<=instant(value['end'])):
        raise ValueError('supported original component interval required')
    result=[];cursor=start
    for row in value['segments']:
        left,right=max(start,instant(row['start'])),min(end,instant(row['end']))
        if left>=right:continue
        if left!=cursor:raise ValueError('complete component slice required')
        result.append(dict(row,start=left.isoformat(),end=right.isoformat()));cursor=right
    if cursor!=end:raise ValueError('complete component slice required')
    return result
