"""PV evidence reuse and chronological challenger selection; no action authority."""
from math import fsum
from .contracts import identity,instant
from .pv_calibration import _pair


def _reuse(previous,rows,*,cutoff,trained_at,fit,validate):
    # Preserve the fitter's exact row order: its dataset identity is ordered.
    chosen=[_pair(r) for r in rows if instant(r['end'])<cutoff]
    chosen=[r for r in chosen if r['potential_proxy_eligible'] is True and r['baseline_w']>=20]
    if previous is not None:
        old=validate(previous)
        if (old['dataset_sha256']==identity(chosen) and instant(old['cutoff'])<=cutoff and
            instant(old['trained_at'])<=trained_at):
            return old,False
    return fit(rows,cutoff=cutoff,trained_at=trained_at),True


def directional_if_changed(previous,rows,*,cutoff,trained_at):
    from .pv_directional_calibration import fit_directional,validate_model
    return _reuse(previous,rows,cutoff=cutoff,trained_at=trained_at,fit=fit_directional,validate=validate_model)


def effective_if_changed(previous,rows,*,cutoff,trained_at):
    from .pv_calibration import fit_gain,validate_model
    return _reuse(previous,rows,cutoff=cutoff,trained_at=trained_at,fit=fit_gain,validate=validate_model)


def compare_incumbent(candidate,incumbent,rows,*,holdout_start,holdout_end):
    from .pv_directional_calibration import validate_model,_calculate
    candidate=validate_model(candidate);incumbent=validate_model(incumbent)
    if not instant(candidate['cutoff'])<=holdout_start<holdout_end:
        raise ValueError('disjoint candidate holdout required')
    # The candidate is an earlier-fitted retrospective challenger, not a
    # falsely backdated deployed model. Only the incumbent actually existed.
    selected=[_pair(r) for r in rows if holdout_start<=instant(r['origin'])<instant(r['start']) and
        instant(incumbent['trained_at'])<=instant(r['origin']) and instant(r['end'])<holdout_end and r['potential_proxy_eligible'] is True]
    def metrics(values):
        def mae(model):
            return None if not values else fsum(abs((r['baseline_w'] if model is None else _calculate(model,r['baseline_w'],r['azimuth_degrees']))-r['outcome_w']) for r in values)/len(values)
        return dict(pairs=len(values),baseline_mae_w=mae(None),candidate_mae_w=mae(candidate),incumbent_mae_w=mae(incumbent))
    result=metrics(selected);days=len({r['start'][:10] for r in selected})
    result.update(schema='earthship-pv-incumbent-comparison/v1',candidate_model_sha256=candidate['model_sha256'],incumbent_model_sha256=incumbent['model_sha256'],
        holdout_start=holdout_start.isoformat(),holdout_end=holdout_end.isoformat(),independent_target_days=days,
        selected=len(selected)>=24 and days>=2 and result['candidate_mae_w']<min(result['incumbent_mae_w'],result['baseline_mae_w']),
        by_lead={name:metrics([r for r in selected if lo<r['lead_hours']<=hi]) for name,lo,hi in [('0-24h',0,24),('24-48h',24,48)]},
        qualification='retrospective_candidate_with_later_available_incumbent_not_prospective',prospective_score=False,physical_calibration_qualified=False,automatic_actuation=False)
    result['report_sha256']=identity(result);return result


def previous_models(output,sources):
    """Read verified prior models only when their numerical sources still match."""
    from pathlib import Path
    from hashlib import sha256
    import json
    from weather_source_files import _read
    output=Path(output);pointer=output/'last-experiment.json'
    if not pointer.exists():return {}
    selected=json.loads(_read(pointer,8192));run=Path(selected['path']);receipt=json.loads(_read(run/'experiment.json',1048576))
    if receipt['receipt_sha256']!=selected['receipt_sha256'] or receipt['receipt_sha256']!=identity({k:v for k,v in receipt.items() if k!='receipt_sha256'}):
        raise ValueError('previous PV experiment differs')
    for name in ('pv_calibration.py','pv_directional_calibration.py','contracts.py'):
        key='openhab/scripts/weather_learning/'+name
        if receipt['runtime_manifest'].get(key)!=sha256(sources[key]).hexdigest():return {}
    training=json.loads(_read(run/'training-model.json',1048576));final=json.loads(_read(run/'final-model.json',1048576))
    if training['model_sha256']!=receipt['training_model_sha256'] or final['model_sha256']!=receipt.get('final_model_sha256',receipt.get('final_model',{}).get('model_sha256')):
        raise ValueError('previous PV model differs')
    return dict(training_model=training,final_model=final)
