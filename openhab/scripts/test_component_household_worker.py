"""Publication truth, retained originals and bounded private preparation."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from hashlib import sha256
from types import SimpleNamespace
import pytest
from household.codec import canonical,identity
from household_native_training import directory

ISSUE=datetime(2026,6,21,12,tzinfo=timezone.utc)

def output():
 return dict(issued_at=ISSUE.isoformat(),profiled_storage=dict(status='unavailable',reason='load_model_unavailable'),
  uncalibrated_profiled_storage=None,raw_potential_kwh=5.,calibrated_potential_kwh=4.,calibration_model_sha256='a'*64,
  calibration_policy_sha256='b'*64,calibration_sha256='c'*64,procedure_sha256='d'*64,baseline_rule='fixture_native_components',
  measurement_cohort_sha256='c'*64,calibration_scope='native_components_only',calibration_mode='experimental_production',source_support={'fixture':True},
  confidence='experimental_native_component_model',status='projected_provisional_calibrated_potential',reason=None)

@pytest.fixture
def cycle(tmp_path,monkeypatch):
 import component_household_worker as worker
 import household_cycle_pressure
 # Publication behavior is independent of a runner's cgroup. Resource-policy
 # refusals have their own lower-level tests and the real managed preview.
 monkeypatch.setattr(household_cycle_pressure,'PublicationHeadroom',lambda:SimpleNamespace(check=lambda:None))
 state=directory(tmp_path/'state');view=tmp_path/'view.json';profile=tmp_path/'profile.json';profile.write_bytes(b'{}');profile.chmod(0o600)
 energy=dict(receipt_sha256='e'*64,output={'array_pv':{'origin':ISSUE.isoformat()}})
 current=dict(energy=energy,plan={},profiled=None,energy_path=tmp_path/'energy',profiled_path=None,originals=(None,None,tmp_path/'plan',None))
 selected=dict(stage=str(tmp_path/'stage'),deployment_sha256='f'*64)
 monkeypatch.setattr(worker,'effective_selection',lambda:selected)
 monkeypatch.setattr(worker,'verify_stage',lambda *a,**k:None)
 monkeypatch.setattr(worker,'read_current_originals',lambda *a,**k:current)
 monkeypatch.setattr(worker,'unchanged_current',lambda value:None)
 monkeypatch.setattr(worker,'prepare_component_inputs',lambda **k:SimpleNamespace(to_dict=lambda:dict(prepared={'issued_at':ISSUE.isoformat(),'load_forecast':None,'load_model':None})))
 class Owner:
  def __init__(self,*a,**k):self.body={'calibration_sha256':'c'*64};self.raw=b'{}'
  def verify(self):return True
 monkeypatch.setattr(worker,'ComponentOwner',Owner)
 receipt=dict(schema='earthship-household-calibrated-energy-receipt/v2',issued=False,inputs=dict(source_freshness_basis='qualified_original_issue_with_85_second_publication_deadline',original_energy_receipt_sha256='e'*64,
   outcome_cohort_id='f'*64,assessed_at=(ISSUE+timedelta(seconds=30)).isoformat(),owner_profile={'bytes_sha256':sha256(b'{}').hexdigest()},context={'prepared':{'load_forecast':None,'load_model':None}}),
  output=output(),native_forecast={},runtime_manifest={},automatic_actuation=False)
 receipt['receipt_sha256']=identity(receipt)
 monkeypatch.setattr(worker,'seal',lambda *a,**k:receipt)
 args=dict(state=state,view=view,profile_path=profile,profile_sha256=sha256(b'{}').hexdigest(),observation_path=tmp_path/'observation',clock=lambda:ISSUE+timedelta(seconds=30),guard=lambda:None)
 return worker,args,receipt

def test_default_worker_is_private_and_retains_original_before_any_cache(cycle):
 worker,args,receipt=cycle;result=worker.run(**args)
 assert result['status']=='component_household_prepared' and result['production_states_written'] is False
 assert not args['view'].exists() and len(list((args['state']/'forecasts').glob('*.component-energy-v2.json')))==1
 assert not list((args['state']/'forecasts').glob('*.component-emission-v1.json'))

def test_confirmed_worker_publication_records_actual_cache_bytes_and_does_not_reissue(cycle):
 worker,args,receipt=cycle;result=worker.run(**args,publish=True)
 assert result['status']=='component_household_published' and result['production_retention_status']=='CONFIRMED'
 raw=args['view'].read_bytes();view=__import__('json').loads(raw)
 assert view['schema']=='earthship-household-calibrated-energy-observation/v4'
 assert view['procedure_sha256']=='d'*64 and view['confidence']=='experimental_native_component_model'
 emissions=list((args['state']/'forecasts').glob('*.component-emission-v1.json'));assert len(emissions)==1
 emission=__import__('json').loads(emissions[0].read_bytes())
 assert emission['view_bytes_sha256']==sha256(raw).hexdigest() and emission['published_at']==args['clock']().isoformat()
 assert emission['receipt_sha256']==receipt['receipt_sha256'] and emission['issued'] is True
 assert worker.run(**args,publish=True)['status']=='component_household_already_published'
 assert args['view'].read_bytes()==raw and len(list((args['state']/'forecasts').glob('*.component-emission-v1.json')))==1

def test_failed_emission_preserves_truth_that_cache_was_published(cycle,monkeypatch):
 worker,args,_=cycle;original=worker._immutable
 def fail(path,raw):
  if str(path).endswith('.component-emission-v1.json'):raise OSError('test retention failure')
  return original(path,raw)
 monkeypatch.setattr(worker,'_immutable',fail)
 result=worker.run(**args,publish=True)
 assert result['status']=='PUBLISHED' and result['production_states_written'] is True
 assert result['production_retention_status']=='FAILED_AFTER_PUBLICATION'
 assert args['view'].exists()

def test_uncertain_cache_readback_reports_unknown_instead_of_claiming_preservation(cycle,monkeypatch):
 worker,args,_=cycle;save=worker.save
 def uncertain(path,value):
  save(path,value)
  if Path(path)==args['view']:raise OSError('test readback uncertainty')
 monkeypatch.setattr(worker,'save',uncertain)
 result=worker.run(**args,publish=True)
 assert result['status']=='PUBLICATION_UNCERTAIN' and result['production_states_written'] is None
 assert result['production_retention_status']=='UNKNOWN_PARTIAL'
 assert args['view'].exists()

def test_capacity_or_changed_originals_refuse_before_public_cache(cycle,monkeypatch):
 worker,args,_=cycle
 def refuse(*a,**k):raise ValueError('originals changed')
 monkeypatch.setattr(worker,'unchanged_current',refuse)
 with pytest.raises(ValueError):worker.run(**args,publish=True)
 assert not args['view'].exists()

def test_expired_original_is_not_reissued_using_a_new_clock(cycle):
 worker,args,_=cycle;args['clock']=lambda:ISSUE+timedelta(seconds=86)
 result=worker.run(**args,publish=True)
 assert result['status']=='awaiting_fresh_origin' and not args['view'].exists()


def test_confirmed_inventory_requires_the_exact_emitted_view_and_original_receipt(cycle):
 from component_household_confirmation import read_confirmed_forecast,confirmed_inventory
 worker,args,receipt=cycle
 worker.run(**args,publish=True);store=args['state']/'forecasts'
 path=next(store.glob('*.component-energy-v2.json'))
 assert read_confirmed_forecast(path)==receipt
 assert len(confirmed_inventory(store,now=args['clock'](),guard=lambda:None))==1
 emission_path=next(store.glob('*.component-emission-v1.json'))
 emission=__import__('json').loads(emission_path.read_bytes())
 emission['view']['calibrated_potential_kwh']+=1
 emission['view_bytes_sha256']=sha256(canonical(emission['view'])).hexdigest()
 emission['emission_sha256']=identity({k:v for k,v in emission.items() if k!='emission_sha256'})
 raw=canonical(emission);emission_path.unlink()
 other=store/(sha256(raw).hexdigest()+'.component-emission-v1.json');other.write_bytes(raw);other.chmod(0o600)
 with pytest.raises(ValueError,match='view/clock/profile'):read_confirmed_forecast(path)


def test_emission_time_cannot_be_resealed_after_the_original_publication_deadline(cycle):
 from component_household_confirmation import confirmed_inventory
 worker,args,_=cycle;worker.run(**args,publish=True);store=args['state']/'forecasts'
 path=next(store.glob('*.component-emission-v1.json'));value=__import__('json').loads(path.read_bytes())
 value['published_at']=(ISSUE+timedelta(seconds=86)).isoformat()
 value['emission_sha256']=identity({k:v for k,v in value.items() if k!='emission_sha256'})
 raw=canonical(value);path.unlink();path=store/(sha256(raw).hexdigest()+'.component-emission-v1.json');path.write_bytes(raw);path.chmod(0o600)
 with pytest.raises(ValueError,match='view/clock/profile'):confirmed_inventory(store,now=ISSUE+timedelta(seconds=90),guard=lambda:None)


def test_cli_monitoring_failure_after_confirmed_publication_returns_nonzero_with_publication_truth(tmp_path,monkeypatch,capsys):
 import component_household_worker as worker
 published=dict(status='component_household_published',production_states_written=True,production_retention_status='CONFIRMED',automatic_actuation=False)
 monkeypatch.setattr(worker,'run',lambda **k:published)
 def fail(*a,**k):raise OSError('test monitor failure')
 monkeypatch.setattr(worker,'save',fail)
 import os
 previous_mask=os.umask(0o077)
 try:result=worker.main(['--state',str(tmp_path/'state'),'--profile',str(tmp_path/'profile'),'--profile-sha256','a'*64])
 finally:os.umask(previous_mask)
 assert result==1
 value=__import__('json').loads(capsys.readouterr().out)
 assert value['production_states_written'] is True and value['production_retention_status']=='CONFIRMED'
 assert value['status']=='PUBLISHED' and value['monitoring_status']=='FAILED_AFTER_PUBLICATION'


def test_full_archive_withholds_new_cache_without_deleting_originals(cycle):
 worker,args,_=cycle;path=args['state']/'retained-original'
 import os
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 try:os.ftruncate(fd,2*1024**3)
 finally:os.close(fd)
 with pytest.raises(ValueError,match='capacity'):worker.run(**args,publish=True)
 assert not args['view'].exists() and path.stat().st_size==2*1024**3


def test_disk_reserve_is_checked_before_any_public_cache(cycle,monkeypatch):
 worker,args,_=cycle
 monkeypatch.setattr(worker.shutil,'disk_usage',lambda *a:SimpleNamespace(free=32*1024**2))
 with pytest.raises(ValueError,match='disk reserve'):worker.run(**args,publish=True)
 assert not args['view'].exists()


def test_current_family_interpreter_follows_initial_and_daily_replacement_stage(cycle,tmp_path,monkeypatch):
 worker,args,_=cycle
 from weather_learning.retained_scenarios import PRODUCER_V2
 binary=tmp_path/'retained-python3.12';binary.write_bytes(b'explicit retained test interpreter');binary.chmod(0o500)
 ref=dict(path=str(binary),sha256=sha256(binary.read_bytes()).hexdigest())
 active=[dict(stage=str(tmp_path/'initial-stage'),deployment_sha256='a'*64)]
 contexts=[];family_checks=[];prepare=worker.prepare_component_inputs
 monkeypatch.setattr(worker,'effective_selection',lambda:dict(active[0]))
 def family(stage,*,deployment_sha256,guard):
  assert str(stage)==active[0]['stage'] and deployment_sha256==active[0]['deployment_sha256']
  family_checks.append((str(stage),deployment_sha256));guard();return ref
 monkeypatch.setattr(worker,'selected_interpreter',family,raising=False)
 def inputs(**kwargs):
  producer=kwargs['producer'];contexts.append(dict(producer))
  assert producer==dict(schema=PRODUCER_V2,**active[0],python_path=ref['path'],python_sha256=ref['sha256'])
  return prepare(**kwargs)
 monkeypatch.setattr(worker,'prepare_component_inputs',inputs)
 assert worker.run(**args)['status']=='component_household_prepared'
 active[0]=dict(stage=str(tmp_path/'daily-replacement-stage'),deployment_sha256='b'*64)
 assert worker.run(**args)['status']=='component_household_prepared'
 assert len(contexts)==len(family_checks)==2 and contexts[0]['stage']!=contexts[1]['stage']
 assert not args['view'].exists()


def test_explicit_original_producer_is_not_silently_retargeted_to_a_new_selection(cycle,tmp_path):
 worker,args,_=cycle
 from weather_learning.retained_scenarios import PRODUCER_SCHEMA
 original=dict(schema=PRODUCER_SCHEMA,stage=str(tmp_path/'original-stage'),deployment_sha256='c'*64)
 with pytest.raises(ValueError,match='current original household producer'):worker.run(**args,producer=original)
 assert not args['view'].exists()
