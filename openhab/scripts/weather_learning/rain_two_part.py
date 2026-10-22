"""One preregistered, source-bound rain interval experiment; no serving authority."""
from collections import Counter
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from math import exp,log1p,fsum,isfinite
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo
from .contracts import canonical,identity,instant,finite,digest
from .rain_calibration import RainForecast,RainObservation,PRODUCTS,_policy
from .probabilistic_artifacts import numerical_environment

SCHEMA='earthship-rain-two-part-model/v1'
ROOT=Path(__file__).resolve().parents[3]
MODEL_FIELDS={'schema','method','policy_sha256','context','cutoff','fitted_at','training_start','training_end','training_dates','training_pairs','training_data_sha256','support','centers','scales','occurrence_coefficients','amount_coefficients','amount_smearing','subthreshold_mean_mm','threshold_mm','climatology_probability','numerical_sources','numerical_environment','automatic_actuation','model_sha256'}


def numerical_sources():
    from .source_bundle import capture_sources
    return {name:sha256(raw).hexdigest() for name,raw in capture_sources(ROOT).items()}


def _clock(at):
    if not isinstance(at,datetime) or at.utcoffset() is None:raise ValueError('aware actual fitting clock required')
    return at.astimezone(timezone.utc)


def lead_scope(forecast):
    hours=(instant(forecast['end'])-instant(forecast['issued_at'])).total_seconds()/3600
    for limit in (24,72,168,360):
        if hours<=limit:return limit
    raise ValueError('bounded native rain lead required')


def context(forecast,cohort):
    digest(cohort)
    return dict(interval_kind=forecast['interval_kind'],lead_scope_hours=lead_scope(forecast),grid_sha256=forecast['grid_sha256'],timezone=forecast['site']['timezone'],availability_basis=forecast['availability_basis'],observation_cohort_sha256=cohort)


def target_date(forecast):return (instant(forecast['end'])-timedelta(microseconds=1)).astimezone(ZoneInfo(forecast['site']['timezone'])).date().isoformat()


def features(forecast):
    values=[forecast['products_mm'][name] for name in PRODUCTS]
    if any(not finite(v) or v<0 for v in values):raise ValueError('complete nonnegative native rain means required')
    return [*[log1p(v) for v in values],(instant(forecast['end'])-instant(forecast['issued_at'])).total_seconds()/86400]


def _budget(policy,guard):
    begin=monotonic()
    def check():
        guard()
        if monotonic()-begin>policy['limits']['maximum_experiment_seconds']:raise TimeoutError('bounded rain experiment expired')
    return check


def selected_forecasts(forecasts,*,cutoff,policy,guard=lambda:None,training_window=True):
    """Choose originals before head completeness or outcome availability is inspected."""
    if not isinstance(forecasts,list) or len(forecasts)>policy['limits']['maximum_rows_per_experiment']:raise ValueError('bounded rain forecast inventory required')
    unique={};size=0
    for original in forecasts:
        guard()
        if type(original) is not RainForecast:raise ValueError('typed original rain forecast required')
        row=RainForecast(original.content).to_dict();key=row['forecast_sha256']
        if key in unique:continue
        size+=len(original.content)
        if size>policy['limits']['maximum_original_bytes']:raise ValueError('rain original collection exceeds byte bound')
        unique[key]=row
    targets={}
    for row in unique.values():
        end=instant(row['end'])
        if not end<cutoff or training_window and end<cutoff-timedelta(days=policy['support']['maximum_training_days']):continue
        if instant(row['actual_source_available_at'])>cutoff:continue
        key=(row['start'],row['end'],row['interval_kind'],row['grid_sha256'],row['availability_basis'])
        previous=targets.get(key);clock=(instant(row['issued_at']),instant(row['completed_at']))
        if previous and clock==(instant(previous['issued_at']),instant(previous['completed_at'])) and row['forecast_sha256']!=previous['forecast_sha256']:raise ValueError('conflicting original rain decisions at the same clock')
        if previous is None or clock>(instant(previous['issued_at']),instant(previous['completed_at'])):targets[key]=row
    scopes={identity({k:v for k,v in context(row,'0'*64).items() if k!='observation_cohort_sha256'}) for row in targets.values()}
    if len(scopes)>1:raise ValueError('one coherent original rain forecast context required before date selection')
    # The caller partitions scientific cohorts. Independent windows and dates are
    # selected without observing whether their gauge labels will be obtainable.
    chosen=[];days=set();last_end=None
    for row in sorted(targets.values(),key=lambda r:(r['end'],r['start'],r['forecast_sha256'])):
        day=target_date(row)
        if day in days or last_end is not None and instant(row['start'])<last_end:continue
        chosen.append(row);days.add(day);last_end=instant(row['end'])
    return chosen,size


