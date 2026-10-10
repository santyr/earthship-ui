"""Bounded provisional production: fixed telemetry, actual receipts, no controls."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic,sleep
from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc
from .runtime_bundle import _owned_bytes
from .policy_registration import _read_private
from .installed_shade_live_inputs import CompressedSourceLiveBackend,TelemetryTransport,SOURCE_PATHS
from .installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM,_receipt
from .installed_shade_publication import RAW_RUNTIME_PATHS
from .origin_capture import build_runtime_binding,_temperatures
from .provisional_artifact import read_candidate
from . import provisional_forecast as forecasts
from .provisional_score import validate_delivery
from thermal_installed_intel import _resource_preflight

SCHEMA='earthship-provisional-thermal-live-config/v1'
SOURCE_FIELDS={'candidate_path','token_file','journal_dsn_file','forecast_dsn_file','native_db_config','native_policy'}
FIELDS=SOURCE_FIELDS|{'schema','openhab_base','evidence_directory','shared_lock','native_cutover'}
RUNTIME_ROOT=Path(__file__).resolve().parents[1]
RUNTIME_PATHS=RAW_RUNTIME_PATHS|frozenset({'thermal_installed_intel.py','provisional_thermal.py',
    'thermal_model/training_pressure_guard.py','thermal_model/provisional_fit.py','thermal_model/provisional_artifact.py',
    'thermal_model/provisional_forecast.py','thermal_model/provisional_score.py','thermal_model/provisional_live.py','thermal_model/provisional_monitor.py'})


def _clock():return datetime.now(timezone.utc)


def current_runtime():return build_runtime_binding(RUNTIME_ROOT,sorted(RUNTIME_PATHS))


def load_settings(path,*,withdraw=False):
    from .capture_readers import BASES
    path=Path(path);_private_directory(path.parent);value=_read_private(path)
    if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA or value['openhab_base'] not in BASES:raise ValueError('closed provisional production configuration required')
    _utc(value['native_cutover'])
    for key in SOURCE_FIELDS|{'evidence_directory','shared_lock'}:
        target=Path(value[key])
        if not target.is_absolute() or target.resolve()!=target:raise ValueError('resolved original provisional source required')
        _private_directory(target.parent)
        if key=='evidence_directory':_private_directory(target)
        elif not withdraw or key in ('token_file','shared_lock'):_owned_bytes(target,16384)
    return deepcopy(value)


def backend_settings(settings):
    value={key:settings[key] for key in SOURCE_FIELDS-{'candidate_path'}}
    value.update(release_inputs_path=settings['candidate_path'],schema=SCHEMA,openhab_base=settings['openhab_base'],evidence_directory=settings['evidence_directory'])
    return value


def _phase_directory(root,kind,at):
    parent=_private_directory(Path(root));folder=parent/(kind+'-'+_utc(at).strftime('%Y%m%d'))
    folder.mkdir(mode=0o700,exist_ok=True);return _private_directory(folder)


def delivery_directory(settings,at):return _phase_directory(settings['evidence_directory'],'origins',at)


def _persisted_after_write(backend,item,state,*,since,guard):
    # JDBC writes are asynchronous. Recheck once with an actual later clock;
    # never substitute an accepted PUT or current state for a persisted receipt.
    for attempt in range(2):
        guard()
        try:
            if isinstance(backend,TelemetryTransport):
                return backend.persisted(item,state,since=since,until=_clock(),preflight=guard)
            return backend.persisted(item,state,since=since)
        except ValueError as error:
            if str(error)!='one exact actual persisted publication required' or attempt:raise
            sleep(1);guard()


def publish_cycle(settings,*,guard,backend=None):
    guard();_resource_preflight();runtime=current_runtime();now=_clock()
    candidate=read_candidate(Path(settings['candidate_path']),assessed_at=now,runtime=runtime)
    issue=now.replace(minute=now.minute//5*5,second=0,microsecond=0)+timedelta(minutes=5)
    if issue-now>timedelta(seconds=60):return dict(status='deferred',next_issue=issue.isoformat(),delivery_verified=False,automatic_actuation=False)
    deadline=monotonic()+85
    known=_clock()
    if not timedelta(0)<issue-known<=timedelta(seconds=60):raise ValueError('actual bounded pre-issue clock required')
    archive=delivery_directory(settings,issue)
    if backend is None:
        translated=backend_settings(settings);translated['evidence_directory']=str(archive)
        backend=CompressedSourceLiveBackend(translated,shared_lock_guard=guard)
    from .replay_budget import capture_source_reads
    with capture_source_reads() as sources:
        # Collect original sources before issue; do not backdate availability.
        inputs=backend.collect(issue=issue,known_at=known);available=_clock()
        if available>issue:raise ValueError('original sources arrived after issue')
        while _clock()<issue:
            guard()
            if monotonic()>=deadline:raise ValueError('provisional publication deadline exceeded')
            sleep(min(.1,max(0,(issue-_clock()).total_seconds())))
        report_path=Path(settings['evidence_directory'])/'latest-provisional-performance.json'
        report=None
        if report_path.exists():
            try:
                possible=_read_private(report_path)
                forecasts._validate_report(possible,candidate['artifact_sha256'],available)
                report=possible
            except (OSError,ValueError,TypeError,KeyError):pass
        capture=forecasts.build_capture(candidate,inputs,issue=issue,available=available,published=_clock(),monitoring_report=report)
        origin_path=forecasts.persist(archive,capture,field='capture_sha256',suffix='.provisional-origin-v1.json')
        def send_guard():
            guard();_resource_preflight();backend.verify_unchanged()
            if monotonic()>=deadline:raise ValueError('provisional publication deadline exceeded')
            current=read_candidate(Path(settings['candidate_path']),assessed_at=_clock(),runtime=current_runtime())
            if _canonical(current)!=_canonical(candidate):raise ValueError('frozen provisional candidate changed')
            _temperatures(capture['inputs']['origin_temperatures'],capture['inputs']['current'],issued_at=issue,published_at=_clock(),version=2)
            sources.verify()
        payload=forecasts.publication(capture);receipts={}
        for item,value in ((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,payload)):
            state=_canonical(value).decode();send_guard();backend.put(item,state,preflight=send_guard)
            receipt=_persisted_after_write(backend,item,state,since=issue,guard=send_guard)
            if receipt is None:raise ValueError('provisional delivery not persisted')
            served,_=_receipt(receipt,item)
            if _canonical(served)!=_canonical(value):raise ValueError('served provisional state differs')
            receipts[item]=receipt
        send_guard();validate_delivery(capture,receipts)
        delivery=dict(schema='earthship-provisional-thermal-delivery/v1',issued_at=issue.isoformat(),capture_path=str(origin_path),capture_sha256=capture['capture_sha256'],artifact_sha256=candidate['artifact_sha256'],receipts=receipts)
        delivery['delivery_sha256']=forecasts.digest(delivery,'delivery_sha256')
        path=forecasts.persist(archive,delivery,field='delivery_sha256',suffix='.provisional-delivery-v1.json')
        if json.loads(_owned_bytes(path,65536))!=delivery:raise ValueError('original delivery readback differs')
    return dict(status='published',mode='provisional',delivery_verified=True,origin_path=str(origin_path),delivery_path=str(path),automatic_actuation=False)


def withdraw(settings,*,guard,backend=None):
    guard();_resource_preflight()
    if backend is None:
        from .capture_readers import ReadBudget
        token=_owned_bytes(Path(settings['token_file']),4096).decode().strip()
        backend=TelemetryTransport(base=settings['openhab_base'],token_reader=lambda:token,budget=ReadBudget(30,max_requests=8,guard=guard))
    at=_clock();main=forecasts.unavailable(at)
    numeric=dict(schema=forecasts.NUMERIC_SCHEMA,status='unavailable',generated_at=at.isoformat(),graduated=False,automatic_actuation=False)
    for item,value in ((NUMERIC_ITEM,numeric),(PUBLICATION_ITEM,main)):
        state=_canonical(value).decode();backend.put(item,state,preflight=guard)
        receipt=_persisted_after_write(backend,item,state,since=at,guard=guard)
        if receipt is None or _canonical(_receipt(receipt,item)[0])!=_canonical(value):raise ValueError('withdrawal delivery unverified')
    return dict(status='withdrawn',mode='unavailable',delivery_verified=True,automatic_actuation=False)
