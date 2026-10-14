"""Native thermal operational adapters; read-only acquisition grants no authority."""
from copy import deepcopy
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from astro_geometry import _instant
from thermal_model.forcing_capture import _canonical
from thermal_model.installed_shade_score_inputs import ScoreReader,COMPRESSED_SOURCE_SCHEMA
from thermal_model.capture_readers import ReadBudget

MAX_QUERY_BYTES=64000000


class NativeScoreReader(ScoreReader):
    """One original stable SQL snapshot per historical endpoint pair."""
    def __init__(self,settings,*,shared_lock_guard):
        if not isinstance(settings,dict) or settings.get('schema')!=COMPRESSED_SOURCE_SCHEMA:
            raise ValueError('native score reader requires compressed source profile')
        super().__init__(deepcopy(settings),shared_lock_guard=shared_lock_guard)
        self.budget=ReadBudget(50,max_requests=40,guard=shared_lock_guard)
        self.transport.budget=self.budget
        self._paired_sources={};self._paired_sizes={};self._query_bytes=0

    def native(self,targets,*,assessed_at,sensor_epoch):
        from hourly_temperature_runtime import read_db_config
        from weather_temperature_config import load_temperature_receiver_configuration
        from weather_temperature_sources import (fetch_temperature_source,write_compressed_temperature_source,
            read_compressed_temperature_source,replay_temperature_source)
        from thermal_model.replay_budget import remaining_budget
        import psycopg2
        if not isinstance(targets,list) or not 1<=len(targets)<=2 or sensor_epoch!=self.epochs['air']:
            raise ValueError('bounded same-phase native pair required')
        targets=list(map(_instant,deepcopy(targets)));assessed=_instant(assessed_at)
        if (len(set(targets))!=len(targets) or targets!=sorted(targets) or targets[-1]>assessed or
                targets[-1]-targets[0]>timedelta(days=1) or assessed>datetime.now(timezone.utc)):
            raise ValueError('original elapsed native pair assessment required')
        self._acquisition_check()
        policies,epochs=load_temperature_receiver_configuration(self.settings['native_policy'])
        if epochs is None or epochs.get('indoor')!=sensor_epoch:raise ValueError('original native phase changed')
        config=read_db_config(self.settings['native_db_config']);key=(tuple(targets),assessed,sensor_epoch)
        path=self._paired_sources.get(key)
        def remaining():
            self._acquisition_check();return remaining_budget(self.budget.remaining())
        if path is None:
            try:packet=fetch_temperature_source(lambda:self._connect(config),targets=targets,assessed_at=assessed,
                stream='indoor',policy=policies['indoor'],sensor_epoch=sensor_epoch,remaining_timeout=remaining)
            except psycopg2.Error:raise ValueError('bounded original paired native source unavailable') from None
            size=len(_canonical(packet))
            if self._query_bytes+size>MAX_QUERY_BYTES:raise ValueError('aggregate native pair source bytes exceed bound')
            path=write_compressed_temperature_source(self.settings['output_directory'],packet,before_publish=self._acquisition_check)
        else:size=self._paired_sizes[key]
        retained=read_compressed_temperature_source(path.parent,path)
        if (retained['targets']!=[at.isoformat() for at in targets] or _instant(retained['assessed_at'])!=assessed or
                retained['sensor_epoch']!=sensor_epoch or retained['stream']!='indoor'):
            raise ValueError('original paired native request context differs')
        selected=replay_temperature_source(retained)
        self._acquisition_check()
        if key not in self._paired_sources:
            if len(self._paired_sources)>=40:raise ValueError('bounded native pair source inventory required')
            self._query_bytes+=size;self._paired_sizes[key]=size;self._paired_sources[key]=path
            self.native_source_paths.append(str(path))
        return selected


from time import monotonic,sleep
from household_cycle_resources import publication_resource_preflight as _publication_resource_preflight
from thermal_model.origin_capture import _source_bytes
from hashlib import sha256
from native_thermal_artifact import current_native_runtime as current_runtime,read_native_candidate,digest as runtime_digest
from thermal_model.provisional_live import _next_issue,delivery_directory,backend_settings,_persisted_after_write
from thermal_model.runtime_bundle import _owned_bytes
from thermal_model.installed_shade_live_inputs import CompressedSourceLiveBackend,TelemetryTransport
from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM,_receipt
from thermal_model.origin_capture import _temperatures

LIVE_SCHEMA='earthship-provisional-thermal-live-config/v2'
SERVING_SCHEMA='earthship-provisional-thermal-live-config/v3'
SOURCE='openhab/scripts/native_thermal_live.py'

RESOURCE_SOURCE_SHA256='46c8b6704592d12fb3637dfc59d0c77978f286954c34101a485e51dc82a3a9ad'


def _resource_preflight():
    # The transitive admission helper is sealed by this runtime-bound source.
    # Check its bytes and loaded location before calling the established kernel
    # verifier; every numerical step keeps the same caps without forking ionice.
    path=Path(__file__).with_name('household_cycle_resources.py')
    # _source_bytes freshly resolves the complete helper path and rejects any
    # alias. Match the loaded code to that same canonical path directly.
    if (not path.is_absolute() or sha256(_source_bytes(path,maximum=262144)).hexdigest()!=RESOURCE_SOURCE_SHA256 or
        Path(_publication_resource_preflight.__code__.co_filename)!=path):
        raise ValueError('native resource checker source changed')
    _publication_resource_preflight()




