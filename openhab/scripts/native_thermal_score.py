"""Source-bound native forecast errors; statistical summaries confer no authority."""
from copy import deepcopy
from datetime import timedelta
import math
import json
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


def _qualified_outcome(value,target,*,sensor_epoch):
    if not isinstance(value,dict):raise ValueError('complete native outcome receipt required')
    try:
        for name in ('receivedAt','storedAt','validUntil'):_instant(value[name])
    except (KeyError,TypeError):raise ValueError('complete native outcome clocks required') from None
    _validate_sensor_receipt(value,target,sensor_epoch=sensor_epoch)


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


def _score(capture,receipts,outcome,*,runtime,expected_artifact_sha256,expected_capture_sha256,horizon_hours,assessed_at,recent,check_budget,capture_validator):
    capture,receipts,outcome,runtime,recent=map(deepcopy,(capture,receipts,outcome,runtime,recent))
    assessed=_instant(assessed_at)
    capture=capture_validator(capture,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,check_budget=check_budget)
    if SOURCE not in runtime['native_source_manifest']:
        raise ValueError('native score implementation must be runtime-bound')
    validate_delivery(capture,receipts);check_budget()
    issue=_instant(capture['issued_at'])
    if type(horizon_hours) is not int or horizon_hours not in (1,6,12,24) or horizon_hours>capture['output']['horizon_hours']:
        raise ValueError('supported native score horizon required')
    target=issue+timedelta(hours=horizon_hours)
    if assessed<target+timedelta(minutes=5):raise ValueError('mature native outcome required')
    _qualified_outcome(outcome,target,sensor_epoch=capture['candidate']['fit']['sensor_epochs']['air'])
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
    _qualified_outcome(pair['outcome'],target,sensor_epoch=pair['outcome'].get('sensorEpoch') if isinstance(pair['outcome'],dict) else None)
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


SOURCE_SCORE_SCHEMA='earthship-native-thermal-score-sources/v1'
QUERY_SCHEMA='earthship-native-thermal-score-query-binding/v1'
SOURCE_SCORE_FIELDS={'schema','artifact_sha256','capture_sha256','runtime_sha256','assessed_at','score_sources',
                     'query_binding','pair','release_authority','source_score_sha256'}
SOURCE_INPUT_FIELDS={'origin_path','receipts','horizon_hours','outcome','recent_cycle_grid'}
MAX_SOURCE_SCORE_BYTES=2*1024*1024
SOURCE_SCORE_SUFFIX='.native-thermal-score-sources-v1.json'


