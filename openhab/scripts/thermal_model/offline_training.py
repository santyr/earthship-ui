"""Train from frozen private inputs with explicit workload opt-in.

The normal pipeline retains every artifact/numerical/promotion gate. This module
never queries household services or grants production release authority.
"""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import os
from pathlib import Path
from uuid import uuid4

from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc,_sha
from .training_inputs import restore_training_inputs,restore_training_inputs_v2,write_training_inputs,write_training_inputs_v2,_bounded,SENSOR_SCHEMA as SENSOR_INPUT_SCHEMA
from .training_assembly import verify_training_assembly,write_training_assembly,verify_training_assembly_v2,write_training_assembly_v2
from .pipeline import run_training
from .training_sources import write_training_sources,write_training_sources_v2
from .fit_evidence import write_fit_evidence
from .runtime_bundle import _write_private,_owned_bytes,_sync_directory
from .rollback import _rename_new

SCHEMA='earthship-thermal-training-input-binding/v1'
ASSEMBLED_SCHEMA='earthship-thermal-training-input-binding/v2'
SENSOR_BINDING_SCHEMA='earthship-thermal-training-input-binding/v3'
SENSOR_ASSEMBLED_SCHEMA='earthship-thermal-training-input-binding/v4'


def _persist_binding(root,record):
    version={SCHEMA:'v1',ASSEMBLED_SCHEMA:'v2',SENSOR_BINDING_SCHEMA:'v3',SENSOR_ASSEMBLED_SCHEMA:'v4'}[record['schema']]
    raw=_canonical(record);target=root/(sha256(raw).hexdigest()+'.training-input-binding-'+version+'.json')
    if target.exists():
        if _owned_bytes(target,4096)!=raw:raise ValueError('original training input binding differs')
        return target
    temporary=root/('.input-binding-'+uuid4().hex)
    try:
        _write_private(temporary,raw);_rename_new(temporary,target);_sync_directory(root)
    finally:
        if temporary.exists():temporary.unlink()
    return target


def require_fitting_optin():
    # Location-neutral intent; the old name remains a compatibility alias.
    if (os.environ.get('EARTHSHIP_QUALIFICATION_FIT')!='1' and
            os.environ.get('EARTHSHIP_REMOTE_QUALIFICATION_FIT')!='1'):
        raise ValueError('explicit fitting workload opt-in required')


def run_snapshot_training(record,*,registry,fit_evidence_directory,clock,revision_reader,assembly_binding=None,assembly_inputs=None):
    require_fitting_optin()
    if (assembly_binding is None)!=(assembly_inputs is None):
        raise ValueError('assembly binding and original inputs required together')
    sensor_inputs=isinstance(record,dict) and record.get('schema')==SENSOR_INPUT_SCHEMA
    if assembly_binding is not None:
        assembly_inputs=_bounded(assembly_inputs,8)
        (verify_training_assembly_v2 if sensor_inputs else verify_training_assembly)(record,assembly_binding,assembly_inputs)
        assembly_binding=deepcopy(assembly_binding);assembly_inputs=deepcopy(assembly_inputs)
    record=deepcopy(record)
    root=_private_directory(Path(fit_evidence_directory))
    now=_utc(clock());revision=_sha(revision_reader())
    frozen=(restore_training_inputs_v2 if sensor_inputs else restore_training_inputs)(record)
    if _utc(record['captured_at'])>now:raise ValueError('future input snapshot unavailable for fitting')
    expected=record['dataset_manifest']
    def compatible(artifact):
        if sensor_inputs and (artifact.schema!='earthship-thermal-model/v6' or artifact.data_manifest.get('temperature_evidence')!=record['temperature_evidence']):
            raise ValueError('fitted sensor phase differs from original inputs')
        if (_utc(artifact.trained_from)!=frozen.start or _utc(artifact.trained_through)!=frozen.end or
                artifact.code_revision!=revision or _sha(revision_reader())!=revision or
                any(artifact.data_manifest.get(key)!=value for key,value in expected.items())):
            raise ValueError('fitted dataset or code differs from frozen training context')
    def sources(artifact,snapshot):
        compatible(artifact)
        (write_training_sources_v2 if sensor_inputs else write_training_sources)(root,snapshot,artifact)
        lineage={}
        if assembly_binding is not None:
            write_input=write_training_inputs_v2 if sensor_inputs else write_training_inputs
            for parent in assembly_inputs:write_input(root,parent)
            write_input(root,record)
            (write_training_assembly_v2 if sensor_inputs else write_training_assembly)(root,record,assembly_binding,assembly_inputs)
            lineage=dict(assembly_binding_sha256=assembly_binding['binding_sha256'],
                         input_snapshot_sha256s=assembly_binding['input_snapshot_sha256s'])
        phase_binding={} if not sensor_inputs else dict(sensor_epochs={role:info['sensor_epoch'] for role,info in record['temperature_evidence']['roles'].items()})
        _persist_binding(root,dict(schema=(SENSOR_ASSEMBLED_SCHEMA if lineage else SENSOR_BINDING_SCHEMA) if sensor_inputs else (ASSEMBLED_SCHEMA if lineage else SCHEMA),snapshot_sha256=record['snapshot_sha256'],
            artifact_sha256=sha256(_canonical(asdict(artifact))).hexdigest(),
            collection_code_revision=record['collection_code_revision'],fit_code_revision=revision,
            captured_at=record['captured_at'],start=record['start'],end=record['end'],release_authorized=False,**lineage,**phase_binding))
    def proof(artifact,value):
        compatible(artifact)
        write_fit_evidence(root,value,artifact)
    return run_training(start=frozen.start,end=frozen.end,registry=registry,
        journal=frozen.journal,series_reader=frozen.series_reader,clock=clock,
        revision_reader=lambda:revision,training_sources_writer=sources,fit_evidence_writer=proof)
