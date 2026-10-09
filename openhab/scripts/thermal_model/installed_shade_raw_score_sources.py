"""Replay retained raw queries before accepting cached native score inputs.

This binding proves selection equality only. Candidate, forcing, publication,
independent support and release qualification remain separate required checks.
"""
from datetime import timedelta
from pathlib import Path

from .forcing_capture import _canonical
from .graduation_policy import _utc
from .installed_shade_artifact import _digest
from .temperature_history import STREAMS,POLICY
from weather_temperature_sources import read_temperature_source,replay_temperature_source

SCHEMA='earthship-installed-shade-native-score-binding/v1'
FIELDS={'schema','score_sources_sha256','issue_at','sensor_epoch','assessed_at','query_sources','release_authority'}
SCORE_FIELDS={'origin_path','publication','horizon_hours','outcome','recent_cycle_grid'}


def build_native_score_binding(score_packet,*,source_paths,issue_at,sensor_epoch,assessed_at,check_budget=None):
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
        packet=read_temperature_source(path.parent,path);bytes_used+=len(_canonical(packet))
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
    return dict(schema=SCHEMA,score_sources_sha256=_digest(score_packet),issue_at=issue.isoformat(),
        sensor_epoch=sensor_epoch,assessed_at=now.isoformat(),query_sources=list(source_paths),release_authority=False)


def replay_native_score_binding(binding,score_packet,*,issue_at,sensor_epoch,assessed_at,check_budget=None):
    if (not isinstance(binding,dict) or set(binding)!=FIELDS or binding['schema']!=SCHEMA or
            binding['release_authority'] is not False or _utc(binding['assessed_at'])>_utc(assessed_at)):
        raise ValueError('closed elapsed raw native score binding required')
    expected=build_native_score_binding(score_packet,source_paths=binding['query_sources'],issue_at=issue_at,
        sensor_epoch=sensor_epoch,assessed_at=binding['assessed_at'],check_budget=check_budget)
    if _canonical(expected)!=_canonical(binding):raise ValueError('original raw native binding differs')
    return expected


def read_raw_score_sources(path,*,assessed_at,check_budget=None):
    """Recompute a collected score only while its original raw sources exist."""
    from .forcing_capture import _private_directory
    from .installed_shade_calibration import _read_json
    from .installed_shade_published_origin import read_publication_capture,score_publication_capture
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved original raw score packet required')
    _private_directory(path.parent);record=_read_json(path)
    if (not isinstance(record,dict) or set(record)!={'schema','score_sources','native_binding','release_authority'} or
            record['schema']!='earthship-installed-shade-score-sources/v2' or record['release_authority'] is not False or
            path.name!=_digest(record)+'.installed-shade-score-sources-v2.json'):
        raise ValueError('closed digest-bound raw score sources required')
    packet=record['score_sources']
    if not isinstance(packet,dict) or set(packet)!=SCORE_FIELDS:raise ValueError('closed original score inputs required')
    if check_budget is not None:check_budget()
    original=read_publication_capture(Path(packet['origin_path']));numeric=original['numeric_capture']
    binding=replay_native_score_binding(record['native_binding'],packet,issue_at=numeric['issued_at'],
        sensor_epoch=numeric['source_epochs']['air'],assessed_at=assessed_at,check_budget=check_budget)
    if check_budget is not None:check_budget()
    score=score_publication_capture(original,**{k:v for k,v in packet.items() if k!='origin_path'},assessed_at=assessed_at)
    if check_budget is not None:check_budget()
    return dict(score_packet=packet,score=score,native_binding_sha256=_digest(binding),raw_score_sources_sha256=_digest(record))
