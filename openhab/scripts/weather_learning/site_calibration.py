"""Small fresh retrospective residual fits with disjoint chronological tests.

This module grants no release or actuator authority. Live prediction requires
actual artifact availability; evaluation alone uses hypothetical historical
training clocks and is always marked retrospective.
"""
from datetime import timedelta
from math import fsum,isfinite
from zoneinfo import ZoneInfo
from .contracts import canonical,identity,instant,finite,digest
from .evidence import utc
from .weights import site_weights,metrics as weighted_metrics,validate_support

SCHEMA='earthship-site-calibration/v2'

PAIR_FIELDS={'schema','kind','origin','target_at','lead_hours','availability_basis','forecast_sha256','features','baseline','outcome','label','origin_labels','prospective_score','automatic_actuation','pair_sha256'}
MODEL_FIELDS={'schema','rule','kind','feature_names','centers','scales','coefficients','intercept','correction_limit','ridge','cutoff','trained_at','training_start','training_end','sample_count','origin_days','timezone','training_pair_sha256s','forecast_sha256s','training_data_sha256','automatic_actuation','model_sha256'}


def _pair(row):
    if (not isinstance(row,dict) or set(row)!=PAIR_FIELDS or row['schema']!='earthship-historical-learning-pair/v1' or
        row['pair_sha256']!=identity({k:v for k,v in row.items() if k!='pair_sha256'}) or
        row['prospective_score'] is not False or row['automatic_actuation'] is not False or
        not instant(row['origin'])<instant(row['target_at']) or not finite(row['baseline']) or not finite(row['outcome'])):
        raise ValueError('unchanged chronological historical pair required')
    digest(row['forecast_sha256']);digest(row['pair_sha256'])
    if not isinstance(row['features'],dict) or not 1<=len(row['features'])<=16 or not all(finite(v) for v in row['features'].values()):
        raise ValueError('finite historical features required')
    return row


def _model(value):
    current=isinstance(value,dict) and value.get('schema')==SCHEMA
    if (not isinstance(value,dict) or set(value)!=(MODEL_FIELDS|{'support'} if current else MODEL_FIELDS) or value['schema'] not in (SCHEMA,'earthship-site-calibration/v1') or
        value['rule']!=('target_weighted_standardized_ridge_residual_v2' if current else 'standardized_ridge_residual_v1') or value['automatic_actuation'] is not False or
        value['model_sha256']!=identity({k:v for k,v in value.items() if k!='model_sha256'})):
        raise ValueError('unchanged original site calibration required')
    if current:
        support=validate_support(value['support'])
        if support['forecast_pairs']!=value['sample_count'] or support['timezone']!=value['timezone']:raise ValueError('site target support differs from model')
    names=value['feature_names'];n=len(names)
    if not 1<=n<=16 or names!=sorted(set(names)) or any(len(value[k])!=n for k in ('centers','scales','coefficients')):
        raise ValueError('complete frozen calibration preprocessing required')
    if (any(not finite(v) for k in ('centers','scales','coefficients') for v in value[k]) or
        any(v<=0 for v in value['scales']) or not finite(value['intercept']) or not finite(value['correction_limit']) or value['correction_limit']<=0 or
        not instant(value['training_start'])<=instant(value['training_end'])<instant(value['cutoff'])<=instant(value['trained_at'])):
        raise ValueError('finite past-trained calibration required')
    return value


