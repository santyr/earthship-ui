"""Reuse exact paired evidence without renewing original model availability."""
from .contracts import identity,instant


def residual_if_changed(previous,rows,**context):
    from .site_calibration import _pair,_model,fit_residual,SCHEMA
    kind,cutoff=context['kind'],context['cutoff'];chosen=[_pair(r) for r in rows if r['kind']==kind and instant(r['target_at'])<cutoff]
    chosen.sort(key=lambda r:(r['origin'],r['target_at'],r['pair_sha256']))
    if previous is not None:
        old=_model(previous)
        if old['schema']==SCHEMA and old['kind']==kind and old['training_data_sha256']==identity(chosen) and old['correction_limit']==context['correction_limit'] and old['ridge']==context.get('ridge',1.) and instant(old['cutoff'])<=cutoff and instant(old['trained_at'])<=context['trained_at']:return old,False
    return fit_residual(rows,**context),True


def gain_if_changed(previous,rows,**context):
    from .weather_response import _pair,validate_model,fit_gain,SCHEMA
    kind,cutoff=context['kind'],context['cutoff'];chosen=[_pair(r) for r in rows if r['kind']==kind and instant(r['target_end'])<cutoff]
    chosen.sort(key=lambda r:(r['origin'],r['target_end'],r['pair_sha256']))
    if previous is not None:
        old=validate_model(previous)
        if old['schema']==SCHEMA and old['kind']==kind and old['training_data_sha256']==identity(chosen) and old['prior_pairs']==context.get('prior_pairs',24) and instant(old['cutoff'])<=cutoff and instant(old['trained_at'])<=context['trained_at']:return old,False
    return fit_gain(rows,**context),True
