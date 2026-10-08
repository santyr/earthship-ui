"""Train from frozen private inputs on an explicitly opted-in off-host worker.

The normal pipeline retains every artifact/numerical/promotion gate. This module
never queries household services or grants production release authority.
"""
from dataclasses import asdict
from hashlib import sha256
import os
from pathlib import Path
from uuid import uuid4

from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc,_sha
from .training_inputs import restore_training_inputs
from .pipeline import run_training
from .training_sources import write_training_sources
from .fit_evidence import write_fit_evidence
from .runtime_bundle import _write_private,_owned_bytes,_sync_directory
from .rollback import _rename_new

SCHEMA='earthship-thermal-training-input-binding/v1'


def _persist_binding(root,record):
    raw=_canonical(record);target=root/(sha256(raw).hexdigest()+'.training-input-binding-v1.json')
    if target.exists():
        if _owned_bytes(target,4096)!=raw:raise ValueError('original training input binding differs')
        return target
    temporary=root/('.input-binding-'+uuid4().hex)
    try:
        _write_private(temporary,raw);_rename_new(temporary,target);_sync_directory(root)
    finally:
        if temporary.exists():temporary.unlink()
    return target


def run_snapshot_training(record,*,registry,fit_evidence_directory,clock,revision_reader):
    # This flag records explicit workload intent, not proof of machine location.
    # Operators must select the approved off-host machine before setting it.
    if os.environ.get('EARTHSHIP_REMOTE_QUALIFICATION_FIT')!='1':
        raise ValueError('explicit off-host fitting opt-in required')
    root=_private_directory(Path(fit_evidence_directory))
    now=_utc(clock());revision=_sha(revision_reader())
    frozen=restore_training_inputs(record)
    if _utc(record['captured_at'])>now:raise ValueError('future input snapshot unavailable for fitting')
    expected=record['dataset_manifest']
    def compatible(artifact):
        if (_utc(artifact.trained_from)!=frozen.start or _utc(artifact.trained_through)!=frozen.end or
                artifact.code_revision!=revision or _sha(revision_reader())!=revision or
                any(artifact.data_manifest.get(key)!=value for key,value in expected.items())):
            raise ValueError('fitted dataset or code differs from frozen training context')
    def sources(artifact,snapshot):
        compatible(artifact)
        write_training_sources(root,snapshot,artifact)
        _persist_binding(root,dict(schema=SCHEMA,snapshot_sha256=record['snapshot_sha256'],
            artifact_sha256=sha256(_canonical(asdict(artifact))).hexdigest(),
            collection_code_revision=record['collection_code_revision'],fit_code_revision=revision,
            captured_at=record['captured_at'],start=record['start'],end=record['end'],release_authorized=False))
    def proof(artifact,value):
        compatible(artifact)
        write_fit_evidence(root,value,artifact)
    return run_training(start=frozen.start,end=frozen.end,registry=registry,
        journal=frozen.journal,series_reader=frozen.series_reader,clock=clock,
        revision_reader=lambda:revision,training_sources_writer=sources,fit_evidence_writer=proof)