def _serving_settings(model,settings,*,assessed_at,guard):
    from native_model_serving_receipt import _require_model
    from native_thermal_artifact import _read
    _require_model(model)
    model.verify_bindings(assessed_at=assessed_at,guard=guard)
    selected=json.loads(model._selection._encoded)
    stage=Path(selected['stage'])
    _,cycle=_read(stage/'cycle.json',8192)
    _,original=_read(cycle['forecast_config'],8192)
    if _canonical(settings)!=_canonical(original):
        raise ValueError('owned serving configuration differs')


def _clock():return datetime.now(timezone.utc)


def publish_cycle(settings,*,guard,geometry=None,backend=None,serving_model=None):
    """Issue a native forecast only with earlier, separately prepared geometry.

    The caller owns the shared lock and publication pressure guard. Geometry
    preparation is deliberately outside the short original issuance window.
    """
    import native_thermal_forecast as forecasts
    from native_thermal_score import validate_delivery
    from thermal_model import provisional_forecast as original
    from thermal_model.replay_budget import capture_source_reads
    from thermal_model.graduation_policy import _sha
    from thermal_model.policy_registration import _read_private
    from astro_geometry_series import NativeGeometrySeries
    settings=deepcopy(settings)
    receipt_profile=settings.get('schema')==SERVING_SCHEMA
    if (settings.get('schema') not in (LIVE_SCHEMA,SERVING_SCHEMA) or
        receipt_profile!=(serving_model is not None) or
        (geometry is not None and type(geometry) is not NativeGeometrySeries)):
        raise ValueError('explicit native settings and prepared geometry required')
    expected_artifact=_sha(settings['artifact_sha256']);expected_runtime=_sha(settings['runtime_sha256'])
    guard();_resource_preflight();now=_clock();issue=_next_issue(now)
    if issue-now>timedelta(seconds=60):
        return dict(status='deferred',next_issue=issue.isoformat(),delivery_verified=False,automatic_actuation=False)
    deadline=monotonic()+85
    def within_deadline():
        guard()
        if monotonic()>=deadline or _clock()>=issue+timedelta(seconds=90):
            raise ValueError('native publication deadline exceeded')
    with capture_source_reads() as sources:
        runtime=current_runtime(guard=within_deadline)
        if runtime_digest(runtime)!=expected_runtime or SOURCE not in runtime['native_source_manifest']:
            raise ValueError('externally pinned native publication runtime differs')
        candidate_path=Path(settings['candidate_path'])
        candidate_raw=_owned_bytes(candidate_path,16384)
        if receipt_profile:
            _serving_settings(serving_model,settings,assessed_at=now,guard=within_deadline)
            candidate=serving_model.candidate
        else:
            candidate=read_native_candidate(candidate_path,assessed_at=now,runtime=runtime,
                expected_artifact_sha256=expected_artifact,guard=within_deadline)
        if geometry is None:geometry=read_geometry(settings,issue=issue,guard=within_deadline)
        while _clock()<issue-timedelta(seconds=20):
            within_deadline();sleep(min(.1,max(0,(issue-timedelta(seconds=20)-_clock()).total_seconds())))
        known=_clock()
        if not timedelta(0)<issue-known<=timedelta(seconds=60):
            raise ValueError('actual bounded native pre-issue clock required')
        # Native geometry must already exist when collection begins; accepting
        # an issue-time packet here would conceal work outside the source clock.
        if _instant(geometry.descriptor()['available_at'])>known:
            raise ValueError('native geometry unavailable before input collection')
        archive=delivery_directory(settings,issue)
        if backend is None:
            translated=backend_settings(settings);translated['evidence_directory']=str(archive)
            backend=CompressedSourceLiveBackend(translated,shared_lock_guard=within_deadline)
        inputs=backend.collect(issue=issue,known_at=known);available=_clock()
        if available>issue:raise ValueError('original native sources arrived after issue')
        while _clock()<issue:
            within_deadline();sleep(min(.1,max(0,(issue-_clock()).total_seconds())))
        report=None;report_path=Path(settings['evidence_directory'])/'latest-native-provisional-performance.json'
        if report_path.exists():
            try:
                possible=_read_private(report_path);original._validate_report(possible,expected_artifact,available);report=possible
            except (OSError,ValueError,TypeError,KeyError):pass
        if receipt_profile:
            capture=forecasts.build_serving_capture(serving_model,inputs,geometry=geometry,
                expected_geometry_sha256=geometry.sha256,issue=issue,available=available,published=_clock(),
                check_budget=within_deadline,monitoring_report=report)
        else:
            capture=forecasts.build_capture(candidate,inputs,geometry=geometry,runtime=runtime,
                expected_artifact_sha256=expected_artifact,expected_geometry_sha256=geometry.sha256,
                issue=issue,available=available,published=_clock(),check_budget=within_deadline,monitoring_report=report)
        origin_path=forecasts.persist(archive,capture)
        if receipt_profile:
            _serving_settings(serving_model,settings,assessed_at=_clock(),guard=within_deadline)
            selected=json.loads(serving_model._selection._encoded)
            association=dict(schema='earthship-native-serving-model-binding/v1',
                capture_sha256=capture['capture_sha256'],artifact_sha256=expected_artifact,
                runtime_sha256=expected_runtime,issued_at=issue.isoformat(),stage=selected['stage'],
                deployment_sha256=selected['deployment_sha256'],
                model_receipt_path=settings['model_receipt_path'],model_receipt_sha256=settings['model_receipt_sha256'],
                automatic_actuation=False)
            association['binding_sha256']=forecasts.digest(association,'binding_sha256')
            binding_path=original.persist(archive,association,field='capture_sha256',
                suffix='.native-serving-model-binding-v1.json',maximum=8192)
            if _owned_bytes(binding_path,8192)!=_canonical(association):
                raise ValueError('serving capture association readback differs')
            within_deadline()
        def send_guard():
            within_deadline();_resource_preflight();backend.verify_unchanged()
            if receipt_profile:_serving_settings(serving_model,settings,assessed_at=_clock(),guard=within_deadline)
            if (_owned_bytes(candidate_path,16384)!=candidate_raw or
                _canonical(current_runtime(guard=within_deadline))!=_canonical(runtime)):
                raise ValueError('frozen native candidate or runtime changed')
            _temperatures(capture['inputs']['origin_temperatures'],capture['inputs']['current'],
                issued_at=issue,published_at=_clock(),version=2)
            sources.verify();within_deadline()
        receipts={}
        for item,value in ((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,forecasts.publication(capture))):
            state=_canonical(value).decode();send_guard();backend.put(item,state,preflight=send_guard)
            receipt=_persisted_after_write(backend,item,state,since=issue,guard=send_guard)
            if receipt is None or _canonical(_receipt(receipt,item)[0])!=_canonical(value):
                raise ValueError('native delivery not actually persisted')
            receipts[item]=receipt
        send_guard();validate_delivery(capture,receipts)
        delivery=dict(schema='earthship-provisional-thermal-delivery/v2',issued_at=issue.isoformat(),
            capture_path=str(origin_path),capture_sha256=capture['capture_sha256'],artifact_sha256=expected_artifact,
            runtime_sha256=expected_runtime,geometry_series_sha256=geometry.sha256,receipts=receipts)
        delivery['delivery_sha256']=forecasts.digest(delivery,'delivery_sha256')
        path=original.persist(archive,delivery,field='delivery_sha256',suffix='.native-provisional-delivery-v2.json',maximum=65536)
        if _owned_bytes(path,65536)!=_canonical(delivery):raise ValueError('original native delivery readback differs')
        send_guard()
    return dict(status='published',mode='provisional',delivery_verified=True,origin_path=str(origin_path),delivery_path=str(path),
        capture_sha256=capture['capture_sha256'],artifact_sha256=expected_artifact,runtime_sha256=expected_runtime,automatic_actuation=False)