def training_pairs(forecasts,observations,*,cutoff,policy,guard=lambda:None):
    selected,size=selected_forecasts(forecasts,cutoff=cutoff,policy=policy,guard=guard)
    if not isinstance(observations,list) or len(observations)>policy['limits']['maximum_rows_per_experiment']:raise ValueError('bounded rain outcome inventory required')
    outcomes={};seen=set()
    for original in observations:
        guard()
        if type(original) is not RainObservation:raise ValueError('typed original rain observation required')
        row=RainObservation(original.content).to_dict();pin=row['observation_sha256']
        if pin in seen:continue
        seen.add(pin);size+=len(original.content)
        if size>policy['limits']['maximum_original_bytes']:raise ValueError('rain original collection exceeds byte bound')
        if instant(row['available_at'])>cutoff:continue
        request=row['request'];key=(instant(request['start']),instant(request['end']))
        previous=outcomes.get(key)
        if previous is None or (instant(row['available_at']),pin)<(instant(previous['available_at']),previous['observation_sha256']):outcomes[key]=row
    pairs=[];refusals=Counter();contexts=set()
    for forecast in selected:
        guard()
        if not forecast['common_complete_targets']:refusals['missing_precipitation_head']+=1;continue
        observation=outcomes.get((instant(forecast['start']),instant(forecast['end'])))
        if observation is None:refusals['label_not_actually_available_by_cutoff']+=1;continue
        cohort=context(forecast,observation['cohort_sha256']);contexts.add(identity(cohort))
        pairs.append(dict(forecast=forecast,observation=observation,context=cohort,date=target_date(forecast)))
    return pairs,dict(refusals),len(selected),contexts


def support(pairs):
    wet=below=events=0;in_event=False
    # An unknown interval or chronological gap does not establish a new event.
    # Only an actually classified below-threshold interval can separate events.
    for pair in pairs:
        label=pair['observation']['event']['event_label']
        if label==1:
            wet+=1
            if not in_event:events+=1
            in_event=True
        elif label==0:below+=1;in_event=False
    return dict(training_targets=len(pairs),independent_target_dates=len({p['date'] for p in pairs}),wet_targets=wet,below_threshold_targets=below,wet_events=events,ambiguous_or_unclassified_targets=len(pairs)-wet-below)


def _refusal(reason,counts,withheld):return dict(status='insufficient_evidence',reason=reason,support=counts,withheld=withheld,model=None,automatic_actuation=False)


