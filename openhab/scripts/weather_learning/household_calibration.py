"""Chronological demand, apparent DC capacity and conversion assessments.

No actuator authority. Apparent capacity does not separately identify battery
losses, SoC calibration or capacity. Controller conversion conditioned on actual
input does not claim to forecast curtailment or battery acceptance.
"""
from datetime import timedelta
from statistics import median
from math import fsum,exp
from zoneinfo import ZoneInfo
from .contracts import identity,instant,finite,digest


def _seal(value):
    value['model_sha256']=identity(value);return value


def _validate(model,kind):
    if model.get('schema')!=kind or model.get('model_sha256')!=identity({k:v for k,v in model.items() if k!='model_sha256'}) or model.get('automatic_actuation') is not False:
        raise ValueError('unchanged household calibration required')
    return model


def _past(rows,cutoff):
    if not isinstance(rows,list) or len(rows)>2160:raise ValueError('bounded original energy hours required')
    selected=[r for r in rows if instant(r['end'])<=cutoff]
    times=[r['start'] for r in selected]
    if times!=sorted(set(times)):raise ValueError('unique ordered original hours required')
    for r in selected:
        if instant(r['end'])-instant(r['start'])!=timedelta(hours=1):raise ValueError('complete source hour required')
        digest(r['source_sha256'])
        for key in ('ac_w','dc_kwh','soc_change','pv_input_kwh','pv_output_kwh'):
            if r[key] is not None and not finite(r[key]):raise ValueError('finite measured energy target required')
    return selected


def hourly_from_bins(bins):
    rows=[]
    if len(bins)%12:raise ValueError('complete ordered hour grids required')
    for i in range(0,len(bins),12):
        group=bins[i:i+12];start=instant(group[0]['start']);end=instant(group[-1]['end'])
        if end-start!=timedelta(hours=1) or any(instant(b['start'])!=start+timedelta(minutes=5*j) for j,b in enumerate(group)) or len({b['source_sha256'] for b in group})!=1:
            raise ValueError('original continuous energy hour required')
        def energy(field,signed=False):
            values=[b['fields'][field] for b in group];covered=fsum(v['covered_seconds'] for v in values)
            if covered<3564:return None
            return fsum(v['positive_kwh']-(v['negative_kwh'] if signed else 0) for v in values)*3600/covered
        ac=energy('inverter.ac_output_w');dc=energy('battery.dc_power_w',True)
        soc_ok=all(b['soc'] is not None and b['soc_covered_seconds']>=297 for b in group)
        rows.append(dict(start=start.isoformat(),end=end.isoformat(),ac_w=None if ac is None else ac*1000,dc_kwh=dc,
            soc_change=group[-1]['soc'][-1]-group[0]['soc'][0] if soc_ok else None,
            pv_input_kwh=energy('pv.input_power_w'),pv_output_kwh=energy('pv.output_power_w'),source_sha256=group[0]['source_sha256']))
    return rows


def fit_storage(rows,*,cutoff,trained_at,nominal_kwh):
    if not cutoff<=trained_at or not finite(nominal_kwh) or nominal_kwh<=0:raise ValueError('past bank-specific capacity context required')
    earlier=_past(rows,cutoff)
    selected=[r for r in earlier if r['dc_kwh'] is not None and r['soc_change'] is not None and abs(r['soc_change'])>=1.5 and r['dc_kwh']*r['soc_change']>0]
    capacities=[100*r['dc_kwh']/r['soc_change'] for r in selected]
    if not capacities:raise ValueError('earlier qualified DC/SoC change windows required')
    capacity=max(.5*nominal_kwh,min(2*nominal_kwh,median(capacities)))
    return _seal(dict(schema='earthship-apparent-storage-calibration/v1',cutoff=cutoff.isoformat(),trained_at=trained_at.isoformat(),nominal_capacity_kwh=nominal_kwh,
        apparent_capacity_kwh=capacity,estimator='median_hourly_qualified_DC_energy_per_SoC_change',pairs=len(selected),dataset_sha256=identity(selected),
        identifiability='combined_capacity_soc_scale_and_DC_losses',physical_calibration_qualified=False,automatic_actuation=False))


def assess_storage(model,rows,*,start,end):
    _validate(model,'earthship-apparent-storage-calibration/v1')
    if not instant(model['cutoff'])<=start<end:raise ValueError('later storage holdout required')
    selected=[r for r in _past(rows,end) if instant(r['start'])>=start and r['dc_kwh'] is not None and r['soc_change'] is not None]
    def mae(cap):return None if not selected else fsum(abs(100*r['dc_kwh']/cap-r['soc_change']) for r in selected)/len(selected)
    base,candidate=mae(model['nominal_capacity_kwh']),mae(model['apparent_capacity_kwh'])
    return dict(pairs=len(selected),baseline_soc_change_mae=base,candidate_soc_change_mae=candidate,selected=bool(selected) and candidate<base,prospective_score=False,automatic_actuation=False)


def fit_conversion(rows,*,cutoff,trained_at):
    if not cutoff<=trained_at:raise ValueError('past conversion training required')
    selected=[r for r in _past(rows,cutoff) if r['pv_input_kwh'] is not None and r['pv_output_kwh'] is not None and r['pv_input_kwh']>=.1]
    if not selected:raise ValueError('earlier qualified simultaneous PV input and output required')
    denominator=fsum(r['pv_input_kwh']**2 for r in selected)
    gain=max(.5,min(1.1,fsum(r['pv_input_kwh']*r['pv_output_kwh'] for r in selected)/denominator))
    return _seal(dict(schema='earthship-controller-conversion-calibration/v1',cutoff=cutoff.isoformat(),trained_at=trained_at.isoformat(),input_to_output_gain=gain,
        target='controller_output_given_measured_controller_input',forecasts_battery_acceptance=False,pairs=len(selected),dataset_sha256=identity(selected),
        physical_calibration_qualified=False,automatic_actuation=False))