def withdraw(settings,*,guard,backend=None):
    """Withdraw fixed native telemetry without reading a candidate or geometry."""
    from thermal_model.provisional_forecast import unavailable
    guard();_resource_preflight()
    if backend is None:
        token=_owned_bytes(Path(settings['token_file']),4096).decode().strip()
        backend=TelemetryTransport(base=settings['openhab_base'],token_reader=lambda:token,
            budget=ReadBudget(30,max_requests=8,guard=guard))
    at=_clock();main=unavailable(at);main.update(schema='earthship-provisional-thermal-publication/v2',version=9)
    numeric=dict(schema='earthship-provisional-thermal-forecast/v2',status='unavailable',generated_at=at.isoformat(),
        graduated=False,automatic_actuation=False)
    for item,value in ((NUMERIC_ITEM,numeric),(PUBLICATION_ITEM,main)):
        state=_canonical(value).decode();backend.put(item,state,preflight=guard)
        receipt=_persisted_after_write(backend,item,state,since=at,guard=guard)
        if receipt is None or _canonical(_receipt(receipt,item)[0])!=_canonical(value):
            raise ValueError('native withdrawal delivery unverified')
    return dict(status='withdrawn',mode='unavailable',delivery_verified=True,automatic_actuation=False)


GEOMETRY_SCHEMA='earthship-native-forecast-geometry/v1'
GEOMETRY_FIELDS={'schema','issued_at','artifact_sha256','runtime_sha256','geometry','geometry_series_sha256','prepared_at','preparation_sha256'}
GEOMETRY_MAX=4*1024*1024+65536


def load_settings(path,*,withdraw=False):
    """Explicit private v2 selection; v1 configurations retain their own loader."""
    from thermal_model.provisional_live import FIELDS,SOURCE_FIELDS
    from thermal_model.forcing_capture import _private_directory
    from thermal_model.policy_registration import _read_private
    from thermal_model.capture_readers import BASES
    from thermal_model.graduation_policy import _sha
    path=Path(path);_private_directory(path.parent)
    if len(_owned_bytes(path,8192))>8192:raise ValueError('bounded native configuration required')
    value=_read_private(path)
    serving=isinstance(value,dict) and value.get('schema')==SERVING_SCHEMA
    if (not isinstance(value,dict) or set(value)!=FIELDS|{'artifact_sha256','runtime_sha256','geometry_directory'}|({'model_receipt_path','model_receipt_sha256'} if serving else set()) or
        value['schema'] not in (LIVE_SCHEMA,SERVING_SCHEMA) or value['openhab_base'] not in BASES):
        raise ValueError('closed native production configuration required')
    _sha(value['artifact_sha256']);_sha(value['runtime_sha256']);_instant(value['native_cutover'])
    if serving:_sha(value['model_receipt_sha256'])
    for key in SOURCE_FIELDS|{'evidence_directory','shared_lock','geometry_directory'}|({'model_receipt_path'} if serving else set()):
        target=Path(value[key])
        if not target.is_absolute() or target.resolve()!=target:raise ValueError('resolved native source required')
        _private_directory(target.parent)
        if key in ('evidence_directory','geometry_directory'):
            if not withdraw:_private_directory(target)
        elif not withdraw or key in ('token_file','shared_lock'):_owned_bytes(target,131072 if key=='model_receipt_path' else 16384)
    return deepcopy(value)