def fit_two_part(forecasts,observations,*,cutoff,fitted_at,policy,guard=lambda:None):
    policy=_policy(policy);cutoff=_clock(cutoff);fitted_at=_clock(fitted_at)
    if fitted_at<cutoff:raise ValueError('actual fit must complete after its cutoff')
    check=_budget(policy,guard);source=numerical_sources();environment=numerical_environment()
    pairs,withheld,selected,contexts=training_pairs(forecasts,observations,cutoff=cutoff,policy=policy,guard=check);counts=support(pairs);counts['selected_targets']=selected
    requirement=policy['support']
    if (len(contexts)!=1 or counts['training_targets']<requirement['minimum_training_targets'] or
        counts['wet_targets']<requirement['minimum_wet_targets'] or counts['below_threshold_targets']<requirement['minimum_below_threshold_targets'] or counts['wet_events']<requirement['minimum_independent_wet_events']):
        return _refusal('coherent_class_event_support_required',counts,withheld)
    usable=[p for p in pairs if p['observation']['event']['event_label'] is not None]
    thresholds={p['observation']['event']['threshold_mm'] for p in usable}
    if len(thresholds)!=1:return _refusal('one_gauge_event_threshold_required',counts,withheld)
    import numpy as np
    x=np.asarray([features(p['forecast']) for p in usable]);y=np.asarray([p['observation']['event']['event_label'] for p in usable],dtype=float)
    measured=np.asarray([p['observation']['observed_mm'] for p in usable]);threshold=thresholds.pop()
    # There is exactly one nonoverlapping target per local date, so each date
    # has unit weight. Duplicated issues cannot increase the ridge data weight.
    centers=x.mean(axis=0);scales=x.std(axis=0);scales=np.where(scales>1e-12,scales,1.)
    x=np.column_stack([np.ones(len(x)),(x-centers)/scales]);penalty=np.diag([0.,1.,1.,1.,1.]);beta=np.zeros(5);beta[0]=np.log((y.sum()+.5)/(len(y)-y.sum()+.5))
    try:
        for iteration in range(25):
            check();p=np.exp(-np.logaddexp(0.,-(x@beta)));variance=p*(1-p)
            delta=np.linalg.solve(x.T@(variance[:,None]*x)+penalty,x.T@(y-p)-penalty@beta);beta+=delta
            if np.max(np.abs(delta))<1e-8:break
        else:return _refusal('occurrence_fit_not_converged',counts,withheld)
        wet=y==1;positive=np.log(measured[wet]-threshold);amount=np.linalg.solve(x[wet].T@x[wet]+penalty,x[wet].T@positive)
        smear=float(np.mean(np.exp(positive-x[wet]@amount)));subthreshold=float(np.mean(measured[~wet]))
        if not np.all(np.isfinite(beta)) or not np.all(np.isfinite(amount)) or not isfinite(smear):return _refusal('nonfinite_fitted_parameters',counts,withheld)
    except (np.linalg.LinAlgError,FloatingPointError,OverflowError):return _refusal('numerical_fit_unavailable',counts,withheld)
    check()
    if numerical_sources()!=source or numerical_environment()!=environment:raise ValueError('rain numerical sources/environment changed during fit')
    model=dict(schema=SCHEMA,method=policy['candidate']['method'],policy_sha256=policy['policy_sha256'],context=usable[0]['context'],cutoff=cutoff.isoformat(),fitted_at=fitted_at.isoformat(),training_start=min(p['forecast']['start'] for p in usable),training_end=max(p['forecast']['end'] for p in usable),training_dates=[p['date'] for p in usable],training_pairs=[dict(forecast_sha256=p['forecast']['forecast_sha256'],observation_sha256=p['observation']['observation_sha256']) for p in usable],training_data_sha256=identity(pairs),support=counts,centers=centers.tolist(),scales=scales.tolist(),occurrence_coefficients=beta.tolist(),amount_coefficients=amount.tolist(),amount_smearing=smear,subthreshold_mean_mm=subthreshold,threshold_mm=threshold,climatology_probability=float((y.sum()+.5)/(len(y)+1)),numerical_sources=source,numerical_environment=environment,automatic_actuation=False)
    model['model_sha256']=identity(model)
    return dict(status='fitted',reason=None,support=counts,withheld=withheld,model=model,automatic_actuation=False)


