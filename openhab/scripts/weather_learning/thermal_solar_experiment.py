"""Distinct empirical air-temperature experiment using forecast solar components.

Horizontal radiation is a predictor, not a calibrated facade heat flux. Existing
radiation-proxy thermal weights and PV electrical gains are never consumed.
"""
from dataclasses import dataclass
from datetime import timedelta
from math import fsum,sin,pi
from .contracts import identity,instant,finite
from .evidence import utc
from .thermal_comparison import ACTIONS

METHODS={False:'native_horizontal_components_empirical_air_change/v1',True:'erbs_horizontal_components_empirical_air_change/v1'}
REFERENCE_ARRAY=dict(module_count=1,module_nameplate_w=1.,dc_nameplate_w=1.,surface_azimuth_degrees=180.,surface_tilt_degrees=0.)


def _state(value):
    for k in ('air_f','north_wall_f'):
        if not finite(value.get(k)) or not -40<=value[k]<=140:raise ValueError('measured bounded origin air/north-wall state required')
    if (value.get('passive_fit_allowed') is not True or any(not finite(value.get(k)) for k in ACTIONS) or
            not 0<=value['indoor_shade_closed']<=1 or value['outdoor_shade_present'] not in (0,1) or not 0<=value['vent_open']<=2):
        raise ValueError('known passive origin action state required')
    return value


def eligible_window(samples,*,origin,target,barriers,late_intervals):
    origin,target=map(utc,(origin,target))
    if not timedelta(0)<target-origin<=timedelta(hours=24):raise ValueError('bounded thermal comparison window required')
    if any(utc(effective)<=origin<utc(received) for effective,received in late_intervals):return False,'actions_received_after_origin'
    if any(origin<utc(at)<=target for at in barriers):return False,'ineligible_heat_or_action_barrier'
    initial=samples.get(origin.isoformat())
    if initial is None:return False,'missing_origin_state'
    try:_state(initial)
    except (ValueError,TypeError):return False,'unknown_or_nonpassive_origin_state'
    at=origin
    while at<=target:
        row=samples.get(at.isoformat())
        if row is None or row.get('passive_fit_allowed') is not True or any(not finite(row.get(k)) for k in ACTIONS):
            return False,'incomplete_or_unknown_action_trajectory'
        if any(row[k]!=initial[k] for k in ACTIONS):return False,'changed_actions'
        at+=timedelta(minutes=5)
    return True,None


@dataclass(frozen=True)
class ThermalComponentTrajectory:
    rows:tuple
    method:str
    projection_sha256:str
    forcing_sha256:str
    policy_sha256:str
    rejection_fraction:float
    evidence_class:str

    def features(self,*,origin_state,start,end):
        state=_state(origin_state);start,end=map(utc,(start,end));pieces=[];cursor=start
        if not timedelta(0)<end-start<=timedelta(hours=24):raise ValueError('bounded empirical response horizon required')
        for left,right,beam,diffuse,outdoor,native,reason in self.rows:
            a,b=max(start,left),min(end,right)
            if a>=b:continue
            if a!=cursor:raise ValueError('complete original thermal forcing coverage required')
            pieces.append(((b-a).total_seconds()/3600,beam,diffuse,outdoor,native,reason));cursor=b
        if cursor!=end:raise ValueError('complete original thermal forcing coverage required')
        h=(end-start).total_seconds()/3600
        transmission=(1-self.rejection_fraction*state['indoor_shade_closed'])*(1-self.rejection_fraction*state['outdoor_shade_present'])
        outdoor=fsum(dt*(temp-state['air_f']) for dt,beam,diffuse,temp,native,reason in pieces)/24
        values=[h,outdoor,(state['north_wall_f']-state['air_f'])*h/24,
            fsum(dt*beam/1000 for dt,beam,diffuse,temp,native,reason in pieces)*transmission,
            fsum(dt*diffuse/1000 for dt,beam,diffuse,temp,native,reason in pieces)*transmission,state['vent_open']*outdoor]
        return dict(features=values,method=self.method,prediction_target='measured_indoor_air_temperature_change_F',
            native_supported=all(native for dt,beam,diffuse,temp,native,reason in pieces),
            fallback_reasons=sorted({reason for dt,beam,diffuse,temp,native,reason in pieces if reason is not None}),
            projection_sha256=self.projection_sha256,forcing_sha256=self.forcing_sha256,policy_sha256=self.policy_sha256,
            evidence_class=self.evidence_class,uses_pv_electrical_correction=False,physical_calibration_qualified=False,automatic_actuation=False)


