"""Unchanged models retain an admission that predates their original forecasts."""
from datetime import datetime,timezone
from types import SimpleNamespace
import json
from pathlib import Path
import pytest


def setup(monkeypatch):
    import household_cycle_deploy as deploy,native_model_serving_receipt as receipts
    candidate=dict(artifact_sha256='a'*64,runtime_sha256='b'*64,payload='same fitted model')
    references=[dict(stage='/private/late',deployment_sha256='c'*64),dict(stage='/private/early',deployment_sha256='d'*64)]
    metadata={ref['stage']:dict(stage=ref['stage'],deployment_sha256=ref['deployment_sha256'],candidate_path=ref['stage']+'/candidate.json',receipt=dict(path=ref['stage']+'/receipt.json',sha256='e'*64)) for ref in references}
    checked=[]
    monkeypatch.setattr(deploy,'verify_stage',lambda stage,**kwargs:dict(artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256']))
    monkeypatch.setattr(receipts,'load_serving_selection',lambda stage,**kwargs:SimpleNamespace(_encoded=json.dumps(metadata[str(stage)])))
    def read(selection,**kwargs):
        data=json.loads(selection._encoded);stamp='2026-10-14T20:00:00+00:00' if data['stage'].endswith('late') else '2026-10-14T18:00:00+00:00'
        return SimpleNamespace(candidate=dict(candidate),_encoded=json.dumps(dict(receipt=dict(verified_at=stamp))),_selection=selection,verify_bindings=lambda **kw:checked.append(data['stage']))
    monkeypatch.setattr(receipts,'read_serving_model',read)
    return candidate,references,checked


def test_unchanged_model_reuses_earliest_verified_admission(monkeypatch):
    import household_native_training as training
    candidate,refs,checked=setup(monkeypatch)
    result=training.retained_model_admission(candidate,selections=refs,guard=lambda:None)
    assert result['candidate_path']=='/private/early/candidate.json'
    assert result['receipt_path']=='/private/early/receipt.json'
    assert result['verified_at']=='2026-10-14T18:00:00+00:00'
    assert checked==['/private/early']


def test_changed_model_requires_fresh_admission(monkeypatch):
    import household_native_training as training
    candidate,refs,checked=setup(monkeypatch)
    changed={**candidate,'artifact_sha256':'f'*64}
    assert training.retained_model_admission(changed,selections=refs,guard=lambda:None) is None
    assert checked==[]


def test_same_identity_with_different_candidate_is_refused(monkeypatch):
    import household_native_training as training
    candidate,refs,checked=setup(monkeypatch)
    changed={**candidate,'payload':'different model'}
    with pytest.raises(ValueError,match='candidate differs'):
        training.retained_model_admission(changed,selections=refs,guard=lambda:None)


@pytest.mark.parametrize('count',[33,64])
def test_full_retained_dispatch_plus_current_keeps_the_original_model_admission(monkeypatch,count):
    import household_native_training as training,household_cycle_deploy as deploy
    candidate,refs,checked=setup(monkeypatch);verify=deploy.verify_stage
    retained=[dict(stage=f'/private/other-{i:02d}',deployment_sha256='0'*64) for i in range(count-2)]+refs
    def stage(path,*,expected_deployment_sha256):
        if str(path).startswith('/private/other-'):
            assert expected_deployment_sha256=='0'*64
            return dict(artifact_sha256='f'*64,runtime_sha256='b'*64)
        return verify(path,expected_deployment_sha256=expected_deployment_sha256)
    monkeypatch.setattr(deploy,'verify_stage',stage)
    result=training.retained_model_admission(candidate,selections=retained,guard=lambda:None)
    assert result['candidate_path']=='/private/early/candidate.json'
    assert result['verified_at']=='2026-10-14T18:00:00+00:00'
    assert checked==['/private/early']


def test_admission_refuses_more_than_complete_dispatch_and_current(monkeypatch):
    import household_native_training as training
    candidate,refs,checked=setup(monkeypatch)
    with pytest.raises(ValueError,match='bounded retained admission'):
        training.retained_model_admission(candidate,selections=[dict(stage=f'/private/{i}',deployment_sha256='c'*64) for i in range(65)],guard=lambda:None)
