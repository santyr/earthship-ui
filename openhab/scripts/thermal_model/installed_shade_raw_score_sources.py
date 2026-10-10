"""Replay retained raw queries before accepting cached native score inputs.

This binding proves selection equality only. Candidate, forcing, publication,
independent support and release qualification remain separate required checks.
"""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

from .forcing_capture import _canonical
from .graduation_policy import _utc
from .installed_shade_artifact import _digest
from .temperature_history import STREAMS,POLICY
from weather_temperature_sources import read_temperature_source,read_compressed_temperature_source,replay_temperature_source

SCHEMA='earthship-installed-shade-native-score-binding/v1'
FIELDS={'schema','score_sources_sha256','issue_at','sensor_epoch','assessed_at','query_sources','release_authority'}
SCORE_FIELDS={'origin_path','publication','horizon_hours','outcome','recent_cycle_grid'}


def _build_native_score_binding(score_packet,*,source_paths,issue_at,sensor_epoch,assessed_at,check_budget=None,_storage_version=1):
    reader,schema=_storage_profile(_storage_version,SCHEMA)
    if not isinstance(score_packet,dict) or set(score_packet)!=SCORE_FIELDS:raise ValueError('closed original score inputs required')
    if (not isinstance(source_paths,list) or not 1<=len(source_paths)<=24 or
            any(not isinstance(p,str) or not 1<=len(p)<=1024 for p in source_paths) or len(set(source_paths))!=len(source_paths)):
        raise ValueError('bounded unique retained raw query paths required')
    issue,now=map(_utc,(issue_at,assessed_at));hours=score_packet['horizon_hours']
    if type(hours) is not int or hours not in (1,6,12,24):raise ValueError('supported original horizon required')
    target=issue+timedelta(hours=hours);outcome=score_packet['outcome'];recent=score_packet['recent_cycle_grid']
    if (not isinstance(outcome,dict) or set(outcome)!={'target_at','receipt'} or _utc(outcome['target_at'])!=target or
            target>now-timedelta(minutes=5) or not isinstance(recent,list) or len(recent)>64):
        raise ValueError('bounded mature original outcome and comparator inputs required')
    expected={}
    for row in recent:
        if not isinstance(row,(list,tuple)) or len(row)!=2:raise ValueError('original comparator target required')
        at=_utc(row[0])
        if at>=issue or at in expected:raise ValueError('duplicate or future comparator target')
        expected[at]=row[1]
    expected[target]=outcome['receipt'];selected={};bytes_used=0
    stream,model,sensor=STREAMS['air'];approved=dict(model=model,sensor_id=sensor,**POLICY)
    for name in source_paths:
        if check_budget is not None:check_budget()
        path=Path(name)
        if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved original query source required')
        packet=reader(path.parent,path);bytes_used+=len(_canonical(packet))
        if bytes_used>64000000:raise ValueError('aggregate raw query bytes exceed bound')
        if packet['stream']!=stream or packet['policy']!=approved or packet['sensor_epoch']!=sensor_epoch:
            raise ValueError('raw query role/policy/hardware phase differs')
        at=_utc(packet['assessed_at']);grid=replay_temperature_source(packet)
        if not at<=now:raise ValueError('raw query assessment is in the future')
        historical=all(_utc(t)<issue for t,_ in grid)
        if historical:
            if at!=issue:raise ValueError('comparator query used a revised issue clock')
        elif len(grid)!=1 or _utc(grid[0][0])!=target or at<target+timedelta(minutes=5):
            raise ValueError('raw outcome query target or maturity differs')
        for instant,value in grid:
            instant=_utc(instant)
            if instant in selected and _canonical(selected[instant])!=_canonical(value):
                raise ValueError('conflicting repeated raw query target')
            selected[instant]=value
    if set(selected)!=set(expected) or any(_canonical(selected[at])!=_canonical(expected[at]) for at in expected):
        raise ValueError('cached receipts differ from retained raw selection')
    return dict(schema=schema,score_sources_sha256=_digest(score_packet),issue_at=issue.isoformat(),
        sensor_epoch=sensor_epoch,assessed_at=now.isoformat(),query_sources=list(source_paths),release_authority=False)


