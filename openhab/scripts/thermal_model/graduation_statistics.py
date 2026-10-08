"""Independent-day thermal statistical gates; never production authority.

Original capture/outcome qualification, numerical fit evidence and immutable
policy registration must also pass before any release wrapper can activate.
"""
from datetime import timedelta
from statistics import mean,stdev,NormalDist
import math
from zoneinfo import ZoneInfo

from .graduation_policy import validate_policy,_utc,_finite

FIELDS={'issue_at','target_at','horizon_hours','regime','artifact_sha256','runtime_sha256',
        'sensor_epochs','model_error_f','persistence_error_f','recent_cycle_error_f',
        'interval_width_f','interval_covered'}
SITE=ZoneInfo('America/Denver')


def _metrics(rows,field):
    values=[row[field] for row in rows]
    if not values:return None
    return dict(mae_f=mean(map(abs,values)),rmse_f=math.sqrt(mean(value*value for value in values)),bias_f=mean(values))


def _skill(rows,baseline,alpha):
    if len(rows)<2:return None
    from scipy.stats import t
    values=[abs(row['model_error_f'])-abs(row[baseline]) for row in rows]
    return mean(values)+float(t.ppf(1-alpha,len(values)-1))*stdev(values)/math.sqrt(len(values))


def _coverage(rows,confidence):
    if not rows:return None
    n=len(rows);fraction=sum(row['interval_covered'] for row in rows)/n
    z=NormalDist().inv_cdf((1+confidence)/2);denominator=1+z*z/n
    center=(fraction+z*z/(2*n))/denominator
    radius=z*math.sqrt(fraction*(1-fraction)/n+z*z/(4*n*n))/denominator
    return dict(fraction=fraction,lower=max(0,center-radius),upper=min(1,center+radius),count=n)


def _sample(rows):
    """A deterministic first issue per local day after UTC non-overlap selection."""
    nonoverlap=[];previous=None
    for row in sorted(rows,key=lambda row:(_utc(row['issue_at']),_utc(row['target_at']))):
        if previous is None or _utc(row['issue_at'])>=previous:
            nonoverlap.append(row);previous=_utc(row['target_at'])
    days=set();selected=[]
    for row in nonoverlap:
        day=_utc(row['issue_at']).astimezone(SITE).date()
        if day not in days:selected.append(row);days.add(day)
    return nonoverlap,selected


def _assess(rows,threshold,policy,now,*,freshness_required=False):
    nonoverlap,selected=_sample(rows)
    metrics={name:_metrics(selected,field) for name,field in (
        ('model','model_error_f'),('persistence','persistence_error_f'),('recent_cycle','recent_cycle_error_f'))}
    bounds={name:_skill(selected,field,policy['comparison_alpha']) for name,field in (
        ('persistence','persistence_error_f'),('recent_cycle','recent_cycle_error_f'))}
    coverage=_coverage(selected,policy['confidence_level'])
    model=metrics['model']
    gates=dict(independent_windows=len(nonoverlap)>=threshold['min_independent_windows'],
        independent_days=len(selected)>=threshold['min_independent_days'],
        mae_cap=model is not None and model['mae_f']<=threshold['max_mae_f'],
        rmse_cap=model is not None and model['rmse_f']<=threshold['max_rmse_f'],
        bias_cap=model is not None and abs(model['bias_f'])<=threshold['max_abs_bias_f'],
        persistence_skill=bounds['persistence'] is not None and bounds['persistence']<0,
        recent_cycle_skill=bounds['recent_cycle'] is not None and bounds['recent_cycle']<0,
        interval_calibration=coverage is not None and coverage['lower']<=policy['nominal_interval_coverage']<=coverage['upper'],
        interval_width=bool(selected) and mean(row['interval_width_f'] for row in selected)<=threshold['max_mean_interval_width_f'],
        prospective_freshness=(not freshness_required or bool(rows) and now-max(_utc(row['target_at']) for row in rows)<=timedelta(hours=policy['max_qualification_age_hours'])))
    return dict(raw_pairs=len(rows),independent_windows=len(nonoverlap),independent_days=len(selected),
        metrics=metrics,skill_upper_f=bounds,interval_coverage=coverage,gates=gates,
        freshness_evaluated=freshness_required,statistical_gates_passed=all(gates.values()))


