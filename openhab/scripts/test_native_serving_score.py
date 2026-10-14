"""Receipt-backed scoring preserves raw outcome replay and historical selection."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import json
import pytest
from test_native_serving_forecast import context,originals
from test_native_thermal_forecast import ISSUE
from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM


def api():
    import native_thermal_score as scores
    assert callable(getattr(scores,'score_serving',None)), 'explicit serving score is missing'
    return scores


def queried(tmp_path,originals,monkeypatch):
    scores=api()
    forecasts,artifacts,candidate,model,inputs,kwargs,paths=context(tmp_path,originals,monkeypatch)
    capture=forecasts.build_serving_capture(model,inputs,**kwargs)
    receipts={name:dict(item=name,time=int((ISSUE+timedelta(seconds=3+i)).timestamp()*1000),state=json.dumps(value))
        for i,(name,value) in enumerate(((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,forecasts.publication(capture))))}
    pins=dict(runtime=model.runtime,expected_artifact_sha256=candidate['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])
    import test_native_thermal_score_sources as old
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(old,'issued',lambda *a:(capture,receipts,pins))
        args=old.queried(tmp_path,monkeypatch,originals)
    serving_args={k:v for k,v in args.items() if k not in ('runtime','expected_artifact_sha256')}
    return scores,model,capture,args,dict(model=model,**serving_args)


def test_serving_score_and_raw_source_equal_independent_full_replay(tmp_path,originals,monkeypatch):
    scores,model,capture,args,serving_args=queried(tmp_path,originals,monkeypatch)
    full=scores.build_source_score(**args)
    recent=full['pair']['recent_cycle']
    def forbidden(*a,**kw):pytest.fail('serving score repeated candidate numerical replay')
    import native_thermal_forecast as forecasts
    monkeypatch.setattr(forecasts,'validate_native_candidate',forbidden)
    pair=scores.score_serving(capture,model,args['receipts'],args['outcome'],expected_capture_sha256=capture['capture_sha256'],horizon_hours=1,assessed_at=args['assessed_at'],recent=recent,check_budget=lambda:None)
    assert pair==full['pair']
    served=scores.build_serving_source_score(**serving_args)
    assert served==full and served['query_binding']==full['query_binding']
    assert scores.validate_serving_source_score(served,model=model,expected_capture_sha256=capture['capture_sha256'],expected_source_score_sha256=served['source_score_sha256'],check_budget=lambda:None)==full
    Path(args['source_paths'][-1]).unlink()
    with pytest.raises((ValueError,OSError)):scores.build_serving_source_score(**serving_args)


def test_serving_completion_and_report_equal_independent_full_replay(tmp_path,originals,monkeypatch):
    scores,model,capture,args,serving_args=queried(tmp_path,originals,monkeypatch)
    record=scores.build_source_score(**args);path=scores.persist_source_score(tmp_path,record)
    pins=dict(runtime=model.runtime,expected_artifact_sha256=args['expected_artifact_sha256'],expected_capture_sha256=capture['capture_sha256'],expected_source_score_sha256=record['source_score_sha256'])
    at=args['assessed_at']+timedelta(seconds=10)
    full=scores.build_source_completion(path,completed_at=at,**pins)
    saved=scores.persist_source_completion(tmp_path,full)
    entries=[dict(completion_path=str(saved),completion_sha256=full['completion_sha256'],source_score_sha256=record['source_score_sha256'],capture_sha256=capture['capture_sha256'])]
    full_report=scores.reconcile_source_report(entries,runtime=model.runtime,artifact_sha256=args['expected_artifact_sha256'],assessed_at=at,check_budget=lambda:None)
    import native_thermal_forecast as forecasts
    monkeypatch.setattr(forecasts,'validate_native_candidate',lambda *a,**kw:pytest.fail('serving completion repeated numerical replay'))
    served=scores.build_serving_source_completion(path,model=model,expected_capture_sha256=capture['capture_sha256'],expected_source_score_sha256=record['source_score_sha256'],completed_at=at,check_budget=lambda:None)
    assert served==full
    assert scores.validate_serving_source_completion(served,model=model,expected_capture_sha256=capture['capture_sha256'],expected_completion_sha256=served['completion_sha256'],check_budget=lambda:None)==full
    assert scores.reconcile_serving_source_report(entries,selections=(model._selection,),artifact_sha256=args['expected_artifact_sha256'],assessed_at=at,check_budget=lambda:None)==full_report
    with pytest.raises(ValueError):scores.reconcile_serving_source_report(entries,selections=(),artifact_sha256=args['expected_artifact_sha256'],assessed_at=at,check_budget=lambda:None)


def test_old_capture_cannot_use_active_receipt(tmp_path,originals,monkeypatch):
    scores=api();forecasts,artifacts,candidate,model,inputs,kwargs,paths=context(tmp_path,originals,monkeypatch)
    older=artifacts.build_native_candidate(originals={role:Path(ref['path']) for role,ref in candidate['originals'].items()},runtime=model.runtime,created_at=__import__('datetime').datetime.fromisoformat(candidate['created_at'])+timedelta(seconds=1))
    capture=forecasts.build_capture(older,inputs,runtime=model.runtime,expected_artifact_sha256=older['artifact_sha256'],**kwargs)
    assert capture['candidate']['artifact_sha256']!=candidate['artifact_sha256']
    with pytest.raises(ValueError):scores.score_serving(capture,model,{},None,expected_capture_sha256=capture['capture_sha256'],horizon_hours=1,assessed_at=ISSUE+timedelta(hours=1,minutes=10),recent={'status':'unavailable','prediction_f':None},check_budget=lambda:None)


def test_missing_historical_receipt_qualifies_no_outcome(tmp_path,originals,monkeypatch):
    scores=api();forecasts,artifacts,candidate,model,inputs,kwargs,paths=context(tmp_path,originals,monkeypatch)
    selected=json.loads(model._selection._encoded)
    Path(selected['receipt']['path']).unlink()
    with pytest.raises((ValueError,OSError)):scores.reconcile_serving_source_report([],selections=(model._selection,),artifact_sha256=candidate['artifact_sha256'],assessed_at=ISSUE+timedelta(hours=1,minutes=10),check_budget=lambda:None)
