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

SUPPORTED_SOURCE_SHA256='2e4abc7c8f655bcc5f7ff839b9750816f56f08b02bd516e10c8b8c2c6aaa6dab'
SUPPORTED_MODEL_HELPER_SHA256='94d85e37afc79e08cf9de93ba937b2ba845acc7111c0a23e483b186d8ff9a57e'
_model_frame=ContextVar('household_report_model_bindings',default=None)


def _supported(scores,report,reader):
    path=Path(scores.__file__).resolve()
    if any(Path(function.__code__.co_filename).resolve()!=path for function in (report,reader)):
        return False
    with path.open('rb') as source:raw=source.read(262145)
    return len(raw)<=262144 and sha256(raw).hexdigest()==SUPPORTED_SOURCE_SHA256



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
        if (assessed_at is None or getattr(scores,'SERVING_RECEIPT_SOURCE_SHA256',None)!=SUPPORTED_MODEL_HELPER_SHA256 or
                Path(original.__code__.co_filename).resolve()!=path):
            yield;return
        with path.open('rb') as source:raw=source.read(262145)
        if len(raw)>262144 or sha256(raw).hexdigest()!=SUPPORTED_MODEL_HELPER_SHA256:
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
            with _model_reads(scores,kwargs.get('assessed_at')):
                return original_report(*args,**kwargs)
        finally:
            cached=None
            scores.read_serving_source_score=previous_reader
    return report
