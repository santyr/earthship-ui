"""Operational selection and publication policy; numerical replay tested separately."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import importlib
import pytest
from types import SimpleNamespace


def api():return importlib.import_module('weather_learning.production_scenario_worker')


@pytest.fixture(autouse=True)
def operational_transport_only(monkeypatch):
 # Resource admission itself has its existing kernel/profile tests. These
 # isolated operation tests also run on CI without the household cgroup tree.
 monkeypatch.setattr('household_cycle_pressure.PublicationHeadroom',lambda:SimpleNamespace(check=lambda:None))


def test_disabled_worker_does_not_read_selector_or_create_state(tmp_path,monkeypatch):
 def forbidden(*a,**k):pytest.fail('disabled producer read runtime inputs')
 monkeypatch.setattr(api(),'effective_selection',forbidden)
 assert api().run(state=tmp_path/'state',observation_path=tmp_path/'missing',enabled=False)['status']=='disabled'
 assert not (tmp_path/'state').exists()


def test_missing_completed_original_keeps_previous_cache(tmp_path,monkeypatch):
 stage=tmp_path/'stage';stage.mkdir();state=tmp_path/'state';state.mkdir(mode=0o700);cache=state/'scenario-advisory.json';cache.write_bytes(b'previous-original-clock')
 monkeypatch.setattr(api(),'effective_selection',lambda:dict(stage=str(stage),deployment_sha256='a'*64))
 monkeypatch.setattr(api(),'verify_stage',lambda *a,**k:None)
 monkeypatch.setattr(api(),'read_current_originals',lambda *a,**k:None)
 value=api().run(state=state,observation_path=tmp_path/'missing',enabled=True)
 assert value['status']=='awaiting_completed_origin' and cache.read_bytes()==b'previous-original-clock'


@pytest.mark.parametrize('offset',[-1,901])
def test_future_or_stale_origin_is_not_reissued(tmp_path,monkeypatch,offset):
 now=datetime(2026,10,23,17,18,tzinfo=timezone.utc);origin=now-timedelta(seconds=offset);stage=tmp_path/'stage';stage.mkdir()
 monkeypatch.setattr(api(),'effective_selection',lambda:dict(stage=str(stage),deployment_sha256='a'*64))
 monkeypatch.setattr(api(),'verify_stage',lambda *a,**k:None)
 monkeypatch.setattr(api(),'read_current_originals',lambda *a,**k:dict(energy=dict(output=dict(array_pv=dict(origin=origin.isoformat())))))
 value=api().run(state=tmp_path/'state',observation_path=tmp_path/'missing',enabled=True,clock=lambda:now)
 assert value['status']=='awaiting_fresh_origin'
 assert not (tmp_path/'state'/'scenario-advisory.json').exists()


def setup_cycle(tmp_path,monkeypatch):
 from test_scenario_reporting import args,ORIGIN
 from weather_learning.scenario_reporting import prepare_report
 from weather_learning.contracts import canonical
 module=api();a=args();report=prepare_report(**a);stage=tmp_path/'stage';stage.mkdir();energy=dict(output=dict(array_pv=dict(origin=ORIGIN.isoformat())));plan={'receipt_sha256':'b'*64}
 ep=stage/'energy.json';ep.write_bytes(canonical(energy));ep.chmod(0o600);pp=stage/'plan.json';pp.write_bytes(canonical(plan));pp.chmod(0o600)
 current=dict(energy=energy,plan=plan,energy_path=ep,originals=(ep,None,pp,None))
 selected=dict(stage=str(stage),deployment_sha256='a'*64)
 monkeypatch.setattr(module,'effective_selection',lambda:selected.copy());monkeypatch.setattr(module,'verify_stage',lambda *a,**k:None)
 monkeypatch.setattr(module,'selected_interpreter',lambda *a,**k:None);monkeypatch.setattr(module,'read_current_originals',lambda *a,**k:current)
 monkeypatch.setattr(module,'unchanged_current',lambda *a:None);monkeypatch.setattr(module,'prepare_owned_inputs',lambda **kw:{k:a[k] for k in ('forcing','household_inputs')})
 # This test isolates publication and retry semantics. Real retained-model
 # computation is independently exercised by production-context tests/probes.
 calls=[]
 def prepare(**kw):
  calls.append(kw);fresh=args();fresh['prepared_at']=kw['prepared_at'];return prepare_report(**fresh)
 monkeypatch.setattr(module,'prepare_report',prepare)
 return module,report,current,calls,ORIGIN


def test_repeated_opportunity_reuses_original_generated_and_confirmed_clocks(tmp_path,monkeypatch):
 module,report,current,calls,origin=setup_cycle(tmp_path,monkeypatch);state=tmp_path/'state'
 first=module.run(state=state,observation_path=tmp_path/'observation',enabled=True,publish=True,clock=lambda:origin+timedelta(seconds=2))
 assert first['status']=='confirmed'
 original={p.name:p.read_bytes() for p in (state/'scenario-reports').glob('*.json')};cache=(state/'scenario-advisory.json').read_bytes()
 second=module.run(state=state,observation_path=tmp_path/'observation',enabled=True,publish=True,clock=lambda:origin+timedelta(seconds=5))
 assert second['status']=='confirmed' and len(calls)==1
 assert (state/'scenario-advisory.json').read_bytes()==cache
 assert {p.name:p.read_bytes() for p in (state/'scenario-reports').glob('*.json')}==original


def test_changed_selector_after_preparation_does_not_publish(tmp_path,monkeypatch):
 module,report,current,calls,origin=setup_cycle(tmp_path,monkeypatch)
 def changed(**kw):
  monkeypatch.setattr(module,'effective_selection',lambda:dict(stage='/different',deployment_sha256='d'*64));return report
 monkeypatch.setattr(module,'prepare_report',changed)
 with pytest.raises(ValueError,match='changed'):module.run(state=tmp_path/'state',observation_path=tmp_path/'observation',enabled=True,publish=True,clock=lambda:origin+timedelta(seconds=2))
 assert not (tmp_path/'state'/'scenario-advisory.json').exists()


def test_interruption_between_original_archive_and_issue_index_preserves_first_preparation_clock(tmp_path,monkeypatch):
 module,report,current,calls,origin=setup_cycle(tmp_path,monkeypatch);state=tmp_path/'state';original_write=module._write;failed=[]
 def interrupt_index(store,path,value,guard):
  if path.name.startswith('issue-') and not failed:
   failed.append(True);raise TimeoutError('interrupted before issue index')
  return original_write(store,path,value,guard)
 monkeypatch.setattr(module,'_write',interrupt_index)
 first=module.run(state=state,observation_path=tmp_path/'observation',enabled=True,publish=True,clock=lambda:origin+timedelta(seconds=2))
 assert first['status']=='publication_uncertain'
 second=module.run(state=state,observation_path=tmp_path/'observation',enabled=True,publish=True,clock=lambda:origin+timedelta(seconds=5))
 assert second['status']=='confirmed'
 assert second['report_sha256']==first['report_sha256']
 assert len(list((state/'scenario-reports').glob('original-*.json')))==1
 assert calls[0]['prepared_at']==calls[1]['prepared_at']==origin+timedelta(seconds=2)
