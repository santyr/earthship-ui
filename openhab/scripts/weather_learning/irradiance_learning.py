"""Local lux-proxy targets; elapsed receipt gates remain authoritative."""
from datetime import timedelta
from math import fsum
from bisect import bisect_right
from .contracts import finite


def numeric_hour(rows,*,start):
    end=start+timedelta(hours=1);times=[at for at,_ in rows]
    if times!=sorted(set(times)) or len(rows)>10000:raise ValueError('bounded ordered original radiation states required')
    pieces=[]
    for i,(at,value) in enumerate(rows):
        stop=min(end,at+timedelta(seconds=120),rows[i+1][0] if i+1<len(rows) else end);left=max(start,at)
        if stop>left and finite(value) and 0<=value<=1200:pieces.append(((stop-left).total_seconds(),value))
    covered=fsum(seconds for seconds,value in pieces);mean=None if covered<3420 else fsum(seconds*value for seconds,value in pieces)/covered
    return dict(mean_w_m2=mean,covered_seconds=covered,quality='legacy_numeric_without_sensor_receipts',unit='W_m2_lux_proxy',measurement_health_qualified=False)


def qualified_hour(rows,*,start,history_start,cutover,policy,assessed_at):
    from weather_radiation_reader import select_radiation_window
    end=start+timedelta(hours=1);times=[at for at,_ in rows];first=max(0,bisect_right(times,start-timedelta(seconds=policy.validity_seconds))-1);last=bisect_right(times,end+timedelta(seconds=policy.validity_seconds))
    value=select_radiation_window(rows[first:last],start=start,end=end,assessed_at=assessed_at,history_start=history_start,cutover=cutover,policy=policy)
    return dict(mean_w_m2=value['irradiance_wh_m2'] if value['status']=='ok' else None,covered_seconds=value['covered_seconds'],
        quality='clean_v2_elapsed_lux_proxy' if value['status']=='ok' else 'native_receipts_unqualified',unit='W_m2_lux_proxy',
        measurement_health_qualified=value['status']=='ok',accounting=value,metrology_calibrated=False)


def pair_irradiance(snapshot,targets,positions,*,target_end,allow_recorded_availability=False):
    """Daylight examples against ending-hour local exposure-proxy means.

    Geometry is evaluated at the hour midpoint. This is a local lux-proxy
    correction experiment; it does not identify calibrated physical GHI.
    """
    from math import sin,cos,pi
    from .historical import verify_history
    from .contracts import identity,instant
    source=verify_history(snapshot)
    if source['historical'] is not True and not allow_recorded_availability:raise ValueError('explicit historical irradiance source required')
    pin=identity(source);origin=instant(source['initialized_at'])+timedelta(hours=9);basis='retrospective_assumed_full_cycle_9h';rows=[]
    if source['historical'] is not True:
        available=instant(source['ingestion_completed_at']);origin=available.replace(minute=0,second=0,microsecond=0)
        if origin<available:origin+=timedelta(hours=1)
        basis='recorded_ingestion_completed_rounded_to_next_hour'
    for p in source['points']:
        if p['variable']!='surface_solar_radiation_downwards_1hr' or p['statistic']!='mean' or not finite(p['value']):continue
        end=instant(p['valid_at']);lead=(end-origin).total_seconds()/3600
        if not origin<end<target_end or not (lead<=168 or lead in (240,336)):continue
        label=targets.get(end.isoformat());position=positions.get((end-timedelta(minutes=30)).isoformat())
        if label is None or not finite(label.get('mean_w_m2')) or position is None or position['elevation_degrees']<=0:continue
        if p['value']<0 or not 0<=label['mean_w_m2']<=1200:raise ValueError('nonnegative plausible irradiance required')
        features=irradiance_features(p['value'],lead_hours=lead,target=end,position=position)
        row=dict(schema='earthship-historical-learning-pair/v1',kind='irradiance_w_m2',origin=origin.isoformat(),target_at=end.isoformat(),lead_hours=lead,
            availability_basis=basis,forecast_sha256=pin,features=features,baseline=p['value'],outcome=label['mean_w_m2'],
            label=dict(label),origin_labels={},prospective_score=False,automatic_actuation=False)
        row['pair_sha256']=identity(row);rows.append(row)
    return rows


