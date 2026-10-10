"""Provisional delivery and withdrawal boundaries; transport and source binding are synthetic."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import json
import pytest
from test_provisional_thermal_forecast import context,ISSUE,module as forecasts
from test_installed_shade_origin import native


def module():
    from thermal_model import provisional_live
    return provisional_live


def fixture(tmp_path,monkeypatch):
    candidate,inputs=context(tmp_path,monkeypatch)
    source=tmp_path/'source-packet';source.write_text('mathematical source seam');source.chmod(0o600)
    inputs['native_source_paths']={'mathematical':str(source)}
    known=ISSUE-timedelta(seconds=30);inputs['current'],inputs['origin_temperatures']=native(known)
    monkeypatch.setattr(forecasts(),'replay_binding',lambda *a,**k:None)
    clock=[known]
    monkeypatch.setattr(module(),'_clock',lambda:clock[0])
    monkeypatch.setattr(module(),'sleep',lambda seconds:clock.__setitem__(0,clock[0]+timedelta(seconds=seconds)))
    monkeypatch.setattr(module(),'current_runtime',lambda:candidate['runtime'])
    monkeypatch.setattr(module(),'read_candidate',lambda *a,**k:deepcopy(candidate))
    monkeypatch.setattr(module(),'_resource_preflight',lambda:None)
    archive=tmp_path/'archive';archive.mkdir(mode=0o700)
    settings=dict(evidence_directory=str(archive),candidate_path=str(tmp_path/'model'),native_cutover=(ISSUE-timedelta(days=1)).isoformat())
    class Backend:
        def __init__(self):self.states={};self.puts=[]
        def verify_unchanged(self):pass
        def collect(self,**kwargs):return deepcopy(inputs)
        def put(self,item,state,*,preflight):preflight();self.states[item]=state;self.puts.append(item)
        def persisted(self,item,state,*,since):
            clock[0]+=timedelta(milliseconds=10)
            return {'item':item,'time':int(clock[0].timestamp()*1000),'state':state}
    return settings,Backend(),clock,candidate


def test_provisional_cycle_requires_both_actual_receipts(tmp_path,monkeypatch):
    settings,backend,_,_=fixture(tmp_path,monkeypatch)
    result=module().publish_cycle(settings,backend=backend,guard=lambda:None)
    assert result['status']=='published' and result['delivery_verified'] is True
    assert len(backend.puts)==2
    receipt=json.loads(Path(result['delivery_path']).read_text())
    assert len(receipt['receipts'])==2
    assert len(list((tmp_path/'archive').glob('origins-*/*.provisional-origin-v1.json')))==1


def test_failed_persistence_never_claims_delivery(tmp_path,monkeypatch):
    settings,backend,_,_=fixture(tmp_path,monkeypatch)
    backend.persisted=lambda *a,**k:None
    with pytest.raises(ValueError):module().publish_cycle(settings,backend=backend,guard=lambda:None)
    assert not list((tmp_path/'archive').glob('origins-*/*.provisional-delivery-v1.json'))


def test_withdrawal_does_not_read_candidate_or_fit(tmp_path,monkeypatch):
    settings,backend,_,_=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(module(),'read_candidate',lambda *a,**k:pytest.fail('withdrawal read model'))
    result=module().withdraw(settings,backend=backend,guard=lambda:None)
    assert result['status']=='withdrawn'
    from thermal_model.installed_shade_published_origin import PUBLICATION_ITEM
    assert json.loads(backend.states[PUBLICATION_ITEM])['status']=='unavailable'


def test_real_provisional_runtime_binds_every_deployed_source(tmp_path,monkeypatch):
    root=tmp_path/'runtime';root.mkdir(mode=0o700)
    original=Path(__file__).resolve().parent
    for name in module().RUNTIME_PATHS:
        target=root/name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        target.write_bytes((original/name).read_bytes());target.chmod(0o600)
    monkeypatch.setattr(module(),'RUNTIME_ROOT',root)
    runtime=module().current_runtime()
    assert set(runtime['source_manifest'])==set(module().RUNTIME_PATHS)
    assert len(runtime['source_manifest'])==72
