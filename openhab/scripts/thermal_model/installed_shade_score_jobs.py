"""One queued mature score per invocation; completion hints never authorize release."""
from datetime import datetime,timedelta,timezone
import json
import os
from hashlib import sha256
from uuid import uuid4
from pathlib import Path
import re
from time import monotonic
from .forcing_capture import _canonical,_private_directory
from .origin_capture import _object
from .graduation_policy import _utc
from .installed_shade_artifact import _digest
from .runtime_bundle import _owned_bytes,_write_private
from .installed_shade_published_origin import read_publication_capture
from .installed_shade_score_collection import collect_published_score
from .installed_shade_raw_score_sources import read_raw_score_sources

SCHEMA='earthship-installed-score-jobs/v1'
COMPLETION_SCHEMA='earthship-installed-score-job-completion/v1'
JOB_FIELDS={'origin_path','horizon_hours'}
COMPLETION_FIELDS={'schema','job','raw_packet_path','raw_score_sources_sha256','release_authority'}


def _clock():return datetime.now(timezone.utc)


def _decode(raw):
    def reject(_):raise ValueError('nonfinite queued job data')
    return json.loads(raw,object_pairs_hook=_object,parse_constant=reject)


def _read(path,maximum):return _decode(_owned_bytes(path,maximum))


def _path(value):
    if not isinstance(value,str) or not 1<=len(value)<=1024:raise ValueError('bounded explicit score path required')
    path=Path(value)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved original score path required')
    return path


def collect_queued_score(*,queue_path,output_directory,backend):
    """Replay completion references or attempt exactly one declared mature job."""
    base=dict(release_authorized=False)
    try:
        queue=_path(str(queue_path));_private_directory(queue.parent)
        out=_private_directory(Path(output_directory));raw=_owned_bytes(queue,65536)
        value=_decode(raw);deadline=monotonic()+55;now=_utc(_clock())
        def check():
            if monotonic()>=deadline:raise ValueError('queued score budget elapsed')
            backend.verify_unchanged()
            if _owned_bytes(queue,65536)!=raw:raise ValueError('original queued jobs changed')
        if (not isinstance(value,dict) or set(value)!={'schema','jobs'} or value['schema']!=SCHEMA or
                not isinstance(value['jobs'],list) or len(value['jobs'])>256):raise ValueError('closed bounded queued jobs required')
        seen=set()
        for job in value['jobs']:
            if (not isinstance(job,dict) or set(job)!=JOB_FIELDS or type(job['horizon_hours']) is not int or
                    job['horizon_hours'] not in (1,6,12,24)):raise ValueError('closed original horizon job required')
            _path(job['origin_path']);key=_digest(job)
            if key in seen:raise ValueError('duplicate queued score job')
            seen.add(key)
        queue_sha=sha256(raw).hexdigest();cursor=out/(queue_sha+'.score-cursor-v1.json')
        jobs=value['jobs'];keys=[_digest(job) for job in jobs]
        if cursor.exists():
            saved=_read(cursor,8192)
            if (not isinstance(saved,dict) or set(saved)!={'schema','queue_sha256','last_job_sha256','release_authority'} or
                    saved['schema']!='earthship-installed-score-cursor/v1' or saved['queue_sha256']!=queue_sha or
                    saved['last_job_sha256'] not in seen or saved['release_authority'] is not False):
                raise ValueError('closed non-authoritative scheduling cursor required')
            start=keys.index(saved['last_job_sha256'])+1;jobs=jobs[start:]+jobs[:start]
        def advance(job):
            check();body=dict(schema='earthship-installed-score-cursor/v1',queue_sha256=queue_sha,
                last_job_sha256=_digest(job),release_authority=False)
            temporary=out/('.score-cursor-'+uuid4().hex)
            try:
                _write_private(temporary,_canonical(body));os.replace(temporary,cursor)
            finally:
                if temporary.exists():temporary.unlink()
        pending=False;source_bytes=0;audits=[];scanned=0
        def verify_raw(path,job):
            path=_path(path)
            if path.parent!=out:raise ValueError('raw completion outside original score archive')
            replay=read_raw_score_sources(path,assessed_at=_utc(_clock()),check_budget=check)
            packet=replay['score_packet']
            if packet['origin_path']!=job['origin_path'] or packet['horizon_hours']!=job['horizon_hours']:
                raise ValueError('raw completion refers to a different job')
            digest=replay['raw_score_sources_sha256']
            if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('original raw packet digest required')
            return digest
        for job in jobs:
            check();marker=out/(_digest(job)+'.score-job-v1.json')
            if marker.exists():
                try:
                    saved=_read(marker,8192)
                    if (not isinstance(saved,dict) or set(saved)!=COMPLETION_FIELDS or saved['schema']!=COMPLETION_SCHEMA or
                            saved['job']!=job or saved['release_authority'] is not False):raise ValueError('closed original completion reference required')
                except (OSError,ValueError,TypeError,KeyError):
                    advance(job);raise
                # Metadata suppresses duplicate scheduling only. New work is
                # never forced to replay the entire completed prefix first.
                audits.append((job,saved));continue
            if scanned>=8:return dict(base,status='pending')
            scanned+=1;advance(job)
            origin=_path(job['origin_path']);source_bytes+=len(_owned_bytes(origin,2000000))
            if source_bytes>64000000:raise ValueError('queued original source inventory exceeds byte bound')
            capture=read_publication_capture(origin);check()
            if _utc(capture['numeric_capture']['issued_at'])+timedelta(hours=job['horizon_hours'],minutes=5)>now:
                pending=True;continue
            result=collect_published_score(origin_path=origin,horizon_hours=job['horizon_hours'],output_directory=out,backend=backend)
            check()
            if result['status']=='scored':
                digest=verify_raw(result['raw_packet_path'],job);check()
                saved=dict(schema=COMPLETION_SCHEMA,job=job,raw_packet_path=result['raw_packet_path'],raw_score_sources_sha256=digest,release_authority=False)
                _write_private(marker,_canonical(saved))
            return result
        if audits:
            job,saved=audits[0];advance(job)
            if verify_raw(saved['raw_packet_path'],job)!=saved['raw_score_sources_sha256']:
                raise ValueError('completed original raw packet changed')
            check();return dict(base,status='completion_verified')
        check();return dict(base,status='pending' if pending else 'queue_complete')
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError):return dict(base,status='withheld')
