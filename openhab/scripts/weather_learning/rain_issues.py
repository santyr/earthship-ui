"""Sealed, unselected interval predictions; historical experiments stay explicit.

The reader replays the versioned numerical contract without granting an old
model permission for fresh inference. A release retaining these objects must
also retain the literal producer package matching their source manifest.
"""
from dataclasses import dataclass
from datetime import timedelta
import json
from .contracts import canonical,identity,instant,digest
from .rain_calibration import RainForecast,_policy,MAX_BYTES,PRODUCTS
from .rain_two_part import numerical_sources,predict_two_part,_prediction,_clock
from .weather_response import validate_model,predict_gain

SCHEMA='earthship-original-local-rain-issue/v1'
FIELDS={'schema','forecast','model','gain_model','local_prediction','gain_prediction_mm','gain_reason','fallback_mean_mm','observation_cohort_sha256','policy_original','producer_sources','prepared_at','mode','prospective_score','raw_production_rain_retained','automatic_actuation','issue_sha256'}


def _local(model,forecast,cohort,policy,*,current):
    if model is not None:
        if current:return predict_two_part(model,forecast,observation_cohort_sha256=cohort,policy=policy)
        return _prediction(model,forecast,observation_cohort_sha256=cohort,policy=policy,require_current=False)
    f=forecast.to_dict()
    return dict(status='insufficient_evidence',reason='supported_past_model_required',probability_wet=None,conditional_wet_mean_mm=None,subthreshold_mean_mm=None,mean_depth_mm=None,climatology_probability=None,target={k:f[k] for k in ('start','end','interval_kind','hours')},forecast_sha256=f['forecast_sha256'],model_sha256=None,method=policy['candidate']['method'],source_label=policy['candidate']['source_label'],native_google_probability=False,probability_calibration_qualified=False,physical_calibration_qualified=False,automatic_actuation=False)


def _gain(model,f):
    if model is None:return None,'original_past_gain_not_available'
    model=validate_model(model)
    if model['kind']!='rain_24h_mm':raise ValueError('rain gain kind required')
    if f['hours']!=24:return None,'existing_rain_24h_gain_does_not_cover_this_elapsed_duration'
    if f['site']['timezone']!=model.get('timezone','America/Denver'):return None,'existing_gain_timezone_contract_differs'
    if instant(model['trained_at'])>instant(f['issued_at']):return None,'gain_not_available_before_decision'
    baseline=f['products_mm'][PRODUCTS[0]]
    if baseline is None:return None,'raw_incumbent_head_unavailable'
    return predict_gain(model,baseline,origin=instant(f['issued_at'])),None


def _derive(request,*,current):
    policy=_policy(request['policy_original']);forecast=RainForecast(canonical(request['forecast']));f=forecast.to_dict();cohort=digest(request['observation_cohort_sha256']);prepared=instant(request['prepared_at']);mode=request['mode']
    if mode not in ('prospective_shadow','causal_retrospective_experiment') or prepared<instant(f['completed_at']):raise ValueError('explicit rain preparation clock and mode required')
    if mode=='prospective_shadow' and (not prepared<instant(f['start']) or prepared-instant(f['issued_at'])>timedelta(hours=2) or f['availability_basis']!='recorded_ingestion_availability'):raise ValueError('prospective rain shadow requires a genuinely future actually available interval')
    sources=request['producer_sources']
    if not isinstance(sources,dict) or not sources or len(sources)>1000:raise ValueError('original bounded rain producer source manifest required')
    for name,pin in sources.items():
        if not isinstance(name,str) or not name.startswith(('openhab/scripts/','scripts/java/')) or '..' in name.split('/'):raise ValueError('original rain producer source path required')
        digest(pin)
    if request['model'] is not None and request['model']['numerical_sources']!=sources:raise ValueError('rain model and issue numerical source identities differ')
    local=_local(request['model'],forecast,cohort,policy,current=current);gain,reason=_gain(request['gain_model'],f)
    result=dict(schema=SCHEMA,**request,local_prediction=local,gain_prediction_mm=gain,gain_reason=reason,fallback_mean_mm=f['products_mm'][PRODUCTS[0]] if local['mean_depth_mm'] is None else local['mean_depth_mm'],prospective_score=False,raw_production_rain_retained=True,automatic_actuation=False)
    result['issue_sha256']=identity(result);return result


@dataclass(frozen=True)
class RainIssue:
    content:bytes
    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>MAX_BYTES:raise ValueError('bounded original rain issue required')
        value=json.loads(self.content)
        if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA:raise ValueError('closed original rain issue required')
        keys={'forecast','model','gain_model','observation_cohort_sha256','policy_original','producer_sources','prepared_at','mode'}
        if canonical(_derive({k:value[k] for k in keys},current=False))!=canonical(value):raise ValueError('rain issue differs from its original numerical prediction')
    def to_dict(self):return json.loads(self.content)


def make_issue(forecast,*,model,observation_cohort_sha256,policy,prepared_at,mode,gain_model=None):
    if type(forecast) is not RainForecast:raise ValueError('typed original rain interval forecast required')
    request=dict(forecast=forecast.to_dict(),model=model,gain_model=gain_model,observation_cohort_sha256=observation_cohort_sha256,policy_original=_policy(policy),producer_sources=numerical_sources(),prepared_at=_clock(prepared_at).isoformat(),mode=mode)
    return RainIssue(canonical(_derive(request,current=True)))
