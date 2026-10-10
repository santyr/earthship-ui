"""Read-only mature main-publication sources, retained before qualification.

Original packets remain authoritative. Derived scalar scores are diagnostics;
this collector never publishes, fits, activates or commands household equipment.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
import fcntl
import os
import stat
from pathlib import Path

from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc
from .installed_shade_artifact import _digest
from .installed_shade_published_origin import (read_publication_capture,score_publication_capture,
    read_raw_publication_capture,score_raw_publication_capture,
    read_source_publication_capture,score_source_publication_capture)
from .installed_shade_calibration import _persist
from .recent_cycles import compare_v2
from . import installed_shade_origin as base
from . import installed_shade_calibrated_origin as calibrated

ERRORS=(OSError,RuntimeError,ValueError,TypeError,KeyError,AttributeError,OverflowError)
HORIZONS=(1,6,12,24)


def _clock():return datetime.now(timezone.utc)


def _locked_published_score(*,origin_path,horizon_hours,output_directory,backend,_version=3):
    """Serialize a mature score with the existing publisher in its source archive."""
    fd=None
    try:
        if type(_version) is not int or _version not in (3,5,7,9):raise ValueError('explicit collection profile required')
        path=Path(origin_path)
        if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved original publication path required')
        archive=_private_directory(path.parent)
        fd=os.open(archive/'.installed-shade-live.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
            raise ValueError('owned private serial publication lock required')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return dict(status='busy',release_authorized=False)
        return _collect_published_score(origin_path=path,horizon_hours=horizon_hours,output_directory=output_directory,backend=backend,_version=_version)
    except ERRORS:return dict(status='withheld',release_authorized=False)
    finally:
        if fd is not None:os.close(fd)


def _collect_published_score(*,origin_path,horizon_hours,output_directory,backend,_version=3):
    """Collect one mature horizon within the caller's bounded serial scope."""
    try:
        if type(_version) is not int or _version not in (3,5,7,9):raise ValueError('explicit collection profile required')
        root=_private_directory(Path(output_directory));path=Path(origin_path)
        if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved original publication path required')
        if type(horizon_hours) is not int or horizon_hours not in HORIZONS:raise ValueError('supported mature collection horizon required')
        reader,scorer={3:(read_publication_capture,score_publication_capture),
            5:(read_raw_publication_capture,score_raw_publication_capture),
            7:(read_source_publication_capture,score_source_publication_capture),
            9:(read_source_publication_capture,score_source_publication_capture)}[_version]
        record=reader(path);numeric=record['numeric_capture']
        if _version in (7,9) and record['schema']!=f'earthship-installed-shade-origin/v{_version}':
            raise ValueError('original main query profile differs')
        issue=_utc(numeric['issued_at']);target=issue+timedelta(hours=horizon_hours);now=_utc(_clock())
        if target>now-timedelta(minutes=5):return dict(status='pending',release_authorized=False)
        if _utc(record['recorded_at'])>now:raise ValueError('future publication capture refused')
        backend.verify_unchanged()
        # Re-read both original persisted receipts. An archived payload alone
        # does not prove that its claimed Item/time/state was actually stored.
        for key in ('numeric_publication','publication'):
            if _canonical(backend.publication(record[key]))!=_canonical(record[key]):raise ValueError('actual persisted receipt differs')
        phase=numeric['source_epochs']['air'];grid={}
        def history(targets,assessed):
            if assessed!=issue or any(at>=issue for at in targets):raise ValueError('future comparator knowledge refused')
            rows=backend.native(targets,assessed_at=issue,sensor_epoch=phase)
            if not isinstance(rows,list) or len(rows)!=len(targets):raise ValueError('complete original comparator request required')
            for at,row in zip(targets,rows):
                if not isinstance(row,(list,tuple)) or len(row)!=2 or _utc(row[0])!=at:raise ValueError('original comparator target differs')
                value=json.loads(_canonical(row[1]))
                if at in grid and _canonical(grid[at])!=_canonical(value):raise ValueError('inconsistent original comparator receipt')
                grid[at]=value
            # Native DB readers return aware clocks; serialized source ports
            # may carry ISO clocks. Keep the original grid above and adapt
            # only the comparator view, matching independent score replay.
            return [[_utc(row[0]),None if row[1] is None else {**row[1],
                **{key:_utc(row[1][key]) for key in ('receivedAt','storedAt','validUntil')}}] for row in rows]
        baseline=compare_v2(issue=issue,target=target,current_f=numeric['output']['initial']['air_f'],grid_reader=history,sensor_epoch=phase)
        if baseline['status']!='available':raise ValueError('seven original qualified cycles unavailable')
        # Outcome acquisition cannot choose the historical cycles above.
        rows=backend.native([target],assessed_at=_utc(_clock()),sensor_epoch=phase)
        if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],(list,tuple)) or len(rows[0])!=2 or _utc(rows[0][0])!=target:
            raise ValueError('exact mature native outcome required')
        packet=json.loads(_canonical(dict(origin_path=str(path),publication=record['publication'],horizon_hours=horizon_hours,
            outcome=dict(target_at=target,receipt=rows[0][1]),recent_cycle_grid=[[at,value] for at,value in sorted(grid.items())])))
        backend.verify_unchanged()
        assessed_at=_utc(_clock())
        score=scorer(record,**{k:v for k,v in packet.items() if k!='origin_path'},assessed_at=assessed_at)
        source_version={3:2,5:3,7:5,9:4}[_version]
        raw_sources=None
        if _version in (5,7,9) and not hasattr(backend,'native_source_paths'):
            raise ValueError('original raw query archive acquisition required')
        if hasattr(backend,'native_source_paths'):
            from .installed_shade_raw_score_sources import build_native_score_binding
            binding=build_native_score_binding(packet,source_paths=list(backend.native_source_paths),issue_at=issue,
                sensor_epoch=phase,assessed_at=assessed_at)
            raw_sources=dict(schema=f'earthship-installed-shade-score-sources/v{source_version}',score_sources=packet,
                native_binding=binding,release_authority=False)
        guard=None
        if _version in (7,9):
            from .installed_shade_raw_score_sources import replay_native_origin_binding,replay_native_score_binding
            from .replay_budget import check_shared_budget
            raw_sources['native_origin_binding_sha256']=_digest(numeric['native_origin_binding'])
            def guard():
                backend.verify_unchanged()
                replay_native_origin_binding(numeric['native_origin_binding'],numeric['origin_temperatures'],
                    issue_at=issue,check_budget=check_shared_budget)
                replay_native_score_binding(binding,packet,issue_at=issue,sensor_epoch=phase,
                    assessed_at=assessed_at,check_budget=check_shared_budget)
                backend.verify_unchanged()
            guard()
            writer=calibrated.write_source_calibrated_capture if _version==7 else base.write_source_issued_capture
        else:
            writer=calibrated.write_raw_calibrated_capture if _version==5 else (calibrated.write_calibrated_capture if numeric['schema']==calibrated.SCHEMA else base.write_issued_capture)
        numeric_path=writer(root,numeric)
        if guard is not None:guard()
        persist_options={} if guard is None else {'before_publish':guard}
        raw=deepcopy(packet);raw['origin_path']=str(numeric_path)
        raw['publication']={k:v for k,v in record['numeric_publication'].items() if k!='item'}
        packet_path=_persist(root,[packet],_digest([packet]),'.installed-shade-score-sources-v1.json',**persist_options)
        numeric_packet_path=_persist(root,[raw],_digest([raw]),'.installed-shade-numeric-score-sources-v1.json',**persist_options)
        score_path=_persist(root,score,_digest(score),f'.installed-shade-score-result-v{source_version}.json' if _version in (7,9) else ('.installed-shade-score-result-v2.json' if _version==5 else '.installed-shade-score-result-v1.json'),**persist_options)
        result=dict(status='scored',packet_path=str(packet_path),numeric_packet_path=str(numeric_packet_path),
            score_path=str(score_path),release_authorized=False)
        if raw_sources is not None:
            raw_path=_persist(root,raw_sources,_digest(raw_sources),f'.installed-shade-score-sources-v{source_version}.json',**persist_options)
            result['raw_packet_path']=str(raw_path)
        if guard is not None:guard()
        return result
    except ERRORS:return dict(status='withheld',release_authorized=False)



def collect_published_score(**values):
    return _locked_published_score(**values,_version=3)


def collect_raw_published_score(**values):
    """Collect the explicit candidate-v3 profile with original raw query archives."""
    return _locked_published_score(**values,_version=5)


def collect_source_published_score(**values):
    """Replay original issue, comparator and outcome queries; never activate."""
    name=Path(values['origin_path']).name
    if name.endswith('.installed-shade-origin-v7.json'):version=7
    elif name.endswith('.installed-shade-origin-v9.json'):version=9
    else:return dict(status='withheld',release_authorized=False)
    return _locked_published_score(**values,_version=version)
