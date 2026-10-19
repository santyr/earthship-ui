"""Explicit withdrawal needs no candidate and never claims HTTP-only delivery."""
import importlib,json,subprocess,sys
from pathlib import Path
import pytest
from thermal_model.forcing_capture import _canonical


def module():
    from thermal_model import installed_shade_live as live
    assert hasattr(live,'withdraw_live_publication'),'missing explicit withdrawal'
    return live


class Backend:
    def __init__(self,fail=False):self.fail=fail;self.states=[]
    def verify_unchanged(self):pass
    def put(self,item,state,*,preflight=None):
        if preflight:preflight()
        self.states.append((item,state))
    def persisted(self,item,state,*,since):
        if self.fail:raise ValueError('synthetic missing receipt')
        return dict(item=item,time=int(since.timestamp()*1000),state=state)


def test_explicit_withdrawal_retains_reason_and_actual_unavailable_receipt(tmp_path):
    tmp_path.chmod(0o700);backend=Backend();result=module().withdraw_live_publication(archive=tmp_path,backend=backend,reason='baseline regression')
    assert result['status']=='withdrawn' and result['delivery_verified'] is True
    assert len(backend.states)==1 and backend.states[0][0]=='Thermal_Model_JSON'
    output=json.loads(backend.states[0][1]);assert output['status']=='unavailable' and output['forecast'] is None
    record=json.loads(Path(result['receipt_path']).read_text())
    assert record['reason']=='baseline regression' and record['publication']['state']==backend.states[0][1]


def test_withdrawal_cannot_claim_delivery_without_matching_jdbc_receipt(tmp_path):
    tmp_path.chmod(0o700);result=module().withdraw_live_publication(archive=tmp_path,backend=Backend(True),reason='source failure')
    assert result['status']=='unverified_failure' and result['delivery_verified'] is False
    assert not list(tmp_path.glob('*.installed-shade-withdrawal-v1.json'))


def test_withdrawal_shares_existing_publication_lock(tmp_path):
    import os,fcntl
    tmp_path.chmod(0o700);fd=os.open(tmp_path/'.installed-shade-live.lock',os.O_RDWR|os.O_CREAT,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);backend=Backend()
        assert module().withdraw_live_publication(archive=tmp_path,backend=backend,reason='operator')['status']=='busy'
        assert backend.states==[]
    finally:os.close(fd)








def test_withdrawal_refuses_lock_replacement_during_source_verification(tmp_path):
    tmp_path.chmod(0o700)
    class ReplacingBackend(Backend):
        def verify_unchanged(self):
            lock=tmp_path/'.installed-shade-live.lock'
            if lock.exists():lock.unlink();lock.touch(mode=0o600)
    backend=ReplacingBackend()
    result=module().withdraw_live_publication(archive=tmp_path,backend=backend,reason='operator')
    assert result['status']=='unverified_failure'
    assert backend.states==[]
