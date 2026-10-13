"""Source-bound native forecast errors; statistical summaries confer no authority."""
from copy import deepcopy
from datetime import timedelta
import math
from astro_geometry import _instant
from native_thermal_model import RULE
from native_thermal_forecast import validate_capture,publication,digest
from thermal_model.forcing_capture import _canonical
from thermal_model.graduation_policy import _sha
from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM,_receipt
from thermal_model.temperature_history import _validate_sensor_receipt
from thermal_model import provisional_score as arithmetic

SCHEMA='earthship-provisional-thermal-scored-pair/v2'
SOURCE='openhab/scripts/native_thermal_score.py'
BASE_FIELDS={'schema','artifact_sha256','runtime_sha256','capture_sha256','issued_at','target_at','assessed_at','horizon_hours',
             'outcome','predictions','errors','recent_cycle','graduated','automatic_actuation','pair_sha256'}
FIELDS=BASE_FIELDS|{'model_rule','geometry_series_sha256'}


def _recent(value):
    if not isinstance(value,dict) or value.get('status') not in ('available','insufficient_qualified_history','prediction_out_of_bounds','unavailable'):
        raise ValueError('explicit recent-cycle status required')
    prediction=value.get('prediction_f')
    if value['status']=='available':
        if type(prediction) not in (int,float) or not math.isfinite(prediction) or not -40<=prediction<=140:
            raise ValueError('physical qualified recent baseline required')
    elif prediction is not None:raise ValueError('unavailable recent baseline cannot predict')
    return prediction


def validate_delivery(capture,receipts):
    if not isinstance(receipts,dict) or set(receipts)!={NUMERIC_ITEM,PUBLICATION_ITEM}:
        raise ValueError('both original native persisted receipts required')
    published=_instant(capture['published_at']);clocks=[]
    for item,value in ((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,publication(capture))):
        original,at=_receipt(receipts[item],item)
        if _canonical(original)!=_canonical(value) or not published<=at<published+timedelta(seconds=90):
            raise ValueError('original native forecast delivery differs')
        clocks.append(at)
    if clocks[1]<clocks[0]:raise ValueError('native main receipt precedes numeric receipt')


def score(capture,receipts,outcome,*,runtime,expected_artifact_sha256,expected_capture_sha256,horizon_hours,assessed_at,recent,check_budget=lambda:None):
    capture,receipts,outcome,runtime,recent=map(deepcopy,(capture,receipts,outcome,runtime,recent))
    assessed=_instant(assessed_at)
    capture=validate_capture(capture,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,check_budget=check_budget)
    if SOURCE not in runtime['native_source_manifest']:
        raise ValueError('native score implementation must be runtime-bound')
    validate_delivery(capture,receipts);check_budget()
    issue=_instant(capture['issued_at'])
    if type(horizon_hours) is not int or horizon_hours not in (1,6,12,24) or horizon_hours>capture['output']['horizon_hours']:
        raise ValueError('supported native score horizon required')
    target=issue+timedelta(hours=horizon_hours)
    if assessed<target+timedelta(minutes=5):raise ValueError('mature native outcome required')
    _validate_sensor_receipt(outcome,target,sensor_epoch=capture['candidate']['fit']['sensor_epochs']['air'])
    actual=float(outcome['temperatureF']);model=capture['output']['trajectory'][horizon_hours-1]
    if _instant(model['at'])!=target:raise ValueError('original native score target differs')
    recent_f=_recent(recent)
    predictions=dict(model=model['air_f'],persistence=capture['output']['initial']['air_f'],recent_cycle=recent_f)
    pair=dict(schema=SCHEMA,model_rule=RULE,geometry_series_sha256=capture['geometry_series_sha256'],
        artifact_sha256=capture['candidate']['artifact_sha256'],runtime_sha256=capture['candidate']['runtime_sha256'],capture_sha256=capture['capture_sha256'],
        issued_at=issue.isoformat(),target_at=target.isoformat(),assessed_at=assessed.isoformat(),horizon_hours=horizon_hours,outcome=outcome,
        predictions=predictions,errors={key:None if value is None else value-actual for key,value in predictions.items()},recent_cycle=recent,
        graduated=False,automatic_actuation=False)
    pair['pair_sha256']=digest(pair,'pair_sha256');check_budget()
    return validate_pair(pair,expected_pair_sha256=pair['pair_sha256'])


def _statistical_view(pair):
    # Only reuse unchanged scalar error/summary checks. This does not replay a
    # legacy model, forecast, receipt or geometry, nor claim native source proof.
    view={key:deepcopy(pair[key]) for key in BASE_FIELDS};view['schema']=arithmetic.SCHEMA
    view['pair_sha256']=digest(view,'pair_sha256')
    return view


def validate_pair(pair,*,expected_pair_sha256):
    pair=deepcopy(pair)
    if (not isinstance(pair,dict) or set(pair)!=FIELDS or pair['schema']!=SCHEMA or pair['model_rule']!=RULE or
            pair['pair_sha256']!=_sha(expected_pair_sha256) or digest(pair,'pair_sha256')!=pair['pair_sha256']):
        raise ValueError('closed original native scored-pair identity required')
    for key in ('artifact_sha256','runtime_sha256','capture_sha256','geometry_series_sha256'):_sha(pair[key])
    issue,target,assessed=map(_instant,(pair['issued_at'],pair['target_at'],pair['assessed_at']))
    if issue.microsecond or issue.second not in (0,15) or issue.minute%5:
        raise ValueError('aligned native scored origin required')
    if _recent(pair['recent_cycle'])!=pair['predictions']['recent_cycle']:
        raise ValueError('original native recent-cycle prediction differs')
    arithmetic.validate_pair(_statistical_view(pair))
    return pair


def summarize(pairs,*,artifact_sha256=None):
    if not isinstance(pairs,list) or len(pairs)>256:raise ValueError('bounded native revision score window required')
    values=[validate_pair(pair,expected_pair_sha256=pair.get('pair_sha256')) for pair in pairs]
    revisions={pair['artifact_sha256'] for pair in values}
    if artifact_sha256 is None and len(revisions)>1:raise ValueError('mixed native model revisions refused')
    selected=next(iter(revisions),None) if artifact_sha256 is None else _sha(artifact_sha256)
    chosen=[pair for pair in values if pair['artifact_sha256']==selected]
    if len({pair['runtime_sha256'] for pair in chosen})>1:raise ValueError('native model runtime changed within score cohort')
    return arithmetic.summarize([_statistical_view(pair) for pair in chosen],artifact_sha256=selected)
