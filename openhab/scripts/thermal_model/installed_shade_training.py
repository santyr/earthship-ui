"""Closed private offline training settings; no source transport or release authority."""
from copy import deepcopy
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import stat
from uuid import UUID

SCHEMA='earthship-installed-shade-training-config/v1'
FIELDS={'schema','snapshot_path','snapshot_sha256','runtime_bundle_path','runtime_sha256','code_revision',
    'sensor_epochs','training_start','training_end','initial_coefficients','output_directory','shared_lock'}


def _directory(path):
    info=path.lstat()
    if path.resolve()!=path or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError('private owned directory required')


def _path(value,*,directory=False):
    if not isinstance(value,str) or not 1<=len(value)<=1024:raise ValueError('bounded original path required')
    path=Path(value)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved absolute original path required')
    if directory:_directory(path)
    else:
        _directory(path.parent);info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
            raise ValueError('owned private single-link file required')
    return path


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate configuration field')
        result[key]=value
    return result


def load_training_settings(path):
    path=_path(str(path))
    before=path.lstat()
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        opened=os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid!=os.getuid() or
                stat.S_IMODE(opened.st_mode)!=0o600 or opened.st_nlink!=1 or
                (opened.st_dev,opened.st_ino)!=(before.st_dev,before.st_ino)):
            raise ValueError('private configuration changed before read')
        with os.fdopen(fd,'rb',closefd=False) as source:raw=source.read(16385)
        after=os.fstat(fd);current=path.lstat()
        if (path.resolve()!=path or (current.st_dev,current.st_ino)!=(opened.st_dev,opened.st_ino) or
                (opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
            raise ValueError('private configuration changed during read')
    finally:os.close(fd)
    if len(raw)>16384:raise ValueError('bounded training settings required')
    def reject(value):raise ValueError('nonfinite settings refused')
    value=json.loads(raw,object_pairs_hook=_object,parse_constant=reject)
    if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA:
        raise ValueError('closed offline training settings required')
    for key in ('snapshot_sha256','runtime_sha256','code_revision'):
        if not isinstance(value[key],str) or re.fullmatch('[0-9a-f]{64}',value[key]) is None:raise ValueError('SHA256 identity required')
    for key in ('snapshot_path','shared_lock'):_path(value[key])
    for key in ('runtime_bundle_path','output_directory'):_path(value[key],directory=True)
    phases=value['sensor_epochs']
    if not isinstance(phases,dict) or set(phases)!={'air','mass','outdoor'}:raise ValueError('complete native phases required')
    for phase in phases.values():
        if not isinstance(phase,str):raise ValueError('canonical sensor phase required')
        parsed=UUID(phase)
        if str(parsed)!=phase or parsed.int==0:raise ValueError('nonzero canonical sensor phase required')
    times=[]
    for key in ('training_start','training_end'):
        if not isinstance(value[key],str):raise ValueError('aware training cutoff required')
        at=datetime.fromisoformat(value[key])
        if at.utcoffset() is None:raise ValueError('aware training cutoff required')
        times.append(at)
    if not times[0]<times[1]:raise ValueError('exclusive ordered training interval required')
    seed=value['initial_coefficients']
    if not isinstance(seed,list) or len(seed)!=10 or any(type(x) not in (int,float) or not math.isfinite(x) for x in seed):
        raise ValueError('finite ten-coefficient seed required')
    return deepcopy(value)


from time import monotonic as _monotonic


def run_candidate_training(settings,*,guard):
    """Fit one frozen development candidate; caller holds the global lock/caps.

    No source acquisition, registry selection or release authorization occurs.
    Every numerical stage consumes the same 85-second invocation budget.
    """
    from datetime import timezone
    from hashlib import sha256
    guard();started_at=datetime.now(timezone.utc);deadline=_monotonic()+85
    def remaining():
        guard();seconds=deadline-_monotonic()
        if not math.isfinite(seconds) or seconds<=0:raise ValueError('candidate build deadline exceeded')
        return min(85,seconds)
    remaining()
    from .runtime_bundle import read_runtime_bundle,_owned_bytes
    from .origin_capture import _source_bytes
    from .origin_capture import build_runtime_binding
    from .installed_shade_publication import RAW_RUNTIME_PATHS
    from .training_inputs import read_training_inputs_v2
    from .installed_shade_fit import fit_development_inputs
    from .installed_shade_artifact import build_candidate_bundle,write_candidate_bundle,read_candidate_bundle
    def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    root=Path(__file__).resolve().parents[1]
    builder_sources={name:_source_bytes(root/name,maximum=65536).decode('utf-8') for name in
        ('thermal_installed_train.py','thermal_model/installed_shade_training.py')}
    remaining();archive=read_runtime_bundle(Path(settings['runtime_bundle_path']))
    if set(archive['revision_paths'])!=set(RAW_RUNTIME_PATHS):raise ValueError('complete raw publication runtime required')
    expected=archive['runtime']
    if sha256(canonical(expected)).hexdigest()!=settings['runtime_sha256'] or expected['code_revision']!=settings['code_revision']:
        raise ValueError('frozen runtime/code identity differs')
    def verify_runtime():
        remaining()
        actual=build_runtime_binding(Path(__file__).resolve().parents[1],archive['revision_paths'])
        if canonical(actual)!=canonical(expected):raise ValueError('executing runtime differs from original archive')
        remaining()
    verify_runtime()
    remaining();inputs=read_training_inputs_v2(Path(settings['snapshot_path']))
    if inputs['snapshot_sha256']!=settings['snapshot_sha256']:raise ValueError('original snapshot identity differs')
    at=datetime.now(timezone.utc)
    saved={key:os.environ.get(key) for key in ('EARTHSHIP_QUALIFICATION_FIT','EARTHSHIP_REMOTE_QUALIFICATION_FIT')}
    try:
        os.environ['EARTHSHIP_QUALIFICATION_FIT']='1';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        fit=fit_development_inputs(inputs,expected_snapshot_sha256=settings['snapshot_sha256'],
            sensor_epochs=settings['sensor_epochs'],assessed_at=at,training_start=settings['training_start'],
            training_end=settings['training_end'],initial=tuple(settings['initial_coefficients']),timeout_seconds=remaining())
        if fit.stability.assessed is not True:raise ValueError('independent-day stability insufficient')
        bundle=build_candidate_bundle(inputs,fit,code_revision=settings['code_revision'],runtime_revision=settings['runtime_sha256'],
            created_at=datetime.now(timezone.utc),timeout_seconds=remaining())
        if bundle['fit_evidence']['fit_gates_passed'] is not True:raise ValueError('original numerical fit gates failed')
        verify_runtime()
        path=write_candidate_bundle(Path(settings['output_directory']),bundle,inputs,
            expected_runtime_revision=settings['runtime_sha256'],assessed_at=datetime.now(timezone.utc),timeout_seconds=remaining())
        restored=read_candidate_bundle(path,expected_runtime_revision=settings['runtime_sha256'],
            assessed_at=datetime.now(timezone.utc),timeout_seconds=remaining())
        if canonical(restored)!=canonical(bundle):raise ValueError('immutable candidate readback differs')
        verify_runtime()
        remaining()
        if any(_source_bytes(root/name,maximum=65536).decode('utf-8')!=raw for name,raw in builder_sources.items()):
            raise ValueError('candidate builder source changed')
        receipt=dict(schema='earthship-installed-shade-build-receipt/v1',started_at=started_at.isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),snapshot_sha256=settings['snapshot_sha256'],
            runtime_sha256=settings['runtime_sha256'],code_revision=settings['code_revision'],
            sensor_epochs=deepcopy(settings['sensor_epochs']),training_start=settings['training_start'],training_end=settings['training_end'],
            artifact_sha256=bundle['artifact']['artifact_sha256'],candidate_path=str(path),
            builder_sources={name:dict(sha256=sha256(raw.encode()).hexdigest(),utf8=raw) for name,raw in builder_sources.items()},
            fit_executed=True,release_authorized=False,production_installed=False)
        from .installed_shade_artifact import _persist,_digest
        receipt['receipt_sha256']=_digest(receipt)
        receipt_path=_persist(Path(settings['output_directory']),receipt,receipt['receipt_sha256'],'.installed-shade-build-v1.json')
        if _owned_bytes(receipt_path,65536)!=canonical(receipt):raise ValueError('original build receipt readback differs')
        remaining()
        return dict(status='development_candidate',fit_executed=True,candidate_path=str(path),
            artifact_sha256=bundle['artifact']['artifact_sha256'],runtime_sha256=settings['runtime_sha256'],
            build_receipt_path=str(receipt_path),release_authorized=False)
    finally:
        for key,value in saved.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
