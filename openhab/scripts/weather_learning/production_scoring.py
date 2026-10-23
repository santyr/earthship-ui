"""Score original confirmed production predictions, without inference or refits."""
from datetime import timedelta
import math,statistics,sys
from hashlib import sha256
from pathlib import Path
from .contracts import canonical,digest,identity,instant
from .evidence import utc
from .production_emissions import read_issue,read_emission
from .marginal_outcomes import MarginalObservation,load_observation
from .probabilistic import ForecastInput,MarginalPrediction,score_marginal,LEVELS
from .probabilistic_retained import prepare_marginal_source
from .probabilistic_evaluation import _raw_score


def scoring_runtime():
    paths=[Path(sys.executable).resolve(),Path(statistics.__file__)]
    if getattr(math,'__file__',None) is not None:paths.append(Path(math.__file__))
    return dict(python=sys.version,scalar_metrics='stored_predictions_stdlib_only_no_fitting',
        math_module='separate_extension' if getattr(math,'__file__',None) else 'built_into_verified_python',
        binary_or_source_sha256s={p.name:sha256(p.read_bytes()).hexdigest() for p in paths})


def _procedure(issue,frame,prediction):
    from .probabilistic import _lead
    from .probabilistic_artifacts import _in_partition
    bundle=None
    if prediction is not None:bundle=issue['model_originals'][prediction['bundle_sha256']]
    else:
        matches=[b for b in issue['model_originals'].values() if b['kind']==frame.kind and b['grid_sha256']==frame.grid_sha256 and b['timezone']==frame.timezone and
            b['lead_scope_hours']==_lead(frame.origin,frame.target_end) and frame.cohort_sha256 in (b['cohort_sha256'],b['serving_parent_cohort_sha256']) and _in_partition(b.get('training_partition'),frame)]
        if len(matches)>1:raise ValueError('ambiguous original production procedure')
        if matches:bundle=matches[0]
    if bundle is None:return dict(method_family=None,procedure_sha256=None,training_policy_sha256=None)
    family=next(iter(bundle['models']))
    procedure=dict(schema='earthship-registered-production-training-procedure/v1',kind=bundle['kind'],family=family,lead_scope_hours=bundle['lead_scope_hours'],
        training_policy_sha256=bundle['policy_sha256'],numerical_manifest=bundle['numerical_manifest'],numerical_environment=bundle['numerical_environment'],transfer_rule=bundle['transfer_rule'])
    return dict(method_family=family,procedure_sha256=identity(procedure),training_policy_sha256=bundle['policy_sha256'])


def _local_score(prediction,outcome):
    if (prediction['prediction_sha256']!=identity({k:v for k,v in prediction.items() if k!='prediction_sha256'}) or
            prediction['quantile_levels']!=list(LEVELS) or prediction['local_quantiles']!=sorted(prediction['local_quantiles']) or
            any(prediction[k] is not False for k in ('issued','local_coverage_qualified','probability_claim','automatic_actuation'))):
        raise ValueError('unchanged prepared numerical prediction under confirmed emission required')
    # A derived numerical view reuses only the scoring formulas. It does not
    # relabel the production original as an old marginal/shadow prediction.
    view=dict(schema='earthship-production-score-numerical-view/v1',original_production_prediction_sha256=prediction['prediction_sha256'],
        distribution=prediction['distribution'],parameters=prediction['distribution_parameters'],quantiles=prediction['local_quantiles'],
        point_estimate=prediction['point_estimate'],model_sha256=prediction['model_sha256'])
    view['prediction_sha256']=identity(view);obj=object.__new__(MarginalPrediction);object.__setattr__(obj,'_raw',canonical(view))
    return score_marginal(obj,outcome)


def score_emitted(state,*,emission_sha256,row_sha256,observation,assessed_at):
    digest(row_sha256);assessed=utc(assessed_at)
    if not isinstance(observation,MarginalObservation):raise ValueError('original acquired production observation required')
    emission=read_emission(state,emission_sha256);issue=read_issue(state,emission['issue_sha256']).to_dict()
    if row_sha256 not in {r['row_sha256'] for r in emission['score_rows']}:raise ValueError('original published predeclared score row required')
    row=next((r for r in issue['rows'] if identity(r)==row_sha256),None)
    if row is None or row['forecast'] is None:raise ValueError('original published forecast input required')
    body=load_observation(observation.to_dict()).to_dict();args=dict(row['forecast']);original_input=args.pop('input_sha256');frame=ForecastInput(**args)
    if frame.input_sha256!=original_input:raise ValueError('unchanged original forecast input required')
    if (body['kind'],body['target_start'],body['target_end'])!=(frame.kind,frame.target_start,frame.target_end):
        raise ValueError('matching original production observation target required')
    if not instant(frame.target_end)+timedelta(minutes=2)<=assessed or instant(body['available_at'])>assessed:
        raise ValueError('mature actually available production observation required')
    source=prepare_marginal_source(issue['source_originals'][frame.forecast_sha256],assessed_at=instant(issue['decision_at']))
    restored=source.forecast(frame.kind,target=instant(frame.target_end),quality=body['quality'],origin=instant(frame.origin))
    compatible=restored is not None and restored.input_sha256==frame.input_sha256
    prediction=row['prediction'];local=None
    if prediction is not None:
        if (prediction['source_input_sha256']!=frame.input_sha256 or prediction['source_forecast_sha256']!=frame.forecast_sha256 or
                (prediction['target_start'],prediction['target_end'])!=(frame.target_start,frame.target_end)):
            raise ValueError('original production prediction input differs')
        if compatible:local=_local_score(prediction,body['value'])
    files=('production_scoring.py','production_emissions.py','probabilistic.py','probabilistic_evaluation.py','marginal_outcomes.py','probabilistic_retained.py','contracts.py')
    manifest={name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in files}
    runtime=scoring_runtime();procedure=_procedure(issue,frame,prediction)
    result=dict(schema='earthship-confirmed-production-weather-score/v1',status='scored' if compatible else 'observation_cohort_mismatch',
        emission_sha256=emission_sha256,issue_sha256=issue['issue_sha256'],row_sha256=row_sha256,
        production_prediction_sha256=None if prediction is None else prediction['prediction_sha256'],
        model_sha256=None if prediction is None else prediction['model_sha256'],bundle_sha256=None if prediction is None else prediction['bundle_sha256'],
        forecast=row['forecast'],observation={k:v for k,v in body.items() if k!='original'},
        raw=_raw_score(frame,body['value']) if compatible else None,local=local,measurement_cohort_compatible=compatible,
        fallback_reason=row['reason'],published_at=emission['published_at'],scoring_manifest=manifest,
        **procedure,scoring_runtime=runtime,scoring_runtime_sha256=identity(runtime),issued_prediction_used=True,model_retrained=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    result['score_sha256']=identity(result);return result
