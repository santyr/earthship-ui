"""Private bounded native/JDBC readers for mature forecast score collection.

Only read endpoints and dedicated local read-only connections are used. No
weather fallback, Item PUT, fitting or release override is exposed.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path

from .forcing_capture import _private_directory
from .graduation_policy import _utc
from .runtime_bundle import _owned_bytes
from .policy_registration import _read_private
from .capture_readers import BASES,ReadBudget,bounded_journal_dsn
from .installed_shade_live_inputs import TelemetryTransport
from .installed_shade_published_origin import _receipt,NUMERIC_ITEM,PUBLICATION_ITEM

SCHEMA='earthship-installed-shade-score-config/v1'
RAW_SCHEMA='earthship-installed-shade-score-config/v2'
SOURCE_SCHEMA='earthship-installed-shade-score-config/v3'
COMPRESSED_SOURCE_SCHEMA='earthship-installed-shade-score-config/v4'
SOURCE_PATHS={'token_file','native_db_config','native_policy'}
FIELDS=SOURCE_PATHS|{'schema','openhab_base','output_directory'}


def _clock():return datetime.now(timezone.utc)


def load_raw_score_settings(path):
    return load_score_settings(path,_version=2)


def load_score_settings(path,*,_version=1):
    if type(_version) is not int or _version not in (1,2,3,4):raise ValueError('explicit score configuration profile required')
    schema={1:SCHEMA,2:RAW_SCHEMA,3:SOURCE_SCHEMA,4:COMPRESSED_SOURCE_SCHEMA}[_version]
    path=Path(path);_private_directory(path.parent);value=_read_private(path)
    if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=schema or value['openhab_base'] not in BASES:
        raise ValueError('closed private score configuration required')
    for key in SOURCE_PATHS|{'output_directory'}:
        name=value[key]
        if not isinstance(name,str) or not 1<=len(name)<=1024:raise ValueError('bounded explicit source path required')
        target=Path(name)
        if not target.is_absolute() or target.resolve()!=target:raise ValueError('resolved original score source path required')
        if key=='output_directory':_private_directory(target)
        else:_private_directory(target.parent);_owned_bytes(target,16384)
    return deepcopy(value)


def load_source_score_settings(path):
    return load_score_settings(path,_version=3)


class ScoreReader:
    def __init__(self,settings,*,shared_lock_guard=None):
        if settings.get('schema') in (SOURCE_SCHEMA,COMPRESSED_SOURCE_SCHEMA) and not callable(shared_lock_guard):
            raise ValueError('source scoring requires a held shared lock guard')
        self.shared_lock_guard=shared_lock_guard
        if shared_lock_guard is not None:shared_lock_guard()
        self.settings=deepcopy(settings);self.budget=ReadBudget(85,max_requests=24,guard=shared_lock_guard);self.native_source_paths=[];self._native_sources={}
        self.hashes={key:sha256(_owned_bytes(Path(settings[key]),16384)).hexdigest() for key in SOURCE_PATHS}
        token=_owned_bytes(Path(settings['token_file']),4096).decode().strip()
        self.transport=TelemetryTransport(base=settings['openhab_base'],token_reader=lambda:token,budget=self.budget)
        from thermal_temperature_runtime import _configured_sensor_epochs
        self.epochs=_configured_sensor_epochs(dict(THERMAL_TEMP_POLICY=settings['native_policy']))
    def verify_unchanged(self):
        guard=getattr(self,'shared_lock_guard',None)
        if guard is not None:guard()
        self.budget.remaining()
        if any(sha256(_owned_bytes(Path(self.settings[key]),16384)).hexdigest()!=value for key,value in self.hashes.items()):
            raise ValueError('original score source configuration changed')
    def _acquisition_check(self):
        # Queue callbacks verify configuration; keep that callback free of
        # shared-budget checks to avoid recursive deadline evaluation.
        from .replay_budget import check_shared_budget
        check_shared_budget();self.verify_unchanged()
    def publication(self,receipt):
        if not isinstance(receipt,dict) or receipt.get('item') not in (NUMERIC_ITEM,PUBLICATION_ITEM):raise ValueError('fixed original telemetry receipt required')
        _,at=_receipt(receipt,receipt['item'])
        if at>_utc(_clock()):raise ValueError('future original telemetry receipt refused')
        self._acquisition_check()
        # OpenHAB persistence bounds may be parsed with second precision.
        # Retrieve a bounded bracket, then require the exact original receipt.
        result=self.transport.persisted(receipt['item'],receipt['state'],since=at-timedelta(seconds=1),until=at+timedelta(seconds=1),preflight=self._acquisition_check)
        if _canonical(result)!=_canonical(receipt):raise ValueError('original persisted publication receipt differs')
        self._acquisition_check();return result
    def _connect(self,config):
        self._acquisition_check()
        import psycopg2
        from psycopg2.extensions import make_dsn,parse_dsn
        params=parse_dsn(bounded_journal_dsn(make_dsn(**config)))
        from .replay_budget import remaining_budget
        timeout=remaining_budget(self.budget.begin())
        if timeout<2:raise ValueError('bounded native connection deadline unavailable')
        self._acquisition_check()
        timeout=remaining_budget(min(timeout,self.budget.remaining()))
        if timeout<2:raise ValueError('bounded native connection deadline unavailable')
        params['connect_timeout']=str(min(3,int(timeout)))
        try:connection=psycopg2.connect(make_dsn(**params))
        except psycopg2.Error:raise ValueError('bounded original native source unavailable') from None
        try:self._acquisition_check();return connection
        except BaseException:connection.close();raise
    def native(self,targets,*,assessed_at,sensor_epoch):
        import psycopg2
        from hourly_temperature_runtime import read_db_config
        from weather_temperature_config import load_temperature_receiver_configuration
        from weather_temperature_sources import (fetch_temperature_source,write_temperature_source,read_temperature_source,
            write_compressed_temperature_source,read_compressed_temperature_source,replay_temperature_source)
        compressed=self.settings.get('schema')==COMPRESSED_SOURCE_SCHEMA
        writer=write_compressed_temperature_source if compressed else write_temperature_source
        source_reader=read_compressed_temperature_source if compressed else read_temperature_source
        assessed_at=_utc(assessed_at)
        if (not isinstance(targets,list) or not 1<=len(targets)<=2 or sensor_epoch!=self.epochs['air']):raise ValueError('bounded same-phase native target request required')
        targets=list(map(_utc,targets))
        if (len(set(targets))!=len(targets) or targets!=sorted(targets) or targets[-1]>assessed_at or
                targets[-1]-targets[0]>timedelta(days=1) or assessed_at>_utc(_clock())):
            raise ValueError('original elapsed native assessment required')
        self._acquisition_check()
        policies,epochs=load_temperature_receiver_configuration(self.settings['native_policy'])
        if epochs is None or epochs.get('indoor')!=sensor_epoch:raise ValueError('original native phase changed')
        config=read_db_config(self.settings['native_db_config'])
        options={}
        if self.settings.get('schema') in (SOURCE_SCHEMA,COMPRESSED_SOURCE_SCHEMA):
            def remaining():
                from .replay_budget import remaining_budget
                self._acquisition_check();return remaining_budget(self.budget.remaining())
            options['remaining_timeout']=remaining
        rows=[]
        for target in targets:
            self._acquisition_check()
            key=(target,assessed_at,sensor_epoch)
            path=self._native_sources.get(key)
            if path is None:
                try:packet=fetch_temperature_source(lambda:self._connect(config),targets=[target],assessed_at=assessed_at,
                    stream='indoor',policy=policies['indoor'],sensor_epoch=sensor_epoch,**options)
                except psycopg2.Error:raise ValueError('bounded original native source unavailable') from None
                self._acquisition_check()
                path=writer(self.settings['output_directory'],packet,before_publish=self._acquisition_check)
            retained=source_reader(path.parent,path)
            selected=replay_temperature_source(retained)
            if (retained['targets']!=[target.isoformat()] or _utc(retained['assessed_at'])!=assessed_at or
                    retained['sensor_epoch']!=sensor_epoch or retained['stream']!='indoor'):
                raise ValueError('original endpoint query context differs')
            self._acquisition_check()
            self._native_sources[key]=path
            if str(path) not in self.native_source_paths:self.native_source_paths.append(str(path))
            rows.extend(selected)
        return rows


def load_compressed_source_score_settings(path):
    """Explicit storage profile; old settings loaders continue refusing it."""
    return load_score_settings(path,_version=4)


# Registered-origin scheduling is part of the retained numerical runtime.
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from uuid import uuid4
import os
from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc,_sha
from .installed_shade_artifact import _digest
from .installed_shade_calibration import _persist,_source_operation
import json
from .origin_capture import _object
REGISTRATION_QUEUE_SCHEMA='earthship-installed-score-jobs/v4'
REGISTRATION_JOB_FIELDS={'origin_path','horizon_hours'}

def _registered_path(value):
    if not isinstance(value,str) or not 1<=len(value)<=1024:raise ValueError('bounded explicit score path required')
    path=Path(value)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved original score path required')
    return path

def _registered_decode(raw):
    def reject(_):raise ValueError('nonfinite queued job data')
    return json.loads(raw,object_pairs_hook=_object,parse_constant=reject)
from .runtime_bundle import _owned_bytes,_write_private,_sync_directory
from .replay_budget import check_shared_budget

REGISTRATION_SCHEMA='earthship-installed-score-registration/v1'
REGISTRATION_HORIZONS=('1','6','12','24')
REGISTRATION_SITE=ZoneInfo('America/Denver')


def _registered_identity(record):
    numeric=record['numeric_capture']
    return dict(artifact_sha256=_sha(numeric['candidate']['artifact_sha256']),
        runtime_sha256=_digest(numeric['runtime']),sensor_epochs=numeric['source_epochs'])


def register_compressed_publication_jobs(*,registration_path,origin_path,guard):
    """Caller holds shared consumer lock; only actual calibrated main13 originals."""
    return _source_operation(_register_publication,registration_path=registration_path,origin_path=origin_path,guard=guard)


def _register_publication(*,registration_path,origin_path,guard):
    from .installed_shade_published_origin import read_compressed_calibrated_publication_capture
    snapshots={}
    def check():
        check_shared_budget();guard()
        for path,(raw,maximum) in snapshots.items():
            if _owned_bytes(path,maximum)!=raw:raise ValueError('original score registration inputs changed')
        check_shared_budget();guard()
    def read(path,maximum):
        path=_registered_path(str(path));_private_directory(path.parent);check();raw=_owned_bytes(path,maximum);snapshots[path]=(raw,maximum);return _registered_decode(raw)
    check();pointer=_registered_path(str(registration_path));root=_private_directory(pointer.parent)
    registration=read(pointer,16384)
    if (not isinstance(registration,dict) or set(registration)!={'schema','candidate','queues'} or registration['schema']!=REGISTRATION_SCHEMA or
            not isinstance(registration['queues'],dict) or set(registration['queues'])!=set(REGISTRATION_HORIZONS)):
        raise ValueError('closed four-horizon registration required')
    queue_records={};origins=None
    for hours,path in registration['queues'].items():
        queue=read(path,65536)
        if (not isinstance(queue,dict) or set(queue)!={'schema','jobs'} or queue['schema']!=REGISTRATION_QUEUE_SCHEMA or
                not isinstance(queue['jobs'],list) or len(queue['jobs'])>256):raise ValueError('bounded original queue4 required')
        sequence=[]
        for job in queue['jobs']:
            if (not isinstance(job,dict) or set(job)!=REGISTRATION_JOB_FIELDS or type(job['horizon_hours']) is not int or
                    job['horizon_hours']!=int(hours) or not _registered_path(job['origin_path']).name.endswith('.installed-shade-origin-v13.json')):
                raise ValueError('closed calibrated horizon queue required')
            sequence.append(job['origin_path'])
        if len(set(sequence))!=len(sequence):raise ValueError('duplicate original registered publication')
        if origins is None:origins=sequence
        elif origins!=sequence:raise ValueError('horizon registrations differ')
        queue_records[hours]=queue
    origin=_registered_path(str(origin_path))
    if not origin.name.endswith('.installed-shade-origin-v13.json'):raise ValueError('calibrated actual main13 original required')
    read(origin,2000000);record=read_compressed_calibrated_publication_capture(origin);check()
    identity=_registered_identity(record);issue=_utc(record['numeric_capture']['issued_at'])
    pin=registration['candidate']
    if pin is None:
        if origins:raise ValueError('existing origins require frozen registration identity')
    elif _canonical(pin)!=_canonical(identity):raise ValueError('registered frozen candidate/runtime/epochs differ')
    if str(origin) in origins:return dict(status='jobs_unchanged',release_authorized=False)
    if origins:
        last=_registered_path(origins[-1]);read(last,2000000);last_record=read_compressed_calibrated_publication_capture(last);check()
        if _canonical(_registered_identity(last_record))!=_canonical(identity):raise ValueError('last original frozen identity differs')
        previous=_utc(last_record['numeric_capture']['issued_at'])
        if issue<previous:raise ValueError('backdated original cannot register new jobs')
        if issue<previous+timedelta(hours=24) or issue.astimezone(REGISTRATION_SITE).date()==previous.astimezone(REGISTRATION_SITE).date():
            return dict(status='origin_not_selected',release_authorized=False)
    if len(origins)>=256:raise ValueError('registered horizon queue capacity reached')
    selected={}
    for hours,queue in queue_records.items():
        updated=dict(schema=REGISTRATION_QUEUE_SCHEMA,jobs=queue['jobs']+[dict(origin_path=str(origin),horizon_hours=int(hours))])
        selected[hours]=str(_persist(root,updated,_digest(updated),'.registered-score-jobs-v4.json',before_publish=check))
    updated=dict(schema=REGISTRATION_SCHEMA,candidate=identity,queues=selected)
    temporary=root/('.score-registration-pointer-'+uuid4().hex)
    try:
        _write_private(temporary,_canonical(updated));check()
        # Re-read the actual current original after the pointer temporary write;
        # a registered job is never a replacement for its retained source bytes.
        current=read_compressed_calibrated_publication_capture(origin)
        if _canonical(current)!=_canonical(record):raise ValueError('actual publication source changed during registration')
        for hours,path in selected.items():
            expected=dict(schema=REGISTRATION_QUEUE_SCHEMA,jobs=queue_records[hours]['jobs']+[dict(origin_path=str(origin),horizon_hours=int(hours))])
            if _owned_bytes(Path(path),65536)!=_canonical(expected):raise ValueError('retained horizon queue changed')
        check();os.replace(temporary,pointer);_sync_directory(root)
    finally:
        if temporary.exists():temporary.unlink()
    return dict(status='jobs_registered',release_authorized=False)


def resolve_registered_score_queue(*,registration_path,horizon_hours,guard):
    """Return selected queue and a guard retaining the exact registry generation."""
    if type(horizon_hours) is not int or str(horizon_hours) not in REGISTRATION_HORIZONS:
        raise ValueError('explicit registered horizon required')
    snapshots={}
    def verify():
        # Queue remaining-budget callbacks invoke backend guards. Keep this
        # ownership/generation guard pure to avoid recursive budget callbacks.
        guard()
        for path,(raw,maximum) in snapshots.items():
            _private_directory(path.parent)
            if _owned_bytes(path,maximum)!=raw:raise ValueError('registered queue generation changed')
        guard()
    def read(path,maximum):
        path=_registered_path(str(path));_private_directory(path.parent);check_shared_budget();verify()
        raw=_owned_bytes(path,maximum);snapshots[path]=(raw,maximum);return _registered_decode(raw)
    pointer=_registered_path(str(registration_path));record=read(pointer,16384)
    if (not isinstance(record,dict) or set(record)!={'schema','candidate','queues'} or record['schema']!=REGISTRATION_SCHEMA or
            not isinstance(record['queues'],dict) or set(record['queues'])!=set(REGISTRATION_HORIZONS)):
        raise ValueError('closed four-horizon registration required')
    pin=record['candidate']
    if pin is not None:
        if (not isinstance(pin,dict) or set(pin)!={'artifact_sha256','runtime_sha256','sensor_epochs'} or
                not isinstance(pin['sensor_epochs'],dict) or set(pin['sensor_epochs'])!={'air','mass','outdoor'} or
                any(not isinstance(value,str) or not 1<=len(value)<=128 for value in pin['sensor_epochs'].values())):
            raise ValueError('closed frozen registration identity required')
        _sha(pin['artifact_sha256']);_sha(pin['runtime_sha256'])
    origins=None
    for hours,path in record['queues'].items():
        queue=read(path,65536)
        if (not isinstance(queue,dict) or set(queue)!={'schema','jobs'} or queue['schema']!=REGISTRATION_QUEUE_SCHEMA or
                not isinstance(queue['jobs'],list) or len(queue['jobs'])>256):raise ValueError('bounded original queue4 required')
        sequence=[]
        for job in queue['jobs']:
            if (not isinstance(job,dict) or set(job)!=REGISTRATION_JOB_FIELDS or type(job['horizon_hours']) is not int or
                    job['horizon_hours']!=int(hours) or not _registered_path(job['origin_path']).name.endswith('.installed-shade-origin-v13.json')):
                raise ValueError('closed calibrated registered horizon required')
            sequence.append(job['origin_path'])
        if len(set(sequence))!=len(sequence) or (pin is None and sequence):raise ValueError('frozen unique registered origins required')
        if origins is None:origins=sequence
        elif origins!=sequence:raise ValueError('registered horizon origin sequences differ')
    verify();check_shared_budget();return _registered_path(record['queues'][str(horizon_hours)]),verify
