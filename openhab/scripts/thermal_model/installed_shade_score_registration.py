"""Schedule independent as-issued origins; registration grants no release authority."""
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from uuid import uuid4
import os
from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc,_sha
from .installed_shade_artifact import _digest
from .installed_shade_calibration import _persist,_source_operation
from .installed_shade_score_jobs import COMPRESSED_SCHEMA,JOB_FIELDS,_path,_decode
from .runtime_bundle import _owned_bytes,_write_private,_sync_directory
from .replay_budget import check_shared_budget

SCHEMA='earthship-installed-score-registration/v1'
HORIZONS=('1','6','12','24')
SITE=ZoneInfo('America/Denver')


def _identity(record):
    numeric=record['numeric_capture']
    return dict(artifact_sha256=_sha(numeric['candidate']['artifact_sha256']),
        runtime_sha256=_digest(numeric['runtime']),sensor_epochs=numeric['source_epochs'])


def register_compressed_publication_jobs(*,registration_path,origin_path,guard):
    """Caller holds shared consumer lock; only actual calibrated main13 originals."""
    return _source_operation(_register,registration_path=registration_path,origin_path=origin_path,guard=guard)


def _register(*,registration_path,origin_path,guard):
    from .installed_shade_published_origin import read_compressed_calibrated_publication_capture
    snapshots={}
    def check():
        check_shared_budget();guard()
        for path,(raw,maximum) in snapshots.items():
            if _owned_bytes(path,maximum)!=raw:raise ValueError('original score registration inputs changed')
        check_shared_budget();guard()
    def read(path,maximum):
        path=_path(str(path));_private_directory(path.parent);check();raw=_owned_bytes(path,maximum);snapshots[path]=(raw,maximum);return _decode(raw)
    check();pointer=_path(str(registration_path));root=_private_directory(pointer.parent)
    registration=read(pointer,16384)
    if (not isinstance(registration,dict) or set(registration)!={'schema','candidate','queues'} or registration['schema']!=SCHEMA or
            not isinstance(registration['queues'],dict) or set(registration['queues'])!=set(HORIZONS)):
        raise ValueError('closed four-horizon registration required')
    queue_records={};origins=None
    for hours,path in registration['queues'].items():
        queue=read(path,65536)
        if (not isinstance(queue,dict) or set(queue)!={'schema','jobs'} or queue['schema']!=COMPRESSED_SCHEMA or
                not isinstance(queue['jobs'],list) or len(queue['jobs'])>256):raise ValueError('bounded original queue4 required')
        sequence=[]
        for job in queue['jobs']:
            if (not isinstance(job,dict) or set(job)!=JOB_FIELDS or type(job['horizon_hours']) is not int or
                    job['horizon_hours']!=int(hours) or not _path(job['origin_path']).name.endswith('.installed-shade-origin-v13.json')):
                raise ValueError('closed calibrated horizon queue required')
            sequence.append(job['origin_path'])
        if len(set(sequence))!=len(sequence):raise ValueError('duplicate original registered publication')
        if origins is None:origins=sequence
        elif origins!=sequence:raise ValueError('horizon registrations differ')
        queue_records[hours]=queue
    origin=_path(str(origin_path))
    if not origin.name.endswith('.installed-shade-origin-v13.json'):raise ValueError('calibrated actual main13 original required')
    read(origin,2000000);record=read_compressed_calibrated_publication_capture(origin);check()
    identity=_identity(record);issue=_utc(record['numeric_capture']['issued_at'])
    pin=registration['candidate']
    if pin is None:
        if origins:raise ValueError('existing origins require frozen registration identity')
    elif _canonical(pin)!=_canonical(identity):raise ValueError('registered frozen candidate/runtime/epochs differ')
    if str(origin) in origins:return dict(status='jobs_unchanged',release_authorized=False)
    if origins:
        last=_path(origins[-1]);read(last,2000000);last_record=read_compressed_calibrated_publication_capture(last);check()
        if _canonical(_identity(last_record))!=_canonical(identity):raise ValueError('last original frozen identity differs')
        previous=_utc(last_record['numeric_capture']['issued_at'])
        if issue<previous:raise ValueError('backdated original cannot register new jobs')
        if issue<previous+timedelta(hours=24) or issue.astimezone(SITE).date()==previous.astimezone(SITE).date():
            return dict(status='origin_not_selected',release_authorized=False)
    if len(origins)>=256:raise ValueError('registered horizon queue capacity reached')
    selected={}
    for hours,queue in queue_records.items():
        updated=dict(schema=COMPRESSED_SCHEMA,jobs=queue['jobs']+[dict(origin_path=str(origin),horizon_hours=int(hours))])
        selected[hours]=str(_persist(root,updated,_digest(updated),'.registered-score-jobs-v4.json',before_publish=check))
    updated=dict(schema=SCHEMA,candidate=identity,queues=selected)
    temporary=root/('.score-registration-pointer-'+uuid4().hex)
    try:
        _write_private(temporary,_canonical(updated));check()
        # Re-read the actual current original after the pointer temporary write;
        # a registered job is never a replacement for its retained source bytes.
        current=read_compressed_calibrated_publication_capture(origin)
        if _canonical(current)!=_canonical(record):raise ValueError('actual publication source changed during registration')
        for hours,path in selected.items():
            expected=dict(schema=COMPRESSED_SCHEMA,jobs=queue_records[hours]['jobs']+[dict(origin_path=str(origin),horizon_hours=int(hours))])
            if _owned_bytes(Path(path),65536)!=_canonical(expected):raise ValueError('retained horizon queue changed')
        check();os.replace(temporary,pointer);_sync_directory(root)
    finally:
        if temporary.exists():temporary.unlink()
    return dict(status='jobs_registered',release_authorized=False)