def _query_binding(packet,paths,*,issue,epoch,assessed,check_budget):
    from pathlib import Path
    from thermal_model.temperature_history import STREAMS,POLICY
    from weather_temperature_sources import read_compressed_temperature_source,replay_temperature_source,MAX_CONTAINER_BYTES
    from thermal_model.runtime_bundle import _owned_bytes
    if (not isinstance(paths,list) or not 1<=len(paths)<=64 or
            any(not isinstance(p,str) or not 1<=len(p)<=1024 for p in paths) or len(set(paths))!=len(paths)):
        raise ValueError('bounded unique original native score queries required')
    hours=packet['horizon_hours']
    if type(hours) is not int or hours not in (1,6,12,24):raise ValueError('supported native source horizon required')
    target=issue+timedelta(hours=hours)
    if assessed<target+timedelta(minutes=5):raise ValueError('mature original native query required')
    grid=packet['recent_cycle_grid']
    if not isinstance(grid,list) or len(grid)>64:raise ValueError('bounded original comparator grid required')
    expected={target:packet['outcome']}
    for row in grid:
        if not isinstance(row,(list,tuple)) or len(row)!=2:raise ValueError('original comparator row required')
        at=_instant(row[0])
        if at>=issue or at in expected:raise ValueError('unique historical native score target required')
        if row[1] is not None:_qualified_outcome(row[1],at,sensor_epoch=epoch)
        expected[at]=row[1]
    _qualified_outcome(packet['outcome'],target,sensor_epoch=epoch)
    stream,model,sensor=STREAMS['air'];selected={};size=0
    for name in paths:
        check_budget();path=Path(name)
        if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved native score query required')
        original_bytes=_owned_bytes(path,MAX_CONTAINER_BYTES)
        source=read_compressed_temperature_source(path.parent,path);size+=len(_canonical(source))
        if _owned_bytes(path,MAX_CONTAINER_BYTES)!=original_bytes:raise ValueError('native score query changed during selection')
        if size>64000000:raise ValueError('bounded aggregate native score source bytes required')
        if source['stream']!=stream or source['policy']!=dict(model=model,sensor_id=sensor,**POLICY) or source['sensor_epoch']!=epoch:
            raise ValueError('original native score role/policy/phase differs')
        observed=_instant(source['assessed_at']);_instant(source['history_start'])
        for at in source['targets']:_instant(at)
        for at,raw in source['native_rows']:
            _instant(at)
            # The legacy selector parses embedded clocks. Inspect original bytes
            # first so accepted receipts cannot silently lose their precision.
            if raw is None:continue
            try:
                from thermal_model.origin_capture import _object
                envelope=json.loads(raw,object_pairs_hook=_object)
            except (ValueError,TypeError):continue  # preserve malformed barriers
            records=envelope.get('records') if isinstance(envelope,dict) else None
            receipt=records.get(stream) if isinstance(records,dict) else None
            if isinstance(receipt,dict) and receipt.get('status')=='valid':
                for field in ('recordedAt','receivedAt','validUntil'):
                    if receipt.get(field) is not None:_instant(receipt[field])
        values=replay_temperature_source(source)
        if observed>assessed:raise ValueError('native score query assessment is future')
        if all(_instant(at)<issue for at,_ in values):
            if observed!=issue:raise ValueError('native comparator query revised the issue clock')
        elif len(values)!=1 or _instant(values[0][0])!=target or observed<target+timedelta(minutes=5):
            raise ValueError('native outcome query target or maturity differs')
        for at,receipt in values:
            at=_instant(at)
            if at in selected and _canonical(selected[at])!=_canonical(receipt):raise ValueError('conflicting native query selections')
            selected[at]=receipt
    if set(selected)!=set(expected) or any(_canonical(selected[at])!=_canonical(expected[at]) for at in expected):
        raise ValueError('cached native score receipts differ from original queries')
    return dict(schema=QUERY_SCHEMA,score_sources_sha256=digest(packet,None),issue_at=issue.isoformat(),sensor_epoch=epoch,
                assessed_at=assessed.isoformat(),query_sources=list(paths),release_authority=False)


def _source_pair(packet,paths,*,runtime,expected_artifact_sha256,expected_capture_sha256,assessed,check_budget,pair_builder):
    from pathlib import Path
    from native_thermal_artifact import _read
    from native_thermal_forecast import MAX_CAPTURE_BYTES
    from thermal_model.runtime_bundle import _owned_bytes
    from weather_temperature_sources import MAX_CONTAINER_BYTES
    from thermal_model.recent_cycles import compare_v2
    if not isinstance(packet,dict) or set(packet)!=SOURCE_INPUT_FIELDS:raise ValueError('closed native source score inputs required')
    raw,capture=_read(Path(packet['origin_path']),MAX_CAPTURE_BYTES)
    origin_queries={Path(name):_owned_bytes(Path(name),MAX_CONTAINER_BYTES) for name in capture['native_origin_binding'].get('query_sources',{}).values()}
    issue=_instant(capture['issued_at']);epoch=capture['candidate']['fit']['sensor_epochs']['air']
    binding=_query_binding(packet,paths,issue=issue,epoch=epoch,assessed=assessed,check_budget=check_budget)
    selected={_instant(at):None if receipt is None else {key:_instant(value) if key in ('receivedAt','storedAt','validUntil') else value for key,value in receipt.items()} for at,receipt in packet['recent_cycle_grid']}
    def reader(targets,at):
        if at!=issue or any(t not in selected for t in targets):raise ValueError('missing original native comparator query coverage')
        return [(t,selected[t]) for t in targets]
    recent=compare_v2(issue=issue,target=issue+timedelta(hours=packet['horizon_hours']),current_f=capture['output']['initial']['air_f'],
                      grid_reader=reader,sensor_epoch=epoch)
    pair=pair_builder(capture,packet['receipts'],packet['outcome'],runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
               expected_capture_sha256=expected_capture_sha256,horizon_hours=packet['horizon_hours'],assessed_at=assessed,
               recent=recent,check_budget=check_budget)
    replay=_query_binding(packet,paths,issue=issue,epoch=epoch,assessed=assessed,check_budget=check_budget)
    if (any(_owned_bytes(path,MAX_CONTAINER_BYTES)!=original for path,original in origin_queries.items()) or
            _canonical(replay)!=_canonical(binding) or _read(Path(packet['origin_path']),MAX_CAPTURE_BYTES)[0]!=raw):
        raise ValueError('original native score sources changed during replay')
    return binding,pair


