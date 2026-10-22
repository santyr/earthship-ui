"""Matched rain interval scores and conservative, unselected dispositions.

Evaluation consumes original predictions; it never refits a model while scoring.
Point-threshold alarms are distinguished from locally learned probabilities.
"""
from collections import Counter,defaultdict
from math import fsum,sqrt,ceil
from .contracts import canonical,identity,finite,instant
from .rain_calibration import RainForecast,RainObservation,PRODUCTS,_policy
from .rain_two_part import context,target_date,selected_forecasts,support,_budget,_clock


def point_metrics(values):
    if not values:return dict(targets=0,mae_mm=None,rmse_mm=None,signed_bias_mm=None,absolute_error_p95_mm=None,boundary_uncertainty_error_bounds=None)
    import numpy as np
    errors=[p-y for p,y,u in values];absolute=[abs(e) for e in errors]
    return dict(targets=len(values),mae_mm=fsum(absolute)/len(values),rmse_mm=sqrt(fsum(e*e for e in errors)/len(values)),signed_bias_mm=fsum(errors)/len(values),absolute_error_p95_mm=float(np.quantile(absolute,.95)),boundary_uncertainty_error_bounds=dict(mae_lower_mm=fsum(max(0.,abs(p-y)-u/2) for p,y,u in values)/len(values),mae_upper_mm=fsum(abs(p-y)+u/2 for p,y,u in values)/len(values)))


def _events(predictions,labels):
    pairs=[(p,y) for p,y in zip(predictions,labels) if p is not None and y in (0,1)]
    return dict(classified_targets=len(pairs),hits=sum(p and y==1 for p,y in pairs),false_alarms=sum(p and y==0 for p,y in pairs),misses=sum(not p and y==1 for p,y in pairs),correct_below_threshold=sum(not p and y==0 for p,y in pairs))


def occurrence_metrics(probabilities,labels):
    if len(probabilities)!=len(labels) or any(p is not None and (not finite(p) or not 0<=p<=1) for p in probabilities) or any(y is not None and type(y) is not int or y is not None and y not in (0,1) for y in labels):raise ValueError('matched finite interval probabilities and event labels required')
    pairs=[(p,y) for p,y in zip(probabilities,labels) if p is not None and y is not None];bins=[]
    for i in range(10):
        group=[(p,y) for p,y in pairs if min(9,int(p*10))==i]
        bins.append(dict(lower_inclusive=i/10,upper_exclusive_except_last=(i+1)/10,upper_inclusive=(i==9),count=len(group),mean_probability=None if not group else fsum(p for p,y in group)/len(group),observed_frequency=None if not group else fsum(y for p,y in group)/len(group)))
    return dict(targets=len(pairs),brier=None if not pairs else fsum((p-y)**2 for p,y in pairs)/len(pairs),reliability=bins,event=_events([None if p is None else p>=.5 for p in probabilities],labels),probability_claim=bool(pairs),probability_calibration_qualified=False)


def paired_bootstrap(rows,*,policy):
    policy=_policy(policy)
    if not isinstance(rows,list) or len(rows)>policy['limits']['maximum_rows_per_experiment']:raise ValueError('bounded paired local-date scores required')
    groups=defaultdict(list)
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'date','candidate','baseline'} or any(not finite(row[k]) for k in ('candidate','baseline')):raise ValueError('paired finite losses by independent local date required')
        __import__('datetime').date.fromisoformat(row['date']);groups[row['date']].append(row['candidate']-row['baseline'])
    if not groups:return dict(blocks=0,resamples=500,mean_difference=None,lower_95=None,upper_95=None)
    import numpy as np
    differences=np.asarray([fsum(groups[d])/len(groups[d]) for d in sorted(groups)]);rng=np.random.default_rng(policy['selection']['seed']);samples=np.asarray([np.mean(differences[rng.integers(0,len(differences),len(differences))]) for _ in range(500)])
    return dict(blocks=len(groups),resamples=500,mean_difference=float(np.mean(differences)),lower_95=float(np.quantile(samples,.025)),upper_95=float(np.quantile(samples,.975)))


