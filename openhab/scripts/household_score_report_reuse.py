"""Avoid one duplicate full replay inside the known original serving report.

The original report still owns model selection, completion validation, duplicate
job checks, arithmetic, and final verification of every observed original file.
No value survives a report invocation; unknown implementations run unchanged.
"""
from copy import deepcopy
from functools import wraps
from hashlib import sha256
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar

SUPPORTED_SOURCE_SHA256='60cd7a67a914ef8d996390f60e9be398475f9a1ef08c5da011d7d279a0db0608'
PRIOR_SOURCE_SHA256='2e4abc7c8f655bcc5f7ff839b9750816f56f08b02bd516e10c8b8c2c6aaa6dab'
INSTALLED_SOURCE_SHA256='40199b757ec35cd80c1aa8eb857fd1e272c0242f13122b30e76d9b2e9c92b9f6'
SUPPORTED_MODEL_HELPER_SHA256='11121a94a4501c7af520b9df54ec879a3c75edadc87a0d15afd279bf83bbf58e'
PRIOR_MODEL_HELPER_SHA256='94d85e37afc79e08cf9de93ba937b2ba845acc7111c0a23e483b186d8ff9a57e'
_model_frame=ContextVar('household_report_model_bindings',default=None)
_temperature_frame=ContextVar('household_report_temperature_replay',default=None)
TEMPERATURE_SOURCE_SHA256={
    'weather_temperature_reader':'efefeebcaf201dd4d85fe01f8fb17e509324ed913de8e996ee76fcbe911b262f',
    'weather_temperature_sources':'c7c53d55cdeb8a4090ea7469bf3d4c6015a88235f7056aa9866f132c81cf493d',
    'weather_temperature_evidence':'0cb88f92fd43ad64ee20880a5b381418afafeb263e80025b2bbf47db09ce6dc2',
    'thermal_model.installed_shade_raw_score_sources':'c92d9fc1f95c54993a91b886d9f92d83b9f90ecf72248004c14c3feedeee680f',
}
MAX_TEMPERATURE_CACHE_ENTRIES=16384
MAX_TEMPERATURE_CACHE_BYTES=8*1024*1024
MAX_SNAPSHOT_CACHE_BYTES=16*1024*1024
CAPTURE_SOURCE_SHA256='de0d87c20c11ff15f27c6474cc558c76532c628fc6cf3aa8e981deb0aaaa0d99'
MAX_CAPTURE_CACHE_BYTES=1024*1024
MAX_CAPTURE_CACHE_ENTRIES=64
MAX_CAPTURE_DEPENDENCIES=4096
_capture_frame=ContextVar('household_report_capture_validation',default=None)
CAPTURE_WEATHER_RUNTIME={
    'production_thermal_source.py':'556163c8de6e6dd7f5378cd2d972ca676c1417fccd1aa375a2b570a3f84e3d91',
    'household/production_weather_conditioning.py':'12d34105ad6d113bb082f1df12eb2dba6563c35d68ebe55abef39aca44c15a5a',
    'thermal_weather_source.py':'34de6ea1385f65d97139c8d134ddf6cc710d65fb36dd7403b8be4a8349ac0478',
    'household/thermal_weather_conditioning.py':'59b79c74f439cf7c818a397000cb27892c53e11d1bbd9f917d4f2360dd55de29',
    'household/codec.py':'f2abc69ca6d1905fe03eb7ff3102fccc3d9616b42ba2f87a92827541b3155204',
    'household/control_contracts.py':'28221f71b58d18dd7078d8e16456743644cf83acd14b4c25fed953384727a308',
    'weather_learning/production_emissions.py':'94dc9a9b92ddb27c498af9e27991b387f94f787dfa1a7d10808b2a0a8e8781f7',
    'weather_learning/production_forecast.py':'8073e91b582e3c57467a7665c4376013cc31fa9cefdd27ff8b435aacbf9f7177',
    'weather_learning/production_scoring.py':'c6c7f56e3dd4112d22a5bc9bfe7dd611e1ca72328bf0a84e7c49e9e3350f8559',
    'weather_learning/contracts.py':'da661a56a4d0d3d012d643d007538c54ccb2ce0511ff5f6a29ec32392eb71543',
    'weather_learning/provider.py':'7775f285fff7f86ff0d697ec048e9dcbd6349daf51bb4a02f9ff8c248554a40f',
    'weather_source_files.py':'e49f3785d3304df77cb8df8bee78a1372151de299d27d388b9cda473c7eac0af',
}


