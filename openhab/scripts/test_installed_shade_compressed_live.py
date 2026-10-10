"""Compressed operator receipt flow with retained synthetic current queries.

Readiness and reference loading are mathematical seams; no real release claim.
"""
from copy import deepcopy
from datetime import datetime,timedelta
import json
from pathlib import Path
import pytest
from test_installed_shade_raw_origin import candidate,raw_math_capture,source_origin_case
from thermal_model.forcing_capture import _canonical
from test_installed_shade_live import FakeBackend


@pytest.fixture
def compressed_cycle(raw_math_capture,tmp_path,monkeypatch):
    from test_installed_shade_raw_publication_capture import compressed_calibrated_delivery
    from thermal_model import installed_shade_live as live,installed_shade_publication as p,installed_shade_qualification as q,installed_shade_published_origin as captures
    from test_installed_shade_raw_origin import build_source_origin_case
    issue=datetime.fromisoformat(raw_math_capture['issued_at'])
    source_case=build_source_origin_case(raw_math_capture,tmp_path,assessed_at=issue-timedelta(seconds=15))
    root,main,_,issue,_,args=compressed_calibrated_delivery(source_case,tmp_path,monkeypatch)
    numeric=main['numeric_capture'];live._test_time=issue-timedelta(seconds=15)
    monkeypatch.setattr(live,'_clock',lambda:live._test_time)
    monkeypatch.setattr(live,'_wait_until',lambda at:setattr(live,'_test_time',at))
    monkeypatch.setattr(p,'_clock',lambda:live._test_time)
    monkeypatch.setattr(captures,'_clock',lambda:live._test_time)
    report=q.qualify_compressed_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=live._test_time)
    prepared=p.PreparedCompressedInstalledQualification(_canonical(report),_canonical(numeric['candidate']),True,True,('thermal_intel.py',),True,str(root/'synthetic-refs.json'))
    monkeypatch.setattr(live,'prepare_compressed_installed_qualification',lambda _:prepared)
    monkeypatch.setattr(p,'prepare_compressed_installed_qualification',lambda _:prepared)
    monkeypatch.setattr(live,'build_runtime_binding',lambda *a:numeric['runtime'])
    monkeypatch.setattr(p,'build_runtime_binding',lambda *a:numeric['runtime'])
    class Backend(FakeBackend):
        def collect(self,*,issue,known_at):
            self.collected=True
            self.m._test_time=self.issue+timedelta(seconds=1) if self.damage=='late_collection' else self.issue-timedelta(seconds=5)
            result={key:deepcopy(numeric[key]) for key in ('forecast','current','origin_temperatures','action_snapshot')}
            return dict(result,native_source_paths=deepcopy(args['native_source_paths']))
    return live,root,issue,Backend(live,issue),args


def test_compressed_cycle_binds_actual_two_receipts_and_final_report(compressed_cycle,monkeypatch):
    from thermal_model.installed_shade_published_origin import read_compressed_calibrated_publication_capture
    live,root,_,backend,_=compressed_cycle
    result=live.run_compressed_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='published' and result['mode']=='shadow'
    assert [item for item,_ in backend.puts]==['Thermal_OriginalForecast_JSON','Thermal_Model_JSON']
    record=read_compressed_calibrated_publication_capture(Path(result['capture_path']))
    assert record['schema']=='earthship-installed-shade-origin/v13'
    assert record['numeric_capture']['schema']=='earthship-installed-shade-origin/v12'
    assert record['numeric_publication']==backend.rows['Thermal_OriginalForecast_JSON'] and record['publication']==backend.rows['Thermal_Model_JSON']
    output=json.loads(record['publication']['state'])
    reports=list(root.glob(output['release']['reportSha256']+'.installed-shade-qualification-v7.json'))
    assert len(reports)==1 and json.loads(reports[0].read_text())['report_sha256']==output['release']['reportSha256']
    assert output['release']['automaticActuation'] is False


@pytest.mark.parametrize('damage',['numeric_receipt','main_receipt','late_collection','config_drift'])
def test_compressed_cycle_failed_receipts_or_input_withdraw_without_main_capture(compressed_cycle,damage):
    live,root,_,backend,_=compressed_cycle;backend.damage=damage
    result=live.run_compressed_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='withdrawn'
    assert not list(root.glob('*.installed-shade-origin-v13.json'))
    assert backend.puts[-1][1]['status']=='unavailable' and backend.puts[-1][1]['version']==7