def _replay_native_score_binding(binding,score_packet,*,issue_at,sensor_epoch,assessed_at,check_budget=None,_storage_version=1):
    _,schema=_storage_profile(_storage_version,SCHEMA)
    if (not isinstance(binding,dict) or set(binding)!=FIELDS or binding['schema']!=schema or
            binding['release_authority'] is not False or _utc(binding['assessed_at'])>_utc(assessed_at)):
        raise ValueError('closed elapsed raw native score binding required')
    expected=_build_native_score_binding(score_packet,source_paths=binding['query_sources'],issue_at=issue_at,
        sensor_epoch=sensor_epoch,assessed_at=binding['assessed_at'],check_budget=check_budget,_storage_version=_storage_version)
    if _canonical(expected)!=_canonical(binding):raise ValueError('original raw native binding differs')
    return expected


def _read_raw_score_sources(path,*,assessed_at,check_budget=None,_version=2):
    """Recompute a collected score only while its original raw sources exist."""
    if type(_version) is not int or _version not in (2,3,4,5):
        raise ValueError('explicit raw score archive version required')
    from .forcing_capture import _private_directory
    from .installed_shade_calibration import _read_json
    from .installed_shade_published_origin import (read_publication_capture,score_publication_capture,
        read_raw_publication_capture,score_raw_publication_capture,
        read_source_publication_capture,score_source_publication_capture)
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved original raw score packet required')
    _private_directory(path.parent);record=_read_json(path)
    fields={'schema','score_sources','native_binding','release_authority'}
    if _version in (4,5):fields.add('native_origin_binding_sha256')
    if (not isinstance(record,dict) or set(record)!=fields or
            record['schema']!=f'earthship-installed-shade-score-sources/v{_version}' or record['release_authority'] is not False or
            path.name!=_digest(record)+f'.installed-shade-score-sources-v{_version}.json'):
        raise ValueError('closed digest-bound raw score sources required')
    packet=record['score_sources']
    if not isinstance(packet,dict) or set(packet)!=SCORE_FIELDS:raise ValueError('closed original score inputs required')
    if check_budget is not None:check_budget()
    reader,scorer={2:(read_publication_capture,score_publication_capture),
        3:(read_raw_publication_capture,score_raw_publication_capture),
        4:(read_source_publication_capture,score_source_publication_capture),
        5:(read_source_publication_capture,score_source_publication_capture)}[_version]
    original=reader(Path(packet['origin_path']));numeric=original['numeric_capture']
    if _version in (4,5):
        expected='earthship-installed-shade-origin/v9' if _version==4 else 'earthship-installed-shade-origin/v7'
        if original['schema']!=expected or record['native_origin_binding_sha256']!=_digest(numeric['native_origin_binding']):
            raise ValueError('original issue-query profile or binding differs')
    binding=replay_native_score_binding(record['native_binding'],packet,issue_at=numeric['issued_at'],
        sensor_epoch=numeric['source_epochs']['air'],assessed_at=assessed_at,check_budget=check_budget)
    if check_budget is not None:check_budget()
    score=scorer(original,**{k:v for k,v in packet.items() if k!='origin_path'},assessed_at=assessed_at)
    if _version in (4,5):
        replay_native_origin_binding(numeric['native_origin_binding'],numeric['origin_temperatures'],
            issue_at=numeric['issued_at'],check_budget=check_budget)
        replay_native_score_binding(record['native_binding'],packet,issue_at=numeric['issued_at'],
            sensor_epoch=numeric['source_epochs']['air'],assessed_at=assessed_at,check_budget=check_budget)
    if check_budget is not None:check_budget()
    return dict(score_packet=packet,score=score,native_binding_sha256=_digest(binding),raw_score_sources_sha256=_digest(record))



def read_raw_score_sources(path,*,assessed_at,check_budget=None):
    return _read_raw_score_sources(path,assessed_at=assessed_at,check_budget=check_budget,_version=2)


def read_calibrated_raw_score_sources(path,*,assessed_at,check_budget=None):
    """Replay raw queries bound to candidate-v3 numeric and actual main receipts."""
    return _read_raw_score_sources(path,assessed_at=assessed_at,check_budget=check_budget,_version=3)