def _json_key(value):
    """Canonical full JSON inputs; custom/tuple values use original validation."""
    import json
    def plain(v):
        if type(v) in (str,int,float,bool,type(None)):return True
        if type(v) is list:return all(plain(item) for item in v)
        if type(v) is dict:return all(type(k) is str and plain(x) for k,x in v.items())
        return False
    if not plain(value):raise TypeError('uncacheable input')
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


@contextmanager
def _capture_reads(guard):
    """One captured numerical replay per exact capture/model in a report.

    Source-score replay still reads each original capture and raw query on
    every call. This only reuses the captured validation after an original full
    success in the SAME observed inventory; the unchanged report streams and
    verifies that entire inventory, and every selected model, before returning.
    Keep only validation metadata, not full captured values: the pinned original
    returns a copy of exactly its input, so a hit copies that fully keyed input.
    """
    from collections import OrderedDict
    import sys
    import native_thermal_forecast as forecasts
    import native_model_serving_receipt as serving
    from thermal_model.origin_capture import _source_bytes
    from thermal_model.runtime_bundle import _owned_bytes
    from thermal_model.replay_budget import _source_reads,OriginalSourceInventory
    original=forecasts.validate_serving_capture;path=Path(forecasts.__file__).absolute()
    frame=object();token=_capture_frame.set(frame);hooked=False;cache=OrderedDict();size=0;identities={}
    try:
        guard();raw=_source_bytes(path,maximum=262144);info=path.lstat()
        identity=(info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink)
        model_helper=Path(serving.__file__).absolute()
        model_raw=_source_bytes(model_helper,maximum=262144)
        model_info=model_helper.lstat()
        model_identity=(model_info.st_dev,model_info.st_ino,model_info.st_mode,model_info.st_uid,model_info.st_gid,model_info.st_nlink)
        if (sha256(raw).hexdigest()!=CAPTURE_SOURCE_SHA256 or
                sha256(model_raw).hexdigest() not in (SUPPORTED_MODEL_HELPER_SHA256,PRIOR_MODEL_HELPER_SHA256) or
                Path(original.__code__.co_filename).absolute()!=path):
            yield;return
        def retained_size(value):
            seen=set()
            def count(v):
                if id(v) in seen:return 0
                seen.add(id(v));total=sys.getsizeof(v)
                if isinstance(v,dict):return total+sum(count(k)+count(x) for k,x in v.items())
                if isinstance(v,(list,tuple)):return total+sum(map(count,v))
                return total
            return count(value)
        def dependencies(value):
            context=value.get('weather_conditioning')
            if context is None:return []
            if (type(context) is not dict or context.get('schema')!='earthship-thermal-weather-context/v2' or
                    context.get('runtime_manifest')!=CAPTURE_WEATHER_RUNTIME or 'originals' not in context):return None
            return context['originals']
        def identity_of(selected):
            info=selected.lstat()
            return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,
                info.st_mode,info.st_uid,info.st_gid,info.st_nlink)
        def remember(selected):
            actual=identity_of(selected);previous=identities.get(selected)
            if previous is not None and actual!=previous:raise ValueError('captured dependency identity changed')
            if previous is None:
                if len(identities)>=MAX_CAPTURE_DEPENDENCIES:raise ValueError('bounded captured dependency inventory required')
                identities[selected]=actual
        def observe_dependencies(value,refs,check):
            # Weather's original streaming reader does not add its reads to
            # the numerical report inventory. Explicitly bind ALL its original
            # files and runtime sources before retaining a validation hit.
            for ref in refs:
                selected=Path(ref['path']);check();remember(selected);body=_owned_bytes(selected,ref['maximum']);remember(selected)
                if sha256(body).hexdigest()!=ref['sha256']:raise ValueError('captured weather original changed')
            if value.get('weather_conditioning') is not None:
                for name,pin in CAPTURE_WEATHER_RUNTIME.items():
                    selected=path.parent/name;check();remember(selected);body=_source_bytes(selected,maximum=262144);remember(selected)
                    if sha256(body).hexdigest()!=pin:raise ValueError('captured weather runtime changed')
            for name in value['native_origin_binding']['query_sources'].values():
                from weather_temperature_sources import MAX_CONTAINER_BYTES
                selected=Path(name);check();remember(selected);_owned_bytes(selected,MAX_CONTAINER_BYTES);remember(selected)
        def read(value,model,*,expected_capture_sha256,check_budget=lambda:None):
            nonlocal size
            def full():return original(value,model,expected_capture_sha256=expected_capture_sha256,check_budget=check_budget)
            inventory=_source_reads.get()
            if (_capture_frame.get() is not frame or type(inventory) is not OriginalSourceInventory or
                    type(model) is not serving.ServingModel or getattr(model,'_seal',None) is not serving._SEAL or
                    type(expected_capture_sha256) is not str):return full()
            value=deepcopy(value)
            check_budget();guard()
            refs=dependencies(value) if type(value) is dict else None
            if refs is None:return full()
            try:key=(inventory,sha256(_json_key(value)).digest(),sha256(model._encoded).digest(),
                    sha256(model._selection._encoded).digest(),expected_capture_sha256)
            except (ValueError,TypeError,RecursionError,OverflowError):return full()
            if key in cache:
                _,weight=cache.pop(key);cache[key]=(True,weight)
                # Preserve the original serving candidate's issue-time model
                # admission/chronology check even when numerical work is reused.
                model.verify_bindings(assessed_at=value['issued_at'],guard=check_budget)
                observe_dependencies(value,refs,check_budget)
                result=deepcopy(value);check_budget();guard();return result
            result=full();check_budget();guard()
            observe_dependencies(result,dependencies(result),check_budget)
            weight=retained_size(key[1:])+512
            if weight<=MAX_CAPTURE_CACHE_BYTES:
                while cache and (len(cache)>=MAX_CAPTURE_CACHE_ENTRIES or size+weight>MAX_CAPTURE_CACHE_BYTES):
                    _,(_,removed)=cache.popitem(last=False);size-=removed
                if MAX_CAPTURE_CACHE_ENTRIES>0:cache[key]=(True,weight);size+=weight
            return result
        forecasts.validate_serving_capture=read;hooked=True
        yield
        for selected,expected in identities.items():
            guard()
            if identity_of(selected)!=expected:raise ValueError('captured dependency identity changed before return')
        for selected,expected,metadata in ((path,raw,identity),(model_helper,model_raw,model_identity)):
            guard();current=_source_bytes(selected,maximum=262144);info=selected.lstat()
            if current!=expected or (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink)!=metadata:
                raise ValueError('capture replay helper changed during report')
        guard()
    finally:
        if hooked:forecasts.validate_serving_capture=original
        cache.clear();identities.clear();_capture_frame.reset(token)