def build_trajectory(*,forcing,positions,start,end,horizon_profile,policy,force_total_only=False):
    from bisect import bisect_left
    from household_pv_components import project_window_components,_point
    if (policy.get('schema')!='earthship-thermal-solar-experiment-policy/v1' or
            policy.get('uses_legacy_proxy_coefficients') is not False or policy.get('uses_pv_electrical_correction') is not False or
            not finite(policy.get('nominal_shade_rejection_fraction')) or not 0<=policy['nominal_shade_rejection_fraction']<=1):
        raise ValueError('explicit non-proxy thermal solar experiment policy required')
    projection=project_window_components(array=REFERENCE_ARRAY,forecast=forcing,positions=positions,start=start,end=end,
        timezone_name=forcing['site']['timezone'],horizon_profile=horizon_profile,force_total_only=force_total_only)
    times=[instant(r['at']) for r in forcing['rows']];position_times=[instant(r['at']) for r in positions];rows=[]
    for row in projection['segments']:
        left,right=map(instant,(row['start'],row['end']));point=positions[bisect_left(position_times,right)]
        sample_at=min(instant(point['at']),left.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1))
        temp,_=_point(forcing['rows'],times,sample_at)
        beam=row['dni_wm2']*max(0.,sin(point['elevation_degrees']*pi/180))
        rows.append((left,right,beam,row['dhi_wm2'],temp,row['method']=='native_components',row['reason']))
    return ThermalComponentTrajectory(tuple(rows),METHODS[force_total_only],projection['projection_sha256'],forcing['forecast_sha256'],
        identity(policy),policy['nominal_shade_rejection_fraction'],projection['evidence_class'])


def component_features(*,forcing,positions,origin_state,origin,horizon_hours,horizon_profile,policy,force_total_only=False):
    if type(horizon_hours) is not int or horizon_hours not in policy['horizons_hours']:raise ValueError('declared thermal response horizon required')
    end=utc(origin)+timedelta(hours=horizon_hours)
    trajectory=build_trajectory(forcing=forcing,positions=positions,start=origin,end=end,horizon_profile=horizon_profile,policy=policy,force_total_only=force_total_only)
    return trajectory.features(origin_state=origin_state,start=origin,end=end)


def _response_rows(rows,policy):
    from .contracts import digest
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('bounded original thermal response pairs required')
    seen=set();cohorts=set();truth={}
    for r in rows:
        if r.get('pair_sha256')!=identity({k:v for k,v in r.items() if k!='pair_sha256'}) or r['pair_sha256'] in seen:
            raise ValueError('unique original thermal response pairs required')
        seen.add(r['pair_sha256']);cohorts.add(r['cohort_sha256'])
        for k in ('forecast_sha256','measurement_sha256','cohort_sha256'):digest(r[k])
        origin,target=map(instant,(r['origin'],r['target_at']))
        if (type(r['lead_hours']) is not int or r['lead_hours'] not in policy['horizons_hours'] or
                target-origin!=timedelta(hours=r['lead_hours']) or instant(r['available_at'])<target or
                r['feature_policy_sha256']!=identity(policy) or type(r['native_supported']) is not bool or
                any(not finite(r[k]) or not -40<=r[k]<=140 for k in ('origin_air_f','outcome_f')) or
                len(r['origin_actions'])!=3 or any(not finite(v) for v in r['origin_actions'])):
            raise ValueError('bounded original thermal response source/target required')
        for k in ('native_features','total_features'):
            x=r[k]
            if (not isinstance(x,list) or len(x)!=6 or any(not finite(v) or abs(v)>1000 for v in x) or
                    x[0]!=r['lead_hours'] or x[3]<0 or x[4]<0):raise ValueError('original six-component thermal feature vector required')
        key=(r['cohort_sha256'],r['target_at']);receipt=(r['outcome_f'],r['measurement_sha256'],r['available_at'])
        if key in truth and truth[key]!=receipt:raise ValueError('conflicting measured thermal target')
        truth[key]=receipt
    if len(cohorts)>1:raise ValueError('different thermal sensor/grid/policy cohorts cannot be pooled')
    return sorted(rows,key=lambda r:(r['origin'],r['target_at'],r['pair_sha256']))


