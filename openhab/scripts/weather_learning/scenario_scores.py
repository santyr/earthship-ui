"""Descriptive scores for original local residual-block trajectories, not risk odds."""
from datetime import timedelta
from math import fsum,sqrt
from zoneinfo import ZoneInfo
from .contracts import canonical,identity,instant
from .scenarios import validate_scenario,make_residual_block

NAMES=('temperature_c','wind_m_s','ghi_wm2')
SCALES=(5.,3.,300.)


def _forecast(rows):return [[(r['tempF']-32)/1.8,r['windMph']*.44704,r['radiationWm2']] for r in rows]
def _distance(a,b):return sqrt(fsum(((x-y)/SCALES[j])**2 for row,other in zip(a,b) for j,(x,y) in enumerate(zip(row,other)))/len(a))


def _correlation(a,b):
    if len(a)<2:return dict(pairs=len(a),correlation=None)
    ma,mb=fsum(a)/len(a),fsum(b)/len(b);va=fsum((x-ma)**2 for x in a);vb=fsum((y-mb)**2 for y in b)
    return dict(pairs=len(a),correlation=None if min(va,vb)<1e-12 else max(-1.,min(1.,fsum((x-ma)*(y-mb) for x,y in zip(a,b))/sqrt(va*vb))))


def _dependence(rows):
    columns=list(zip(*rows))
    return dict(lag1={name:_correlation(column[:-1],column[1:]) for name,column in zip(NAMES,columns)},cross_variable={NAMES[i]+':'+NAMES[j]:_correlation(columns[i],columns[j]) for i in range(3) for j in range(i+1,3)})