def _load_context(rows,origin):
    zone=ZoneInfo('America/Denver')
    local_cutoff=origin.astimezone(zone).replace(hour=0,minute=0,second=0,microsecond=0)
    cutoff=local_cutoff.astimezone(origin.tzinfo)
    floor=(local_cutoff-timedelta(days=14)).astimezone(origin.tzinfo)
    past=[r for r in rows if floor<=instant(r['start']) and instant(r['end'])<=origin and r['ac_w'] is not None]
    if not past:return None
    # Match the daily owner's completed-local-day cutoff. Intraday observations
    # may update the residual and persistence, never the frozen daily baseline.
    groups={}
    for r in past:
        if instant(r['end'])>cutoff:continue
        at=instant(r['start']).astimezone(zone)
        groups.setdefault((at.date(),at.hour),[]).append(r['ac_w'])
    buckets={hour:[] for hour in range(24)}
    for (_,hour),values in groups.items():
        # Repeated DST hours belong to one independent day/hour. Each retained
        # ac_w is an already-qualified normalized hourly mean.
        buckets[hour].append(fsum(values)/len(values))
    baselines={hour:median(v) if len(v)>=3 else None for hour,v in buckets.items()}
    recent=[]
    for r in past:
        if instant(r['end'])<=origin-timedelta(hours=3):continue
        normal=baselines[instant(r['start']).astimezone(zone).hour]
        if normal is not None:recent.append(r['ac_w']-normal)
    return baselines,median(recent) if recent else 0.,past[-1]['ac_w']


def _load_from_context(context,origin,lead,tau):
    if context is None:return None
    baselines,residual,persistence=context;target=origin+timedelta(hours=lead-1)
    base=baselines[target.astimezone(ZoneInfo('America/Denver')).hour]
    if base is None:return None
    correction=0. if tau==0 else residual*exp(-(lead-.5)/tau)
    return dict(daily_profile=base,current_load_persistence=persistence,hourly_adjusted_profile=max(0.,base+correction))


def _load_prediction(rows,origin,lead,tau):
    return _load_from_context(_load_context(rows,origin),origin,lead,tau)


def _load_errors(rows,*,start,end,tau):
    outcomes={r['start']:r for r in rows if r['ac_w'] is not None};errors={key:[] for key in ('daily_profile','current_load_persistence','hourly_adjusted_profile')};origins=[]
    at=start
    while at<end:
        context=_load_context(rows,at)
        for lead in range(1,25):
            target=at+timedelta(hours=lead-1);actual=outcomes.get(target.isoformat())
            if actual is None or instant(actual['end'])>end:continue
            prediction=_load_from_context(context,at,lead,tau)
            if prediction is None:continue
            for key,value in prediction.items():errors[key].append(abs(value-actual['ac_w']))
            origins.append(at.isoformat())
        at+=timedelta(hours=6)
    return dict(pairs=len(origins),origin_days=len({at[:10] for at in origins}),mae_w={key:None if not v else fsum(v)/len(v) for key,v in errors.items()})


def fit_load_adjustment(rows,*,cutoff,trained_at):
    if not cutoff<=trained_at:raise ValueError('past load training required')
    earlier=_past(rows,cutoff)
    if not earlier:raise ValueError('earlier qualified load hours required')
    start=instant(earlier[0]['start'])+timedelta(days=14)
    comparisons={str(tau):_load_errors(earlier,start=start,end=cutoff,tau=tau) for tau in (0,1,3,6)}
    supported=[(value['mae_w']['hourly_adjusted_profile'],int(tau)) for tau,value in comparisons.items() if value['pairs']]
    if not supported:raise ValueError('earlier chronological load validation required')
    tau=min(supported)[1]
    return _seal(dict(schema='earthship-hourly-load-adjustment/v2',cutoff=cutoff.isoformat(),trained_at=trained_at.isoformat(),residual_decay_hours=tau,
        rule='median_last_3_completed_hour_residual_over_frozen_14_local_day_profile',training_comparisons=comparisons,dataset_sha256=identity(earlier),
        physical_calibration_qualified=False,automatic_actuation=False))


def assess_load_adjustment(model,rows,*,start,end):
    _validate(model,'earthship-hourly-load-adjustment/v2')
    if not instant(model['cutoff'])<=start<end:raise ValueError('later load holdout required')
    report=_load_errors(_past(rows,end),start=start,end=end,tau=model['residual_decay_hours'])
    report.update(selected=report['pairs']>0 and report['mae_w']['hourly_adjusted_profile']<report['mae_w']['daily_profile'],prospective_score=False,automatic_actuation=False)
    return report


def predict_load(model,rows,*,origin,lead_hours):
    _validate(model,'earthship-hourly-load-adjustment/v2')
    if instant(model['trained_at'])>origin:raise ValueError('hourly adjustment not available at origin')
    if type(lead_hours) is not int or not 1<=lead_hours<=24:raise ValueError('bounded load lead required')
    return _load_prediction(_past(rows,origin),origin,lead_hours,model['residual_decay_hours'])