ORIGIN_SCHEMA='earthship-installed-shade-native-origin-binding/v1'
ORIGIN_FIELDS={'schema','origin_temperatures_sha256','issue_at','assessed_at','query_sources','release_authority'}


def _build_native_origin_binding(origin_temperatures,*,source_paths,issue_at,check_budget=None,_storage_version=1):
    """Replay each original issue query; selected grids alone are insufficient.

    This proof is only source selection authority. Initial-state observer,
    forcing, candidate and release checks remain independently required.
    """
    reader,schema=_storage_profile(_storage_version,ORIGIN_SCHEMA)
    proof=origin_temperatures
    if (not isinstance(proof,dict) or set(proof)!={'schema','assessed_at','roles'} or
            proof['schema']!='earthship-thermal-origin-temperatures/v2' or
            not isinstance(proof['roles'],dict) or set(proof['roles'])!=set(STREAMS) or
            not isinstance(source_paths,dict) or set(source_paths)!=set(STREAMS)):
        raise ValueError('complete native issue-query proof required')
    issue,observed=map(_utc,(issue_at,proof['assessed_at']))
    if observed>issue:raise ValueError('original query was unavailable at issue')
    floor=observed.replace(minute=observed.minute//5*5,second=0,microsecond=0)
    targets=[floor-timedelta(minutes=5*i) for i in reversed(range(288))]
    if targets[-1]!=observed:targets.append(observed)
    # Bound the supplied cache before copying or canonicalizing it. Native
    # receipt validation is separate from original query replay below.
    from .temperature_history import _validate_sensor_receipt
    from weather_temperature_evidence import sensor_epoch_id
    for role,(stream,model,sensor) in STREAMS.items():
        evidence=proof['roles'][role]
        if (not isinstance(evidence,dict) or set(evidence)!={'identity','grid'} or
                not isinstance(evidence['identity'],dict) or
                set(evidence['identity'])!={'stream','model','sensor_id','sensor_epoch'} or
                not isinstance(evidence['grid'],list) or len(evidence['grid'])!=len(targets)):
            raise ValueError('bounded complete original issue grid required')
        phase=sensor_epoch_id(evidence['identity']['sensor_epoch'])
        if (evidence['identity']!=dict(stream=stream,model=model,sensor_id=sensor,sensor_epoch=phase) or
                type(evidence['identity']['sensor_id']) is not int or
                not isinstance(source_paths[role],str) or not 1<=len(source_paths[role])<=1024):
            raise ValueError('bounded original role identity and query path required')
        for target,row in zip(targets,evidence['grid']):
            if not isinstance(row,(list,tuple)) or len(row)!=2 or _utc(row[0])!=target:
                raise ValueError('original issue grid target differs')
            if row[1] is not None:
                _validate_sensor_receipt(row[1],target,sensor_epoch=evidence['identity']['sensor_epoch'])
    proof,source_paths=deepcopy((proof,source_paths))
    paths={};bytes_used=0
    for role,(stream,model,sensor) in STREAMS.items():
        if check_budget is not None:check_budget()
        name=source_paths[role]
        if not isinstance(name,str) or not 1<=len(name)<=1024:raise ValueError('bounded original issue-query path required')
        path=Path(name)
        if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved original issue-query path required')
        packet=reader(path.parent,path);bytes_used+=len(_canonical(packet))
        if bytes_used>24000000:raise ValueError('aggregate issue-query bytes exceed bound')
        evidence=proof['roles'][role]
        if (not isinstance(evidence,dict) or set(evidence)!={'identity','grid'} or
                evidence['identity']!=dict(stream=stream,model=model,sensor_id=sensor,sensor_epoch=packet['sensor_epoch']) or
                type(evidence['identity'].get('sensor_id')) is not int or
                packet['stream']!=stream or packet['policy']!=dict(model=model,sensor_id=sensor,**POLICY) or
                _utc(packet['assessed_at'])!=observed or list(map(_utc,packet['targets']))!=targets):
            raise ValueError('original issue query role, policy, phase or clock differs')
        grid=replay_temperature_source(packet)
        if _canonical(grid)!=_canonical(evidence['grid']):raise ValueError('original issue grid differs from raw selection')
        if check_budget is not None:check_budget()
        paths[role]=name
    return dict(schema=schema,origin_temperatures_sha256=_digest(proof),
        issue_at=issue.isoformat(),assessed_at=observed.isoformat(),query_sources=paths,release_authority=False)


def _replay_native_origin_binding(binding,origin_temperatures,*,issue_at,check_budget=None,_storage_version=1):
    _,schema=_storage_profile(_storage_version,ORIGIN_SCHEMA)
    if (not isinstance(binding,dict) or set(binding)!=ORIGIN_FIELDS or
            binding['schema']!=schema or binding['release_authority'] is not False):
        raise ValueError('closed original issue-query binding required')
    expected=_build_native_origin_binding(origin_temperatures,source_paths=binding['query_sources'],
        issue_at=issue_at,check_budget=check_budget,_storage_version=_storage_version)
    if _canonical(expected)!=_canonical(binding):raise ValueError('original issue-query binding differs')
    return expected


def read_source_base_score_sources(path,*,assessed_at,check_budget=None):
    return _read_raw_score_sources(path,assessed_at=assessed_at,check_budget=check_budget,_version=4)


def read_source_calibrated_score_sources(path,*,assessed_at,check_budget=None):
    return _read_raw_score_sources(path,assessed_at=assessed_at,check_budget=check_budget,_version=5)


def read_source_score_sources(path,*,assessed_at,check_budget=None):
    name=Path(path).name
    if name.endswith('.installed-shade-score-sources-v4.json'):reader=read_source_base_score_sources
    elif name.endswith('.installed-shade-score-sources-v5.json'):reader=read_source_calibrated_score_sources
    else:raise ValueError('explicit query-bound score archive required')
    return reader(path,assessed_at=assessed_at,check_budget=check_budget)


def _storage_profile(version,schema):
    if type(version) is not int or version not in (1,2):raise ValueError('explicit native query storage profile required')
    return (read_temperature_source,schema) if version==1 else (read_compressed_temperature_source,schema.removesuffix('/v1')+'/v2')


def build_native_score_binding(score_packet,*,source_paths,issue_at,sensor_epoch,assessed_at,check_budget=None):
    return _build_native_score_binding(score_packet,source_paths=source_paths,issue_at=issue_at,sensor_epoch=sensor_epoch,assessed_at=assessed_at,check_budget=check_budget,_storage_version=1)


def replay_native_score_binding(binding,score_packet,*,issue_at,sensor_epoch,assessed_at,check_budget=None):
    return _replay_native_score_binding(binding,score_packet,issue_at=issue_at,sensor_epoch=sensor_epoch,assessed_at=assessed_at,check_budget=check_budget,_storage_version=1)


def build_native_origin_binding(origin_temperatures,*,source_paths,issue_at,check_budget=None):
    return _build_native_origin_binding(origin_temperatures,source_paths=source_paths,issue_at=issue_at,check_budget=check_budget,_storage_version=1)


def replay_native_origin_binding(binding,origin_temperatures,*,issue_at,check_budget=None):
    return _replay_native_origin_binding(binding,origin_temperatures,issue_at=issue_at,check_budget=check_budget,_storage_version=1)


def build_compressed_native_score_binding(score_packet,*,source_paths,issue_at,sensor_epoch,assessed_at,check_budget=None):
    return _build_native_score_binding(score_packet,source_paths=source_paths,issue_at=issue_at,sensor_epoch=sensor_epoch,assessed_at=assessed_at,check_budget=check_budget,_storage_version=2)


def replay_compressed_native_score_binding(binding,score_packet,*,issue_at,sensor_epoch,assessed_at,check_budget=None):
    return _replay_native_score_binding(binding,score_packet,issue_at=issue_at,sensor_epoch=sensor_epoch,assessed_at=assessed_at,check_budget=check_budget,_storage_version=2)


def build_compressed_native_origin_binding(origin_temperatures,*,source_paths,issue_at,check_budget=None):
    return _build_native_origin_binding(origin_temperatures,source_paths=source_paths,issue_at=issue_at,check_budget=check_budget,_storage_version=2)


def replay_compressed_native_origin_binding(binding,origin_temperatures,*,issue_at,check_budget=None):
    return _replay_native_origin_binding(binding,origin_temperatures,issue_at=issue_at,check_budget=check_budget,_storage_version=2)