def geometry_path(settings,issue):
    from thermal_model.forcing_capture import _private_directory
    from thermal_model.graduation_policy import _sha
    issue=_instant(issue)
    if issue.minute%5 or issue.second!=15 or issue.microsecond:raise ValueError('aligned native geometry issue required')
    root=_private_directory(Path(settings['geometry_directory']))
    return root/(issue.strftime('%Y%m%dT%H%M%SZ')+'-'+_sha(settings['artifact_sha256'])+'.native-forecast-geometry-v1.json')


def read_geometry(settings,*,issue,guard):
    """Replay an earlier packet for this exact issue and external model pins."""
    from native_thermal_artifact import _read
    from native_thermal_forecast import digest
    from astro_geometry_series import replay_series
    settings=deepcopy(settings);issue=_instant(issue);guard();path=geometry_path(settings,issue)
    raw,body=_read(path,GEOMETRY_MAX)
    if (not isinstance(body,dict) or set(body)!=GEOMETRY_FIELDS or body['schema']!=GEOMETRY_SCHEMA or
        digest(body,'preparation_sha256')!=body['preparation_sha256'] or
        _instant(body['issued_at'])!=issue or body['artifact_sha256']!=settings['artifact_sha256'] or
        body['runtime_sha256']!=settings['runtime_sha256']):
        raise ValueError('original native geometry preparation binding differs')
    packet=body['geometry'];geometry=replay_series(_canonical(packet),request=packet['request'],
        expected_series_sha256=body['geometry_series_sha256'],expected_native_runtime=packet['native_runtime'])
    if (packet['request']['instants']!=[(issue+timedelta(minutes=5*i)).isoformat() for i in range(1,289)] or
        not _instant(geometry.descriptor()['available_at'])<=_instant(body['prepared_at'])<issue-timedelta(seconds=20) or
        _instant(body['prepared_at'])>_clock()):
        raise ValueError('whole native geometry unavailable before collection')
    guard()
    if _owned_bytes(path,GEOMETRY_MAX)!=raw:raise ValueError('original native prepared geometry changed')
    return geometry


def prepare_geometry(settings,*,issue,library_paths,guard,serving_model=None):
    """Bounded installed SunCalc batches, completed before input collection."""
    import secrets
    from hashlib import sha256
    from native_thermal_artifact import _read,LIMITS
    from native_thermal_forecast import digest
    from astro_geometry import build_source
    from astro_geometry_series import build_series_request,split_series_request,build_series
    from astro_geometry_worker import runtime_identity,capture_batch
    from thermal_model.runtime_bundle import _write_private,_sync_directory
    from thermal_model.rollback import _rename_new
    from thermal_model.replay_budget import capture_source_reads
    settings=deepcopy(settings);issue=_instant(issue);path=geometry_path(settings,issue);started=_clock()
    receipt_profile=settings.get('schema')==SERVING_SCHEMA
    if (settings.get('schema') not in (LIVE_SCHEMA,SERVING_SCHEMA) or receipt_profile!=(serving_model is not None) or
            not timedelta(seconds=20)<issue-started<=timedelta(minutes=5)):
        raise ValueError('bounded earlier native preparation window required')
    deadline=monotonic()+75
    def check():
        guard();_resource_preflight()
        if monotonic()>=deadline or _clock()>=issue-timedelta(seconds=20):
            raise ValueError('native geometry preparation deadline elapsed')
    check()
    if receipt_profile:_serving_settings(serving_model,settings,assessed_at=started,guard=check)
    if path.exists():
        read_geometry(settings,issue=issue,guard=check)
        return dict(status='prepared',path=str(path),automatic_actuation=False)
    with capture_source_reads() as sources:
        runtime=current_runtime(guard=check)
        if runtime_digest(runtime)!=settings['runtime_sha256'] or SOURCE not in runtime['native_source_manifest']:
            raise ValueError('externally pinned native preparation runtime differs')
        if receipt_profile:
            candidate=serving_model.candidate
        else:
            candidate=read_native_candidate(Path(settings['candidate_path']),assessed_at=started,runtime=runtime,
                expected_artifact_sha256=settings['artifact_sha256'],guard=check)
        ref=candidate['originals']['geometry'];raw,training=_read(ref['path'],LIMITS['geometry'])
        if sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('original fitted native geometry changed')
        native_runtime=training['native_runtime'];source=training['caches'][0]['source'];site=source['site'];zone=training['request']['timezone']
        if runtime_identity(library_paths,binding_version=native_runtime['binding_version'],guard=check)!=native_runtime:
            raise ValueError('installed geometry differs from fitted native runtime')
        request=build_series_request([issue+timedelta(minutes=5*i) for i in range(1,289)],requested_at=_clock(),
            latitude=site['latitude'],longitude=site['longitude'],timezone_name=zone)
        caches=[]
        for chunk in split_series_request(request):
            check();observed=build_source(chunk,observed_at=_clock(),native_runtime=native_runtime,source_status='ONLINE',
                latitude=site['latitude'],longitude=site['longitude'],timezone_name=zone,altitude_m=site['altitude_m'])
            caches.append(capture_batch(chunk,observed,library_paths=library_paths,scratch=path.parent,guard=check,clock=_clock));check()
        geometry=build_series(request,caches,expected_native_runtime=native_runtime)
        body=dict(schema=GEOMETRY_SCHEMA,issued_at=issue.isoformat(),artifact_sha256=candidate['artifact_sha256'],
            runtime_sha256=settings['runtime_sha256'],geometry=geometry.to_dict(),geometry_series_sha256=geometry.sha256,prepared_at=_clock().isoformat())
        body['preparation_sha256']=digest(body,'preparation_sha256');raw=_canonical(body)
        if len(raw)>GEOMETRY_MAX:raise ValueError('bounded original native preparation required')
        temporary=path.parent/('.native-geometry-'+secrets.token_hex(16));created=False
        try:
            _write_private(temporary,raw);created=True;check();sources.verify()
            if receipt_profile:_serving_settings(serving_model,settings,assessed_at=_clock(),guard=check)
            _rename_new(temporary,path);created=False;_sync_directory(path.parent)
        finally:
            if created:temporary.unlink()
        check();read_geometry(settings,issue=issue,guard=check);sources.verify()
        if receipt_profile:_serving_settings(serving_model,settings,assessed_at=_clock(),guard=check)
    return dict(status='prepared',path=str(path),geometry_series_sha256=geometry.sha256,automatic_actuation=False)


