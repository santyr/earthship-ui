"""Serial installed-domain publication with two verified persisted receipts.

Preparation replays original sources before short-lived input acquisition. The
entrypoint supplies a closed private configuration and real bounded backends.
This module never fits, changes physical controls or accepts an active override.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import fcntl
import json
import os
from pathlib import Path
import stat
from time import sleep

from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc
from .installed_shade_artifact import _digest
from .origin_capture import build_runtime_binding
from .installed_shade_publication import (prepare_installed_qualification,build_installed_publication,
    unavailable_installed_publication,validate_installed_publication)
from .installed_shade_published_origin import (NUMERIC_ITEM,PUBLICATION_ITEM,build_publication_capture,
    write_publication_capture,_receipt)
from .installed_shade_qualification import (write_installed_shade_qualification_report,
    write_calibrated_installed_shade_qualification_report,write_published_installed_shade_qualification_report,
    write_raw_published_installed_shade_qualification_report)
from . import installed_shade_origin as base
from . import installed_shade_calibrated_origin as calibrated

ERRORS=(OSError,RuntimeError,ValueError,TypeError,KeyError,AttributeError,OverflowError)
RUNTIME_ROOT=Path(__file__).resolve().parents[1]


def _clock():return datetime.now(timezone.utc)


def _next_issue(now):
    now=_utc(now);issue=now.replace(minute=now.minute//5*5,second=0,microsecond=0)+timedelta(minutes=5)
    if not timedelta(0)<issue-now<=timedelta(seconds=60):raise ValueError('bounded scheduled pre-issue window required')
    return issue


def _wait_until(issue):
    remaining=(issue-_utc(_clock())).total_seconds()
    if not 0<=remaining<=60:raise ValueError('bounded original issue wait required')
    if remaining:sleep(remaining)
    if _utc(_clock())<issue:raise ValueError('original issue wait interrupted')


def _runtime(prepared,artifact):
    value=build_runtime_binding(RUNTIME_ROOT,prepared.runtime_paths)
    if _digest(value)!=artifact['runtime_revision']:raise ValueError('executing runtime differs from prepared candidate')
    return value


def _numeric(prepared,inputs,*,issue,available,published,runtime):
    artifact=json.loads(prepared.candidate_json);report=json.loads(prepared.report_json)
    validated=_utc(report['assessed_at'])
    if set(inputs)!={'forecast','current','origin_temperatures','action_snapshot'}:raise ValueError('closed original input context required')
    if artifact['schema']=='earthship-installed-shade-candidate/v2':
        candidate=calibrated.PreparedCalibratedCandidate(prepared.candidate_json,validated);builder=calibrated.build_calibrated_capture
    else:candidate=base.PreparedCandidate(prepared.candidate_json,validated);builder=base.build_issued_capture
    return builder(candidate,issued_at=issue,inputs_available_at=available,published_at=published,runtime=runtime,**inputs)


def _send_guard(prepared,artifact,inputs,issue,backend,*,output=None):
    from thermal_temperature_runtime import validate_shadow_receipt_expiry
    # Expiry uses the actual clock after potentially slower configuration and
    # runtime reads. This callback runs after HTTP metadata lookup and pacing.
    backend.verify_unchanged();_runtime(prepared,artifact)
    report=json.loads(prepared.report_json);now=_utc(_clock())
    validate_shadow_receipt_expiry(inputs['current'],now)
    if not issue<=now<issue+timedelta(minutes=10):raise ValueError('original issue expired before send')
    assessed=_utc(report['assessed_at'])
    if not assessed<=now<assessed+timedelta(minutes=20):raise ValueError('source assessment expired before send')
    if report['forecast_qualified'] and not now<_utc(report['qualification_expires_at']):
        raise ValueError('source qualification expired before send')
    if output is not None and not now<_utc(output['validUntil']):raise ValueError('publication expired before send')


def _write_numeric(root,record):
    writer=calibrated.write_calibrated_capture if record['schema']==calibrated.SCHEMA else base.write_issued_capture
    return writer(root,record)


def _report_cache(root,report):
    writers={'earthship-installed-shade-qualification-report/v1':write_installed_shade_qualification_report,
        'earthship-installed-shade-qualification-report/v2':write_calibrated_installed_shade_qualification_report,
        'earthship-installed-shade-qualification-report/v3':write_published_installed_shade_qualification_report,
        'earthship-installed-shade-qualification-report/v4':write_raw_published_installed_shade_qualification_report}
    return writers[report['schema']](root,report)


def _confirmed_receipt(backend,item,state,*,since):
    receipt=backend.persisted(item,state,since=since)
    actual,stored=_receipt(receipt,item)
    floor=_utc(since).replace(microsecond=_utc(since).microsecond//1000*1000)
    if not floor<=stored<=_utc(_clock()) or _canonical(actual)!=_canonical(json.loads(state)):
        raise ValueError('actual persisted receipt clock/state differs')
    return receipt


def _withdraw(backend):
    output=unavailable_installed_publication(_clock())
    try:
        state=_canonical(output).decode();since=_utc(_clock())
        backend.put(PUBLICATION_ITEM,state)
        _confirmed_receipt(backend,PUBLICATION_ITEM,state,since=since)
        return dict(status='withdrawn',mode='unavailable',delivery_verified=True,automatic_actuation=False)
    except ERRORS:return dict(status='unverified_failure',mode='unavailable',delivery_verified=False,automatic_actuation=False)


def run_live_cycle(*,reference_path,archive,backend):
    root=_private_directory(Path(archive));fd=os.open(root/'.installed-shade-live.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):
            raise ValueError('owned private serial publication lock required')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return dict(status='busy',delivery_verified=False,automatic_actuation=False)
        try:
            backend.verify_unchanged();issue=_next_issue(_clock())
            prepared=prepare_installed_qualification(reference_path)
            if prepared.source_ready is not True:raise ValueError('original source preparation failed')
            artifact=json.loads(prepared.candidate_json);runtime=_runtime(prepared,artifact)
            known=_utc(_clock())
            if _utc(json.loads(prepared.report_json)['assessed_at'])>known:raise ValueError('future source qualification refused')
            if known>=issue:raise ValueError('qualification missed original issue')
            inputs=deepcopy(backend.collect(issue=issue,known_at=known));available=_utc(_clock())
            if not known<=available<=issue:raise ValueError('inputs unavailable at original issue')
            backend.verify_unchanged();_runtime(prepared,artifact);_wait_until(issue)
            before=_utc(_clock());view=_numeric(prepared,inputs,issue=issue,available=available,published=before,runtime=runtime)
            # One attempt per scheduled issue. A crash or partial acceptance is
            # not permission to repost the same forecast as new source evidence.
            attempt=dict(schema='earthship-installed-shade-delivery-attempt/v1',issued_at=issue.isoformat(),started_at=before.isoformat())
            attempt_path=root/(issue.strftime('%Y%m%dT%H%M%SZ')+'.attempt.json')
            if attempt_path.exists():return dict(status='duplicate_attempt',delivery_verified=False,automatic_actuation=False)
            from .runtime_bundle import _write_private
            _write_private(attempt_path,_canonical(attempt))
            _report_cache(root,json.loads(prepared.report_json))
            backend.verify_unchanged();_runtime(prepared,artifact)
            # Rebuild after retention; the transport callback performs the
            # final expiry check after metadata/pacing before the sole PUT.
            view=_numeric(prepared,inputs,issue=issue,available=available,published=_utc(_clock()),runtime=runtime)
            sent=_canonical(view['output']).decode();numeric_since=_utc(_clock())
            backend.put(NUMERIC_ITEM,sent,preflight=lambda:_send_guard(prepared,artifact,inputs,issue,backend))
            numeric=_confirmed_receipt(backend,NUMERIC_ITEM,sent,since=numeric_since)
            persisted,_=_receipt(numeric,NUMERIC_ITEM)
            if _canonical(persisted)!=_canonical(view['output']):raise ValueError('actual numeric receipt differs')
            original=_numeric(prepared,inputs,issue=issue,available=available,published=_utc(_clock()),runtime=runtime)
            original_path=_write_numeric(root,original)
            output=build_installed_publication(original_path,prepared);validate_installed_publication(output)
            if output['status']=='unavailable':raise ValueError('current publication gates failed')
            backend.verify_unchanged();_runtime(prepared,artifact)
            # The publication builder replays current expiry/runtime again here.
            output=build_installed_publication(original_path,prepared)
            if output['status']=='unavailable':raise ValueError('publication expired before delivery')
            main_since=_utc(_clock());sent=_canonical(output).decode()
            backend.put(PUBLICATION_ITEM,sent,preflight=lambda:_send_guard(prepared,artifact,inputs,issue,backend,output=output))
            main=_confirmed_receipt(backend,PUBLICATION_ITEM,sent,since=main_since)
            capture=build_publication_capture(original_path,numeric_publication=numeric,publication=main)
            path=write_publication_capture(root,capture)
            return dict(status='published',mode=output['status'],delivery_verified=True,capture_path=str(path),
                capture_sha256=capture['capture_sha256'],automatic_actuation=False)
        except ERRORS:return _withdraw(backend)
    finally:os.close(fd)
