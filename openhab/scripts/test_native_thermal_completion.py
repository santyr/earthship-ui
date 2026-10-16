"""Native completion reports count only independently replayed original sources."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import pytest
from test_native_thermal_score_sources import queried,build,originals
from test_native_thermal_score import api


def source(tmp_path,monkeypatch,originals):
    args=queried(tmp_path,monkeypatch,originals);record=build(args)
    path=api().persist_source_score(tmp_path,record)
    roots={k:args[k] for k in ('runtime','expected_artifact_sha256','expected_capture_sha256')}
    roots['expected_source_score_sha256']=record['source_score_sha256']
    return args,record,path,roots


def completed(tmp_path,monkeypatch,originals):
    args,record,path,roots=source(tmp_path,monkeypatch,originals)
    completion=api().build_source_completion(path,completed_at=args['assessed_at']+timedelta(seconds=10),**roots)
    return args,record,path,roots,completion


def entry(tmp_path,completion):
    path=api().persist_source_completion(tmp_path,completion)
    return dict(completion_path=str(path),completion_sha256=completion['completion_sha256'],
                source_score_sha256=completion['source_score_sha256'],capture_sha256=completion['capture_sha256'])


def replay(completion,roots):
    return api().validate_source_completion(completion,expected_completion_sha256=completion['completion_sha256'],**roots)


def report(entries,args,*,assessed_at=None,check_budget=lambda:None):
    return api().reconcile_source_report(entries,runtime=args['runtime'],artifact_sha256=args['expected_artifact_sha256'],
        assessed_at=assessed_at or args['assessed_at']+timedelta(minutes=1),check_budget=check_budget)


def test_native_completion_private_roundtrip_replays_original_source_score(tmp_path,monkeypatch,originals):
    args,record,path,roots,completion=completed(tmp_path,monkeypatch,originals)
    assert completion['pair_sha256']==record['pair']['pair_sha256']
    assert completion['release_authority'] is False
    assert replay(completion,roots)==completion
    saved=api().persist_source_completion(tmp_path,completion)
    assert saved.stat().st_mode & 0o777==0o600
    assert api().read_source_completion(saved,expected_completion_sha256=completion['completion_sha256'],**roots)==completion


def test_native_reconciled_report_rederives_model_and_both_baselines(tmp_path,monkeypatch,originals):
    args,record,path,roots,completion=completed(tmp_path,monkeypatch,originals)
    result=report([entry(tmp_path,completion)],args)
    assert result['graduated'] is False
    assert result['by_horizon']['1']['model']['mae_f']==abs(record['pair']['errors']['model'])
    assert result['by_horizon']['1']['persistence']=={'count':1,'mae_f':1,'bias_f':-1}
    assert result['by_horizon']['1']['recent_cycle']=={'count':1,'mae_f':1,'bias_f':1}
    assert result['by_horizon']['6']['model']['count']==0


@pytest.mark.parametrize('deleted',['score','capture','query'])
def test_native_completion_and_report_refuse_deleted_originals(tmp_path,monkeypatch,originals,deleted):
    args,record,path,roots,completion=completed(tmp_path,monkeypatch,originals);e=entry(tmp_path,completion)
    original={'score':path,'capture':Path(args['capture_path']),'query':Path(args['source_paths'][-1])}[deleted]
    original.unlink()
    with pytest.raises((ValueError,OSError)):replay(completion,roots)
    with pytest.raises((ValueError,OSError)):report([e],args)


@pytest.mark.parametrize('changed',['pair','source','capture','artifact','runtime','clock'])
def test_resealed_native_completions_require_external_pins_and_original_pair(tmp_path,monkeypatch,originals,changed):
    args,record,path,roots,completion=completed(tmp_path,monkeypatch,originals)
    if changed=='clock':completion['completed_at']=args['assessed_at'].isoformat().split('+')[0]+'.0000009+00:00'
    else:completion[{'pair':'pair_sha256','source':'source_score_sha256','capture':'capture_sha256','artifact':'artifact_sha256','runtime':'runtime_sha256'}[changed]]='f'*64
    completion['completion_sha256']=api().digest(completion,'completion_sha256')
    with pytest.raises(ValueError):replay(completion,roots)


def test_native_report_refuses_duplicates_future_assessment_and_changed_caller(tmp_path,monkeypatch,originals):
    args,record,path,roots,completion=completed(tmp_path,monkeypatch,originals);e=entry(tmp_path,completion)
    with pytest.raises(ValueError):report([e,e],args)
    with pytest.raises(ValueError):report([e],args,assessed_at=args['assessed_at'])
    entries=[e]
    def mutate():e['capture_sha256']='f'*64;entries.clear()
    result=report(entries,args,check_budget=mutate)
    assert result['by_horizon']['1']['model']['count']==1 and entries==[]


def test_native_empty_report_bounds_and_budget_are_explicit(tmp_path,monkeypatch,originals):
    args,record,path,roots=source(tmp_path,monkeypatch,originals)
    assert report([],args)['by_horizon']['1']['model']['count']==0
    with pytest.raises(ValueError):report([{}]*257,args)
    def refused():raise ValueError('shared deadline elapsed')
    with pytest.raises(ValueError,match='shared deadline'):report([],args,check_budget=refused)


def test_native_report_refuses_original_change_during_aggregation(tmp_path,monkeypatch,originals):
    args,record,path,roots,completion=completed(tmp_path,monkeypatch,originals);e=entry(tmp_path,completion)
    original=api().summarize
    def changed(pairs,**kwargs):
        Path(args['source_paths'][-1]).unlink()
        return original(pairs,**kwargs)
    monkeypatch.setattr(api(),'summarize',changed)
    with pytest.raises(ValueError):report([e],args)