def _metrics(members,truth,guard):
    n=len(members);distance=fsum(_distance(row,truth) for row in members)/n
    energy=distance-.5*fsum(_distance(a,b) for a in members for b in members)/(n*n)
    flattened=[[value/SCALES[j] for row in sample for j,value in enumerate(row)] for sample in members];y=[value/SCALES[j] for row in truth for j,value in enumerate(row)]
    variogram=mass=0.
    for i in range(len(y)):
        guard()
        for j in range(i+1,len(y)):
            weight=1/(1+abs(j//3-i//3));expected=fsum(abs(row[i]-row[j])**.5 for row in flattened)/n
            variogram+=weight*(abs(y[i]-y[j])**.5-expected)**2;mass+=weight
    mean=[[fsum(s[t][j] for s in members)/n for j in range(3)] for t in range(len(truth))]
    ramps={name:None if len(truth)<2 else fsum(abs((mean[t][j]-mean[t-1][j])-(truth[t][j]-truth[t-1][j])) for t in range(1,len(truth)))/(len(truth)-1) for j,name in enumerate(NAMES)}
    return dict(energy_score=max(0.,energy),variogram_score_p05=variogram/mass if mass else None,hourly_ramp_mae=ramps,point_mean_mae={name:fsum(abs(row[j]-y[j]) for row,y in zip(mean,truth))/len(truth) for j,name in enumerate(NAMES)},member_dependence=[_dependence(m) for m in members])


def assess_joint(scenarios,*,observations,assessed_at,training_blocks=None,guard=lambda:None):
    if not isinstance(scenarios,list) or not 1<=len(scenarios)<=6:raise ValueError('bounded original joint scenarios required')
    values=[validate_scenario(s) for s in scenarios];first=values[0];original=first['original_forecast'];origin=instant(first['origin']);now=instant(assessed_at.isoformat())
    cohort=first['block_original']['cohort_sha256'] if first['block_original'] is not None else None
    if (cohort is None or len({s['forecast_sha256'] for s in values})!=len(values) or any(s['recipe']['name']!='residual_block' or canonical(s['original_forecast'])!=canonical(original) or s['block_original']['cohort_sha256']!=cohort for s in values)):
        raise ValueError('unique same-original/cohort joint members required; stress cases are not a distribution')
    labels=make_residual_block(forcing=original,observations=observations,cohort_sha256=cohort).to_dict()
    if instant(labels['available_at'])>now:raise ValueError('complete outcomes must be actually available by assessment')
    indices=[i for i,r in enumerate(first['rows']) if origin<instant(r['at'])<=origin+timedelta(hours=first['horizon_hours'])]
    if not indices:raise ValueError('complete future targets required')
    truth=[[observations[i][name] for name in NAMES] for i in indices]
    members=[_forecast([s['rows'][i] for i in indices]) for s in values];raw=_forecast([original['rows'][i] for i in indices])
    inside=[[min(m[t][j] for m in members)<=truth[t][j]<=max(m[t][j] for m in members) for j in range(3)] for t in range(len(truth))]
    zone=ZoneInfo(first['site']['timezone']);dates={instant(first['rows'][i]['at']).astimezone(zone).date() for i in indices}
    report=dict(schema='earthship-local-joint-scenario-weather-assessment/v1',method=first['policy']['joint_method'],policy_sha256=first['policy']['policy_sha256'],original_forecast_sha256=original['forecast_sha256'],scenario_sha256s=[s['forecast_sha256'] for s in values],observation_block_sha256=labels['block_sha256'],assessed_at=now.isoformat(),target_semantics='temperature/wind point values; matching ending-hour mean physical GHI',empirical_score_definition='equal local constructed members; Euclidean scaled whole future trajectory divided by sqrt(target_count)',scale_by_variable=dict(zip(NAMES,SCALES)),variogram_definition='p=0.5; all scaled time/variable pairs; weight=1/(1+elapsed_hour_lag); normalized by weight sum',support=dict(forecast_origins=1,targets=len(indices),local_dates=len(dates),scenarios=len(values)),candidate=_metrics(members,truth,guard),raw_mean_reference=_metrics([raw],truth,guard),observed_dependence=_dependence(truth),trajectory_range_coverage=dict(all_targets_and_variables_inside=all(all(row) for row in inside),coordinate_fraction=fsum(sum(row) for row in inside)/(3*len(inside)),interpretation='descriptive finite constructed range; not a calibrated probability interval'),joint_extremes=_extremes(first,members,truth,training_blocks,cohort,guard),household_outcomes=dict(status='not_assessed',reason='matching_source_bound_household_targets_required'),disposition='insufficient_evidence',as_issued_score=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    report['assessment_sha256']=identity(report);return report



def _extremes(first,members,truth,blocks,cohort,guard):
    from collections import defaultdict
    from .scenarios import template_population
    if blocks is None:return dict(status='unavailable',reason='complete_training_threshold_population_not_supplied')
    eligible,withheld=template_population(forcing=first['original_forecast'],blocks=blocks,cohort_sha256=cohort,policy=first['policy'],guard=guard)
    zone=ZoneInfo(first['site']['timezone']);by_date={}
    for pin in sorted(eligible):by_date.setdefault(instant(eligible[pin]['through']).astimezone(zone).date(),pin)
    result=dict(status='unavailable',reason='fewer_than_frozen_template_dates',support=dict(template_dates=len(by_date),target_dates=0,targets=0),withheld=withheld,probability_claim=False)
    if len(by_date)<first['policy']['minimum_template_dates']:return result
    targets={};days=defaultdict(set)
    for pin in by_date.values():
        block=eligible[pin];origin,through=map(instant,(block['origin'],block['through']))
        for row in block['observations']:
            if not origin<instant(row['at'])<=through:continue
            values=tuple(row[name] for name in NAMES)
            if row['at'] in targets and targets[row['at']]!=values:raise ValueError('conflicting original training target values')
            targets[row['at']]=values;days[instant(row['at']).astimezone(zone).date()].add(row['at'])
    masses={at:1/len(days)/len(days[instant(at).astimezone(zone).date()]) for at in targets}
    def quantile(index,level):
        cumulative=0.
        for value,mass in sorted((row[index],masses[at]) for at,row in targets.items()):
            cumulative+=mass
            if cumulative>=level-1e-12:return value
        return max(row[index] for row in targets.values())
    thresholds={name:dict(p10=quantile(i,.1),p90=quantile(i,.9)) for i,name in enumerate(NAMES)}
    def event(row):return row[0]>=thresholds['temperature_c']['p90'] and row[1]<=thresholds['wind_m_s']['p10'] and row[2]<=thresholds['ghi_wm2']['p10']
    result.update(status='descriptive_only',reason=None,support=dict(template_dates=len(by_date),target_dates=len(days),targets=len(targets)),thresholds=thresholds,training_block_sha256s=sorted(by_date.values()),weights='equal_actual_local_target_dates_then_unique_targets; one original block per template date',event='hot_calm_low_solar_using_training_10th_and90th_percentiles',observed_joint_extreme_targets=sum(event(r) for r in truth),member_joint_extreme_target_counts=[sum(event(r) for r in rows) for rows in members],interpretation='finite local constructed trajectories; counts are not calibrated risk probabilities')
    return result