def _build_source_score(*,capture_path,receipts,outcome,recent_cycle_grid,source_paths,horizon_hours,assessed_at,
                       runtime,expected_artifact_sha256,expected_capture_sha256,check_budget,pair_builder):
    packet=deepcopy(dict(origin_path=capture_path,receipts=receipts,horizon_hours=horizon_hours,outcome=outcome,recent_cycle_grid=recent_cycle_grid))
    runtime,paths=map(deepcopy,(runtime,source_paths));assessed=_instant(assessed_at)
    binding,pair=_source_pair(packet,paths,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,assessed=assessed,check_budget=check_budget,pair_builder=pair_builder)
    record=dict(schema=SOURCE_SCORE_SCHEMA,artifact_sha256=pair['artifact_sha256'],capture_sha256=pair['capture_sha256'],
        runtime_sha256=pair['runtime_sha256'],assessed_at=assessed.isoformat(),score_sources=packet,query_binding=binding,pair=pair,release_authority=False)
    record['source_score_sha256']=digest(record,'source_score_sha256')
    if len(_canonical(record))>MAX_SOURCE_SCORE_BYTES:raise ValueError('bounded native source score record required')
    return record


def _validate_source_score(record,*,runtime,expected_artifact_sha256,expected_capture_sha256,expected_source_score_sha256,check_budget,source_builder):
    record,runtime=map(deepcopy,(record,runtime))
    if (not isinstance(record,dict) or set(record)!=SOURCE_SCORE_FIELDS or record['schema']!=SOURCE_SCORE_SCHEMA or
            record['release_authority'] is not False or record['source_score_sha256']!=_sha(expected_source_score_sha256) or
            digest(record,'source_score_sha256')!=record['source_score_sha256'] or len(_canonical(record))>MAX_SOURCE_SCORE_BYTES):
        raise ValueError('closed externally pinned native source score required')
    if record['artifact_sha256']!=_sha(expected_artifact_sha256) or record['capture_sha256']!=_sha(expected_capture_sha256):
        raise ValueError('original native source score identities differ')
    if not isinstance(record['score_sources'],dict) or set(record['score_sources'])!=SOURCE_INPUT_FIELDS:
        raise ValueError('closed original native score inputs required')
    binding=record['query_binding']
    if not isinstance(binding,dict):raise ValueError('original native query binding required')
    rebuilt=source_builder(capture_path=record['score_sources']['origin_path'],receipts=record['score_sources']['receipts'],
        outcome=record['score_sources']['outcome'],recent_cycle_grid=record['score_sources']['recent_cycle_grid'],
        source_paths=binding.get('query_sources'),horizon_hours=record['score_sources']['horizon_hours'],assessed_at=_instant(record['assessed_at']),
        runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,expected_capture_sha256=expected_capture_sha256,check_budget=check_budget)
    if _canonical(rebuilt)!=_canonical(record):raise ValueError('original native source score differs on replay')
    return record


def persist_source_score(directory,record):
    from thermal_model.provisional_forecast import persist
    if not isinstance(record,dict) or digest(record,'source_score_sha256')!=record.get('source_score_sha256'):
        raise ValueError('digest-bound native source score required')
    return persist(directory,record,field='source_score_sha256',suffix=SOURCE_SCORE_SUFFIX,maximum=MAX_SOURCE_SCORE_BYTES)