@contextmanager
def _temperature_reads(guard):
    """Reuse pure work, never the original on-disk reads or final inventory.

    Keys fingerprint complete inputs with SHA256, never paths/mtime/scalars.
    Snapshot/query LRUs are limited to 16/8MiB of accounted keys/results and
    16384 entries each; oversized values run normally.
    A private execution frame prevents nested/foreign contexts borrowing hits.
    Original validation exceptions are never cached. All hooks restore even on
    cancellation, pressure refusal or final verification failure.
    """
    from collections import OrderedDict
    from datetime import datetime
    import weather_temperature_reader as reader
    import weather_temperature_sources as sources
    import weather_temperature_evidence as evidence
    import thermal_model.installed_shade_raw_score_sources as raw_sources
    from thermal_model.origin_capture import _source_bytes
    from thermal_model.replay_budget import check_shared_budget
    frame=object();token=_temperature_frame.set(frame)
    snapshot=reader._snapshot;query=sources.replay_temperature_source
    hooked=False;caches=[OrderedDict(),OrderedDict()];sizes=[0,0];originals=[];alias=raw_sources.replay_temperature_source
    try:
        guard()
        for module in (reader,sources,evidence,raw_sources):
            path=Path(module.__file__).absolute()
            raw=_source_bytes(path,maximum=262144)
            if sha256(raw).hexdigest()!=TEMPERATURE_SOURCE_SHA256.get(module.__name__):
                yield;return
            info=path.lstat()
            originals.append((path,raw,(info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink)))
        if any(Path(fn.__code__.co_filename).absolute()!=Path(module.__file__).absolute()
                for fn,module in ((snapshot,reader),(query,sources))):
            # Reentry must start from original functions, not a parent's cache.
            yield;return
        def copy_result(index,value):
            # The pinned reader returns only datetime/scalar metadata. Copy
            # its mutable dict/list containers; immutable datetime values need
            # no recursive reconstruction on every snapshot hit.
            def point(pair):return pair[0],None if pair[1] is None else dict(pair[1])
            return point(value) if index==0 else [point(pair) for pair in value]
        def reuse(index,key,compute,key_bytes):
            check=check_shared_budget if index==0 else guard
            check();cache=caches[index]
            if key in cache:
                value,weight=cache.pop(key);cache[key]=(value,weight)
                result=copy_result(index,value);check();return result
            value=compute();check()
            weight=key_bytes+len(repr(value).encode())+512
            limit=MAX_SNAPSHOT_CACHE_BYTES if index==0 else MAX_TEMPERATURE_CACHE_BYTES
            if weight<=limit:
                while cache and (len(cache)>=MAX_TEMPERATURE_CACHE_ENTRIES or sizes[index]+weight>limit):
                    _,(_,removed)=cache.popitem(last=False);sizes[index]-=removed
                if MAX_TEMPERATURE_CACHE_ENTRIES>0:
                    cache[key]=(copy_result(index,value),weight);sizes[index]+=weight
            return value
        def read_snapshot(raw,stored_at,stream,policy,*,version=1,sensor_epoch=None):
            def original():return snapshot(raw,stored_at,stream,policy,version=version,sensor_epoch=sensor_epoch)
            if (_temperature_frame.get() is not frame or type(stored_at) is not datetime or
                    type(policy) is not evidence.TemperaturePolicy or type(raw) is not str or
                    type(stream) is not str or type(version) is not int or
                    (sensor_epoch is not None and type(sensor_epoch) is not str)):return original()
            key=(sha256(raw.encode()).digest(),stored_at.isoformat(),stream,policy,version,sensor_epoch)
            return reuse(0,key,original,32+len(stream.encode())+len(repr(policy))+256)
        def replay(packet):
            if _temperature_frame.get() is not frame:return query(packet)
            packet=deepcopy(packet)
            try:key=sha256(_json_key(packet)).digest()
            except (ValueError,TypeError,RecursionError,OverflowError):return query(packet)
            return reuse(1,key,lambda:query(packet),len(key))
        reader._snapshot=read_snapshot;sources.replay_temperature_source=replay;hooked=True
        if alias is query:raw_sources.replay_temperature_source=replay
        yield
        # This supplements, rather than replaces, the original report's full
        # source/model inventory. Detect same-byte replacement of our helpers.
        for path,raw,identity in originals:
            guard();current=_source_bytes(path,maximum=262144);info=path.lstat()
            if current!=raw or (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink)!=identity:
                raise ValueError('temperature replay helper changed during report')
        guard()
    finally:
        if hooked:
            reader._snapshot=snapshot;sources.replay_temperature_source=query
            raw_sources.replay_temperature_source=alias
        for cache in caches:cache.clear()
        _temperature_frame.reset(token)


