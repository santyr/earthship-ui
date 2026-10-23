"""Frozen-protocol, target/date-weighted matched solar development experiment.

Fixed correction is diagnostic on both baselines. Each refit has its own method
identity and uses earlier targets only. Retrospective target-order assumptions
never assert historical outcome acquisition or release/physical qualification.
"""
from collections import Counter,defaultdict
from datetime import timedelta
from math import ceil,fsum,sqrt
from random import Random
from zoneinfo import ZoneInfo
from .contracts import identity,instant,finite,digest

FIELDS={'start','end','origin','native_w','total_only_w','outcome_w','fixed_gain','fixed_gain_source_sha256',
        'forecast_sha256','energy_source_sha256','outcome_available_at','cohort_sha256','availability_basis',
        'native_supported','fallback_reason','azimuth_degrees','pair_sha256'}
METHODS={'total_only':'ending_hour_erbs_isotropic_faiman_interpolated_point_weather_v2',
         'native':'native_fdir_ssrd_isotropic_faiman_proxy_pvwatts_dc_v2'}
BASES={'retrospective_assumed_full_cycle_9h','retrospective_recorded_ingestion_next_whole_hour','recorded_operational_original'}


def _validated(rows,zone):
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('at most ten thousand matched solar pairs required')
    unique=set();cohorts=set();truth={}
    for r in rows:
        if (not isinstance(r,dict) or set(r)!=FIELDS or r['pair_sha256']!=identity({k:v for k,v in r.items() if k!='pair_sha256'}) or
                r['pair_sha256'] in unique):raise ValueError('unique unchanged matched solar pairs required')
        unique.add(r['pair_sha256']);cohorts.add(r['cohort_sha256'])
        for name in ('forecast_sha256','energy_source_sha256','cohort_sha256'):digest(r[name])
        if r['fixed_gain_source_sha256'] is not None:digest(r['fixed_gain_source_sha256'])
        if (any(not finite(r[k]) or not 0<=r[k]<=20000 for k in ('native_w','total_only_w','outcome_w')) or
                not finite(r['fixed_gain']) or not .5<=r['fixed_gain']<=1.5 or
                not finite(r['azimuth_degrees']) or not 0<=r['azimuth_degrees']<360 or
                type(r['native_supported']) is not bool or
                r['native_supported']!=(r['fallback_reason'] is None) or
                r['fallback_reason'] is not None and (not isinstance(r['fallback_reason'],str) or not 1<=len(r['fallback_reason'])<=80) or
                r['availability_basis'] not in BASES):raise ValueError('bounded matched solar quantities and source basis required')
        start,end,origin,available=map(instant,(r['start'],r['end'],r['origin'],r['outcome_available_at']))
        if not origin<start<end<=start+timedelta(minutes=5) or available<end:
            raise ValueError('ordered original solar target/source times required')
        key=(r['cohort_sha256'],r['start'],r['end']);receipt=(r['outcome_w'],r['energy_source_sha256'],r['outcome_available_at'])
        if key in truth and truth[key]!=receipt:raise ValueError('conflicting original measured solar target')
        truth[key]=receipt
    if len(cohorts)>1:raise ValueError('different solar measurement/grid cohorts cannot be pooled')
    return sorted(rows,key=lambda r:(instant(r['origin']),instant(r['end']),r['pair_sha256']))


def _target(r):return r['cohort_sha256'],r['start'],r['end']
def _day(r,zone):return instant(r['start']).astimezone(zone).date().isoformat()
def _weights(rows,zone):
    days=defaultdict(set);counts=Counter(_target(r) for r in rows)
    for r in rows:days[_day(r,zone)].add(_target(r))
    return [1/(len(days)*len(days[_day(r,zone)])*counts[_target(r)]) for r in rows]

def _support(rows,zone):
    return dict(forecast_pairs=len(rows),targets=len({_target(r) for r in rows}),local_dates=len({_day(r,zone) for r in rows}))


