"""One report replays each source score once and still verifies every original."""
from datetime import timedelta
from pathlib import Path
import pytest
from test_native_serving_score import queried,originals


def report_fixture(tmp_path,originals,monkeypatch):
    scores,model,capture,args,serving_args=queried(tmp_path,originals,monkeypatch)
    record=scores.build_serving_source_score(**serving_args)
    path=scores.persist_source_score(tmp_path,record)
    at=args['assessed_at']+timedelta(seconds=10)
    completion=scores.build_serving_source_completion(path,model=model,
        expected_capture_sha256=capture['capture_sha256'],expected_source_score_sha256=record['source_score_sha256'],completed_at=at)
    saved=scores.persist_source_completion(tmp_path,completion)
    entries=[dict(completion_path=str(saved),completion_sha256=completion['completion_sha256'],
        source_score_sha256=record['source_score_sha256'],capture_sha256=capture['capture_sha256'])]
    calls=[];validate=scores.validate_serving_source_score
    def counted(*a,**kw):
        result=validate(*a,**kw);calls.append(True);return result
    monkeypatch.setattr(scores,'validate_serving_source_score',counted)
    expected=scores.summarize([record['pair']],artifact_sha256=args['expected_artifact_sha256'])
    expected['assessed_at']=at.isoformat()
    kwargs=dict(selections=(model._selection,),artifact_sha256=args['expected_artifact_sha256'],assessed_at=at)
    return scores,entries,kwargs,expected,calls,args,path


def test_actual_completion_report_replays_source_once_per_report(tmp_path,originals,monkeypatch):
    from household_forecast_score import production_score_policy
    scores,entries,kwargs,expected,calls,args,path=report_fixture(tmp_path,originals,monkeypatch)
    original_reader=scores.read_serving_source_score;original_report=scores.reconcile_serving_source_report
    with production_score_policy():
        assert scores.reconcile_serving_source_report(entries,**kwargs)==expected
        assert len(calls)==1, 'completion and report repeated the same full source replay'
        assert scores.reconcile_serving_source_report(entries,**kwargs)==expected
        assert len(calls)==2, 'a new report must replay the original source again'
    assert scores.read_serving_source_score is original_reader
    assert scores.reconcile_serving_source_report is original_report


@pytest.mark.parametrize('changed',['query','capture','score','model'])
def test_actual_report_refuses_original_change_after_first_replay(tmp_path,originals,monkeypatch,changed):
    from household_forecast_score import production_score_policy
    scores,entries,kwargs,expected,calls,args,path=report_fixture(tmp_path,originals,monkeypatch)
    import json
    receipt=Path(json.loads(kwargs['selections'][0]._encoded)['receipt']['path'])
    target={'query':Path(args['source_paths'][-1]),'capture':Path(args['capture_path']),'score':path,'model':receipt}[changed]
    old=target.read_bytes();mutated=[];original_reader=scores.read_serving_source_score;original_report=scores.reconcile_serving_source_report
    def guard():
        if calls and not mutated:
            target.write_bytes(old+b' ');mutated.append(True)
    with pytest.raises(ValueError):
        with production_score_policy():scores.reconcile_serving_source_report(entries,check_budget=guard,**kwargs)
    assert mutated
    assert scores.read_serving_source_score is original_reader
    assert scores.reconcile_serving_source_report is original_report


def test_unknown_report_implementation_is_left_unchanged(monkeypatch):
    import household_score_report_reuse as reuse,native_thermal_score as scores
    monkeypatch.setattr(reuse,'SUPPORTED_SOURCE_SHA256','0'*64)
    original=scores.reconcile_serving_source_report
    assert reuse.wrap_report(scores) is original


def test_changed_operational_helper_refuses_before_loading(tmp_path,monkeypatch):
    import household_forecast_score as coordinator,native_thermal_score as scores
    helper=tmp_path/'household_score_report_reuse.py';helper.write_text("raise AssertionError('changed helper executed')\n");helper.chmod(0o644)
    monkeypatch.setattr(coordinator,'__file__',str(tmp_path/'household_forecast_score.py'))
    with pytest.raises(ValueError,match='report replay helper source differs'):
        coordinator.production_report_replay(scores)