def _target_weights(rows,zone):
    from collections import Counter,defaultdict
    groups=defaultdict(set);counts=Counter((r['cohort_sha256'],r['target_at']) for r in rows)
    for r in rows:groups[instant(r['target_at']).astimezone(zone).date()].add((r['cohort_sha256'],r['target_at']))
    return [1/(len(groups)*len(groups[instant(r['target_at']).astimezone(zone).date()])*counts[(r['cohort_sha256'],r['target_at'])]) for r in rows]


def _support(rows,zone):
    return dict(forecast_pairs=len(rows),targets=len({(r['cohort_sha256'],r['target_at']) for r in rows}),local_dates=len({instant(r['target_at']).astimezone(zone).date() for r in rows}))


def _temperature_metrics(rows,key,zone):
    from .weights import metrics
    selected=[r for r in rows if r.get(key) is not None];support=_support(selected,zone)
    if not selected:return dict(support,mae_c=None,rmse_c=None,bias_c=None,absolute_error_p95_c=None)
    weights=_target_weights(selected,zone);errors=[(r[key]-r['outcome_f'])*5/9 for r in selected]
    values=metrics(errors,weights);mass=0.;p95=None
    for error,weight in sorted(zip(map(abs,errors),weights)):
        mass+=weight
        if mass>=.95-1e-12:p95=error;break
    return dict(support,mae_c=values['mae'],rmse_c=values['rmse'],bias_c=values['bias'],absolute_error_p95_c=p95)


def _solve(rows,method,ridge,policy,zone):
    import numpy as np
    from scipy.optimize import lsq_linear
    weights=np.sqrt(np.asarray(_target_weights(rows,zone),dtype=float));key=method+'_features'
    matrix=np.asarray([r[key] for r in rows],dtype=float)*weights[:,None]
    target=np.asarray([r['outcome_f']-r['origin_air_f'] for r in rows])*weights
    matrix=np.vstack([matrix,np.eye(6)*ridge**.5]);target=np.concatenate([target,np.zeros(6)])
    fit=lsq_linear(matrix,target,bounds=(policy['coefficient_lower'],policy['coefficient_upper']),tol=1e-10,max_iter=200)
    if not fit.success or not np.isfinite(fit.x).all():raise ValueError('bounded thermal response fit did not converge')
    return list(map(float,fit.x))