def _native_completion_index(root,now,guard):
    from thermal_model.provisional_monitor import _folders
    from native_thermal_artifact import _read
    from native_thermal_score import COMPLETION_FIELDS,COMPLETION_SCHEMA,COMPLETION_SUFFIX
    paths=[]
    for folder in _folders(root,'scores',now):
        guard();paths.extend(folder.glob('*'+COMPLETION_SUFFIX))
    if len(paths)>4096:raise ValueError('bounded native completion inventory required')
    index={}
    for path in paths:
        guard();_,value=_read(path,65536)
        if (not isinstance(value,dict) or set(value)!=COMPLETION_FIELDS or value['schema']!=COMPLETION_SCHEMA or
            value['release_authority'] is not False or runtime_digest(value,'completion_sha256')!=value['completion_sha256'] or
            path.name!=value['completion_sha256']+COMPLETION_SUFFIX or _instant(value['completed_at'])>now):
            raise ValueError('closed original native completion index required')
        score_path=Path(value['source_score_path'])
        if not score_path.is_absolute() or score_path.resolve()!=score_path or not score_path.is_relative_to(root):
            raise ValueError('native source score outside original archive')
        if value['job_id'] in index:raise ValueError('duplicate native completed job')
        index[value['job_id']]=(path,value)
    return index


def _write_native_report(root,report,guard):
    import os,secrets
    from thermal_model.forcing_capture import _private_directory
    from thermal_model.runtime_bundle import _write_private,_sync_directory
    root=_private_directory(root);path=root/'latest-native-provisional-performance.json'
    if path.exists():_owned_bytes(path,131072)
    temporary=root/('.native-performance-'+secrets.token_hex(16))
    try:
        _write_private(temporary,_canonical(report));guard();os.replace(temporary,path);_sync_directory(root)
    finally:
        if temporary.exists():temporary.unlink()


def refresh_report(settings,*,runtime,artifact_sha256,now,guard,serving_model=None):
    """Reconcile retained raw-source completions before replacing native stats."""
    from native_thermal_score import reconcile_source_report
    from thermal_model.forcing_capture import _private_directory
    root=_private_directory(Path(settings['evidence_directory']));now=_instant(now)
    index=_native_completion_index(root,now,guard)
    selected=sorted((entry for entry in index.values() if entry[1]['artifact_sha256']==artifact_sha256),
        key=lambda entry:_instant(entry[1]['completed_at']),reverse=True)[:256]
    entries=[dict(completion_path=str(path),completion_sha256=value['completion_sha256'],
        source_score_sha256=value['source_score_sha256'],capture_sha256=value['capture_sha256']) for path,value in selected]
    if serving_model is not None:
        from native_thermal_score import reconcile_serving_source_report
        _serving_settings(serving_model,settings,assessed_at=now,guard=guard)
        report=reconcile_serving_source_report(entries,selections=(serving_model._selection,),artifact_sha256=artifact_sha256,
            assessed_at=now,check_budget=guard)
        serving_model.verify_bindings(assessed_at=now,guard=guard)
    else:
        if settings.get('schema')==SERVING_SCHEMA:raise ValueError('owned serving report context required')
        report=reconcile_source_report(entries,runtime=runtime,artifact_sha256=artifact_sha256,assessed_at=now,check_budget=guard)
    guard();_write_native_report(root,report,guard);return report