def read_source_score(path,*,runtime,expected_artifact_sha256,expected_capture_sha256,expected_source_score_sha256,check_budget=lambda:None):
    from pathlib import Path
    from native_thermal_artifact import _read
    path=Path(path)
    if path.name!=_sha(expected_source_score_sha256)+SOURCE_SCORE_SUFFIX:raise ValueError('named original native source score required')
    _,record=_read(path,MAX_SOURCE_SCORE_BYTES)
    return validate_source_score(record,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,expected_source_score_sha256=expected_source_score_sha256,check_budget=check_budget)


COMPLETION_SCHEMA='earthship-native-thermal-completion/v1'
COMPLETION_SUFFIX='.native-thermal-completion-v1.json'
COMPLETION_FIELDS={'schema','job_id','artifact_sha256','runtime_sha256','capture_sha256','source_score_path',
                   'source_score_sha256','pair_sha256','issued_at','target_at','horizon_hours','completed_at','release_authority','completion_sha256'}
REPORT_ENTRY_FIELDS={'completion_path','completion_sha256','source_score_sha256','capture_sha256'}
MAX_COMPLETION_BYTES=65536


def _build_source_completion(source_score_path,*,runtime,expected_artifact_sha256,expected_capture_sha256,
                            expected_source_score_sha256,completed_at,check_budget,source_reader):
    from pathlib import Path
    runtime=deepcopy(runtime);completed=_instant(completed_at);path=str(Path(source_score_path))
    record=source_reader(path,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,expected_source_score_sha256=expected_source_score_sha256,check_budget=check_budget)
    if completed<_instant(record['assessed_at']):raise ValueError('native score completion precedes assessment')
    pair=record['pair'];job=digest({'capture_sha256':pair['capture_sha256'],'horizon_hours':pair['horizon_hours']},None)
    result=dict(schema=COMPLETION_SCHEMA,job_id=job,artifact_sha256=pair['artifact_sha256'],runtime_sha256=pair['runtime_sha256'],
        capture_sha256=pair['capture_sha256'],source_score_path=path,source_score_sha256=record['source_score_sha256'],
        pair_sha256=pair['pair_sha256'],issued_at=pair['issued_at'],target_at=pair['target_at'],horizon_hours=pair['horizon_hours'],
        completed_at=completed.isoformat(),release_authority=False)
    result['completion_sha256']=digest(result,'completion_sha256');check_budget()
    return result


def _validate_source_completion(completion,*,runtime,expected_artifact_sha256,expected_capture_sha256,
                               expected_source_score_sha256,expected_completion_sha256,check_budget,completion_builder):
    completion,runtime=map(deepcopy,(completion,runtime))
    if (not isinstance(completion,dict) or set(completion)!=COMPLETION_FIELDS or completion['schema']!=COMPLETION_SCHEMA or
            completion['release_authority'] is not False or completion['completion_sha256']!=_sha(expected_completion_sha256) or
            digest(completion,'completion_sha256')!=completion['completion_sha256']):
        raise ValueError('closed externally pinned native completion required')
    for key,expected in (('artifact_sha256',expected_artifact_sha256),('capture_sha256',expected_capture_sha256),
                         ('source_score_sha256',expected_source_score_sha256)):
        if completion[key]!=_sha(expected):raise ValueError('original native completion identity differs')
    result=completion_builder(completion['source_score_path'],runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,expected_source_score_sha256=expected_source_score_sha256,
        completed_at=_instant(completion['completed_at']),check_budget=check_budget)
    if _canonical(result)!=_canonical(completion):raise ValueError('original native completion differs on replay')
    return completion


def persist_source_completion(directory,completion):
    from thermal_model.provisional_forecast import persist
    if not isinstance(completion,dict) or digest(completion,'completion_sha256')!=completion.get('completion_sha256'):
        raise ValueError('digest-bound native completion required')
    return persist(directory,completion,field='completion_sha256',suffix=COMPLETION_SUFFIX,maximum=MAX_COMPLETION_BYTES)


def read_source_completion(path,*,runtime,expected_artifact_sha256,expected_capture_sha256,
                           expected_source_score_sha256,expected_completion_sha256,check_budget=lambda:None):
    from pathlib import Path
    from native_thermal_artifact import _read
    path=Path(path)
    if path.name!=_sha(expected_completion_sha256)+COMPLETION_SUFFIX:raise ValueError('named original native completion required')
    _,completion=_read(path,MAX_COMPLETION_BYTES)
    return validate_source_completion(completion,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,expected_source_score_sha256=expected_source_score_sha256,
        expected_completion_sha256=expected_completion_sha256,check_budget=check_budget)