def test_compressed_cycle_original_loss_during_main_metadata_lookup_prevents_send(compressed_cycle):
    live,root,_,backend,args=compressed_cycle;put=backend.put
    def lost(item,state,*,preflight=None):
        if item=='Thermal_Model_JSON' and json.loads(state)['status']!='unavailable':Path(args['native_source_paths']['air']).unlink()
        return put(item,state,preflight=preflight)
    backend.put=lost
    result=live.run_compressed_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='withdrawn'
    assert not list(root.glob('*.installed-shade-origin-v13.json'))
    assert all(value['status']=='unavailable' for item,value in backend.puts if item=='Thermal_Model_JSON')


def test_compressed_cycle_duplicate_attempt_never_reposts_numeric(compressed_cycle):
    live,root,issue,backend,_=compressed_cycle
    (root/(issue.strftime('%Y%m%dT%H%M%SZ')+'.attempt.json')).write_text('{}')
    result=live.run_compressed_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='duplicate_attempt' and backend.puts==[]


def test_compressed_send_refuses_native_expiry_during_last_query_replay(compressed_cycle,monkeypatch):
    live,root,issue,backend,_=compressed_cycle;numeric=live._numeric
    def elapsed(*args,**kwargs):
        result=numeric(*args,**kwargs)
        if kwargs['available']==issue:live._test_time=issue+timedelta(minutes=3)
        return result
    monkeypatch.setattr(live,'_numeric',elapsed)
    result=live.run_compressed_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='withdrawn'
    assert all(item!='Thermal_OriginalForecast_JSON' for item,_ in backend.puts)


@pytest.mark.parametrize('kind',['calibration','development','release'])
def test_final_main_metadata_loss_of_qualification_original_prevents_send(compressed_cycle,monkeypatch,kind):
    from dataclasses import replace
    from thermal_model import installed_shade_publication as p
    from thermal_model.replay_budget import capture_source_reads
    from thermal_model.runtime_bundle import _owned_bytes
    live,root,_,backend,_=compressed_cycle
    original=root/(kind+'-original.json');original.write_bytes(b'{}');original.chmod(0o600)
    with capture_source_reads() as inventory:_owned_bytes(original,32)
    # The mathematical qualification seam now supplies the actual invocation guard.
    prepared=replace(p.prepare_compressed_installed_qualification(root/'refs'),source_guard=inventory.verify)
    monkeypatch.setattr(live,'prepare_compressed_installed_qualification',lambda _:prepared)
    monkeypatch.setattr(p,'prepare_compressed_installed_qualification',lambda _:prepared)
    put=backend.put;removed=[]
    def delayed(item,state,*,preflight=None):
        if item=='Thermal_Model_JSON' and json.loads(state)['status']!='unavailable':
            original.unlink();removed.append(True)
        return put(item,state,preflight=preflight)
    backend.put=delayed
    result=live.run_compressed_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert removed and result['status']=='withdrawn'
    assert not list(root.glob('*.installed-shade-origin-v13.json'))
    assert all(value['status']=='unavailable' for item,value in backend.puts if item=='Thermal_Model_JSON')


def test_final_guard_uses_fresh_report_preparation_and_rechecks_clock(compressed_cycle,monkeypatch):
    from dataclasses import replace
    from thermal_model import installed_shade_publication as p
    live,root,issue,backend,_=compressed_cycle;prepared=p.prepare_compressed_installed_qualification(root/'refs');calls=[]
    def obsolete():pytest.fail('initial preparation guard used instead of fresh publication authority')
    def fresh():calls.append(True);live._test_time=issue+timedelta(minutes=3)
    monkeypatch.setattr(live,'prepare_compressed_installed_qualification',lambda _:replace(prepared,source_guard=obsolete))
    monkeypatch.setattr(p,'prepare_compressed_installed_qualification',lambda _:replace(prepared,source_guard=fresh))
    result=live.run_compressed_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert calls and result['status']=='withdrawn'
    assert all(value['status']=='unavailable' for item,value in backend.puts if item=='Thermal_Model_JSON')