def fit_residual(rows,*,kind,cutoff,trained_at,correction_limit,ridge=1.,timezone_name='America/Denver'):
    import numpy as np
    cutoff,trained_at=utc(cutoff),utc(trained_at);zone=ZoneInfo(timezone_name)
    if (not isinstance(rows,list) or len(rows)>50000 or not cutoff<=trained_at or not finite(ridge) or ridge<=0 or
        not finite(correction_limit) or not 0<correction_limit<=100000):raise ValueError('bounded fresh residual fitting context required')
    # Select temporal eligibility before looking at future outcomes.
    selected=[_pair(row) for row in rows if row['kind']==kind and instant(row['target_at'])<cutoff]
    selected.sort(key=lambda r:(r['origin'],r['target_at'],r['pair_sha256']))
    if not selected:raise ValueError('completed earlier training outcomes required')
    if len({r['pair_sha256'] for r in selected})!=len(selected):raise ValueError('unique training pairs required')
    names=sorted(selected[0]['features'])
    if any(sorted(r['features'])!=names for r in selected):raise ValueError('consistent feature contract required')
    x=np.asarray([[r['features'][name] for name in names] for r in selected],dtype=float)
    y=np.asarray([r['outcome']-r['baseline'] for r in selected],dtype=float)
    weights,support=site_weights(selected,timezone_name);weights=np.asarray(weights)
    centers=np.average(x,axis=0,weights=weights);scales=np.sqrt(np.average((x-centers)**2,axis=0,weights=weights));scales=np.where(scales>1e-12,scales,1.)
    x=(x-centers)/scales;intercept=float(np.average(y,weights=weights))
    coefficients=np.linalg.solve(x.T@(weights[:,None]*x)+ridge*np.eye(len(names)),x.T@(weights*(y-intercept)))
    out=dict(schema=SCHEMA,rule='target_weighted_standardized_ridge_residual_v2',support=support,kind=kind,feature_names=names,
        centers=centers.tolist(),scales=scales.tolist(),coefficients=coefficients.tolist(),intercept=intercept,
        correction_limit=float(correction_limit),ridge=float(ridge),cutoff=cutoff.isoformat(),trained_at=trained_at.isoformat(),
        training_start=min(r['target_at'] for r in selected),training_end=max(r['target_at'] for r in selected),sample_count=len(selected),
        origin_days=len({instant(r['origin']).astimezone(zone).date() for r in selected}),timezone=timezone_name,
        training_pair_sha256s=[r['pair_sha256'] for r in selected],forecast_sha256s=sorted({r['forecast_sha256'] for r in selected}),
        training_data_sha256=identity(selected),automatic_actuation=False)
    out['model_sha256']=identity(out);_model(out);return out


def _calculate(model,features,baseline):
    names=model['feature_names']
    if not isinstance(features,dict) or sorted(features)!=names or not finite(baseline) or not all(finite(v) for v in features.values()):
        raise ValueError('original calibration feature contract required')
    correction=model['intercept']+fsum(c*(features[name]-center)/scale for name,center,scale,c in zip(names,model['centers'],model['scales'],model['coefficients']))
    if not isfinite(correction):raise ValueError('nonfinite calibration correction')
    return baseline+max(-model['correction_limit'],min(model['correction_limit'],correction))


def predict(model,features,*,baseline,origin):
    model=_model(model);origin=utc(origin)
    if instant(model['trained_at'])>origin:raise ValueError('site calibration was not available at origin')
    return _calculate(model,features,baseline)


def evaluate(model,rows,*,holdout_start,holdout_end):
    model=_model(model);start,end=map(utc,(holdout_start,holdout_end));zone=ZoneInfo(model['timezone'])
    if not instant(model['cutoff'])<=start<end:raise ValueError('later disjoint holdout interval required')
    selected=[_pair(r) for r in rows if r['kind']==model['kind'] and start<=instant(r['origin'])<instant(r['target_at'])<end]
    weights,support=site_weights(selected,model['timezone'])
    baseline=[r['baseline']-r['outcome'] for r in selected]
    candidate=[_calculate(model,r['features'],r['baseline'])-r['outcome'] for r in selected]
    horizons={}
    for row in selected:
        label='0-24h' if row['lead_hours']<=24 else '24-72h' if row['lead_hours']<=72 else '72-168h' if row['lead_hours']<=168 else '168-360h'
        horizons.setdefault(label,[]).append(row)
    def compare(values):
        w,s=site_weights(values,model['timezone'])
        return dict(support=s,baseline=weighted_metrics([r['baseline']-r['outcome'] for r in values],w),
            candidate=weighted_metrics([_calculate(model,r['features'],r['baseline'])-r['outcome'] for r in values],w))
    a,b=weighted_metrics(baseline,weights),weighted_metrics(candidate,weights)
    out=dict(schema='earthship-site-calibration-comparison/v2',support=support,kind=model['kind'],model_sha256=model['model_sha256'],
        holdout_start=start.isoformat(),holdout_end=end.isoformat(),pairs=len(selected),
        origin_days=len({instant(r['origin']).astimezone(zone).date() for r in selected}),
        target_days=len({instant(r['target_at']).astimezone(zone).date() for r in selected}),
        baseline_target='raw_google_temperature' if model['kind']=='outdoor_temperature_c' else 'origin_temperature_persistence',
        baseline_mae=a['mae'],candidate_mae=b['mae'],baseline=a,candidate=b,
        by_horizon={key:compare(values) for key,values in horizons.items()},
        availability_basis='retrospective_assumed_full_cycle_9h' if all(r['availability_basis']=='retrospective_assumed_full_cycle_9h' for r in selected) else 'retrospective_mixed_recorded_and_assumed_availability',prospective_score=False,automatic_actuation=False)
    out['report_sha256']=identity(out);return out
