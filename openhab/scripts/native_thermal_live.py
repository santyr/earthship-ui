"""Native thermal operational adapters; read-only acquisition grants no authority."""
from copy import deepcopy
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
SOURCE='openhab/scripts/native_thermal_live.py'

RESOURCE_SOURCE_SHA256='7d400813515db43fb6debf222ccaf02d6b057131b7137f4d4fb4d4495fe10d30'


def _resource_preflight():
    # The transitive admission helper is sealed by this runtime-bound source.
    # Check its bytes and loaded location before calling the established kernel
    # verifier; every numerical step keeps the same caps without forking ionice.
    path=Path(__file__).resolve().with_name('household_cycle_resources.py')
    if (sha256(_source_bytes(path,maximum=262144)).hexdigest()!=RESOURCE_SOURCE_SHA256 or
        Path(_publication_resource_preflight.__code__.co_filename).resolve()!=path):
        raise ValueError('native resource checker source changed')
    _publication_resource_preflight()



def _clock():return datetime.now(timezone.utc)


def publish_cycle(settings,*,guard,geometry=None,backend=None):
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
    if settings.get('schema')!=LIVE_SCHEMA or (geometry is not None and type(geometry) is not NativeGeometrySeries):
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
        capture=forecasts.build_capture(candidate,inputs,geometry=geometry,runtime=runtime,
            expected_artifact_sha256=expected_artifact,expected_geometry_sha256=geometry.sha256,
            issue=issue,available=available,published=_clock(),check_budget=within_deadline,monitoring_report=report)
        origin_path=forecasts.persist(archive,capture)
        def send_guard():
            within_deadline();_resource_preflight();backend.verify_unchanged()
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
    if (not isinstance(value,dict) or set(value)!=FIELDS|{'artifact_sha256','runtime_sha256','geometry_directory'} or
        value['schema']!=LIVE_SCHEMA or value['openhab_base'] not in BASES):
        raise ValueError('closed native production configuration required')
    _sha(value['artifact_sha256']);_sha(value['runtime_sha256']);_instant(value['native_cutover'])
    for key in SOURCE_FIELDS|{'evidence_directory','shared_lock','geometry_directory'}:
        target=Path(value[key])
        if not target.is_absolute() or target.resolve()!=target:raise ValueError('resolved native source required')
        _private_directory(target.parent)
        if key in ('evidence_directory','geometry_directory'):
            if not withdraw:_private_directory(target)
        elif not withdraw or key in ('token_file','shared_lock'):_owned_bytes(target,16384)
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


def prepare_geometry(settings,*,issue,library_paths,guard):
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
    if settings.get('schema')!=LIVE_SCHEMA or not timedelta(seconds=20)<issue-started<=timedelta(minutes=5):
        raise ValueError('bounded earlier native preparation window required')
    deadline=monotonic()+75
    def check():
        guard();_resource_preflight()
        if monotonic()>=deadline or _clock()>=issue-timedelta(seconds=20):
            raise ValueError('native geometry preparation deadline elapsed')
    check()
    if path.exists():
        read_geometry(settings,issue=issue,guard=check)
        return dict(status='prepared',path=str(path),automatic_actuation=False)
    with capture_source_reads() as sources:
        runtime=current_runtime(guard=check)
        if runtime_digest(runtime)!=settings['runtime_sha256'] or SOURCE not in runtime['native_source_manifest']:
            raise ValueError('externally pinned native preparation runtime differs')
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
            _rename_new(temporary,path);created=False;_sync_directory(path.parent)
        finally:
            if created:temporary.unlink()
        check();read_geometry(settings,issue=issue,guard=check);sources.verify()
    return dict(status='prepared',path=str(path),geometry_series_sha256=geometry.sha256,automatic_actuation=False)