def selection_decision(counts,*,amount_improvement,brier_improvement,amount_interval,brier_interval,subgroups,policy,wet_amount_improvement=None,wet_amount_interval=None):
    requirement=_policy(policy)['support'];rule=policy['selection'];result=dict(disposition='insufficient_evidence',selected=False,eligible_for_review=False,reason='independent_outer_class_event_support_required',automatic_promotion=False)
    if (counts['independent_dates']<requirement['minimum_outer_local_date_blocks'] or counts['wet_targets']<requirement['minimum_outer_wet_targets'] or counts['below_threshold_targets']<requirement['minimum_outer_below_threshold_targets'] or counts['wet_events']<requirement['minimum_independent_wet_events']):return result
    if (amount_improvement is None or brier_improvement is None or len(amount_interval)!=2 or len(brier_interval)!=2 or any(v is None for v in amount_interval+brier_interval)):
        result['reason']='matched_point_probability_and_uncertainty_required';return result
    if (wet_amount_improvement is None or wet_amount_improvement<rule['relative_improvement'] or wet_amount_interval is None or len(wet_amount_interval)!=2 or any(v is None for v in wet_amount_interval) or wet_amount_interval[1]>=0):
        result.update(disposition='retain_incumbent',reason='wet_amount_improvement_not_demonstrated');return result
    if any(g['targets']>=rule['minimum_subgroup_targets'] and (g.get('relative_regression') is None or g['relative_regression']>rule['maximum_supported_subgroup_regression']) for g in subgroups):result.update(disposition='reject_candidate',reason='supported_subgroup_regression');return result
    if (amount_improvement>=rule['relative_improvement'] and brier_improvement>=rule['relative_improvement'] and amount_interval[1]<0 and brier_interval[1]<0):result.update(disposition='adopt_candidate',eligible_for_review=True,reason='predeclared_experimental_gate_passed_review_required')
    else:result.update(disposition='retain_incumbent',reason='joint_point_and_probability_improvement_not_demonstrated')
    return result


def _point(pairs,values):return point_metrics([(v,p['observation']['observed_mm'],p['observation']['boundary_uncertainty_mm']) for p,v in zip(pairs,values) if v is not None])


def _point_result(pairs,values):
    labels=[p['observation']['event']['event_label'] for p in pairs];wet=[i for i,y in enumerate(labels) if y==1]
    event=_events([None if v is None or p['observation']['event']['threshold_mm'] is None else v>=p['observation']['event']['threshold_mm'] for p,v in zip(pairs,values)],labels)
    event.update(probability_claim=False,method='point_depth_crosses_declared_event_threshold_not_a_probability')
    return dict(point=_point(pairs,values),wet_amount=_point([pairs[i] for i in wet],[values[i] for i in wet]),event=event)


def _losses(pairs,candidate,baseline):return [dict(date=p['date'],candidate=abs(c-p['observation']['observed_mm']),baseline=abs(b-p['observation']['observed_mm'])) for p,c,b in zip(pairs,candidate,baseline) if c is not None and b is not None]


def _improvement(candidate,baseline):
    if candidate==baseline==0:return 0.
    return None if candidate is None or baseline is None or baseline<=0 else (baseline-candidate)/baseline


