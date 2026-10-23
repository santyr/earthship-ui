"""Sanitized fixed public ranges from confirmed original production emissions."""
from datetime import timedelta
from hashlib import sha256
from .contracts import canonical,identity,instant
from .production_forecast import MPH
from .production_emissions import read_issue,read_emission
from .production_scoring import _procedure
from .shadow import _directory

MAX_BYTES=512*1024
MAX_RECEIPT_BYTES=4096


def retain_public_view(state,emission_sha256):
    # Validate the complete original confirmation. Neither today's model nor a
    # regenerated publisher can confer issued status on a prepared prediction.
    emission=read_emission(state,emission_sha256);issue=read_issue(state,emission['issue_sha256']).to_dict()
    indexed={identity(r):r for r in issue['rows']};rows=[];models={};sources={}
    for ref in emission['published_rows']:
        row=indexed[ref['row_sha256']];frame=row['forecast'];prediction=row['prediction'];kind=row['kind'];pin=row['source_sha256']
        original=issue['source_originals'][pin]
        sources[pin]=dict(initialized_at=original['initialized_at'],available_at=original['ingestion_completed_at'])
        raw=(row['raw_presentation_value']-32)*5/9 if kind=='temperature' and row['raw_presentation_value'] is not None else None
        if kind=='wind' and row['raw_presentation_value'] is not None:raw=row['raw_presentation_value']/MPH
        raw=dict(mean=raw if frame is None else frame['baseline'],p10=None if frame is None else frame['p10'],
            p50=None if frame is None else frame['p50'],p90=None if frame is None else frame['p90'],
            statistic='native_point' if kind=='temperature' else 'native_boundary_mean_hour_approximation' if frame is not None else 'native_instantaneous')
        local=None
        if prediction is not None:
            model=prediction['model_sha256'];bundle=issue['model_originals'][prediction['bundle_sha256']]
            models[model]=dict(method_family=prediction['method_family'],bundle_sha256=prediction['bundle_sha256'],admission_sha256=prediction['admission_sha256'],
                procedure_sha256=_procedure(issue,None,prediction)['procedure_sha256'],training_policy_sha256=bundle['policy_sha256'],
                training_availability_basis=bundle['training_availability_basis'],cutoff=bundle['cutoff'],actual_completed_at=bundle['actual_completed_at'],expires_at=bundle['expires_at'],support=bundle['support'])
            local=dict(model_sha256=model,point_estimate=prediction['point_estimate'],point_estimate_kind=prediction['point_estimate_kind'],quantiles=prediction['local_quantiles'])
        rows.append(dict(kind=kind,profile=row['profile'],source_sha256=pin,target_start=row['at'] if frame is None else frame['target_start'],target_end=row['at'],raw=raw,local=local,reason=row['reason']))
    rows.sort(key=lambda r:(instant(r['target_end']),r['kind']))
    if not rows or len(rows)>672:raise ValueError('bounded confirmed public hourly rows required')
    decision=instant(issue['decision_at']);until=min([decision+timedelta(minutes=90),*[instant(s['initialized_at'])+timedelta(hours=24) for s in sources.values()]])
    body=dict(schema='earthship-confirmed-production-weather-view/v1',issue_sha256=issue['issue_sha256'],production_emission_sha256=emission_sha256,
        generated_at=issue['decision_at'],published_at=emission['published_at'],valid_until=until.isoformat(),
        sources=sources,models=models,rows=rows,issued=True,parallel_shadow_required=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    body['report_sha256']=identity(body);raw=canonical(body)
    if len(raw)>MAX_BYTES:raise ValueError('bounded public production view exceeded')
    receipt=dict(schema='earthship-confirmed-production-view-receipt/v1',issue_sha256=issue['issue_sha256'],production_emission_sha256=emission_sha256,
        report_sha256=body['report_sha256'],cache_bytes_sha256=sha256(raw).hexdigest(),generated_at=body['generated_at'],published_at=body['published_at'],valid_until=body['valid_until'],issued=True,automatic_actuation=False)
    receipt['receipt_sha256']=identity(receipt)
    if len(canonical(receipt))>MAX_RECEIPT_BYTES:raise ValueError('bounded public production receipt required')
    _directory(state.root/'production-views')
    state._write(state.root/'production-views'/('view-'+body['report_sha256']+'.json'),receipt,immutable=True)
    state._write(state.root/'production-forecast.json',body)
    return body