def assess_predictive_skill(policy,scored_pairs,*,now):
    validate_policy(policy);now=_utc(now)
    if not isinstance(scored_pairs,(list,tuple)) or len(scored_pairs)>10000:
        raise ValueError('bounded scored evidence required')
    candidate=policy['candidate'];intervals=policy['intervals'];prepared=[];seen=set()
    for original in scored_pairs:
        if not isinstance(original,dict) or set(original)!=FIELDS:
            raise ValueError('closed source-scored evidence row required')
        row=dict(original);issue,target=map(_utc,(row['issue_at'],row['target_at']))
        hours=row['horizon_hours']
        if (type(hours) is not int or hours not in policy['horizons'] or row['regime'] not in policy['regimes'] or
                row['artifact_sha256']!=candidate['artifact_sha256'] or row['runtime_sha256']!=candidate['runtime_sha256'] or
                row['sensor_epochs']!=candidate['sensor_epochs']):
            raise ValueError('frozen candidate/runtime/regime/sensor binding differs')
        if (not _utc(candidate['created_at'])<=issue<target<=now or
                abs((target-issue).total_seconds()-hours*3600)>1800):
            raise ValueError('future or origin-incompatible scored evidence')
        identity=(issue,target,hours)
        if identity in seen:raise ValueError('duplicate scored evidence')
        seen.add(identity)
        for field in ('model_error_f','persistence_error_f','recent_cycle_error_f','interval_width_f'):
            row[field]=_finite(row[field])
        if type(row['interval_covered']) is not bool or row['interval_width_f']<0:
            raise ValueError('interval evidence invalid')
        prepared.append(row)
    holdout=[row for row in prepared if _utc(intervals['holdout_start'])<=_utc(row['issue_at']) and
             _utc(row['target_at'])<=_utc(intervals['holdout_end'])]
    prospective=[row for row in prepared if _utc(intervals['prospective_start'])<=_utc(row['issue_at']) and
                 (intervals['prospective_end'] is None or _utc(row['target_at'])<=_utc(intervals['prospective_end']))]
    horizons={};by_regime={};prospective_results={};prospective_by_regime={}
    for hours in policy['horizons']:
        key=str(hours)
        horizons[key]=_assess([row for row in holdout if row['horizon_hours']==hours],policy['thresholds'][key],policy,now)
        prospective_results[key]=_assess([row for row in prospective if row['horizon_hours']==hours],policy['thresholds'][key],policy,now,freshness_required=True)
        by_regime[key]={regime:_assess([row for row in holdout if row['horizon_hours']==hours and row['regime']==regime],
            policy['thresholds_by_regime'][key][regime],policy,now) for regime in policy['regimes']}
        prospective_by_regime[key]={regime:_assess([row for row in prospective if row['horizon_hours']==hours and row['regime']==regime],
            policy['thresholds_by_regime'][key][regime],policy,now) for regime in policy['regimes']}
    passed=(now>=_utc(intervals['holdout_end']) and all(value['statistical_gates_passed'] for value in horizons.values())
        and all(value['statistical_gates_passed'] for value in prospective_results.values())
        and all(value['statistical_gates_passed'] for values in by_regime.values() for value in values.values())
        and all(value['statistical_gates_passed'] for values in prospective_by_regime.values() for value in values.values()))
    return dict(schema='earthship-thermal-statistical-assessment/v1',policy_sha256=policy['policy_sha256'],
        assessed_at=now.isoformat(),horizons=horizons,by_regime=by_regime,prospective=prospective_results,
        prospective_by_regime=prospective_by_regime,
        holdout_complete=now>=_utc(intervals['holdout_end']),
        holdout_prospective_overlap_pairs=len({(r['issue_at'],r['target_at'],r['horizon_hours']) for r in holdout}&
            {(r['issue_at'],r['target_at'],r['horizon_hours']) for r in prospective}),
        statistical_forecast_gates_passed=passed,action_evidence_evaluated=False,
        source_qualification_evaluated=False,fit_qualification_evaluated=False,release_authorized=False)


def assess_current_predictive_skill(policy,scored_pairs,*,now):
    """Require both historical skill and the latest independent prospective block.

    The monitoring block length and every numerical cap come from the frozen
    policy. Dense recent issues cannot displace independent days. The original
    v1 assessment remains available with its original all-history semantics.
    This diagnostic layer still grants no source, fit or release authority.
    """
    historical=assess_predictive_skill(policy,scored_pairs,now=now)
    now=_utc(now);intervals=policy['intervals']
    prospective=[row for row in scored_pairs if _utc(intervals['prospective_start'])<=_utc(row['issue_at']) and
                 (intervals['prospective_end'] is None or _utc(row['target_at'])<=_utc(intervals['prospective_end']))]
    def recent(rows,threshold,*,freshness_required=False):
        _,independent=_sample(rows)
        required=max(threshold['min_independent_windows'],threshold['min_independent_days'])
        selected=independent[-required:]
        result=_assess(selected,threshold,policy,now,freshness_required=freshness_required)
        result['selection']=dict(required_independent_days=required,
            first_issue_at=_utc(selected[0]['issue_at']).isoformat() if selected else None,
            last_target_at=max(_utc(row['target_at']) for row in selected).isoformat() if selected else None)
        return result
    horizons={};by_regime={}
    for hours in policy['horizons']:
        key=str(hours);rows=[row for row in prospective if row['horizon_hours']==hours]
        horizons[key]=recent(rows,policy['thresholds'][key],freshness_required=True)
        by_regime[key]={regime:recent([row for row in rows if row['regime']==regime],
            policy['thresholds_by_regime'][key][regime]) for regime in policy['regimes']}
    passed=(historical['statistical_forecast_gates_passed'] and
        all(value['statistical_gates_passed'] for value in horizons.values()) and
        all(value['statistical_gates_passed'] for values in by_regime.values() for value in values.values()))
    return dict(schema='earthship-thermal-statistical-assessment/v2',policy_sha256=policy['policy_sha256'],
        assessed_at=now.isoformat(),historical_assessment=historical,recent_prospective=horizons,
        recent_prospective_by_regime=by_regime,
        monitoring_sampling_policy='latest_required_independent_days_after_declared_UTC_nonoverlap_and_Denver_daily_selection',
        statistical_forecast_gates_passed=passed,action_evidence_evaluated=False,
        source_qualification_evaluated=False,fit_qualification_evaluated=False,release_authorized=False)