def _reconcile_source_report(entries,*,runtime,artifact_sha256,assessed_at,check_budget,completion_reader=None,source_reader=None):
    from native_thermal_artifact import validate_native_runtime
    if completion_reader is None:completion_reader=read_source_completion
    if source_reader is None:source_reader=read_source_score
    if not isinstance(entries,list) or len(entries)>256:raise ValueError('bounded native completion report inventory required')
    entries,runtime=map(deepcopy,(entries,runtime));runtime=validate_native_runtime(runtime)
    if SOURCE not in runtime['native_source_manifest']:raise ValueError('native report implementation must be runtime-bound')
    artifact=_sha(artifact_sha256);assessed=_instant(assessed_at);pairs=[];jobs=set();check_budget()
    for entry in entries:
        if not isinstance(entry,dict) or set(entry)!=REPORT_ENTRY_FIELDS:raise ValueError('externally pinned native report entry required')
        completion=completion_reader(entry['completion_path'],runtime=runtime,expected_artifact_sha256=artifact,
            expected_capture_sha256=entry['capture_sha256'],expected_source_score_sha256=entry['source_score_sha256'],
            expected_completion_sha256=entry['completion_sha256'],check_budget=check_budget)
        if _instant(completion['completed_at'])>assessed:raise ValueError('native report completion is future')
        if completion['job_id'] in jobs:raise ValueError('duplicate native completed score job')
        jobs.add(completion['job_id'])
        source=source_reader(completion['source_score_path'],runtime=runtime,expected_artifact_sha256=artifact,
            expected_capture_sha256=entry['capture_sha256'],expected_source_score_sha256=entry['source_score_sha256'],check_budget=check_budget)
        if source['pair']['pair_sha256']!=completion['pair_sha256']:raise ValueError('native completed pair differs')
        pairs.append(source['pair']);check_budget()
    result=summarize(pairs,artifact_sha256=artifact);result['assessed_at']=assessed.isoformat();check_budget()
    return result


def reconcile_source_report(entries,*,runtime,artifact_sha256,assessed_at,check_budget=lambda:None):
    from thermal_model.replay_budget import capture_source_reads
    with capture_source_reads() as originals:
        result=_reconcile_source_report(entries,runtime=runtime,artifact_sha256=artifact_sha256,
            assessed_at=assessed_at,check_budget=check_budget)
        check_budget()
        if originals.file_count:originals.verify()
        check_budget()
        return result


SERVING_RECEIPT_SOURCE_SHA256='11121a94a4501c7af520b9df54ec879a3c75edadc87a0d15afd279bf83bbf58e'



def score(capture,receipts,outcome,*,runtime,expected_artifact_sha256,expected_capture_sha256,horizon_hours,assessed_at,recent,check_budget=lambda:None):
    return _score(capture,receipts,outcome,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,horizon_hours=horizon_hours,assessed_at=assessed_at,
        recent=recent,check_budget=check_budget,capture_validator=validate_capture)


def build_source_score(*,capture_path,receipts,outcome,recent_cycle_grid,source_paths,horizon_hours,assessed_at,
                       runtime,expected_artifact_sha256,expected_capture_sha256,check_budget=lambda:None):
    return _build_source_score(capture_path=capture_path,receipts=receipts,outcome=outcome,recent_cycle_grid=recent_cycle_grid,
        source_paths=source_paths,horizon_hours=horizon_hours,assessed_at=assessed_at,runtime=runtime,
        expected_artifact_sha256=expected_artifact_sha256,expected_capture_sha256=expected_capture_sha256,
        check_budget=check_budget,pair_builder=score)


def validate_source_score(record,*,runtime,expected_artifact_sha256,expected_capture_sha256,expected_source_score_sha256,check_budget=lambda:None):
    return _validate_source_score(record,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,expected_source_score_sha256=expected_source_score_sha256,
        check_budget=check_budget,source_builder=build_source_score)