def test_consecutive_reuse_preserves_caller_isolation_and_consumes_only_one_hit(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from copy import deepcopy
    import json
    import household_score_report_reuse as reuse
    from thermal_model.replay_budget import capture_source_reads
    monkeypatch.setattr(reuse,'_supported',lambda *args:True)
    value={'assessed_at':'2026-10-14T00:00:00+00:00','pair':{'result':1}}
    path=tmp_path/'source.json';path.write_text(json.dumps(value));path.chmod(0o600)
    calls=[];model=object();other_model=object()
    def reader(path,**kwargs):calls.append(kwargs);return deepcopy(value)
    scores=SimpleNamespace(read_serving_source_score=reader,MAX_SOURCE_SCORE_BYTES=1024,
        _canonical=lambda v:json.dumps(v,sort_keys=True),_model_pins=lambda model,**kw:kw['check_budget']())
    def original_report():
        kwargs=dict(model=model,expected_capture_sha256='a'*64,expected_source_score_sha256='b'*64)
        with capture_source_reads() as inventory:
            first=scores.read_serving_source_score(path,**kwargs);first['pair']['result']=9
            assert scores.read_serving_source_score(path,**kwargs)==value
            assert len(calls)==1
            scores.read_serving_source_score(path,**kwargs)
            assert len(calls)==2  # the previous cached entry was consumed
            scores.read_serving_source_score(path,**{**kwargs,'model':other_model})
            assert len(calls)==3
            scores.read_serving_source_score(path,**{**kwargs,'expected_capture_sha256':'c'*64})
            assert len(calls)==4
            inventory.verify()
        return 'verified'
    scores.reconcile_serving_source_report=original_report
    assert reuse.wrap_report(scores)()=='verified'
    assert scores.read_serving_source_score is reader


def test_report_rechecks_model_bindings_at_boundaries_not_per_historical_step(tmp_path,originals,monkeypatch):
    from household_forecast_score import production_score_policy
    import native_model_serving_receipt as serving
    scores,entries,kwargs,expected,calls,args,path=report_fixture(tmp_path,originals,monkeypatch)
    kwargs['assessed_at']+=timedelta(seconds=60);expected['assessed_at']=kwargs['assessed_at'].isoformat()
    full_bindings=serving._bindings;reads=[]
    def counted(*args,**kwargs):
        result=full_bindings(*args,**kwargs);reads.append(result);return result
    monkeypatch.setattr(serving,'_bindings',counted)
    original=serving.read_serving_model
    with production_score_policy():
        assert scores.reconcile_serving_source_report(entries,**kwargs)==expected
        assert len(reads)==2, 'one model must be fully rebound at report entry and final verification only'
        assert scores.reconcile_serving_source_report(entries,**kwargs)==expected
        assert len(reads)==4, 'each new report must obtain fresh model bindings'
    assert serving.read_serving_model is original


@pytest.mark.parametrize('changed',['candidate','dataset','receipt'])
def test_reused_model_still_refuses_final_original_changes(tmp_path,originals,monkeypatch,changed):
    from household_forecast_score import production_score_policy
    import json,native_model_serving_receipt as serving
    scores,entries,kwargs,expected,calls,args,path=report_fixture(tmp_path,originals,monkeypatch)
    kwargs['assessed_at']+=timedelta(seconds=60)
    selected=json.loads(kwargs['selections'][0]._encoded)
    candidate=json.loads(Path(selected['candidate_path']).read_bytes())
    target=Path({'candidate':selected['candidate_path'],'dataset':candidate['originals']['dataset']['path'],
        'receipt':selected['receipt']['path']}[changed])
    old=target.read_bytes();mutated=[];reader=serving.read_serving_model
    def guard():
        if calls and not mutated:target.write_bytes(old+b' ');mutated.append(True)
    with pytest.raises(ValueError):
        with production_score_policy():scores.reconcile_serving_source_report(entries,check_budget=guard,**kwargs)
    assert mutated and serving.read_serving_model is reader


def test_intermediate_model_reuse_preserves_chronology_and_caller_isolation(tmp_path,originals,monkeypatch):
    import json
    import household_score_report_reuse as reuse,native_model_serving_receipt as serving
    scores,entries,kwargs,expected,calls,args,path=report_fixture(tmp_path,originals,monkeypatch)
    at=kwargs['assessed_at']+timedelta(seconds=60);selection=kwargs['selections'][0]
    original=serving.read_serving_model
    with reuse._model_reads(scores,at):
        model=serving.read_serving_model(selection,assessed_at=at,guard=lambda:None)
        receipt=json.loads(model._encoded)['receipt'];verified=serving._utc(receipt['verified_at'])
        with pytest.raises(ValueError,match='chronology'):
            serving.read_serving_model(selection,assessed_at=verified-timedelta(microseconds=1),guard=lambda:None)
        changed=model.candidate;changed['artifact_sha256']='0'*64
        cached=serving.read_serving_model(selection,assessed_at=kwargs['assessed_at'],guard=lambda:None)
        assert cached.candidate['artifact_sha256']==expected['artifact_sha256']
        with pytest.raises(TimeoutError):
            serving.read_serving_model(selection,assessed_at=kwargs['assessed_at'],guard=lambda:(_ for _ in ()).throw(TimeoutError()))
        assert serving.read_serving_model(selection,assessed_at=at,guard=lambda:None)._encoded==model._encoded
    assert serving.read_serving_model is original


def test_unknown_model_helper_runs_full_original_report(tmp_path,originals,monkeypatch):
    import household_score_report_reuse as reuse,native_model_serving_receipt as serving
    scores,entries,kwargs,expected,calls,args,path=report_fixture(tmp_path,originals,monkeypatch)
    monkeypatch.setattr(reuse,'SUPPORTED_MODEL_HELPER_SHA256','0'*64)
    bindings=serving._bindings;reads=[]
    def counted(*args,**kwargs):
        value=bindings(*args,**kwargs);reads.append(1);return value
    monkeypatch.setattr(serving,'_bindings',counted)
    assert reuse.wrap_report(scores)(entries,**kwargs)==expected
    assert len(reads)==12


def test_nested_and_other_execution_contexts_cannot_borrow_model_cache(tmp_path,originals,monkeypatch):
    from contextvars import Context
    import household_score_report_reuse as reuse,native_model_serving_receipt as serving
    scores,entries,kwargs,expected,calls,args,path=report_fixture(tmp_path,originals,monkeypatch)
    at=kwargs['assessed_at']+timedelta(seconds=60);selection=kwargs['selections'][0]
    bindings=serving._bindings;reads=[];original=serving.read_serving_model
    def counted(*args,**kwargs):
        value=bindings(*args,**kwargs);reads.append(1);return value
    monkeypatch.setattr(serving,'_bindings',counted)
    with reuse._model_reads(scores,at):
        serving.read_serving_model(selection,assessed_at=at,guard=lambda:None)
        serving.read_serving_model(selection,assessed_at=kwargs['assessed_at'],guard=lambda:None)
        assert len(reads)==1
        Context().run(serving.read_serving_model,selection,assessed_at=kwargs['assessed_at'],guard=lambda:None)
        assert len(reads)==2
        with reuse._model_reads(scores,at):
            serving.read_serving_model(selection,assessed_at=kwargs['assessed_at'],guard=lambda:None)
        assert len(reads)==3
        serving.read_serving_model(selection,assessed_at=kwargs['assessed_at'],guard=lambda:None)
        assert len(reads)==3
        serving.read_serving_model(selection,assessed_at=at,guard=lambda:None)
        assert len(reads)==4
    assert serving.read_serving_model is original