def score_jobs(settings,*,guard,reader=None,max_jobs=1,serving_model=None,historical_selections=()):
    """One native outcome with raw query replay and source-backed reporting."""
    import json
    import native_thermal_score as scores
    from native_thermal_artifact import _read
    from household_cycle import load_cycle_delivery
    from thermal_model.forcing_capture import _private_directory
    from thermal_model.provisional_monitor import _folders
    from thermal_model.provisional_live import _phase_directory
    from thermal_model.recent_cycles import compare_v2
    from thermal_model.replay_budget import shared_replay_budget,capture_source_reads
    if type(max_jobs) is not int or max_jobs!=1:raise ValueError('one serial native score job required')
    settings=deepcopy(settings);guard();_resource_preflight();now=_clock();deadline=monotonic()+50
    def remaining():
        guard();seconds=deadline-monotonic()
        if seconds<=0:raise ValueError('native scoring deadline exceeded')
        return seconds
    receipt_profile=settings.get('schema')==SERVING_SCHEMA
    if settings.get('schema') not in (LIVE_SCHEMA,SERVING_SCHEMA):raise ValueError('explicit native scoring selection required')
    if receipt_profile:
        if type(historical_selections) is not tuple or len(historical_selections)>31:raise ValueError('bounded owned historical score selections required')
        _serving_settings(serving_model,settings,assessed_at=now,guard=remaining)
    elif serving_model is not None or historical_selections:raise ValueError('receipt context requires explicit serving profile')
    root=_private_directory(Path(settings['evidence_directory']))
    report_path=root/'latest-native-provisional-performance.json'
    if report_path.exists():
        from thermal_model.runtime_bundle import _sync_directory
        _owned_bytes(report_path,131072);remaining();report_path.unlink();_sync_directory(root)
    with shared_replay_budget(remaining),capture_source_reads() as originals:
        runtime=serving_model.runtime if receipt_profile else current_runtime(guard=remaining)
        if runtime_digest(runtime)!=settings['runtime_sha256'] or SOURCE not in runtime['native_source_manifest']:
            raise ValueError('externally pinned native scoring runtime differs')
        if receipt_profile:candidate=serving_model.candidate
        else:candidate=read_native_candidate(Path(settings['candidate_path']),assessed_at=now,runtime=runtime,
            expected_artifact_sha256=settings['artifact_sha256'],guard=remaining)
        folder=_phase_directory(root,'scores',now)
        if reader is None:
            config={key:settings[key] for key in ('token_file','native_db_config','native_policy','openhab_base')}
            config.update(schema=COMPRESSED_SOURCE_SCHEMA,output_directory=str(folder))
            reader=NativeScoreReader(config,shared_lock_guard=remaining)
        paths=[]
        for directory in _folders(root,'origins',now):paths.extend(directory.glob('*.native-provisional-delivery-v2.json'))
        if len(paths)>1024:raise ValueError('bounded native delivered forecast inventory required')
        deliveries=[]
        fields={'schema','issued_at','capture_path','capture_sha256','artifact_sha256','runtime_sha256','geometry_series_sha256','receipts','delivery_sha256'}
        for path in paths:
            remaining();_,delivery=_read(path,65536)
            if (not isinstance(delivery,dict) or set(delivery)!=fields or delivery['schema']!='earthship-provisional-thermal-delivery/v2' or
                runtime_digest(delivery,'delivery_sha256')!=delivery['delivery_sha256'] or path.name!=delivery['delivery_sha256']+'.native-provisional-delivery-v2.json'):
                raise ValueError('closed original native delivered record required')
            origin=Path(delivery['capture_path'])
            if not origin.is_absolute() or origin.resolve()!=origin or origin.parent!=path.parent:
                raise ValueError('native origin outside original delivery archive')
            deliveries.append((path,delivery))
        deliveries.sort(key=lambda entry:(entry[1]['artifact_sha256']!=candidate['artifact_sha256'],_instant(entry[1]['issued_at'])))
        completed=_native_completion_index(root,now,remaining);scored=0;missing=False;historical_unavailable=False
        for path,delivery in deliveries:
            remaining();issue=_instant(delivery['issued_at'])
            for horizon in (1,6,12,24):
                target=issue+timedelta(hours=horizon)
                if now<target+timedelta(minutes=5):continue
                job=runtime_digest({'capture_sha256':delivery['capture_sha256'],'horizon_hours':horizon})
                if job in completed:
                    marker=completed[job][1]
                    if any(marker[key]!=delivery[key] for key in ('artifact_sha256','capture_sha256','runtime_sha256')) or marker['horizon_hours']!=horizon:
                        raise ValueError('native completed job binding differs')
                    continue
                selected_model=None
                if receipt_profile:
                    selected_model=serving_delivery_model(path,delivery,current_model=serving_model,
                        historical_selections=historical_selections,assessed_at=now,guard=remaining)
                    if selected_model is None:
                        historical_unavailable=True;break
                archive_pins=dict(runtime=runtime if selected_model is None else selected_model.runtime,
                    expected_artifact_sha256=delivery['artifact_sha256'],expected_capture_sha256=delivery['capture_sha256'])
                if receipt_profile:archive_pins['serving_model']=selected_model
                archive=load_cycle_delivery(dict(status='published' ,delivery_verified=True,origin_path=delivery['capture_path'],delivery_path=str(path)),
                    issue=issue,guard=remaining,**archive_pins)
                capture=archive['capture']
                if _native_gap_pending(root,now,job,delivery,path,capture,remaining):continue
                for receipt in archive['receipts'].values():
                    if _canonical(reader.publication(receipt))!=_canonical(receipt):raise ValueError('actual original native publication missing')
                phase=capture['candidate']['fit']['sensor_epochs']['air']
                outcome=reader.native([target],assessed_at=now,sensor_epoch=phase)
                if len(outcome)!=1 or _instant(outcome[0][0])!=target:raise ValueError('original native outcome shape differs')
                if outcome[0][1] is None:
                    reader.verify_unchanged();archive['verify_unchanged']();originals.verify();remaining()
                    _retain_native_gap(folder,job,delivery,path,capture,horizon=horizon,target=target,now=now,
                        paths=list(reader.native_source_paths),guard=remaining)
                    missing=True;break
                grid={}
                def historical(targets,assessed):
                    rows=reader.native(targets,assessed_at=assessed,sensor_epoch=phase)
                    for at,receipt in rows:
                        key=_instant(at).isoformat()
                        encoded=None if receipt is None else {name:value.isoformat() if isinstance(value,datetime) else value for name,value in receipt.items()}
                        if key in grid and grid[key]!=encoded:raise ValueError('original native comparator endpoint changed')
                        grid[key]=encoded
                    return rows
                compare_v2(issue=issue,target=target,current_f=capture['output']['initial']['air_f'],grid_reader=historical,sensor_epoch=phase)
                source_args=dict(capture_path=delivery['capture_path'],receipts=archive['receipts'],outcome=outcome[0][1],
                    recent_cycle_grid=[[at,value] for at,value in sorted(grid.items())],source_paths=list(reader.native_source_paths),
                    horizon_hours=horizon,assessed_at=now,expected_capture_sha256=delivery['capture_sha256'],check_budget=remaining)
                if receipt_profile:source=scores.build_serving_source_score(model=selected_model,**source_args)
                else:source=scores.build_source_score(runtime=runtime,expected_artifact_sha256=delivery['artifact_sha256'],**source_args)
                reader.verify_unchanged();archive['verify_unchanged']();originals.verify();remaining()
                if receipt_profile:selected_model.verify_bindings(assessed_at=_clock(),guard=remaining)
                source_path=scores.persist_source_score(folder,source)
                completion_args=dict(expected_capture_sha256=delivery['capture_sha256'],expected_source_score_sha256=source['source_score_sha256'],
                    completed_at=_clock(),check_budget=remaining)
                if receipt_profile:completion=scores.build_serving_source_completion(source_path,model=selected_model,**completion_args)
                else:completion=scores.build_source_completion(source_path,runtime=runtime,expected_artifact_sha256=delivery['artifact_sha256'],**completion_args)
                reader.verify_unchanged();archive['verify_unchanged']();originals.verify();remaining()
                if receipt_profile:selected_model.verify_bindings(assessed_at=_clock(),guard=remaining)
                scores.persist_source_completion(folder,completion);scored=1;break
            if scored or missing:break
        report_args={} if not receipt_profile else dict(serving_model=serving_model)
        report=refresh_report(settings,runtime=runtime,artifact_sha256=candidate['artifact_sha256'],now=_clock(),guard=remaining,**report_args)
        reader.verify_unchanged();originals.verify();remaining()
        result=dict(status='scored' if scored else 'monitoring_refreshed' if missing else 'waiting',scored=scored,
            current_revision_scored=sum(row['model']['count'] for row in report['by_horizon'].values()),automatic_actuation=False)
        if missing:result['pending_reason']='mature_outcome_unavailable'
        elif historical_unavailable:result['pending_reason']='historical_model_selection_unavailable'
        return result