def build_source_completion(source_score_path,*,runtime,expected_artifact_sha256,expected_capture_sha256,
                            expected_source_score_sha256,completed_at,check_budget=lambda:None):
    return _build_source_completion(source_score_path,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,expected_source_score_sha256=expected_source_score_sha256,
        completed_at=completed_at,check_budget=check_budget,source_reader=read_source_score)


def validate_source_completion(completion,*,runtime,expected_artifact_sha256,expected_capture_sha256,
                               expected_source_score_sha256,expected_completion_sha256,check_budget=lambda:None):
    return _validate_source_completion(completion,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,expected_source_score_sha256=expected_source_score_sha256,
        expected_completion_sha256=expected_completion_sha256,check_budget=check_budget,completion_builder=build_source_completion)


def _model_pins(model,*,assessed_at,check_budget):
    from native_model_serving_receipt import _require_model
    _require_model(model);model.verify_bindings(assessed_at=_instant(assessed_at),guard=check_budget)
    return dict(runtime=model.runtime,expected_artifact_sha256=model.candidate['artifact_sha256'])


def _serving_callback(model,function):
    def selected(*args,runtime,expected_artifact_sha256,**kwargs):
        from native_model_serving_receipt import _require_model
        _require_model(model)
        if _canonical(runtime)!=_canonical(model.runtime) or expected_artifact_sha256!=model.candidate['artifact_sha256']:
            raise ValueError('historical serving score selection differs')
        return function(*args,model=model,**kwargs)
    return selected


def score_serving(capture,model,receipts,outcome,*,expected_capture_sha256,horizon_hours,assessed_at,recent,check_budget=lambda:None):
    from native_thermal_forecast import validate_serving_capture
    capture,receipts,outcome,recent=map(deepcopy,(capture,receipts,outcome,recent))
    pins=_model_pins(model,assessed_at=assessed_at,check_budget=check_budget)
    def validator(value,*,runtime,expected_artifact_sha256,**kwargs):
        return validate_serving_capture(value,model,**kwargs)
    result=_score(capture,receipts,outcome,**pins,expected_capture_sha256=expected_capture_sha256,
        horizon_hours=horizon_hours,assessed_at=assessed_at,recent=recent,check_budget=check_budget,capture_validator=validator)
    model.verify_bindings(assessed_at=_instant(assessed_at),guard=check_budget)
    return result


def build_serving_source_score(*,model,capture_path,receipts,outcome,recent_cycle_grid,source_paths,horizon_hours,assessed_at,
                               expected_capture_sha256,check_budget=lambda:None):
    receipts,outcome,recent_cycle_grid,source_paths=map(deepcopy,(receipts,outcome,recent_cycle_grid,source_paths))
    pins=_model_pins(model,assessed_at=assessed_at,check_budget=check_budget)
    # Adapt the public positional model interface to the shared source core.
    def pair(capture,receipts,outcome,*,runtime,expected_artifact_sha256,**kwargs):
        return score_serving(capture,model,receipts,outcome,**kwargs)
    result=_build_source_score(capture_path=capture_path,receipts=receipts,outcome=outcome,recent_cycle_grid=recent_cycle_grid,
        source_paths=source_paths,horizon_hours=horizon_hours,assessed_at=assessed_at,**pins,
        expected_capture_sha256=expected_capture_sha256,check_budget=check_budget,pair_builder=pair)
    model.verify_bindings(assessed_at=_instant(assessed_at),guard=check_budget)
    return result


def validate_serving_source_score(record,*,model,expected_capture_sha256,expected_source_score_sha256,check_budget=lambda:None):
    record=deepcopy(record)
    if not isinstance(record,dict):raise ValueError('original native source score required')
    pins=_model_pins(model,assessed_at=record.get('assessed_at'),check_budget=check_budget)
    return _validate_source_score(record,**pins,expected_capture_sha256=expected_capture_sha256,
        expected_source_score_sha256=expected_source_score_sha256,check_budget=check_budget,
        source_builder=_serving_callback(model,build_serving_source_score))