def _supported(scores,report,reader):
    path=Path(scores.__file__).resolve()
    if any(Path(function.__code__.co_filename).resolve()!=path for function in (report,reader)):
        return False
    with path.open('rb') as source:raw=source.read(262145)
    return len(raw)<=262144 and sha256(raw).hexdigest() in (SUPPORTED_SOURCE_SHA256,PRIOR_SOURCE_SHA256,INSTALLED_SOURCE_SHA256)



@contextmanager
def _model_reads(scores,assessed_at):
    """Reuse immutable bindings only between this known report's full checks.

    The pinned report first reads every selected model at its assessment time,
    then verifies every model at that same time before its final source-inventory
    verification. Reads at that time ALWAYS execute the original full reader.
    Historical inner steps need only the original admission chronology because
    no report can escape the final full model and original-source checks.
    """
    import json
    import native_model_serving_receipt as serving
    frame=object();token=_model_frame.set(frame);cache={};original=serving.read_serving_model
    hooked=False
    try:
        path=Path(serving.__file__).resolve()
        expected=getattr(scores,'SERVING_RECEIPT_SOURCE_SHA256',None)
        if (assessed_at is None or expected not in (SUPPORTED_MODEL_HELPER_SHA256,PRIOR_MODEL_HELPER_SHA256) or
                Path(original.__code__.co_filename).resolve()!=path):
            yield;return
        with path.open('rb') as source:raw=source.read(262145)
        if len(raw)>262144 or sha256(raw).hexdigest()!=expected:
            yield;return
        report_at=serving._utc(assessed_at)
        def read(selection,*,assessed_at,guard):
            if (_model_frame.get() is not frame or type(selection) is not serving.OwnedServingSelection or
                    getattr(selection,'_seal',None) is not serving._SEAL):
                return original(selection,assessed_at=assessed_at,guard=guard)
            guard();at=serving._utc(assessed_at);key=selection._encoded
            previous=cache.get(key)
            if at==report_at or previous is None:
                model=original(selection,assessed_at=assessed_at,guard=guard)
                if previous is not None and model._encoded!=previous[0]._encoded:
                    raise ValueError('report model bindings changed')
                if previous is None and len(cache)>=32:raise ValueError('bounded report model bindings required')
                receipt=json.loads(model._encoded)['receipt']
                cache[key]=(model,serving._utc(receipt['verified_at']))
            else:
                model,verified_at=previous
                serving._require_model(model)
                if at<verified_at:raise ValueError('verified model admission chronology differs')
            guard();return model
        serving.read_serving_model=read;hooked=True
        yield
    finally:
        if hooked:serving.read_serving_model=original
        cache.clear();_model_frame.reset(token)