GAP_SCHEMA='earthship-native-thermal-gap/v1'
GAP_FIELDS={'schema','job_id','delivery_sha256','capture_sha256','artifact_sha256','runtime_sha256','horizon_hours',
    'target_at','assessed_at','retry_after','native_source_paths','original_fingerprints','queue_source_sha256','automatic_actuation','gap_sha256'}


def _validate_native_absence(paths,capture,*,target,assessed,guard):
    from weather_temperature_sources import read_compressed_temperature_source,replay_temperature_source
    if not isinstance(paths,list) or len(paths)!=1:raise ValueError('one original native absence query required')
    path=Path(paths[0]);guard();packet=read_compressed_temperature_source(path.parent,path)
    if (packet['targets']!=[target.isoformat()] or _instant(packet['assessed_at'])!=assessed or packet['stream']!='indoor' or
        packet['sensor_epoch']!=capture['candidate']['fit']['sensor_epochs']['air']):
        raise ValueError('original native absence query context differs')
    values=replay_temperature_source(packet);guard()
    if len(values)!=1 or _instant(values[0][0])!=target or values[0][1] is not None:
        raise ValueError('native absence query selected a measurement')


def _native_gap_pending(root,now,job,delivery,delivery_path,capture,guard):
    from thermal_model.provisional_monitor import _folders,_fingerprint
    from native_thermal_artifact import _read
    paths=[]
    for folder in _folders(root,'scores',now):paths.extend(folder.glob(job+'-*.native-thermal-gap-v1.json'))
    # Three retained UTC days contain at most 289 quarter-hour retries.
    if len(paths)>512:raise ValueError('bounded native absence retries required')
    latest=None
    for path in paths:
        guard();_,value=_read(path,131072)
        if (not isinstance(value,dict) or set(value)!=GAP_FIELDS or value['schema']!=GAP_SCHEMA or value['automatic_actuation'] is not False or
            runtime_digest(value,'gap_sha256')!=value['gap_sha256'] or path.name!=job+'-'+value['gap_sha256']+'.native-thermal-gap-v1.json' or
            value['queue_source_sha256']!=sha256(_source_bytes(Path(__file__).resolve(),maximum=2000000)).hexdigest() or
            value['job_id']!=job or any(value[key]!=delivery[key] for key in ('delivery_sha256','capture_sha256','artifact_sha256','runtime_sha256'))):
            raise ValueError('original native retry gap binding differs')
        assessed=_instant(value['assessed_at']);target=_instant(value['target_at'])
        if (assessed>now or _instant(value['retry_after'])!=assessed+timedelta(minutes=15) or
            target!=_instant(capture['issued_at'])+timedelta(hours=value['horizon_hours'])):
            raise ValueError('original native retry clock differs')
        for name,fingerprint in value['original_fingerprints'].items():
            if _fingerprint(name)!=fingerprint:raise ValueError('native absence originals changed')
        _validate_native_absence(value['native_source_paths'],capture,target=target,assessed=assessed,guard=guard)
        if latest is None or assessed>_instant(latest['assessed_at']):latest=value
    return latest is not None and now<_instant(latest['retry_after'])