def read_serving_source_score(path,*,model,expected_capture_sha256,expected_source_score_sha256,check_budget=lambda:None):
    from pathlib import Path
    from native_thermal_artifact import _read
    path=Path(path)
    if path.name!=_sha(expected_source_score_sha256)+SOURCE_SCORE_SUFFIX:raise ValueError('named original native source score required')
    raw,record=_read(path,MAX_SOURCE_SCORE_BYTES)
    result=validate_serving_source_score(record,model=model,expected_capture_sha256=expected_capture_sha256,
        expected_source_score_sha256=expected_source_score_sha256,check_budget=check_budget)
    if _read(path,MAX_SOURCE_SCORE_BYTES)[0]!=raw:raise ValueError('original native source score changed during readback')
    return result


def build_serving_source_completion(source_score_path,*,model,expected_capture_sha256,expected_source_score_sha256,completed_at,check_budget=lambda:None):
    pins=_model_pins(model,assessed_at=completed_at,check_budget=check_budget)
    result=_build_source_completion(source_score_path,**pins,expected_capture_sha256=expected_capture_sha256,
        expected_source_score_sha256=expected_source_score_sha256,completed_at=completed_at,check_budget=check_budget,
        source_reader=_serving_callback(model,read_serving_source_score))
    model.verify_bindings(assessed_at=_instant(completed_at),guard=check_budget)
    return result


def validate_serving_source_completion(completion,*,model,expected_capture_sha256,expected_completion_sha256,check_budget=lambda:None):
    completion=deepcopy(completion)
    if not isinstance(completion,dict):raise ValueError('original native completion required')
    pins=_model_pins(model,assessed_at=completion.get('completed_at'),check_budget=check_budget)
    return _validate_source_completion(completion,**pins,expected_capture_sha256=expected_capture_sha256,
        expected_source_score_sha256=completion.get('source_score_sha256'),expected_completion_sha256=expected_completion_sha256,
        check_budget=check_budget,completion_builder=_serving_callback(model,build_serving_source_completion))


def read_serving_source_completion(path,*,model,expected_capture_sha256,expected_source_score_sha256,expected_completion_sha256,check_budget=lambda:None):
    from pathlib import Path
    from native_thermal_artifact import _read
    path=Path(path)
    if path.name!=_sha(expected_completion_sha256)+COMPLETION_SUFFIX:raise ValueError('named original native completion required')
    raw,value=_read(path,MAX_COMPLETION_BYTES)
    if not isinstance(value,dict) or value.get('source_score_sha256')!=_sha(expected_source_score_sha256):
        raise ValueError('original native completed score differs')
    result=validate_serving_source_completion(value,model=model,expected_capture_sha256=expected_capture_sha256,
        expected_completion_sha256=expected_completion_sha256,check_budget=check_budget)
    if _read(path,MAX_COMPLETION_BYTES)[0]!=raw:raise ValueError('original native completion changed during readback')
    return result


def reconcile_serving_source_report(entries,*,selections,artifact_sha256,assessed_at,check_budget=lambda:None):
    from native_model_serving_receipt import read_serving_model
    from thermal_model.replay_budget import capture_source_reads
    entries=deepcopy(entries);assessed=_instant(assessed_at);artifact=_sha(artifact_sha256)
    if type(selections) is not tuple or not 1<=len(selections)<=32:raise ValueError('explicit retained serving selections required')
    with capture_source_reads() as originals:
        models=[read_serving_model(selection,assessed_at=assessed,guard=check_budget) for selection in selections]
        identities=[(m.candidate['artifact_sha256'],m.candidate['runtime_sha256']) for m in models]
        if len(set(identities))!=len(identities):raise ValueError('unique retained serving model selections required')
        selected=[m for m in models if m.candidate['artifact_sha256']==artifact]
        if len(selected)!=1:raise ValueError('retained report model selection unavailable')
        model=selected[0]
        result=_reconcile_source_report(entries,runtime=model.runtime,artifact_sha256=artifact,assessed_at=assessed,
            check_budget=check_budget,completion_reader=_serving_callback(model,read_serving_source_completion),
            source_reader=_serving_callback(model,read_serving_source_score))
        for value in models:value.verify_bindings(assessed_at=assessed,guard=check_budget)
        check_budget()
        if originals.file_count:originals.verify()
        check_budget();return result
