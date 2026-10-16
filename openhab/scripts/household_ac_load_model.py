"""Pure daily AC-output profile and chronological hourly projection.

Historical interval qualification belongs to the original-source adapter. This
arithmetic never interprets missing time as zero load or grants equipment rights.
"""
from datetime import timedelta
from statistics import median
from zoneinfo import ZoneInfo
import math
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc

SCHEMA='earthship-ac-load-profile/v1'
RULE='median_of_independent_day_hour_AC_output_means_v1'
POLICY=dict(lookback_days=14,minimum_origin_days=3,minimum_coverage=.99,model_max_age_hours=36,
    sample_basis='mean_on_qualified_covered_intervals',estimator='median_of_independent_day_hour_means')
ROW_FIELDS={'start','end','known_ac_kwh','covered_seconds'}
MODEL_FIELDS={'schema','model_rule','inputs','policy','hours','status','reason','valid_until','latest_qualified_hour_end','prediction_intervals','physical_calibration_qualified','automatic_actuation','model_sha256'}


def _number(value,low,high):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError('bounded finite AC accounting value required')
    return value


def _zone(name):
    # This version follows the explicitly configured Earthship site. Other time
    # zones require a versioned contract rather than implicit offset assumptions.
    if name!='America/Denver':raise ValueError('explicit Earthship timezone required')
    return ZoneInfo(name)


def fit_profile(*,hourly_rows,training_end,trained_at,timezone_name='America/Denver'):
    end,trained=utc(training_end),utc(trained_at);zone=_zone(timezone_name);local=end.astimezone(zone)
    if local!=local.replace(hour=0,minute=0,second=0,microsecond=0) or trained<end:raise ValueError('completed local-day training cutoff required')
    floor=(local-timedelta(days=POLICY['lookback_days'])).astimezone(end.tzinfo)
    if not isinstance(hourly_rows,list) or len(hourly_rows)>POLICY['lookback_days']*25:raise ValueError('bounded original hourly accounting required')
    rows=loads(canonical(dict(rows=hourly_rows)))['rows'];groups={};previous=None;latest=None
    for row in rows:
        if not isinstance(row,dict) or set(row)!=ROW_FIELDS:raise ValueError('closed hourly AC accounting row required')
        start,stop=instant(row['start']),instant(row['end']);at=start.astimezone(zone)
        if (stop-start!=timedelta(hours=1) or start<floor or stop>end or
            at.minute or at.second or at.microsecond or previous is not None and start<previous):
            raise ValueError('ordered nonoverlapping original completed hours required')
        previous=stop;covered=_number(row['covered_seconds'],0,3600);energy=_number(row['known_ac_kwh'],0,20*covered/3600)
        if covered/3600<POLICY['minimum_coverage']:continue
        latest=stop
        key=(at.date().isoformat(),at.hour);group=groups.setdefault(key,[0.,0.]);group[0]+=energy;group[1]+=covered
    buckets={}
    for hour in range(24):
        daily=[(energy*3600000/covered,covered) for (_,h),(energy,covered) in groups.items() if h==hour]
        supported=len(daily)>=POLICY['minimum_origin_days'];values=[v for v,_ in daily]
        buckets[str(hour)]=dict(origin_days=len(daily),observed_seconds=math.fsum(seconds for _,seconds in daily),
            median_ac_w=median(values) if supported else None,training_min_ac_w=min(values) if supported else None,
            training_max_ac_w=max(values) if supported else None)
    supported=all(row['median_ac_w'] is not None for row in buckets.values())
    value=dict(schema=SCHEMA,model_rule=RULE,inputs=dict(hourly_rows=rows,training_end=end.isoformat(),trained_at=trained.isoformat(),timezone=timezone_name),
        policy=dict(POLICY),hours=buckets,status='profiled' if supported else 'insufficient_support',reason=None if supported else 'independent_hour_support_required',
        latest_qualified_hour_end=None if latest is None else latest.isoformat(),
        valid_until=None if latest is None else (min(end,latest)+timedelta(hours=POLICY['model_max_age_hours'])).isoformat(),prediction_intervals=None,
        physical_calibration_qualified=False,automatic_actuation=False)
    value['model_sha256']=identity(value)
    if len(canonical(value))>262144:raise ValueError('bounded original load profile required')
    return loads(canonical(value))


def replay_profile(value):
    if (not isinstance(value,dict) or set(value)!=MODEL_FIELDS or value['schema']!=SCHEMA or len(canonical(value))>262144 or
        identity({k:v for k,v in value.items() if k!='model_sha256'})!=value['model_sha256']):raise ValueError('closed original load profile required')
    inputs=value['inputs']
    if not isinstance(inputs,dict) or set(inputs)!={'hourly_rows','training_end','trained_at','timezone'}:raise ValueError('original hourly training arguments required')
    result=fit_profile(hourly_rows=inputs['hourly_rows'],training_end=instant(inputs['training_end']),trained_at=instant(inputs['trained_at']),timezone_name=inputs['timezone'])
    if canonical(result)!=canonical(value):raise ValueError('original load profile numerics differ')
    return result


def project_load(model,*,origin,now):
    model=replay_profile(model);origin,now=utc(origin),utc(now);inputs=model['inputs'];zone=_zone(inputs['timezone'])
    if not origin<=now<=origin+timedelta(seconds=120):raise ValueError('original bounded load issue clock required')
    reason=None
    if origin<instant(inputs['trained_at']):reason='load_model_not_available_at_issue'
    elif model['status']!='profiled':reason='load_model_support_unavailable'
    elif origin>=instant(model['valid_until']):reason='load_model_expired'
    out=dict(schema='earthship-ac-load-forecast/v1',model_rule=RULE,status='unavailable',reason=reason,
        origin=origin.isoformat(),assessed_at=now.isoformat(),model_sha256=model['model_sha256'],trained_through=model['latest_qualified_hour_end'],training_cutoff=inputs['training_end'],
        model_valid_until=model['valid_until'],horizon_hours=24,trajectory=[],total_ac_kwh=None,
        target='inverter_AC_output_energy',load_assumption='hourly_mean_held_within_each_elapsed_forecast_hour',
        prediction_intervals=None,physical_calibration_qualified=False,automatic_actuation=False)
    if reason is None:
        points=[]
        for hour in range(24):
            start=origin+timedelta(hours=hour);stop=start+timedelta(hours=1);at=start;energy=0.;days=[];low=high=0.
            while at<stop:
                boundary=min(stop,at.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1));bucket=model['hours'][str(at.astimezone(zone).hour)]
                fraction=(boundary-at).total_seconds()/3600000
                energy+=bucket['median_ac_w']*fraction;low+=bucket['training_min_ac_w']*fraction;high+=bucket['training_max_ac_w']*fraction
                days.append(bucket['origin_days']);at=boundary
            points.append(dict(at=stop.isoformat(),mean_ac_w=energy*1000,ac_kwh=energy,
                minimum_support_days=min(days),training_spread_mean_w=[low*1000,high*1000]))
        out.update(status='projected',trajectory=points,total_ac_kwh=math.fsum(row['ac_kwh'] for row in points))
    out['forecast_sha256']=identity(out);return loads(canonical(out))