def wrap_report(scores):
    """Wrap only the known source whose report verifies its full read inventory."""
    original_report=scores.reconcile_serving_source_report
    original_reader=scores.read_serving_source_score
    if not _supported(scores,original_report,original_reader):return original_report

    @wraps(original_report)
    def report(*args,**kwargs):
        if not _supported(scores,original_report,original_reader):
            return original_report(*args,**kwargs)
        from thermal_model.origin_capture import _source_bytes
        guard=kwargs.get('check_budget',lambda:None);own=Path(__file__).absolute()
        def identity():
            info=own.lstat()
            return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,
                info.st_mode,info.st_uid,info.st_gid,info.st_nlink)
        guard();own_raw=_source_bytes(own,maximum=262144);own_identity=identity()
        cached=None
        def read(path,*,model,expected_capture_sha256,expected_source_score_sha256,check_budget=lambda:None):
            nonlocal cached
            from native_thermal_artifact import _read
            key=(str(path),expected_capture_sha256,expected_source_score_sha256)
            previous=cached;cached=None
            check_budget()
            if previous is not None and previous[0]==key and previous[1] is model:
                # The completion just replayed this exact source. Recheck the
                # model and original score bytes; the original report verifies
                # all captured query/capture/runtime files before returning.
                scores._model_pins(model,assessed_at=previous[3]['assessed_at'],check_budget=check_budget)
                raw,_=_read(Path(path),scores.MAX_SOURCE_SCORE_BYTES)
                if raw!=previous[2]:raise ValueError('original source score changed before report reuse')
                check_budget();return deepcopy(previous[3])
            value=original_reader(path,model=model,expected_capture_sha256=expected_capture_sha256,
                expected_source_score_sha256=expected_source_score_sha256,check_budget=check_budget)
            raw,record=_read(Path(path),scores.MAX_SOURCE_SCORE_BYTES)
            if scores._canonical(record)!=scores._canonical(value):
                raise ValueError('validated original source score changed before report reuse')
            check_budget();cached=(key,model,raw,deepcopy(value))
            return value
        previous_reader=scores.read_serving_source_score
        try:
            scores.read_serving_source_score=read
            with _model_reads(scores,kwargs.get('assessed_at')), _temperature_reads(guard), _capture_reads(guard):
                result=original_report(*args,**kwargs)
            guard()
            if _source_bytes(own,maximum=262144)!=own_raw or identity()!=own_identity:
                raise ValueError('operational report helper changed before return')
            guard();return result
        finally:
            cached=None
            scores.read_serving_source_score=previous_reader
    return report
