"""Append original calibrated outcomes; pointer updates grant no release authority."""
from datetime import datetime,timezone
from pathlib import Path
import os
from uuid import uuid4
from .forcing_capture import _canonical,_private_directory
from .installed_shade_artifact import _digest
from .installed_shade_calibration import _raw_packet_digest,_persist,_source_operation
from .policy_registration import _read_private
from .runtime_bundle import _owned_bytes,_write_private,_sync_directory
from .replay_budget import check_shared_budget

SOURCE_GATES=frozenset(('preregistered_policy','frozen_candidate','frozen_runtime',
    'qualified_training_sources','measured_fit','raw_development_sources','raw_calibration_sources',
    'original_source_pairs','raw_native_issue_sources','raw_native_score_sources','calibrated_intervals'))


def append_compressed_release_sources(*,reference_path,additional_pairs_path,guard):
    """Caller holds shared lock/resource preflight; preserve bad predictive outcomes."""
    return _source_operation(_append,reference_path=reference_path,additional_pairs_path=additional_pairs_path,guard=guard)


def _append(*,reference_path,additional_pairs_path,guard):
    from .installed_shade_publication import REFERENCE_FIELDS,COMPRESSED_REFERENCE_SCHEMA
    from . import installed_shade_qualification as q
    snapshots={}
    def check():
        check_shared_budget();guard()
        for path,raw in snapshots.items():
            if _owned_bytes(path,4000000)!=raw:raise ValueError('original release inputs changed')
        check_shared_budget();guard()
    def read(path):
        path=Path(path).absolute()
        value=_read_private(path);snapshots[path]=_owned_bytes(path,4000000)
        # Compare parser's view with the bytes retained for change detection.
        if _canonical(_read_private(path))!=_canonical(value):raise ValueError('original input changed during read')
        check();return value
    check();reference=Path(reference_path).absolute();root=_private_directory(reference.parent)
    refs=read(reference)
    if not isinstance(refs,dict) or set(refs)!=REFERENCE_FIELDS or refs['schema']!=COMPRESSED_REFERENCE_SCHEMA:
        raise ValueError('closed compressed release references required')
    paths={}
    for key in REFERENCE_FIELDS-{'schema'}:
        value=refs[key]
        if value is None and key=='original_pairs_path':paths[key]=None;continue
        if not isinstance(value,str) or not 1<=len(value)<=1024:raise ValueError('complete original release paths required')
        target=Path(value);paths[key]=target if target.is_absolute() else root/target
    for key in ('registration_path','candidate_path','runtime_bundle_path'):read(paths[key])
    previous=[] if paths['original_pairs_path'] is None else read(paths['original_pairs_path'])
    additional=read(additional_pairs_path)
    if previous:_raw_packet_digest(previous)
    _raw_packet_digest(additional)
    merged=list(previous);seen=set()
    for row in previous:
        value=row['raw_score_sources_path']
        if value in seen:raise ValueError('duplicate original release source')
        seen.add(value)
    for row in additional:
        value=row['raw_score_sources_path']
        if Path(value).resolve()!=Path(value):raise ValueError('resolved original score source required')
        if value not in seen:merged.append(row);seen.add(value)
    _raw_packet_digest(merged);check()
    report=q.qualify_compressed_installed_shade_candidate(registration_path=paths['registration_path'],
        candidate_path=paths['candidate_path'],runtime_bundle_path=paths['runtime_bundle_path'],
        original_pairs=merged,now=datetime.now(timezone.utc))
    q.validate_compressed_installed_shade_qualification_report(report);check()
    if any(report['gates'].get(name) is not True for name in SOURCE_GATES):
        raise ValueError('complete frozen original source qualification required')
    identity={key:report['candidate'][key] for key in ('artifact_sha256','runtime_sha256','sensor_epochs')}
    def source_guard():
        check()
        scored=q.score_compressed_source_calibrated_packets(merged,assessed_at=datetime.now(timezone.utc),candidate=identity)
        if _canonical(scored['bindings'])!=_canonical(report['original_pair_bindings']):
            raise ValueError('original score bindings changed during index retention')
        check()
    if merged==previous:
        source_guard();return dict(status='index_unchanged',release_authorized=False)
    index=_persist(root,merged,_digest(merged),'.installed-release-sources-v1.json',before_publish=source_guard)
    updated=dict(refs,original_pairs_path=str(index));temporary=root/('.release-index-pointer-'+uuid4().hex)
    try:
        _write_private(temporary,_canonical(updated))
        if _owned_bytes(index,4000000)!=_canonical(merged):raise ValueError('retained original index changed')
        source_guard()
        os.replace(temporary,reference);_sync_directory(root)
    finally:
        if temporary.exists():temporary.unlink()
    return dict(status='index_updated',release_authorized=False)