def fit_response(rows,*,method,cutoff,fitted_at,policy,protocol,timezone_name='UTC'):
    from zoneinfo import ZoneInfo
    if method not in ('native','total'):raise ValueError('declared response baseline required')
    rows=_response_rows(rows,policy);cutoff=utc(cutoff);zone=ZoneInfo(timezone_name)
    if fitted_at is not None and utc(fitted_at)<cutoff:raise ValueError('actual thermal analysis fitting clock required')
    if len({r['lead_hours'] for r in rows})>1:raise ValueError('one declared response horizon per fit required')
    temporal=protocol['temporal']
    train=[r for r in rows if cutoff-timedelta(days=temporal['maximum_training_days'])<=instant(r['target_at'])<cutoff]
    def enough(values):
        s=_support(values,zone);return s['targets']>=temporal['minimum_training_targets'] and s['local_dates']>=temporal['minimum_training_local_dates']
    if not enough(train):return None
    dates=sorted({instant(r['target_at']).astimezone(zone).date() for r in train});last=dates[-1]
    earlier=[r for r in train if instant(r['target_at']).astimezone(zone).date()<last];inner=[r for r in train if instant(r['target_at']).astimezone(zone).date()==last]
    ridge=policy['cold_inner_selection_ridge'];scores={}
    if enough(earlier):
        for value in policy['ridge_candidates']:
            coefficients=_solve(earlier,method,value,policy,zone)
            scored=[dict(r,predicted=r['origin_air_f']+fsum(a*b for a,b in zip(coefficients,r[method+'_features']))) for r in inner]
            scores[str(value)]=_temperature_metrics(scored,'predicted',zone)['mae_c']
        ridge=min(policy['ridge_candidates'],key=lambda v:(scores[str(v)],-v))
    coefficients=_solve(train,method,ridge,policy,zone)
    from datetime import datetime,timezone
    completed=datetime.now(timezone.utc) if fitted_at is None else utc(fitted_at)
    if completed<cutoff:raise ValueError('thermal fit completion cannot precede training cutoff')
    value=dict(schema='earthship-component-thermal-response/v1',method=METHODS[method=='total'],prediction_target=policy['target'],
        lead_hours=train[0]['lead_hours'],cohort_sha256=train[0]['cohort_sha256'],coefficients=coefficients,ridge=ridge,inner_scores=scores,
        cutoff=cutoff.isoformat(),fitted_at=completed.isoformat(),training_end=max(r['target_at'] for r in train),support=_support(train,zone),
        training_pair_sha256s=sorted(r['pair_sha256'] for r in train),feature_policy_sha256=identity(policy),protocol_sha256=identity(protocol),
        evidence_class='retrospective_development_only',training_availability='target_end_order_assumption; actual acquisition clocks preserved',
        uses_legacy_proxy_coefficients=False,uses_pv_electrical_correction=False,physical_calibration_qualified=False,release_authorized=False,automatic_actuation=False)
    value['model_sha256']=identity(value);return value


def predict_response(model,*,features,origin_air_f,policy):
    if (model.get('schema')!='earthship-component-thermal-response/v1' or
            model.get('model_sha256')!=identity({k:v for k,v in model.items() if k!='model_sha256'}) or
            model.get('prediction_target')!=policy['target'] or model.get('feature_policy_sha256')!=identity(policy) or
            model.get('method') not in METHODS.values() or model.get('release_authorized') is not False or
            model.get('automatic_actuation') is not False or model.get('uses_legacy_proxy_coefficients') is not False or
            model.get('uses_pv_electrical_correction') is not False or model.get('physical_calibration_qualified') is not False or
            model.get('evidence_class')!='retrospective_development_only' or
            not instant(model['training_end'])<instant(model['cutoff'])<=instant(model['fitted_at']) or len(model.get('coefficients',[]))!=6 or
            any(not finite(v) or not lo<=v<=hi for lo,v,hi in zip(policy['coefficient_lower'],model['coefficients'],policy['coefficient_upper']))):
        raise ValueError('original bounded distinct thermal response model required')
    if (not isinstance(features,list) or len(features)!=6 or any(not finite(v) for v in features) or features[0]!=model['lead_hours'] or
            not finite(origin_air_f) or not -40<=origin_air_f<=140):raise ValueError('matched thermal response state/features required')
    value=origin_air_f+fsum(a*b for a,b in zip(model['coefficients'],features))
    return value if -40<=value<=140 else None


