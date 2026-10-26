"""Exact native origin binding over one retained lossless shared query.

This proof grants selection equality only. Model, receipt, publication and
release checks remain the caller's independent obligations.
"""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path

from astro_geometry import _instant
from thermal_model.forcing_capture import _canonical
from thermal_model.graduation_policy import _sha
from thermal_model.temperature_history import STREAMS, POLICY, _validate_sensor_receipt
from thermal_model.runtime_bundle import _owned_bytes
from weather_temperature_evidence import sensor_epoch_id
from weather_temperature_source_segments import (
    read_shared_temperature_source, replay_shared_temperature_source,
    shared_temperature_source_files, MAX_STORED_SEGMENT_BYTES)

SCHEMA='earthship-installed-shade-native-origin-binding/v3'
FIELDS={'schema','origin_temperatures_sha256','issue_at','assessed_at','query_sources',
        'source_manifest_sha256','context_sha256','release_authority'}


def _check(check):
    if check is not None:check()


def _path(paths):
    if (not isinstance(paths,dict) or set(paths)!=set(STREAMS) or
            any(not isinstance(name,str) or not 1<=len(name)<=1024 for name in paths.values()) or
            len(set(paths.values()))!=1):
        raise ValueError('one exact shared manifest for all three native roles required')
    path=Path(paths['air'])
    if not path.is_absolute() or path.resolve()!=path:
        raise ValueError('resolved original shared query required')
    return path


def _retained(paths,check):
    path=_path(paths);_check(check)
    source=read_shared_temperature_source(path.parent,path,guard=check)
    return source,json.loads(source.manifest_bytes)


def _observe(source,check,observe_files=None):
    # The codec's neutral file primitive is deliberately unchanged. Add every
    # observed original to the existing enclosing qualification/report inventory.
    files=shared_temperature_source_files(source)
    for path in files:
        _check(check);_owned_bytes(path,MAX_STORED_SEGMENT_BYTES)
    if observe_files is not None:observe_files(files)
    _check(check)
    # No callback follows this complete custody check before returning files.
    return shared_temperature_source_files(source)


def build_segmented_native_origin_binding(origin_temperatures,*,source_paths,issue_at,check_budget=None,observe_files=None):
    if observe_files is not None and not callable(observe_files):raise ValueError('callable complete source observer required')
    proof=origin_temperatures
    if (not isinstance(proof,dict) or set(proof)!={'schema','assessed_at','roles'} or
            proof['schema']!='earthship-thermal-origin-temperatures/v2' or
            not isinstance(proof['roles'],dict) or set(proof['roles'])!=set(STREAMS)):
        raise ValueError('complete original native role proof required')
    issue,observed=map(_instant,(issue_at,proof['assessed_at']))
    if observed>issue:raise ValueError('shared original unavailable at issue')
    floor=observed.replace(minute=observed.minute//5*5,second=0,microsecond=0)
    targets=[floor-timedelta(minutes=5*i) for i in reversed(range(288))]
    if targets[-1]!=observed:targets.append(observed)
    _path(source_paths)
    contexts={}
    for role,(stream,model,sensor) in STREAMS.items():
        evidence=proof['roles'][role]
        if (not isinstance(evidence,dict) or set(evidence)!={'identity','grid'} or
                not isinstance(evidence['identity'],dict) or
                set(evidence['identity'])!={'stream','model','sensor_id','sensor_epoch'} or
                not isinstance(evidence['grid'],list) or len(evidence['grid'])!=len(targets)):
            raise ValueError('bounded complete original shared role grid required')
        identity=evidence['identity'];phase=sensor_epoch_id(identity['sensor_epoch'])
        if identity!=dict(stream=stream,model=model,sensor_id=sensor,sensor_epoch=phase) or type(identity['sensor_id']) is not int:
            raise ValueError('approved shared native role and hardware phase required')
        contexts[role]=dict(stream=stream,policy=dict(model=model,sensor_id=sensor,**POLICY),sensor_epoch=phase)
        for target,row in zip(targets,evidence['grid']):
            if not isinstance(row,(list,tuple)) or len(row)!=2 or _instant(row[0])!=target:
                raise ValueError('exact original shared grid target required')
            if row[1] is not None:
                _validate_sensor_receipt(row[1],target,sensor_epoch=phase)
                for name in ('receivedAt','storedAt','validUntil'):_instant(row[1][name])
    proof,paths=deepcopy((proof,source_paths))
    source,manifest=_retained(paths,check_budget)
    expected=dict(contexts=contexts,targets=[at.isoformat() for at in targets],
        assessed_at=observed.isoformat(),history_start=(targets[0]-timedelta(seconds=120)).isoformat())
    # TemperaturePolicy accepts equal int/float bounds. The actual canonical
    # context bytes remain independently sealed by the manifest/context digests.
    if manifest['context']!=expected:
        raise ValueError('shared native role, policy, phase or request clock differs')
    selected=replay_shared_temperature_source(source,guard=check_budget)
    if any(_canonical(selected[role])!=_canonical(proof['roles'][role]['grid']) for role in STREAMS):
        raise ValueError('original shared grid differs from complete raw replay')
    value=dict(schema=SCHEMA,origin_temperatures_sha256=sha256(_canonical(proof)).hexdigest(),
        issue_at=issue.isoformat(),assessed_at=observed.isoformat(),query_sources=paths,
        source_manifest_sha256=sha256(source.manifest_bytes).hexdigest(),context_sha256=manifest['context_sha256'],
        release_authority=False)
    _observe(source,check_budget,observe_files)
    return value


def replay_segmented_native_origin_binding(binding,origin_temperatures,*,issue_at,check_budget=None):
    binding=deepcopy(binding)
    _validate_binding(binding)
    expected=build_segmented_native_origin_binding(origin_temperatures,source_paths=binding['query_sources'],
        issue_at=issue_at,check_budget=check_budget)
    if _canonical(expected)!=_canonical(binding):raise ValueError('original shared native binding differs')
    return expected


def _validate_binding(binding):
    if (not isinstance(binding,dict) or set(binding)!=FIELDS or binding['schema']!=SCHEMA or
            binding['release_authority'] is not False):
        raise ValueError('closed original shared native binding required')
    for name in ('origin_temperatures_sha256','source_manifest_sha256','context_sha256'):_sha(binding[name])
    if _instant(binding['assessed_at'])>_instant(binding['issue_at']):raise ValueError('original shared query chronology differs')
    _path(binding['query_sources'])


def segmented_native_origin_files(binding,*,check_budget=None):
    """Freshly read and enumerate the manifest AND every child, never a grid cache."""
    binding=deepcopy(binding);_validate_binding(binding)
    source,manifest=_retained(binding['query_sources'],check_budget)
    if (sha256(source.manifest_bytes).hexdigest()!=binding['source_manifest_sha256'] or
            manifest['context_sha256']!=binding['context_sha256'] or
            manifest['context']['assessed_at']!=binding['assessed_at']):
        raise ValueError('original shared source identity differs')
    return _observe(source,check_budget)
