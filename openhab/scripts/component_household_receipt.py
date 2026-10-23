"""Compact literal custody for selected component PV/storage forecasts."""
from pathlib import Path
from datetime import timedelta
from hashlib import sha256
from household.codec import canonical,loads,identity
from household_observation import _private_file
from household_native_training import directory
from household_ac_load_store import _immutable
from weather_learning.contracts import digest
from weather_learning.retained_scenarios import RetainedComponentInputs,COMPONENT_SCHEMA

SCHEMA='earthship-household-calibrated-energy-receipt/v2'
SUFFIX='.component-energy-v2.json'
MAX_BYTES=2*1024**2

def file_reference(path,*,limit):
 path=Path(path)
 if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved original component input required')
 raw=_private_file(path,limit)[0]
 return dict(path=str(path),bytes_sha256=sha256(raw).hexdigest(),document_sha256=identity(loads(raw)))

def read_reference(ref,*,limit):
 if not isinstance(ref,dict) or set(ref)!={'path','bytes_sha256','document_sha256'}:raise ValueError('closed original component input reference required')
 for k in ('bytes_sha256','document_sha256'):digest(ref[k])
 path=Path(ref['path'])
 if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved original component input required')
 raw=_private_file(path,limit)[0];value=loads(raw)
 if sha256(raw).hexdigest()!=ref['bytes_sha256'] or identity(value)!=ref['document_sha256']:raise ValueError('original component input bytes differ')
 return value

def retain_context(context,*,original_paths,state):
 if type(context) is not RetainedComponentInputs:raise ValueError('verified retained component household inputs required')
 value=context.to_dict();originals=value.pop('owned_sources');package=value.pop('original_source_package')
 if set(original_paths)!=set(originals):raise ValueError('same original component parents required')
 refs={}
 for name,original in originals.items():
  path=original_paths[name]
  if original is None:
   if path is not None:raise ValueError('absent original component parent required')
   refs[name]=None
  else:
   ref=file_reference(path,limit=MAX_BYTES)
   if ref['document_sha256']!=identity(original):raise ValueError('same original component parent required')
   refs[name]=ref
 root=directory(Path(state)/'packages');raw=canonical(package);path=root/(sha256(raw).hexdigest()+'.source-package.json')
 _immutable(path,raw);ref=file_reference(path,limit=16*1024**2)
 compact=dict(value,original_references=refs,source_package=ref)
 if expand_context(compact)!=context.to_dict():raise ValueError('literal original context custody differs')
 return compact

def expand_context(compact):
 fields={'schema','producer','prepared','original_source_manifest','adapter_source_sha256','native_environment','native_binary_files','context_sha256','original_references','source_package'}
 if not isinstance(compact,dict) or set(compact)!=fields or compact['schema']!=COMPONENT_SCHEMA:raise ValueError('closed compact original component context required')
 value={k:v for k,v in compact.items() if k not in ('original_references','source_package')}
 refs=compact['original_references']
 if not isinstance(refs,dict) or set(refs)!={'energy','plan','profiled'}:raise ValueError('closed original component parent references required')
 if refs['energy'] is None or refs['plan'] is None:raise ValueError('original component energy and plan required')
 value['owned_sources']={k:None if ref is None else read_reference(ref,limit=MAX_BYTES) for k,ref in refs.items()}
 value['original_source_package']=read_reference(compact['source_package'],limit=16*1024**2)
 if value['context_sha256']!=identity({k:v for k,v in value.items() if k!='context_sha256'}):raise ValueError('original component context changed')
 return value


def seal(context,*,owner,original_paths,state,assessed_at):
 from household.control_contracts import instant
 from household_component_energy import project_inputs
 from weather_learning.production_pv_runtime import runtime_manifest
 owner.verify();value=context.to_dict();origin=instant(value['prepared']['issued_at'])
 if not origin<=assessed_at<=origin+timedelta(seconds=85):raise ValueError('bounded original component assessment required')
 forcing,out=project_inputs(owner,context)
 compact=retain_context(context,original_paths=original_paths,state=state)
 owners=directory(Path(state)/'owners');profile=owners/(sha256(owner.raw).hexdigest()+'.profile.json')
 _immutable(profile,owner.raw)
 receipt=dict(schema=SCHEMA,issued=False,inputs=dict(context=compact,owner_profile=file_reference(profile,limit=32768),
  original_energy_document_sha256=identity(value['owned_sources']['energy']),original_profiled_document_sha256=None if value['owned_sources']['profiled'] is None else identity(value['owned_sources']['profiled']),
  original_energy_receipt_sha256=value['owned_sources']['energy']['receipt_sha256'],plan_receipt_sha256=value['owned_sources']['plan']['receipt_sha256'],
  assessed_at=assessed_at.isoformat(),source_freshness_basis='qualified_original_issue_with_85_second_publication_deadline'),
  native_forecast=forcing,runtime_manifest=runtime_manifest(),output=out,automatic_actuation=False)
 from household_calibrated_outcomes import _predictions
 receipt['inputs']['outcome_cohort_id']=_predictions(receipt,value['owned_sources']['plan'],value['owned_sources']['profiled'])['cohort_id']
 receipt['receipt_sha256']=identity(receipt)
 if len(canonical(receipt))>MAX_BYTES:raise ValueError('bounded original component household receipt required')
 owner.verify();return loads(canonical(receipt))

def validate(receipt):
 if (not isinstance(receipt,dict) or set(receipt)!={'schema','issued','inputs','native_forecast','runtime_manifest','output','automatic_actuation','receipt_sha256'} or
  receipt['schema']!=SCHEMA or receipt['issued'] is not False or receipt['automatic_actuation'] is not False or
  receipt['receipt_sha256']!=identity({k:v for k,v in receipt.items() if k!='receipt_sha256'}) or len(canonical(receipt))>MAX_BYTES):
  raise ValueError('unchanged original component household receipt required')
 return receipt

def replay(receipt,*,guard=lambda:None):
 """Use original assessment time only for an explicitly frozen replay."""
 from household.control_contracts import instant
 from household_component_energy import project_inputs
 from weather_learning.retained_scenarios import restore_component_inputs
 from weather_learning.production_pv_runtime import ComponentOwner,runtime_manifest
 validate(receipt)
 if receipt['runtime_manifest']!=runtime_manifest():raise ValueError('original component runtime required')
 inputs=receipt['inputs'];value=expand_context(inputs['context']);context=restore_component_inputs(value,guard=guard)
 ref=inputs['owner_profile'];read_reference(ref,limit=32768)
 owner=ComponentOwner(ref['path'],expected_sha256=ref['bytes_sha256'],clock=lambda:instant(inputs['assessed_at']),guard=guard)
 forcing,out=project_inputs(owner,context)
 owned=value['owned_sources']
 if (inputs['original_energy_document_sha256']!=identity(owned['energy']) or
  inputs['original_energy_receipt_sha256']!=owned['energy']['receipt_sha256'] or inputs['plan_receipt_sha256']!=owned['plan']['receipt_sha256'] or
  inputs['original_profiled_document_sha256']!=(None if owned['profiled'] is None else identity(owned['profiled'])) or
  canonical(forcing)!=canonical(receipt['native_forecast']) or canonical(out)!=canonical(receipt['output'])):
  raise ValueError('original component household projection differs')
 from household_calibrated_outcomes import _predictions
 if inputs['outcome_cohort_id']!=_predictions(receipt,owned['plan'],owned['profiled'])['cohort_id']:raise ValueError('original component outcome cohort differs')
 return receipt
