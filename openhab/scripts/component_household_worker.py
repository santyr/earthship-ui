#!/usr/bin/env python3
"""Replace calibrated household PV publication using the selected component fit."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import argparse,json,os,stat,shutil,time,traceback
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household_native_training import effective_selection,directory,save
from household_cycle_deploy import verify_stage
from household_observation import _private_file
from household_ac_load_store import _immutable
from component_household_files import read_current_originals,unchanged_current
from component_household_receipt import seal,SUFFIX,MAX_BYTES
from weather_learning.retained_scenarios import prepare_component_inputs,producer_reference,PRODUCER_SCHEMA
from weather_learning.production_pv_runtime import ComponentOwner
from weather_learning.worker import collector_lock

EMISSION_SUFFIX='.component-emission-v1.json'

def capacity(state,additional,*,guard):
 count=0;used=0;pending=[(Path(state),0)]
 while pending:
  root,depth=pending.pop()
  if root.resolve()!=root:raise ValueError('resolved original household namespace required')
  with os.scandir(root) as entries:
   for entry in entries:
    count+=1
    if count+4>10000:raise ValueError('original household capacity exhausted')
    if count%100==0:guard()
    info=entry.stat(follow_symlinks=False)
    if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:raise ValueError('private owned household namespace required')
    if stat.S_ISDIR(info.st_mode):
     if depth!=0 or entry.name not in ('forecasts','packages','owners','outcomes'):raise ValueError('bounded household capacity directories required')
     pending.append((Path(entry.path),depth+1))
    elif stat.S_ISREG(info.st_mode) and info.st_nlink==1:used+=info.st_size
    else:raise ValueError('regular original household capacity files required')
    if used+additional>2*1024**3:raise ValueError('original household capacity exhausted')
 if shutil.disk_usage(state).free<additional+32*1024**2:raise ValueError('household publication disk reserve exhausted')
 guard()

def curated(receipt,prepared,*,generated):
 out=receipt['output'];origin=instant(out['issued_at']);storage=out['profiled_storage'];available=storage['status']=='conditional_nominal_simulation'
 load=prepared['load_forecast'];model=prepared['load_model'];load_available=load is not None and load['status']=='projected'
 trajectory=[]
 if load_available:
  if model is None:raise ValueError('original learned-load model required')
  for i,row in enumerate(load['trajectory']):
   if available and (storage['trajectory'][i]['at']!=row['at'] or out['uncalibrated_profiled_storage']['trajectory'][i]['at']!=row['at']):
    raise ValueError('same original component/load storage targets required')
   trajectory.append(dict(at=row['at'],mean_ac_w=row['mean_ac_w'],minimum_support_days=row['minimum_support_days'],training_spread_ac_w=row['training_spread_mean_w'],
    calibrated_soc_pct=None if not available else storage['trajectory'][i]['nominal_soc_pct'],raw_soc_pct=None if not available else out['uncalibrated_profiled_storage']['trajectory'][i]['nominal_soc_pct']))
 view=dict(schema='earthship-household-calibrated-energy-observation/v4',generated_at=generated.isoformat(),issued_at=origin.isoformat(),
  valid_until=(origin+timedelta(minutes=15)).isoformat(),receipt_sha256=receipt['receipt_sha256'],
  original_energy_receipt_sha256=receipt['inputs'].get('original_energy_receipt_sha256'),
  calibration_model_sha256=out['calibration_model_sha256'],calibration_policy_sha256=out['calibration_policy_sha256'],
  calibration_sha256=out['calibration_sha256'],procedure_sha256=out['procedure_sha256'],baseline_rule=out['baseline_rule'],
  cohort_id=receipt['inputs']['outcome_cohort_id'],measurement_cohort_sha256=out['measurement_cohort_sha256'],
  calibration_scope=out['calibration_scope'],calibration_mode=out['calibration_mode'],source_support=out['source_support'],
  status=out['status'],reason=out['reason'],raw_potential_kwh=out['raw_potential_kwh'],calibrated_potential_kwh=out['calibrated_potential_kwh'],
  load_status='projected' if load_available else 'unavailable',load_model_sha256=None if not load_available else model['model_sha256'],
  load_trained_through=None if not load_available else model['trained_through'],load_training_cutoff=None if not load_available else model['training_cutoff'],
  load_total_ac_kwh=None if not load_available else load['total_ac_kwh'],profiled_storage_status=storage['status'],profiled_storage_reason=storage['reason'],
  profiled_captured_pv_kwh=None if not available else storage['modeled_captured_pv_kwh'],
  raw_profiled_captured_pv_kwh=None if not available else out['uncalibrated_profiled_storage']['modeled_captured_pv_kwh'],
  initial_soc_pct=None if not available else storage['initial_soc_pct'],nominal_bank_kwh=None if not available else storage['nominal_bank_kwh'],
  trajectory=trajectory,source_freshness_basis=receipt['inputs']['source_freshness_basis'],confidence='experimental_native_component_model',
  physical_calibration_qualified=False,automatic_actuation=False)
 view['view_sha256']=identity(view)
 if len(canonical(view))>32768:raise ValueError('bounded curated component household view required')
 return view

def _already_published(store,*,origin,profile_sha256,guard):
 with os.scandir(store) as entries:
  for i,entry in enumerate(entries):
   if i>=10000:raise ValueError('bounded original household emission inventory required')
   if i%100==0:guard()
   if not entry.name.endswith(EMISSION_SUFFIX):continue
   raw=_private_file(Path(entry.path),32768)[0];value=loads(raw)
   if entry.name!=sha256(raw).hexdigest()+EMISSION_SUFFIX or value.get('schema')!='earthship-confirmed-component-household-emission/v1' or value.get('emission_sha256')!=identity({k:v for k,v in value.items() if k!='emission_sha256'}):
    raise ValueError('unchanged original household emission required')
   if value['issued_at']==origin.isoformat() and value['owner_profile_sha256']==profile_sha256:
    return value
 return None

def run(*,state,view,profile_path,profile_sha256,observation_path,producer=None,publish=False,clock=lambda:datetime.now(timezone.utc),guard=lambda:None):
 from household_cycle_pressure import PublicationHeadroom
 if type(publish) is not bool:raise ValueError('explicit component publication mode required')
 state=directory(state);store=directory(state/'forecasts');started=time.monotonic();pressure=PublicationHeadroom()
 def check():
  guard();pressure.check()
  if time.monotonic()-started>80:raise TimeoutError('component household publication opportunity elapsed')
 with collector_lock(state/'worker.lock'):
  check();selected=effective_selection();stage=Path(selected['stage']);verify_stage(stage,expected_deployment_sha256=selected['deployment_sha256'])
  current=read_current_originals(stage,observation_path,guard=check)
  if current is None:return dict(status='awaiting_original_energy_forecast',production_states_written=False,automatic_actuation=False)
  energy=current['energy'];origin=instant(energy['output']['array_pv']['origin'])
  if not origin<=clock()<=origin+timedelta(seconds=85):return dict(status='awaiting_fresh_origin',production_states_written=False,automatic_actuation=False)
  if publish:
   previous=_already_published(store,origin=origin,profile_sha256=profile_sha256,guard=check)
   if previous is not None:return dict(status='component_household_already_published',emission_sha256=previous['emission_sha256'],production_states_written=False,automatic_actuation=False)
  owner=ComponentOwner(profile_path,expected_sha256=profile_sha256,clock=clock,guard=check)
  producer=producer_reference(producer or dict(schema=PRODUCER_SCHEMA,stage=str(stage),deployment_sha256=selected['deployment_sha256']))
  if producer['stage']!=str(stage) or producer['deployment_sha256']!=selected['deployment_sha256']:raise ValueError('current original household producer required')
  context=prepare_component_inputs(energy=energy,plan=current['plan'],profiled=current['profiled'],producer=producer,guard=check)
  # The source package is retained once per generation, not once per issue.
  capacity(state,len(canonical(context.to_dict()))+2*MAX_BYTES+16384,guard=check)
  receipt=seal(context,owner=owner,original_paths=dict(energy=current['energy_path'],plan=current['originals'][2],profiled=current['profiled_path']),state=state,assessed_at=clock())
  encoded=canonical(receipt);target=store/(sha256(encoded).hexdigest()+SUFFIX)
  unchanged_current(current)
  if effective_selection()!=selected:raise ValueError('original household selector changed')
  owner.verify();check();capacity(state,len(encoded)+16384,guard=check);_immutable(target,encoded)
  result=dict(status='component_household_prepared',receipt_sha256=receipt['receipt_sha256'],production_states_written=False,
   calibration_sha256=owner.body['calibration_sha256'],automatic_actuation=False)
  if not publish:return result
  output=Path(view)
  if not output.is_absolute() or output.resolve()!=output:raise ValueError('resolved component household cache required')
  directory(output.parent)
  try:old=loads(_private_file(output,32768)[0])
  except FileNotFoundError:old=None
  if old is not None and old.get('schema') not in tuple('earthship-household-calibrated-energy-observation/v'+str(i) for i in range(1,5)):
   raise ValueError('household cache belongs to another producer')
  generated=clock()
  if not origin<=generated<=origin+timedelta(seconds=85):raise ValueError('original component household publication expired')
  payload=curated(receipt,context.to_dict()['prepared'],generated=generated);raw=canonical(payload)
  unchanged_current(current)
  if effective_selection()!=selected:raise ValueError('original household selector changed before publication')
  owner.verify();check();published=False
  try:
   save(output,payload)
   if _private_file(output,32768)[0]!=raw:raise ValueError('component household cache readback differs')
   published=True;completed=clock()
   if completed>origin+timedelta(seconds=85):raise ValueError('original component publication expired during cache write')
   unchanged_current(current)
   if effective_selection()!=selected:raise ValueError('original household selector changed during publication')
   owner.verify();check()
   emission=dict(schema='earthship-confirmed-component-household-emission/v1',issued=True,issued_at=origin.isoformat(),published_at=completed.isoformat(),
    receipt_sha256=receipt['receipt_sha256'],receipt_file_sha256=sha256(encoded).hexdigest(),owner_profile_sha256=profile_sha256,
    view_bytes_sha256=sha256(raw).hexdigest(),view=payload,automatic_actuation=False)
   emission['emission_sha256']=identity(emission);encoded_emission=canonical(emission)
   _immutable(store/(sha256(encoded_emission).hexdigest()+EMISSION_SUFFIX),encoded_emission)
  except Exception as error:
   return dict(result,status='PUBLISHED' if published else 'PUBLICATION_UNCERTAIN',production_states_written=True if published else None,
    production_retention_status='FAILED_AFTER_PUBLICATION' if published else 'UNKNOWN_PARTIAL',reason=type(error).__name__)
  return dict(result,status='component_household_published',production_states_written=True,production_retention_status='CONFIRMED',
   emission_sha256=emission['emission_sha256'],seconds=time.monotonic()-started)

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--state',type=Path,default=Path.home()/'.local/state/household-intel/calibrated-energy')
 p.add_argument('--view',type=Path,default=Path.home()/'.local/state/household-intel/calibrated-energy-observation.json')
 p.add_argument('--observation',type=Path,default=Path.home()/'.local/state/household-intel/observation.json')
 p.add_argument('--profile',type=Path,required=True);p.add_argument('--profile-sha256',required=True);p.add_argument('--producer-reference',type=Path)
 p.add_argument('--publish',action='store_true');a=p.parse_args(argv);os.umask(0o077)
 try:
  producer=None if a.producer_reference is None else loads(_private_file(a.producer_reference,32768)[0])
  result=run(state=a.state,view=a.view,profile_path=a.profile,profile_sha256=a.profile_sha256,observation_path=a.observation,producer=producer,publish=a.publish)
  try:save(a.state/'last-result.json',dict(result,checked_at=datetime.now(timezone.utc).isoformat()))
  except Exception as error:
   result=dict(result,status='PUBLISHED' if result.get('production_states_written') is True else result['status'],
    monitoring_status='FAILED_AFTER_PUBLICATION' if result.get('production_states_written') is True else 'FAILED',monitoring_reason=type(error).__name__)
   print(json.dumps(result),flush=True);return 1
  print(json.dumps(result),flush=True)
  return 1 if result['status'] in ('PUBLISHED','PUBLICATION_UNCERTAIN') else 0
 except Exception as error:
  try:
   directory(a.state);save(a.state/'last-error.json',dict(reason=type(error).__name__,traceback=traceback.format_exc()[-8192:]))
  except Exception:pass
  print(json.dumps(dict(status='component_household_withheld',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
