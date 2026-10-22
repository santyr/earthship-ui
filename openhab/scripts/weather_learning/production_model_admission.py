"""Pure direct-production preparation and selected prediction, never installation.

The caller chooses one fitted method explicitly and supplies the real release
owner's admission at prediction time. Old candidate/training receipts are never
rewritten. Experimental production use conveys no calibration or action authority.
"""
from pathlib import Path
from hashlib import sha256
import json
from .contracts import canonical,digest,identity,instant,finite
from .evidence import utc
from . import probabilistic as kernel
from .probabilistic_artifacts import CandidateBundle,load_candidate_bundle,candidate_frame,numerical_manifest

SCHEMA='earthship-experimental-production-model-admission/v1'
TARGETS={'temperature':'outdoor_temperature_c','wind':'local_station_hour_mean_wind_m_s','solar_proxy':'qualified_lux_proxy_hour_mean_w_m2'}
FIELDS={'schema','kind','target_kind','method_family','bundle_sha256','model_sha256','training_inputs_sha256','training_policy_sha256',
 'authorization_policy_sha256','admitted_at','valid_until','runtime_manifest','admission_scope','parallel_shadow_required',
 'local_coverage_qualified','probability_claim','automatic_actuation','automatic_promotion','admission_sha256'}


def _runtime():
    path=Path(__file__)
    return numerical_manifest()|{'openhab/scripts/weather_learning/production_model_admission.py':sha256(path.read_bytes()).hexdigest()}


def _authorization(value,expected):
    digest(expected)
    if (not isinstance(value,dict) or identity(value)!=expected or value.get('schema')!='earthship-weathernext-deployment-policy/v2' or
            value.get('deployment_mode')!='direct_production_replacement' or value.get('production_model_replacement_authorized') is not True or
            any(value.get(k) is not False for k in ('parallel_shadow_required','advance_superiority_required_for_deployment','automatic_promotion','automatic_actuation','scientific_qualification_changed'))):
        raise ValueError('exact explicit experimental production authorization required')


def _bundle(bundle,policy):
    if not isinstance(bundle,CandidateBundle):raise ValueError('original actually fitted bundle required')
    body=bundle.to_dict()
    load_candidate_bundle(body,expected_sha256=body['bundle_sha256'],policy=policy,require_current=True)
    return body


def prepare_admission(bundle,*,family,expected_model_sha256,policy,authorization,authorization_sha256,admitted_at):
    """Prepare a new receipt. This neither activates a selector nor emits a forecast."""
    _authorization(authorization,authorization_sha256);body=_bundle(bundle,policy);digest(expected_model_sha256)
    model=body['models'].get(family)
    if model is None or model['model_sha256']!=expected_model_sha256:raise ValueError('explicit actually fitted model identity required')
    admitted=utc(admitted_at);ready,expiry=map(instant,(body['actual_completed_at'],body['expires_at']))
    if not ready<=admitted<expiry:raise ValueError('original fitted model admission lifetime required')
    value=dict(schema=SCHEMA,kind=body['kind'],target_kind=TARGETS[body['kind']],method_family=family,
        bundle_sha256=body['bundle_sha256'],model_sha256=expected_model_sha256,training_inputs_sha256=body['training_inputs_sha256'],
        training_policy_sha256=body['policy_sha256'],authorization_policy_sha256=authorization_sha256,
        admitted_at=admitted.isoformat(),valid_until=expiry.isoformat(),runtime_manifest=_runtime(),
        admission_scope='prepared_for_explicit_production_owner_not_proof_of_installation_or_emission',parallel_shadow_required=False,
        local_coverage_qualified=False,probability_claim=False,automatic_actuation=False,automatic_promotion=False)
    value['admission_sha256']=identity(value);return value


def _validate(bundle,admission,*,policy,at):
    body=_bundle(bundle,policy)
    if (not isinstance(admission,dict) or set(admission)!=FIELDS or admission['schema']!=SCHEMA or
            admission['admission_sha256']!=identity({k:v for k,v in admission.items() if k!='admission_sha256'}) or
            admission['runtime_manifest']!=_runtime() or admission['admission_scope']!='prepared_for_explicit_production_owner_not_proof_of_installation_or_emission' or
            any(admission[k] is not False for k in ('parallel_shadow_required','local_coverage_qualified','probability_claim','automatic_actuation','automatic_promotion'))):
        raise ValueError('unchanged exact-source production admission required')
    digest(admission['authorization_policy_sha256'])
    if any(admission[k]!=body[n] for k,n in (('kind','kind'),('bundle_sha256','bundle_sha256'),('training_inputs_sha256','training_inputs_sha256'),('training_policy_sha256','policy_sha256'))):
        raise ValueError('original production model/training identity differs')
    model=body['models'].get(admission['method_family'])
    if model is None or model['model_sha256']!=admission['model_sha256'] or admission['target_kind']!=TARGETS[body['kind']]:
        raise ValueError('original production model/target identity differs')
    ready,admitted,expiry=map(instant,(body['ready_at'],admission['admitted_at'],admission['valid_until']))
    if not ready<=admitted<=at<expiry==instant(body['expires_at']):raise ValueError('original production model lifetime expired or not yet admitted')
    return body


def predict_production(bundle,admission,frame,*,policy,authorize=None):
    """Prepare one forecast-only output after current owner/release admission.

    This makes no network request, fit, publication or scoring claim. A publisher
    must retain the actual emitted output separately before it becomes issued.
    """
    receipt=json.loads(canonical(admission));at=instant(frame.origin);body=_validate(bundle,receipt,policy=policy,at=at)
    mapped=candidate_frame(bundle,frame)
    if mapped is None:raise ValueError('production model target/cohort differs')
    if not callable(authorize):raise ValueError('current production owner admission required')
    checked=json.loads(canonical(receipt))
    if authorize(checked) is not True or checked!=receipt:raise ValueError('unchanged current production owner admission required')
    family=receipt['method_family'];model=body['models'][family]
    restored=object.__new__(kernel.CalibrationModel);object.__setattr__(restored,'_raw',canonical(model))
    if family=='adaptive':
        selected=kernel.adaptive_point(restored,mapped,policy=policy)
        if not selected or selected.get('candidate_used') is not True:raise ValueError('selected production adaptive model unavailable')
        point,statistic=selected['value'],'adaptive_point'
    else:
        prediction=kernel.predict_marginal(restored,mapped,policy=policy)
        selected=None if prediction is None else prediction.to_dict()
        if selected is None:raise ValueError('selected production marginal model unavailable')
        point,statistic=selected['point_estimate'],selected['point_estimate_kind']
    if not finite(point) or selected['model_sha256']!=receipt['model_sha256']:raise ValueError('selected production point/model differs')
    # A long preparation cannot renew an admission/source; the writer must recheck
    # the actual current clock at publication through its independent owner gate.
    result=dict(schema='earthship-experimental-production-point/v1',status='production_prediction',
        target_kind=receipt['target_kind'],target_start=frame.target_start,target_end=frame.target_end,decision_at=frame.origin,
        source_forecast_sha256=frame.forecast_sha256,source_available_at=frame.actual_source_available_at,
        admission_sha256=receipt['admission_sha256'],bundle_sha256=body['bundle_sha256'],model_sha256=receipt['model_sha256'],method_family=family,
        point_estimate=point,point_estimate_kind=statistic,raw_mean=frame.baseline,raw_median=frame.p50,
        local_coverage_qualified=False,probability_claim=False,issued=False,automatic_actuation=False)
    result['prediction_sha256']=identity(result);return result