def assess_response(rows,*,timezone_name,policy,protocol,guard=lambda:None,fitted_at=None):
    from datetime import datetime,timezone
    from math import ceil
    from zoneinfo import ZoneInfo
    from collections import defaultdict
    from random import Random
    rows=_response_rows(rows,policy);zone=ZoneInfo(timezone_name)
    models=[];horizons={};predictions=[]
    for horizon in policy['horizons_hours']:
        values=[r for r in rows if r['lead_hours']==horizon];dates=sorted({instant(r['target_at']).astimezone(zone).date().isoformat() for r in values})
        outer=set(dates[-ceil(len(dates)/3):]) if dates else set();fits={};scored=[]
        for r in values:
            guard()
            if instant(r['target_at']).astimezone(zone).date().isoformat() not in outer:continue
            ready=instant(r['origin'])-timedelta(minutes=policy['assumed_fit_latency_minutes'])
            cutoff=ready.replace(hour=ready.hour//policy['model_cutoff_cadence_hours']*policy['model_cutoff_cadence_hours'],minute=0,second=0,microsecond=0)
            if cutoff not in fits:
                fits[cutoff]={method:fit_response(values,method=method,cutoff=cutoff,fitted_at=fitted_at,policy=policy,protocol=protocol,timezone_name=timezone_name) for method in ('native','total')}
                models.extend(m for m in fits[cutoff].values() if m is not None)
            row=dict(r,persistence_f=r['origin_air_f']);both=True
            for method in ('native','total'):
                m=fits[cutoff][method];value=None if m is None else predict_response(m,features=r[method+'_features'],origin_air_f=r['origin_air_f'],policy=policy)
                row[method+'_f']=r['origin_air_f'] if value is None else value;both=both and value is not None
            row['both_fitted']=both;scored.append(row);predictions.append(row)
        def metrics(group):return {name:_temperature_metrics(group,name+'_f',zone) for name in ('native','total','persistence')}
        matched=[r for r in scored if r['both_fitted'] and r['native_supported']];all_metrics=metrics(scored);matched_metrics=metrics(matched);support=_support(matched,zone)
        subgroups={};regressing=[]
        for action in sorted({tuple(r['origin_actions']) for r in matched}):
            subset=[r for r in matched if tuple(r['origin_actions'])==action];m=metrics(subset);subgroups[str(action)]=m
            if _support(subset,zone)['targets']>=protocol['selection']['minimum_subgroup_targets'] and m['native']['mae_c']>m['total']['mae_c']*(1+protocol['selection']['maximum_supported_subgroup_relative_regression'])+1e-9:
                regressing.append(str(action))
        by_day=defaultdict(list)
        for r in matched:by_day[instant(r['target_at']).astimezone(zone).date()].append(r)
        differences=[metrics(g)['native']['mae_c']-metrics(g)['total']['mae_c'] for g in by_day.values()];interval=None
        if len(differences)>=2:
            rng=Random(protocol['limits']['scenario_seed']);boot=sorted(fsum(rng.choice(differences) for _ in differences)/len(differences) for _ in range(128));interval=[boot[3],boot[124]]
        enough=support['targets']>=protocol['temporal']['minimum_outer_targets'] and support['local_dates']>=protocol['temporal']['minimum_outer_local_dates']
        disposition='insufficient_evidence'
        if enough:
            disposition='retain_incumbent';base=matched_metrics['total']['mae_c'];candidate=matched_metrics['native']['mae_c']
            if base>0 and candidate<=base*(1-protocol['selection']['point_or_proper_score_relative_improvement']) and not regressing and interval is not None and interval[1]<0:disposition='adopt_candidate'
        horizons[str(horizon)]=dict(outer_dates=sorted(outer),support=_support(scored,zone),fitted_native_support=support,
            fallback_inclusive=all_metrics,matched_native=matched_metrics,subgroups=subgroups,regressing_subgroups=regressing,
            paired_date_block_delta_mae_95pct_c=interval,disposition=disposition)
    result=dict(schema='earthship-component-thermal-assessment/v1',target=policy['target'],feature_policy_sha256=identity(policy),protocol_sha256=identity(protocol),
        horizons=horizons,models=models,predictions=predictions,weighting='equal_target_date_then_measured_target_then_forecast',
        evidence_class='retrospective_development; target_order_training_assumption',longer_temporal_independence_verified=False,
        actual_operational_incumbent_replacement=False,automatic_promotion=False,prospective_score=False,physical_calibration_qualified=False,automatic_actuation=False)
    result['report_sha256']=identity(result);return result