def _model(model,policy,*,require_current=True):
    if (not isinstance(model,dict) or set(model)!=MODEL_FIELDS or model['schema']!=SCHEMA or model['model_sha256']!=identity({k:v for k,v in model.items() if k!='model_sha256'}) or
        model['policy_sha256']!=policy['policy_sha256'] or model['method']!=policy['candidate']['method'] or model['automatic_actuation'] is not False):raise ValueError('unchanged source-bound rain model required')
    if require_current and (model['numerical_sources']!=numerical_sources() or model['numerical_environment']!=numerical_environment()):raise ValueError('rain model numerical sources/environment differ')
    if not isinstance(model['numerical_sources'],dict) or not model['numerical_sources']:raise ValueError('original numerical source identities required')
    for pin in model['numerical_sources'].values():digest(pin)
    for key,length in (('centers',4),('scales',4),('occurrence_coefficients',5),('amount_coefficients',5)):
        if not isinstance(model[key],list) or len(model[key])!=length or any(not finite(v) for v in model[key]):raise ValueError('finite original rain preprocessing/coefficients required')
    if any(v<=0 for v in model['scales']) or not 0<=model['climatology_probability']<=1 or any(not finite(model[k]) or model[k]<0 for k in ('amount_smearing','subthreshold_mean_mm','threshold_mm')):raise ValueError('finite original rain amount components required')
    if not instant(model['training_start'])<instant(model['training_end'])<instant(model['cutoff'])<=instant(model['fitted_at']):raise ValueError('original chronological rain model required')
    return model


def _prediction(model,forecast,*,observation_cohort_sha256,policy,guard=lambda:None,require_current=True):
    policy=_policy(policy);check=_budget(policy,guard);model=_model(model,policy,require_current=require_current)
    if type(forecast) is not RainForecast:raise ValueError('typed original rain interval forecast required')
    row=RainForecast(forecast.content).to_dict();check()
    result=dict(status='insufficient_evidence',reason=None,probability_wet=None,conditional_wet_mean_mm=None,subthreshold_mean_mm=None,mean_depth_mm=None,climatology_probability=None,target={k:row[k] for k in ('start','end','interval_kind','hours')},forecast_sha256=row['forecast_sha256'],model_sha256=model['model_sha256'],method=model['method'],source_label=policy['candidate']['source_label'],native_google_probability=False,probability_calibration_qualified=False,physical_calibration_qualified=False,automatic_actuation=False)
    if context(row,observation_cohort_sha256)!=model['context']:result['reason']='unseen_interval_lead_grid_gauge_or_availability_context';return result
    if instant(model['fitted_at'])>instant(row['issued_at']):result['reason']='model_not_available_before_decision';return result
    day=datetime.fromisoformat(target_date(row));training=[datetime.fromisoformat(d) for d in model['training_dates']]
    if not training or min(abs((day-d).days) for d in training)>policy['support']['season_distance_days']:result['reason']='unseen_season_context';return result
    if not row['common_complete_targets']:result['reason']='missing_precipitation_head';return result
    x=[1.,*[(v-c)/s for v,c,s in zip(features(row),model['centers'],model['scales'])]]
    try:
        eta=fsum(a*b for a,b in zip(x,model['occurrence_coefficients']));probability=1/(1+exp(-eta)) if eta>=0 else exp(eta)/(1+exp(eta))
        mean=model['threshold_mm']+exp(fsum(a*b for a,b in zip(x,model['amount_coefficients'])))*model['amount_smearing'];below=model['subthreshold_mean_mm'];total=probability*mean+(1-probability)*below
        if not all(isfinite(v) for v in (probability,mean,below,total)):raise OverflowError
    except (OverflowError,ValueError):result['reason']='numerical_prediction_unavailable';return result
    check();result.update(status='experimental_prediction',reason=None,probability_wet=probability,conditional_wet_mean_mm=mean,subthreshold_mean_mm=below,mean_depth_mm=total,climatology_probability=model['climatology_probability']);return result


def predict_two_part(model,forecast,*,observation_cohort_sha256,policy,guard=lambda:None):
    """Fresh inference always requires the fitted original runtime/environment."""
    return _prediction(model,forecast,observation_cohort_sha256=observation_cohort_sha256,policy=policy,guard=guard,require_current=True)