def _metrics(rows,name,zone):
    rows=[r for r in rows if r[name] is not None];support=_support(rows,zone)
    if not rows:return dict(support,mae=None,rmse=None,bias=None,absolute_error_p95=None)
    weights=_weights(rows,zone);errors=[r[name]-r['outcome_w'] for r in rows]
    ordered=sorted(zip(map(abs,errors),weights));mass=0.;p95=ordered[-1][0]
    for error,weight in ordered:
        mass+=weight
        if mass>=.95-1e-12:p95=error;break
    return dict(support,mae=fsum(w*abs(e) for w,e in zip(weights,errors)),
        rmse=sqrt(fsum(w*e*e for w,e in zip(weights,errors))),bias=fsum(w*e for w,e in zip(weights,errors)),absolute_error_p95=p95)


def _fit(rows,method,decision,zone,temporal):
    rows=[r for r in rows if r['native_w']>=20 and r['total_only_w']>=20]
    support=_support(rows,zone)
    if (support['targets']<temporal['minimum_training_targets'] or support['local_dates']<temporal['minimum_training_local_dates']):return None
    weights=_weights(rows,zone);key='native_w' if method=='native' else 'total_only_w'
    denominator=fsum(w*r[key]**2 for w,r in zip(weights,rows))
    if denominator<=0:return None
    gain=max(.5,min(1.5,fsum(w*r[key]*r['outcome_w'] for w,r in zip(weights,rows))/denominator))
    model=dict(schema='earthship-solar-matched-effective-gain/v1',baseline_rule=METHODS[method],gain=gain,
        decision_origin=decision.isoformat(),training_end=max(r['end'] for r in rows),support=support,
        training_pair_sha256s=sorted(r['pair_sha256'] for r in rows),weighting='equal_local_date_then_measured_target_then_forecast',
        physical_calibration_qualified=False,automatic_actuation=False)
    model['model_sha256']=identity(model);return model


def _comparison(rows,zone):
    return dict(support=_support(rows,zone),**{name:_metrics(rows,name+'_w',zone) for name in ('fixed_total','fixed_native','refit_total','refit_native')})


def _bootstrap(rows,zone,seed):
    rows=[r for r in rows if r['refit_native_w'] is not None and r['refit_total_w'] is not None]
    by_day=defaultdict(list)
    for r in rows:by_day[_day(r,zone)].append(r)
    daily=[]
    for group in by_day.values():
        weights=_weights(group,zone)
        daily.append(fsum(w*(abs(r['refit_native_w']-r['outcome_w'])-abs(r['refit_total_w']-r['outcome_w'])) for w,r in zip(weights,group)))
    if len(daily)<2:return None
    rng=Random(seed);values=sorted(fsum(rng.choice(daily) for _ in daily)/len(daily) for _ in range(128))
    return dict(method='paired_local_date_block_resampling',blocks=len(daily),replicates=128,seed=seed,
        native_minus_total_mae_95pct=[values[3],values[124]],independence='consecutive_date_blocks; longer_dependence_not_estimated')