def assess_irradiance(model,rows,*,holdout_start,holdout_end):
    from zoneinfo import ZoneInfo
    from .weights import site_weights,metrics as weighted_metrics,TIMEZONE
    from . import site_calibration as calibration
    from .contracts import identity,instant
    model=calibration._model(model)
    if not instant(model['cutoff'])<=holdout_start<holdout_end:raise ValueError('later irradiance holdout required')
    selected=[calibration._pair(r) for r in rows if r['kind']=='irradiance_w_m2' and holdout_start<=instant(r['origin'])<instant(r['target_at'])<holdout_end]
    def compare(values):
        weights,support=site_weights([r for r,_,_ in values])
        return dict(pairs=len(values),support=support,independent_target_days=support['local_target_dates'],
            baseline=weighted_metrics([a for _,a,_ in values],weights),candidate=weighted_metrics([b for _,_,b in values],weights))
    values=[(r,r['baseline']-r['outcome'],max(0.,calibration._calculate(model,r['features'],r['baseline']))-r['outcome']) for r in selected]
    groups={}
    for name,key in [('quality',lambda r:r['label']['quality']),('month',lambda r:instant(r['target_at']).astimezone(ZoneInfo(TIMEZONE)).strftime('%Y-%m')),('lead',lambda r:'0-24h' if r['lead_hours']<=24 else '24-72h' if r['lead_hours']<=72 else '72-168h' if r['lead_hours']<=168 else '168-360h'),('azimuth_sector',lambda r:str(int(r['features']['azimuth_degrees']//45)*45))]:
        result={}
        for entry in values:result.setdefault(key(entry[0]),[]).append(entry)
        groups['by_'+name]={k:compare(v) for k,v in result.items()}
    out=dict(schema='earthship-local-irradiance-comparison/v2',timezone=TIMEZONE,kind='irradiance_w_m2',model_sha256=model['model_sha256'],holdout_start=holdout_start.isoformat(),holdout_end=holdout_end.isoformat(),
        **compare(values),**groups,baseline_target='raw_google_ending_hour_ghi_against_lux_proxy',metrology_calibrated=False,prospective_score=False,automatic_actuation=False)
    out['report_sha256']=identity(out);return out


def infer_proxy_units(overlaps):
    """Record semantic unit evidence, never qualify older hardware health."""
    from .contracts import digest
    evidence=[]
    for day in overlaps:
        pairs=day['pairs'];digest(day['numeric_sha256']);digest(day['radiation_sha256'])
        if len(pairs)<3 or any(not finite(a) or not finite(b) for a,b in pairs):continue
        errors={unit:fsum(abs(a*scale-b) for a,b in pairs)/len(pairs) for unit,scale in [('W_m2_lux_proxy',1.),('lux',1/126.7)]}
        if errors['W_m2_lux_proxy']>40 or errors['lux']-errors['W_m2_lux_proxy']<100:raise ValueError('consistent radiation unit overlap required')
        evidence.append({k:v for k,v in day.items() if k!='pairs'}|dict(pairs=len(pairs),mae_by_unit=errors))
    if len({v['date'] for v in evidence})<3:raise ValueError('consistent three-day radiation unit overlap required')
    return dict(unit='W_m2_lux_proxy',overlap_days=evidence,unit_assumed_constant_before_receipt_coverage=True,
        availability_basis='retrospective_recent_receipt_semantic_unit_inference',hardware_health_assumed_before_receipts=False,metrology_calibrated=False)



def irradiance_features(ghi,*,lead_hours,target,position):
    from math import sin,cos,pi
    season=2*pi*target.timetuple().tm_yday/365.25;az=position['azimuth_degrees'];margin=position['elevation_degrees']-position['horizon_elevation_degrees']
    return dict(google_ghi_w_m2=ghi,lead_days=lead_hours/24,elevation_degrees=position['elevation_degrees'],azimuth_degrees=az,
        azimuth_sin=sin(az*pi/180),azimuth_cos=cos(az*pi/180),season_sin=sin(season),season_cos=cos(season),
        horizon_margin_degrees=margin,terrain_blocked_ghi_w_m2=ghi if margin<=0 else 0.)


def correct_forcing_hours(hours,*,model,origin,positions,horizon_profile,horizon_hours):
    """Retrospective thermal experiment; cutoff-plus-ten-minute readiness assumed.

    Actual model creation clocks remain unchanged. This function must not be
    used as evidence that a historical forecast was operationally served.
    """
    from copy import deepcopy
    from . import site_calibration as calibration
    from .contracts import instant
    from household_solar_horizon import horizon_height
    model=calibration._model(model)
    if model['kind']!='irradiance_w_m2' or instant(model['cutoff'])+timedelta(minutes=10)>origin:raise ValueError('earlier irradiance model must be ready')
    if type(horizon_hours) is not int or not 1<=horizon_hours<=24 or origin.minute or origin.second or origin.microsecond:raise ValueError('bounded full-hour replay required')
    result=deepcopy(hours)
    for i in range(1,horizon_hours+1):
        target=origin+timedelta(hours=i);position=positions.get((target-timedelta(minutes=30)).isoformat());row=result.get(target.isoformat())
        if position is None or row is None or not finite(row.get('surface_solar_radiation_downwards_1hr')):raise ValueError('original future geometry and irradiance required')
        if position['elevation_degrees']<=0:continue
        position=dict(position,horizon_elevation_degrees=0. if horizon_profile is None else horizon_height(horizon_profile,position['azimuth_degrees']))
        raw=row['surface_solar_radiation_downwards_1hr'];features=irradiance_features(raw,lead_hours=i,target=target,position=position)
        row['surface_solar_radiation_downwards_1hr']=max(0.,min(1600.,calibration._calculate(model,features,raw)))
    return result