def _retain_native_gap(folder,job,delivery,delivery_path,capture,*,horizon,target,now,paths,guard):
    from thermal_model.provisional_monitor import _fingerprint
    from thermal_model.provisional_forecast import persist
    _validate_native_absence(paths,capture,target=target,assessed=now,guard=guard)
    sources=set(paths)|{str(delivery_path),delivery['capture_path']}|{ref['path'] for ref in capture['candidate']['originals'].values()}|set(capture['native_origin_binding'].get('query_sources',{}).values())
    value=dict(schema=GAP_SCHEMA,job_id=job,delivery_sha256=delivery['delivery_sha256'],capture_sha256=delivery['capture_sha256'],
        artifact_sha256=delivery['artifact_sha256'],runtime_sha256=delivery['runtime_sha256'],horizon_hours=horizon,target_at=target.isoformat(),
        assessed_at=now.isoformat(),retry_after=(now+timedelta(minutes=15)).isoformat(),native_source_paths=list(paths),
        original_fingerprints={name:_fingerprint(name) for name in sorted(sources)},
        queue_source_sha256=sha256(_source_bytes(Path(__file__).resolve(),maximum=2000000)).hexdigest(),automatic_actuation=False)
    value['gap_sha256']=runtime_digest(value,'gap_sha256');guard()
    persist(folder,value,field='gap_sha256',suffix='.native-thermal-gap-v1.json',maximum=131072)
    stored=folder/(value['gap_sha256']+'.native-thermal-gap-v1.json');target_path=folder/(job+'-'+value['gap_sha256']+'.native-thermal-gap-v1.json')
    from thermal_model.rollback import _rename_new
    _rename_new(stored,target_path);guard()
    return value


SERVING_RECEIPT_SOURCE_SHA256='94d85e37afc79e08cf9de93ba937b2ba845acc7111c0a23e483b186d8ff9a57e'


def serving_delivery_model(delivery_path,delivery,*,current_model,historical_selections,assessed_at,guard):
    """Resolve a capture audit through explicit owned selections, never its own pin."""
    from native_model_serving_receipt import _require_model,OwnedServingSelection,read_serving_model
    from native_thermal_artifact import _read
    from thermal_model.graduation_policy import _sha
    _require_model(current_model)
    if type(historical_selections) is not tuple or len(historical_selections)>31:
        raise ValueError('bounded retained historical selections required')
    path=Path(delivery_path).parent/(_sha(delivery['capture_sha256'])+'.native-serving-model-binding-v1.json')
    if not path.exists() and not path.is_symlink():return None
    guard();raw,binding=_read(path,8192)
    fields={'schema','capture_sha256','artifact_sha256','runtime_sha256','issued_at','stage','deployment_sha256',
        'model_receipt_path','model_receipt_sha256','automatic_actuation','binding_sha256'}
    if (not isinstance(binding,dict) or set(binding)!=fields or binding['schema']!='earthship-native-serving-model-binding/v1' or
        binding['automatic_actuation'] is not False or runtime_digest(binding,'binding_sha256')!=_sha(binding['binding_sha256']) or
        any(binding[name]!=delivery[name] for name in ('capture_sha256','artifact_sha256','runtime_sha256','issued_at'))):
        raise ValueError('original serving capture association differs')
    selected_model=None;key=(binding['stage'],_sha(binding['deployment_sha256']))
    current=json.loads(current_model._selection._encoded)
    if key==(current['stage'],current['deployment_sha256']):selected_model=current_model
    else:
        for selection in historical_selections:
            if type(selection) is not OwnedServingSelection:raise ValueError('owned historical model selection required')
            selected=json.loads(selection._encoded)
            if key==(selected['stage'],selected['deployment_sha256']):
                # Different executing source/runtime must use its explicitly
                # scheduled retained worker, never current process numerics.
                if selected['runtime_sha256']!=current['runtime_sha256']:return None
                if selected_model is not None:raise ValueError('unique historical capture selection required')
                selected_model=read_serving_model(selection,assessed_at=assessed_at,guard=guard)
    if selected_model is None:return None
    chosen=json.loads(selected_model._selection._encoded)
    if (binding['model_receipt_path']!=chosen['receipt']['path'] or binding['model_receipt_sha256']!=chosen['receipt']['sha256'] or
        binding['artifact_sha256']!=selected_model.candidate['artifact_sha256'] or binding['runtime_sha256']!=selected_model.candidate['runtime_sha256']):
        raise ValueError('historical receipt cannot qualify another capture model')
    selected_model.verify_bindings(assessed_at=assessed_at,guard=guard)
    if _read(path,8192)[0]!=raw:raise ValueError('serving capture association changed during selection')
    guard();return selected_model
