"""Chronological provisional prediction errors, never qualification or actuation."""
from copy import deepcopy
from datetime import timedelta
from statistics import mean
import math
from .forcing_capture import _canonical
from .graduation_policy import _utc
from .installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM,_receipt
from .temperature_history import _validate_sensor_receipt
from .provisional_forecast import validate_capture,publication,digest

SCHEMA='earthship-provisional-thermal-scored-pair/v1'


def validate_delivery(capture,receipts):
    if not isinstance(receipts,dict) or set(receipts)!={NUMERIC_ITEM,PUBLICATION_ITEM}:raise ValueError('both original persisted receipts required')
    issue,published=map(_utc,(capture['issued_at'],capture['published_at']))
    clocks=[]
    for item,value in ((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,publication(capture))):
        original,at=_receipt(receipts[item],item)
        if _canonical(original)!=_canonical(value) or not published<=at<published+timedelta(seconds=90):raise ValueError('original provisional delivery differs')
        clocks.append(at)
    if clocks[1]<clocks[0]:raise ValueError('main receipt precedes numeric receipt')


def score(capture,receipts,outcome,*,horizon_hours,assessed_at,recent,check_budget=lambda:None):
    capture=validate_capture(capture,check_budget=check_budget);validate_delivery(capture,receipts)
    issue=_utc(capture['issued_at']);assessed=_utc(assessed_at)
    if type(horizon_hours) is not int or horizon_hours not in (1,6,12,24) or horizon_hours>capture['output']['horizon_hours']:raise ValueError('supported score horizon required')
    target=issue+timedelta(hours=horizon_hours)
    if assessed<target+timedelta(minutes=5):raise ValueError('mature outcome required')
    _validate_sensor_receipt(outcome,target,sensor_epoch=capture['candidate']['fit']['sensor_epochs']['air'])
    actual=float(outcome['temperatureF'])
    model=capture['output']['trajectory'][horizon_hours-1]
    if _utc(model['at'])!=target:raise ValueError('original score target differs')
    if not isinstance(recent,dict) or recent.get('status') not in ('available','insufficient_qualified_history','prediction_out_of_bounds','unavailable'):raise ValueError('explicit recent-cycle status required')
    recent_f=recent.get('prediction_f')
    if recent['status']=='available':
        if type(recent_f) not in (int,float) or not math.isfinite(recent_f) or not -40<=recent_f<=140:raise ValueError('physical recent baseline required')
    elif recent_f is not None:raise ValueError('unavailable recent baseline cannot predict')
    predictions=dict(model=model['air_f'],persistence=capture['output']['initial']['air_f'],recent_cycle=recent_f)
    pair=dict(schema=SCHEMA,artifact_sha256=capture['candidate']['artifact_sha256'],runtime_sha256=capture['candidate']['runtime_sha256'],
        capture_sha256=capture['capture_sha256'],issued_at=issue.isoformat(),target_at=target.isoformat(),assessed_at=assessed.isoformat(),horizon_hours=horizon_hours,
        outcome=deepcopy(outcome),predictions=predictions,errors={key:None if value is None else value-actual for key,value in predictions.items()},
        recent_cycle=deepcopy(recent),graduated=False,automatic_actuation=False)
    pair['pair_sha256']=digest(pair,'pair_sha256');return pair


def validate_pair(pair):
    if not isinstance(pair,dict) or pair.get('schema')!=SCHEMA or pair.get('graduated') is not False or pair.get('automatic_actuation') is not False:
        raise ValueError('provisional score authority differs')
    if pair.get('pair_sha256')!=digest(pair,'pair_sha256'):raise ValueError('original provisional score differs')
    issue,target,assessed=map(_utc,(pair['issued_at'],pair['target_at'],pair['assessed_at']))
    if type(pair['horizon_hours']) is not int or pair['horizon_hours'] not in (1,6,12,24) or target!=issue+timedelta(hours=pair['horizon_hours']) or assessed<target+timedelta(minutes=5):raise ValueError('score chronology differs')
    actual=pair['outcome']['temperatureF']
    if type(actual) not in (int,float) or not math.isfinite(actual) or not -40<=actual<=140:raise ValueError('physical outcome required')
    if set(pair['predictions'])!={'model','persistence','recent_cycle'} or set(pair['errors'])!=set(pair['predictions']):raise ValueError('closed baseline errors required')
    for key,predicted in pair['predictions'].items():
        if predicted is None:
            if key!='recent_cycle' or pair['errors'][key] is not None:raise ValueError('missing baseline error differs')
        elif type(predicted) not in (int,float) or not math.isfinite(predicted) or not -40<=predicted<=140 or pair['errors'][key]!=predicted-actual:
            raise ValueError('original baseline arithmetic differs')
    return deepcopy(pair)


def summarize(pairs,*,artifact_sha256=None):
    if not isinstance(pairs,list) or len(pairs)>256:raise ValueError('bounded current revision score window required')
    pairs=[validate_pair(pair) for pair in pairs]
    revisions={pair['artifact_sha256'] for pair in pairs}
    if artifact_sha256 is None:
        if len(revisions)>1:raise ValueError('mixed model revision report refused')
        artifact_sha256=next(iter(revisions),None)
    pairs=[pair for pair in pairs if pair['artifact_sha256']==artifact_sha256]
    identities=[(pair['capture_sha256'],pair['horizon_hours']) for pair in pairs]
    if len(set(identities))!=len(identities):raise ValueError('duplicate original outcome scoring refused')
    report=dict(schema='earthship-provisional-thermal-performance/v1',artifact_sha256=artifact_sha256,graduated=False,by_horizon={})
    for horizon in (1,6,12,24):
        group=[pair for pair in pairs if pair['horizon_hours']==horizon];stats={}
        for key in ('model','persistence','recent_cycle'):
            errors=[pair['errors'][key] for pair in group if pair['errors'][key] is not None]
            stats[key]=dict(count=len(errors),mae_f=mean(abs(x) for x in errors) if errors else None,bias_f=mean(errors) if errors else None)
        report['by_horizon'][str(horizon)]=stats
    return report