def assess_pv_components(rows,*,timezone_name,protocol,evidence_class='retrospective_development',guard=lambda:None):
    zone=ZoneInfo(timezone_name);rows=_validated(rows,zone)
    if (protocol.get('schema')!='earthship-weather-capability-evaluation-protocol/v1' or protocol['selection']['automatic_promotion'] is not False or
            evidence_class not in ('retrospective_development','operational_originals')):
        raise ValueError('frozen non-promoting solar experiment protocol required')
    if evidence_class=='operational_originals' and any(r['availability_basis']!='recorded_operational_original' for r in rows):
        raise ValueError('retrospective source assumptions cannot become operational evidence')
    temporal=protocol['temporal'];dates=sorted({_day(r,zone) for r in rows});n=ceil(len(dates)/3)
    outer=dates[-n:] if n else [];outer_set=set(outer);predictions=[];models=[];audit=[];fits={}
    for r in rows:
        guard()
        if _day(r,zone) not in outer_set:continue
        decision=instant(r['origin'])
        if decision not in fits:
            training=[q for q in rows if decision-timedelta(days=temporal['maximum_training_days'])<=instant(q['end'])<decision and
                (evidence_class!='operational_originals' or instant(q['outcome_available_at'])<=decision)]
            a=_fit(training,'total_only',decision,zone,temporal);b=_fit(training,'native',decision,zone,temporal)
            fits[decision]=(a,b)
            if a is not None and b is not None:
                models.append(dict(decision_origin=decision.isoformat(),total_only=a,native=b))
                audit.append(dict(decision_origin=decision.isoformat(),target_end=max(a['training_end'],b['training_end'])))
        a,b=fits[decision]
        predictions.append(dict(r,fixed_total_w=r['total_only_w']*r['fixed_gain'],fixed_native_w=r['native_w']*r['fixed_gain'],
            refit_total_w=None if a is None else r['total_only_w']*a['gain'],refit_native_w=None if b is None else r['native_w']*b['gain']))
    inclusive=_comparison(predictions,zone);matched_rows=[r for r in predictions if r['native_supported']];matched=_comparison(matched_rows,zone)
    supported=[r for r in predictions if r['refit_native_w'] is not None and r['refit_total_w'] is not None]
    supported_native=[r for r in supported if r['native_supported']]
    support=_support(supported,zone);native_support=_support(supported_native,zone);selection=protocol['selection']
    regressions=[];subgroups={}
    for group,subset in (
        [(f'azimuth_{edge}',[r for r in supported if edge<=r['azimuth_degrees']<edge+45]) for edge in range(0,360,45)]+
        [(f'lead_{low}_{high}',[r for r in supported if low<(instant(r['end'])-instant(r['origin'])).total_seconds()/3600<=high]) for low,high in ((0,24),(24,48))]):
        scored=_comparison(subset,zone);subgroups[group]=scored
        if scored['support']['targets']>=selection['minimum_subgroup_targets']:
            base=scored['refit_total']['mae'];candidate=scored['refit_native']['mae']
            if candidate>base*(1+selection['maximum_supported_subgroup_relative_regression'])+1e-9:regressions.append(group)
    bootstrap=_bootstrap(supported,zone,protocol['limits']['scenario_seed'])
    disposition='insufficient_evidence';reason='training_or_outer_or_native_support_below_frozen_minimum'
    if (support['targets']>=temporal['minimum_outer_targets'] and support['local_dates']>=temporal['minimum_outer_local_dates'] and
            native_support['targets']>=temporal['minimum_outer_targets'] and native_support['local_dates']>=temporal['minimum_outer_local_dates']):
        base=inclusive['refit_total']['mae'];candidate=inclusive['refit_native']['mae']
        meaningful=base>0 and candidate<=base*(1-selection['point_or_proper_score_relative_improvement'])
        disposition='retain_incumbent';reason='matched_refit_does_not_show_supported_improvement'
        if meaningful and not regressions and bootstrap is not None and bootstrap['native_minus_total_mae_95pct'][1]<0:
            disposition='adopt_candidate';reason='matched_refit_improves_with_supported_subgroups; experimental_disposition_only'
    result=dict(schema='earthship-solar-matched-experiment/v1',protocol_sha256=identity(protocol),evidence_class=evidence_class,
        training_chronology='earlier_target_end_assumption; actual acquisition clocks retained' if evidence_class=='retrospective_development' else 'original_outcome_available_before_decision',
        fixed_correction_role='same_unchanged_correction_on_both_baselines; diagnostic_not_historical_availability_claim',
        outer_dates=outer,support=dict(outer_targets=inclusive['support']['targets'],outer_forecast_pairs=len(predictions),outer_local_dates=len(outer)),
        fallback_inclusive=inclusive,matched_native=matched,fallback_reasons=dict(Counter(r['fallback_reason'] for r in rows if r['fallback_reason'] is not None)),
        models=models,training_audit=audit,predictions=predictions,subgroups=subgroups,regressing_subgroups=regressions,paired_uncertainty=bootstrap,
        disposition=disposition,reason=reason,automatic_promotion=False,prospective_score=False,physical_calibration_qualified=False,automatic_actuation=False)
    result['report_sha256']=identity(result);return result
