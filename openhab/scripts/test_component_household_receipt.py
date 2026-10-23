"""Literal compact custody, original replay and confirmed publication gates."""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
import pytest
from household.codec import canonical,identity
from household_native_training import directory

def write(path,value):
 directory(path.parent);path.write_bytes(canonical(value));path.chmod(0o600);return path

def fixture_context(tmp_path):
 from weather_learning import retained_scenarios as boundary
 owned=dict(energy={'receipt_sha256':'e'*64},plan={'receipt_sha256':'p'*64},profiled=None)
 refs={k:None if v is None else write(tmp_path/'evidence'/(k+'.json'),v) for k,v in owned.items()}
 value=dict(schema=boundary.COMPONENT_SCHEMA,producer=dict(schema=boundary.PRODUCER_SCHEMA,stage=str(tmp_path),deployment_sha256='a'*64),
  owned_sources=owned,prepared={'issued_at':'2026-06-21T12:00:00+00:00'},original_source_manifest={'original.py':'f'*64},
  original_source_package={'original.py':'original compressed bytes'},adapter_source_sha256='c'*64,
  native_environment={'fixture':True},native_binary_files={})
 value['context_sha256']=identity(value)
 result=object.__new__(boundary.RetainedComponentInputs)
 object.__setattr__(result,'_content',canonical(value));object.__setattr__(result,'_seal',boundary._SEAL)
 return result,refs

def test_compact_originals_reconstruct_exact_context_without_copying_source_per_origin(tmp_path):
 from component_household_receipt import retain_context,expand_context
 context,refs=fixture_context(tmp_path);state=directory(tmp_path/'state')
 compact=retain_context(context,original_paths=refs,state=state)
 assert 'original_source_package' not in compact and 'owned_sources' not in compact
 assert expand_context(compact)==context.to_dict()
 second=retain_context(context,original_paths=refs,state=state)
 assert compact==second and len(list((state/'packages').iterdir()))==1
 assert compact['context_sha256']==context.to_dict()['context_sha256']

def test_compact_context_refuses_tampered_original_bytes_and_package(tmp_path):
 from component_household_receipt import retain_context,expand_context
 context,refs=fixture_context(tmp_path);compact=retain_context(context,original_paths=refs,state=directory(tmp_path/'state'))
 original=refs['energy'].read_bytes();refs['energy'].write_bytes(original+b'\n')
 with pytest.raises(ValueError,match='original'):expand_context(compact)
 refs['energy'].write_bytes(original)
 package=Path(compact['source_package']['path']);package.write_bytes(package.read_bytes()+b'\n')
 with pytest.raises(ValueError,match='original'):expand_context(compact)

def test_compact_context_rejects_unmatched_parent_even_when_a_valid_other_file_exists(tmp_path):
 from component_household_receipt import retain_context
 context,refs=fixture_context(tmp_path);refs['energy']=write(tmp_path/'other.json',{'receipt_sha256':'b'*64})
 with pytest.raises(ValueError,match='original'):retain_context(context,original_paths=refs,state=directory(tmp_path/'state'))
