"""Do not select an in-progress energy receipt before the observer commits it."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import pytest
from household.codec import canonical,identity

T=datetime(2026,10,23,5,5,15,tzinfo=timezone.utc)

def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);raw=canonical(value);path.write_bytes(raw);path.chmod(0o600);return path

def originals(root,tag,*,profile=True):
 plan=dict(receipt_sha256=tag*64,inputs={});doc=identity(plan)
 write(root/(doc+'.household-model-plan-v6.json'),plan)
 energy=dict(schema='earthship-household-energy-forecast-receipt/v1',inputs=dict(plan_document_sha256=doc,plan_receipt_sha256=plan['receipt_sha256']),
  output=dict(array_pv=dict(origin=T.isoformat())))
 energy['receipt_sha256']=identity(energy);pin=identity(energy)
 path=write(root/(pin+'.household-energy-forecast-v1.json'),energy)
 if profile:
  value=dict(schema='earthship-household-profiled-energy-receipt/v1',inputs=dict(original_energy_document_sha256=pin,original_energy_receipt_sha256=energy['receipt_sha256']))
  value['receipt_sha256']=identity(value);write(root/(identity(value)+'.household-profiled-energy-v1.json'),value)
 return path,plan

def observed(path,plan):
 return write(path,dict(schema='earthship-household-observation/v1',receipt_sha256=plan['receipt_sha256'],automatic_actuation=False))


def test_energy_appearing_first_cannot_replace_the_complete_observed_pair(tmp_path):
 from component_household_files import read_current_originals
 evidence=tmp_path/'stage/evidence';old,a=originals(evidence,'a');obs=observed(tmp_path/'observation.json',a)
 new,b=originals(evidence,'b',profile=False)
 value=read_current_originals(tmp_path/'stage',obs)
 assert value['energy_path']==old and value['profiled'] is not None
 observed(obs,b);value=read_current_originals(tmp_path/'stage',obs)
 assert value['energy_path']==new and value['profiled'] is None


def test_observer_commit_selects_the_matching_profile_and_refuses_changed_cache(tmp_path):
 from component_household_files import read_current_originals,unchanged_current
 evidence=tmp_path/'stage/evidence';old,a=originals(evidence,'a');new,b=originals(evidence,'b')
 obs=observed(tmp_path/'observation.json',b);value=read_current_originals(tmp_path/'stage',obs)
 assert value['energy_path']==new and value['profiled']['inputs']['original_energy_document_sha256']==identity(value['energy'])
 unchanged_current(value);observed(obs,a)
 with pytest.raises(ValueError):unchanged_current(value)


def test_missing_current_plan_is_awaited_without_borrowing_another_origin(tmp_path):
 from component_household_files import read_current_originals
 evidence=tmp_path/'stage/evidence';_,a=originals(evidence,'a')
 obs=observed(tmp_path/'observation.json',dict(receipt_sha256='f'*64))
 assert read_current_originals(tmp_path/'stage',obs) is None

def test_current_observation_v4_keeps_the_same_original_plan_link(tmp_path):
 from component_household_files import read_current_originals
 path,plan=originals(tmp_path/'stage/evidence','c')
 obs=write(tmp_path/'observation.json',dict(schema='earthship-household-observation/v4',receipt_sha256=plan['receipt_sha256'],automatic_actuation=False))
 assert read_current_originals(tmp_path/'stage',obs)['energy_path']==path