def _subgroups(pairs,candidate,baseline,policy):
    output=[];groups=defaultdict(list)
    for i,p in enumerate(pairs):
        f=p['forecast'];event=p['observation']['event']['classification'];month=int(p['date'][5:7]);season=('winter','spring','summer','fall')[(month%12)//3]
        for name,value in (('event',event),('interval_kind',f['interval_kind']),('lead_scope_hours',str(context(f,p['observation']['cohort_sha256'])['lead_scope_hours'])),('season',season)):
            groups[(name,value)].append(i)
    for (name,value),indices in sorted(groups.items()):
        matched=[i for i in indices if candidate[i] is not None and baseline[i] is not None];cp=_point([pairs[i] for i in matched],[candidate[i] for i in matched]);bp=_point([pairs[i] for i in matched],[baseline[i] for i in matched]);improvement=_improvement(cp['mae_mm'],bp['mae_mm'])
        output.append(dict(group=name,value=value,targets=len(matched),candidate=cp,baseline=bp,relative_regression=None if improvement is None else -improvement,uncertainty=paired_bootstrap(_losses([pairs[i] for i in matched],[candidate[i] for i in matched],[baseline[i] for i in matched]),policy=policy)))
    return output


def _cohort_report(pairs,issues,policy,check):
    raw={p:_point_result(pairs,[r['forecast']['products_mm'][p] for r in pairs]) for p in PRODUCTS};n=len(pairs);split=n-ceil(n/3);outer=pairs[split:];inner=pairs[:split]
    outer_counts=support(outer);outer_counts['independent_dates']=outer_counts.pop('independent_target_dates')
    baseline=[p['forecast']['products_mm'][PRODUCTS[0]] for p in pairs];predictions=[];probabilities=[];climatology=[];gain=[];reasons=Counter()
    for pair in pairs:
        check();f=pair['forecast'];issue=issues.get(f['forecast_sha256']);prediction=None if issue is None else issue['local_prediction']
        if issue is not None and (issue['forecast']['forecast_sha256']!=f['forecast_sha256'] or issue['observation_cohort_sha256']!=pair['observation']['cohort_sha256']):raise ValueError('rain issue differs from exact matched forecast/gauge context')
        available=prediction is not None and prediction['status']=='experimental_prediction'
        predictions.append(None if not available else prediction['mean_depth_mm']);probabilities.append(None if not available else prediction['probability_wet']);climatology.append(None if not available else prediction['climatology_probability']);gain.append(None if issue is None else issue['gain_prediction_mm'])
        if not available:reasons['original_local_prediction_not_issued' if prediction is None else prediction['reason']]+=1
    labels=[p['observation']['event']['event_label'] for p in pairs];candidate=_point_result(pairs,predictions);candidate['occurrence']=occurrence_metrics(probabilities,labels);candidate['training_only_climatology']=occurrence_metrics(climatology,labels)
    candidate['coverage']=dict(eligible_targets=n,predicted_targets=sum(v is not None for v in predictions),withheld=dict(reasons),selection_coverage_complete=all(v is not None for v in predictions))
    fallback=[b if v is None else v for b,v in zip(baseline,predictions)];candidate['fallback_policy']=_point_result(pairs,fallback)
    # Comparisons and day-block uncertainty use the same original targets. The
    # untouched final third is never used to choose a raw head or tune a fit.
    candidate['outer']=_point_result(outer,predictions[split:]);candidate['outer']['occurrence']=occurrence_metrics(probabilities[split:],labels[split:]);candidate['outer']['training_only_climatology']=occurrence_metrics(climatology[split:],labels[split:])
    incumbent=_point(outer,baseline[split:]);gain_result=_point_result(pairs,gain)
    amount_ci=paired_bootstrap(_losses(outer,predictions[split:],baseline[split:]),policy=policy)
    wet_indices=[i for i,p in enumerate(outer) if p['observation']['event']['event_label']==1];wet_pairs=[outer[i] for i in wet_indices];wet_local=[predictions[split+i] for i in wet_indices];wet_incumbent=[baseline[split+i] for i in wet_indices]
    wet_ci=paired_bootstrap(_losses(wet_pairs,wet_local,wet_incumbent),policy=policy);wet_improvement=_improvement(_point(wet_pairs,wet_local)['mae_mm'],_point(wet_pairs,wet_incumbent)['mae_mm'])
    brier_rows=[dict(date=p['date'],candidate=(v-y)**2,baseline=(c-y)**2) for p,v,c,y in zip(outer,probabilities[split:],climatology[split:],labels[split:]) if None not in (v,c,y)]
    brier_ci=paired_bootstrap(brier_rows,policy=policy);subgroups=_subgroups(outer,predictions[split:],baseline[split:],policy)
    local_decision=selection_decision(outer_counts,amount_improvement=_improvement(candidate['outer']['point']['mae_mm'],incumbent['mae_mm']),brier_improvement=_improvement(candidate['outer']['occurrence']['brier'],candidate['outer']['training_only_climatology']['brier']),amount_interval=[amount_ci['lower_95'],amount_ci['upper_95']],brier_interval=[brier_ci['lower_95'],brier_ci['upper_95']],subgroups=subgroups,policy=policy,wet_amount_improvement=wet_improvement,wet_amount_interval=[wet_ci['lower_95'],wet_ci['upper_95']])
    complete_outer=all(v is not None for v in predictions[split:])
    if not complete_outer:local_decision.update(disposition='insufficient_evidence',eligible_for_review=False,reason='complete_outer_candidate_policy_required')
    # A fitted candidate must beat the existing gain on its supported exact-24h
    # scope too. Unsupported durations retain the raw incumbent as fallback.
    gain_outer=_point(outer,gain[split:]);gain_complete=all(v is not None for v in gain[split:])
    gain_required=all(p['forecast']['hours']==24 and p['forecast']['site']['timezone']=='America/Denver' for p in outer)
    gain_ci=paired_bootstrap(_losses(outer,predictions[split:],gain[split:]),policy=policy)
    gain_wet=[gain[split+i] for i in wet_indices];gain_wet_ci=paired_bootstrap(_losses(wet_pairs,wet_local,gain_wet),policy=policy)
    gain_improvement=_improvement(candidate['outer']['point']['mae_mm'],gain_outer['mae_mm']);gain_wet_improvement=_improvement(_point(wet_pairs,wet_local)['mae_mm'],_point(wet_pairs,gain_wet)['mae_mm'])
    if local_decision['eligible_for_review'] and gain_required and not gain_complete:local_decision.update(disposition='insufficient_evidence',eligible_for_review=False,reason='matching_existing_gain_baseline_required')
    if local_decision['eligible_for_review'] and gain_complete and (gain_improvement is None or gain_improvement<policy['selection']['relative_improvement'] or gain_wet_improvement is None or gain_wet_improvement<policy['selection']['relative_improvement'] or gain_ci['upper_95'] is None or gain_ci['upper_95']>=0 or gain_wet_ci['upper_95'] is None or gain_wet_ci['upper_95']>=0):local_decision.update(disposition='retain_incumbent',eligible_for_review=False,reason='gain_baseline_amount_wet_or_uncertainty_not_improved')
    chosen=min(PRODUCTS,key=lambda p:(_point(inner,[r['forecast']['products_mm'][p] for r in inner])['mae_mm'] if inner else float('inf'),PRODUCTS.index(p)))
    chosen_values=[p['forecast']['products_mm'][chosen] for p in outer];head_ci=paired_bootstrap(_losses(outer,chosen_values,baseline[split:]),policy=policy)
    wet_outer=[p for p in outer if p['observation']['event']['event_label']==1];wet_baseline=_point(wet_outer,[p['forecast']['products_mm'][PRODUCTS[0]] for p in wet_outer]);wet_selected=_point(wet_outer,[p['forecast']['products_mm'][chosen] for p in wet_outer]);head_improvement=_improvement(_point(outer,chosen_values)['mae_mm'],incumbent['mae_mm']);wet_improvement=_improvement(wet_selected['mae_mm'],wet_baseline['mae_mm'])
    head_wet_ci=paired_bootstrap(_losses(wet_outer,[p['forecast']['products_mm'][chosen] for p in wet_outer],[p['forecast']['products_mm'][PRODUCTS[0]] for p in wet_outer]),policy=policy)
    head_groups=_subgroups(outer,chosen_values,baseline[split:],policy);enough=outer_counts['independent_dates']>=policy['support']['minimum_outer_local_date_blocks'] and outer_counts['wet_targets']>=policy['support']['minimum_outer_wet_targets'] and outer_counts['below_threshold_targets']>=policy['support']['minimum_outer_below_threshold_targets']
    head_eligible=enough and chosen!=PRODUCTS[0] and head_improvement is not None and head_improvement>=policy['selection']['relative_improvement'] and wet_improvement is not None and wet_improvement>=policy['selection']['relative_improvement'] and head_ci['upper_95']<0 and head_wet_ci['upper_95'] is not None and head_wet_ci['upper_95']<0 and not any(g['targets']>=policy['selection']['minimum_subgroup_targets'] and (g['relative_regression'] is None or g['relative_regression']>policy['selection']['maximum_supported_subgroup_regression']) for g in head_groups)
    return dict(context=pairs[0]['context'],matched_targets=n,independent_dates=n,raw=raw,inner=dict(targets=len(inner),selected_raw_head=chosen),outer=dict(**outer_counts,target_sha256s=[p['forecast']['forecast_sha256'] for p in outer]),raw_head_decision=dict(disposition='adopt_candidate' if head_eligible else 'retain_incumbent' if enough else 'insufficient_evidence',eligible_for_review=head_eligible,selected=False,inner_selected_head=chosen,outer_improvement=head_improvement,outer_wet_amount_improvement=wet_improvement,uncertainty=head_ci,wet_amount_uncertainty=head_wet_ci,subgroups=head_groups),candidate=candidate,gain=dict(**gain_result,coverage=dict(predicted_targets=sum(v is not None for v in gain),eligible_targets=n),scope='existing gain only exact 24 elapsed hours and its original measurement/timezone contract; otherwise raw fallback'),uncertainty=dict(amount_vs_incumbent=amount_ci,wet_amount_vs_incumbent=wet_ci,amount_vs_gain=gain_ci,wet_amount_vs_gain=gain_wet_ci,brier_vs_training_climatology=brier_ci),subgroups=subgroups,timing=dict(status='insufficient_evidence',reason='separately_qualified_hourly_counter_brackets_required; interval_model_has_no_intrainterval_probability'),**local_decision)


def evaluate_rain(forecasts,observations,*,assessed_at,policy,issues=None,issue_mode='causal_retrospective_experiment',guard=lambda:None):
    policy=_policy(policy);assessed_at=_clock(assessed_at);check=_budget(policy,guard)
    if issue_mode not in ('causal_retrospective_experiment','prospective_shadow'):raise ValueError('explicit unmixed rain prediction mode required')
    if issues is not None and (not isinstance(issues,list) or len(issues)>policy['limits']['maximum_rows_per_experiment']):raise ValueError('bounded original rain prediction inventory required')
    groups=defaultdict(list);total=0;seen=set();withheld=Counter()
    if not isinstance(forecasts,list) or not isinstance(observations,list) or len(forecasts)+len(observations)>policy['limits']['maximum_rows_per_experiment']:raise ValueError('bounded original rain experiment required')
    for original in forecasts:
        check()
        if type(original) is not RainForecast:raise ValueError('typed original rain forecast required')
        row=RainForecast(original.content).to_dict();pin=row['forecast_sha256']
        if pin in seen:continue
        seen.add(pin);total+=len(original.content);scope=context(row,'0'*64);groups[identity(scope)].append(original)
    for original in observations:
        check()
        if type(original) is not RainObservation:raise ValueError('typed original rain observation required')
        total+=len(original.content)
    if total>policy['limits']['maximum_original_bytes']:raise ValueError('rain original collection exceeds byte bound')
    outcome={}
    for original in observations:
        check();row=RainObservation(original.content).to_dict()
        if instant(row['available_at'])>assessed_at:withheld['outcome_acquired_after_assessment']+=1;continue
        r=row['request'];key=(instant(r['start']),instant(r['end']));old=outcome.get(key)
        if old is None or (instant(row['available_at']),row['observation_sha256'])<(instant(old['available_at']),old['observation_sha256']):outcome[key]=row
    issue_map={}
    for issue in issues or []:
        from .rain_issues import RainIssue
        if type(issue) is not RainIssue:raise ValueError('typed original rain prediction required')
        check();body=RainIssue(issue.content).to_dict();pin=body['forecast']['forecast_sha256']
        if instant(body['prepared_at'])>assessed_at:withheld['prediction_prepared_after_assessment']+=1;continue
        if body['mode']!=issue_mode:withheld['different_prediction_mode']+=1;continue
        if pin not in issue_map:
            total+=len(issue.content)
            if total>policy['limits']['maximum_original_bytes']:raise ValueError('rain originals and predictions exceed byte bound')
        if pin in issue_map and issue_map[pin]!=body:raise ValueError('conflicting original rain predictions')
        issue_map[pin]=body
    cohorts=defaultdict(list);selected_total=0
    for group in groups.values():
        # Raw comparisons have no training lookback. The 28-day window applies
        # exclusively to fitting; assessment may compare every retained date.
        selected,_=selected_forecasts(group,cutoff=assessed_at,policy=policy,guard=check,training_window=False);selected_total+=len(selected)
        for forecast in selected:
            if not forecast['common_complete_targets']:withheld['missing_precipitation_head']+=1;continue
            observation=outcome.get((instant(forecast['start']),instant(forecast['end'])))
            if observation is None:withheld['qualified_counter_interval_unavailable']+=1;continue
            c=context(forecast,observation['cohort_sha256']);cohorts[identity(c)].append(dict(forecast=forecast,observation=observation,date=target_date(forecast),context=c))
    reports={pin:_cohort_report(pairs,issue_map,policy,check) for pin,pairs in sorted(cohorts.items())};check()
    result=dict(schema='earthship-rain-matched-interval-evaluation/v1',prediction_mode=issue_mode,assessed_at=assessed_at.isoformat(),policy_sha256=policy['policy_sha256'],selected_targets=selected_total,matched_targets=sum(v['matched_targets'] for v in reports.values()),withheld=dict(withheld),cohorts=reports,original_forecast_sha256s=sorted(seen),original_observation_sha256s=sorted({v.to_dict()['observation_sha256'] for v in observations}),scoring_scope='retained_raw_means_and_original_local_interval_predictions; independent_cohorts_not_pooled',as_issued_score=False,probability_calibration_qualified=False,physical_calibration_qualified=False,raw_production_rain_retained=True,automatic_actuation=False)
    result['evaluation_sha256']=identity(result);return result


def score_hourly_timing(forecast,observations,*,assessed_at,policy,guard=lambda:None):
    """Native hourly mean timing only, with complete independently qualified bins."""
    from datetime import timedelta
    policy=_policy(policy);check=_budget(policy,guard);assessed_at=_clock(assessed_at)
    if type(forecast) is not RainForecast or not isinstance(observations,list) or len(observations)>policy['limits']['maximum_rows_per_experiment']:raise ValueError('bounded original rain timing inputs required')
    f=RainForecast(forecast.content).to_dict();size=len(forecast.content);start,end=map(instant,(f['start'],f['end']));index={}
    result=dict(status='insufficient_evidence',reason='complete_qualified_hourly_counter_brackets_required',matched_hours=0,heads={},local_model_timing=None,native_google_probability=False,physical_calibration_qualified=False,automatic_actuation=False)
    for original in observations:
        check()
        if type(original) is not RainObservation:raise ValueError('typed original hourly counter observation required')
        size+=len(original.content)
        if size>policy['limits']['maximum_original_bytes']:raise ValueError('rain timing originals exceed byte bound')
        row=RainObservation(original.content).to_dict();r=row['request'];left,right=map(instant,(r['start'],r['end']))
        if not start<=left<right<=end or right-left!=timedelta(hours=1) or instant(row['available_at'])>assessed_at:continue
        old=index.get((left,right))
        if old is None or (instant(row['available_at']),row['observation_sha256'])<(instant(old['available_at']),old['observation_sha256']):index[(left,right)]=row
    expected=[(start+timedelta(hours=i),start+timedelta(hours=i+1)) for i in range(f['hours'])]
    if any(key not in index for key in expected) or not f['common_complete_targets']:return result
    rows=[index[key] for key in expected]
    if len({r['cohort_sha256'] for r in rows})!=1:result['reason']='coherent_hourly_measurement_epoch_and_policy_required';return result
    measured=[r['observed_mm'] for r in rows];positions=[i+.5 for i in range(f['hours'])];total=fsum(measured)
    for head in PRODUCTS:
        values=[r['statistics']['mean'] for r in f['hourly_statistics'][head]];forecast_total=fsum(values);actual_peak=[i for i,v in enumerate(measured) if v==max(measured)];forecast_peak=[i for i,v in enumerate(values) if v==max(values)]
        peak=None;reason=None
        if total<=0:reason='no_measured_rain_to_locate'
        elif forecast_total<=0:reason='no_forecast_rain_to_locate'
        elif len(actual_peak)!=1:reason='nonunique_measured_peak'
        elif len(forecast_peak)!=1:reason='nonunique_native_peak'
        else:peak=abs(actual_peak[0]-forecast_peak[0])
        centroid=None if min(total,forecast_total)<=0 else abs(fsum(t*v for t,v in zip(positions,values))/forecast_total-fsum(t*v for t,v in zip(positions,measured))/total)
        result['heads'][head]=dict(hourly_point=point_metrics([(v,r['observed_mm'],r['boundary_uncertainty_mm']) for v,r in zip(values,rows)]),depth_weighted_centroid_error_hours=centroid,peak_hour_absolute_error_hours=peak,peak_reason=reason)
    result.update(status='available',reason=None,matched_hours=len(rows),observation_sha256s=[r['observation_sha256'] for r in rows]);check();return result
