"""Private immutable raw training snapshots; never infer source qualification."""
from hashlib import sha256
import json
from datetime import timezone
import os
from pathlib import Path
import stat
from uuid import uuid4

from .dataset import _canonical_sample
from .temperature_history import STREAMS,_validate_receipt,validate_evidence_manifest,_ceil,STEP
from .forcing_capture import _canonical,_private_directory
from .origin_capture import _object
from .graduation_policy import _utc

SCHEMA='earthship-thermal-training-sources/v1'
MAX_BYTES=64000000


def _digest(value):return sha256(_canonical(value)).hexdigest()


def build_training_sources(samples,reader):
    if not callable(getattr(reader,'temperature_grids',None)):
        raise ValueError('original retained native training grids required')
    ordered=sorted(samples,key=lambda row:row.at.astimezone(timezone.utc))
    provenance=getattr(samples,'radiation_provenance_by_at',None)
    rows=[_canonical_sample(row,'observed' if provenance is None else provenance[row.at]) for row in ordered]
    record=dict(schema=SCHEMA,samples=rows,temperature_grids=reader.temperature_grids())
    encoded=_canonical(record)
    if len(encoded)>MAX_BYTES:raise ValueError('raw training snapshot exceeds bounded size')
    return json.loads(encoded)


def validate_training_sources(record,artifact):
    if not isinstance(record,dict) or set(record)!={'schema','samples','temperature_grids'} or record['schema']!=SCHEMA:
        raise ValueError('closed raw training snapshot required')
    manifest=artifact.data_manifest;rows=record['samples'];grids=record['temperature_grids']
    if (not isinstance(rows,list) or len(rows)!=manifest['sample_count'] or
            _digest(rows)!=manifest['canonical_rows_sha256'] or len(_canonical(record))>MAX_BYTES):
        raise ValueError('raw training samples differ from artifact')
    temperature=manifest.get('temperature_evidence')
    validate_evidence_manifest(temperature,start=manifest['start'],end=manifest['end'])
    if not isinstance(grids,dict) or set(grids)!=set(STREAMS):raise ValueError('complete original native grids required')
    for role in STREAMS:
        info=temperature['roles'][role];grid=grids[role]
        if not isinstance(grid,list) or len(grid)!=info['targets']:raise ValueError('native grid count differs from source manifest')
        target=_ceil(max(_utc(manifest['start']),_utc(temperature['cutover'])))
        digest=sha256();qualified=missing=0
        for row in grid:
            if not isinstance(row,list) or len(row)!=2 or _utc(row[0])!=target:raise ValueError('native grid target order differs')
            receipt=row[1]
            if receipt is not None:
                _validate_receipt(receipt,target);qualified+=1
            else:missing+=1
            digest.update((_canonical([target.isoformat(),receipt]).decode()+'\n').encode())
            target+=STEP
        if (digest.hexdigest()!=info['grid_sha256'] or qualified!=info['qualified'] or missing!=info['missing']):
            raise ValueError('retained native grid differs from artifact source digest')
    return record


def _read_private(path):
    _private_directory(path.parent);info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or
            stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or info.st_size>MAX_BYTES):
        raise ValueError('owned bounded private training snapshot required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if (before.st_dev,before.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('training snapshot changed')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(MAX_BYTES+1)
        after=os.fstat(fd)
    finally:os.close(fd)
    if len(raw)!=info.st_size or (before.st_mtime_ns,before.st_ctime_ns)!=(after.st_mtime_ns,after.st_ctime_ns):
        raise ValueError('training snapshot changed during read')
    return raw


def read_training_sources(path,artifact):
    def reject(_):raise ValueError('nonfinite training snapshot')
    try:record=json.loads(_read_private(Path(path)),object_pairs_hook=_object,parse_constant=reject)
    except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('training snapshot JSON invalid') from None
    return validate_training_sources(record,artifact)


def write_training_sources(directory,record,artifact):
    root=_private_directory(Path(directory));raw=_canonical(validate_training_sources(record,artifact))
    target=root/(_digest(artifact.data_manifest)+'.training-sources-v1.json')
    temporary=root/('.training-'+uuid4().hex+'.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        try:os.link(temporary,target,follow_symlinks=False)
        except FileExistsError:
            if _read_private(target)!=raw:raise ValueError('original training snapshot has different content')
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:temporary.unlink(missing_ok=True)
    return target
