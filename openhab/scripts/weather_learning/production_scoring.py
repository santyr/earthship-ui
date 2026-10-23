"""Score original confirmed production predictions, without inference or refits."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from .contracts import canonical,digest,identity,instant
from .evidence import utc
from .production_emissions import read_issue,read_emission
from .marginal_outcomes import MarginalObservation,load_observation
from .probabilistic import ForecastInput,MarginalPrediction,score_marginal,LEVELS
from .probabilistic_retained import prepare_marginal_source
from .probabilistic_evaluation import _raw_score


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
    result=dict(schema='earthship-confirmed-production-weather-score/v1',status='scored' if compatible else 'observation_cohort_mismatch',
        emission_sha256=emission_sha256,issue_sha256=issue['issue_sha256'],row_sha256=row_sha256,
        production_prediction_sha256=None if prediction is None else prediction['prediction_sha256'],
        model_sha256=None if prediction is None else prediction['model_sha256'],bundle_sha256=None if prediction is None else prediction['bundle_sha256'],
        forecast=row['forecast'],observation={k:v for k,v in body.items() if k!='original'},
        raw=_raw_score(frame,body['value']) if compatible else None,local=local,measurement_cohort_compatible=compatible,
        fallback_reason=row['reason'],published_at=emission['published_at'],scoring_manifest=manifest,
        issued_prediction_used=True,model_retrained=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    result['score_sha256']=identity(result);return result
