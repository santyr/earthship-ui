"""Avoid one duplicate full replay inside the known original serving report.

The original report still owns model selection, completion validation, duplicate
job checks, arithmetic, and final verification of every observed original file.
No value survives a report invocation; unknown implementations run unchanged.
"""
from copy import deepcopy
from functools import wraps
from hashlib import sha256
from pathlib import Path

SUPPORTED_SOURCE_SHA256='2e4abc7c8f655bcc5f7ff839b9750816f56f08b02bd516e10c8b8c2c6aaa6dab'


def _supported(scores,report,reader):
    path=Path(scores.__file__).resolve()
    if any(Path(function.__code__.co_filename).resolve()!=path for function in (report,reader)):
        return False
    with path.open('rb') as source:raw=source.read(262145)
    return len(raw)<=262144 and sha256(raw).hexdigest()==SUPPORTED_SOURCE_SHA256


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
            return original_report(*args,**kwargs)
        finally:
            cached=None
            scores.read_serving_source_score=previous_reader
    return report
