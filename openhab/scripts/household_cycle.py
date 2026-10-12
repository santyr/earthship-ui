"""Observe the unchanged forecast cycle under its caller-owned lock.

This module is outside both producer source manifests. Original forecast inputs,
transport and numerical outputs are delegated unchanged; no model fitting or
device request is introduced by observation.
"""
from datetime import datetime,timedelta,timezone
import math,time
from household.codec import canonical,loads
from household.evidence import utc

MAX_SOURCE_BYTES=1048576
MAX_COLLECTION_SECONDS=6.
ISSUE_MARGIN=timedelta(seconds=3)


class ObservingBackend:
    def __init__(self,parent,*,collector,guard,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic):
        self.parent=parent;self.collector=collector;self.guard=guard
        self.clock=clock;self.monotonic=monotonic
        self.collection=dict(status='unavailable',reason='not_collected')

    def __getattr__(self,name):
        return getattr(self.parent,name)

    def collect(self,*,issue,known_at):
        # Parent exceptions are authoritative forecast failures, not observer
        # failures. Do not catch or replace its exact original input object.
        inputs=self.parent.collect(issue=issue,known_at=known_at)
        issue=utc(issue);now=utc(self.clock())
        budget=min(MAX_COLLECTION_SECONDS,(issue-ISSUE_MARGIN-now).total_seconds())
        if not math.isfinite(budget) or budget<=0:
            self.collection=dict(status='unavailable',reason='insufficient_preissue_budget')
            return inputs
        deadline=self.monotonic()+budget
        def remaining():
            self.guard()
            value=min(deadline-self.monotonic(),(issue-ISSUE_MARGIN-utc(self.clock())).total_seconds())
            if not math.isfinite(value) or not 0<value<=MAX_COLLECTION_SECONDS:
                raise ValueError('household pre-issue budget elapsed')
            return value
        try:
            remaining()
            originals=self.collector(issue=issue,remaining=remaining,guard=self.guard)
            remaining()
            if not isinstance(originals,dict):raise ValueError('closed original source object required')
            raw=canonical(originals)
            if len(raw)>MAX_SOURCE_BYTES:raise ValueError('bounded household originals required')
            remaining()
            captured=utc(self.clock())
            if captured<now:raise ValueError('household collection clock moved backward')
            self.collection=dict(status='collected',reason=None,issue=issue.isoformat(),
                captured_at=captured.isoformat(),originals=loads(raw))
        except Exception:
            self.collection=dict(status='unavailable',reason='source_collection_failed')
        return inputs


def derive_cycle(*,originals,capture,receipts,thermal,weather,parameter_record,runtime_manifest,code_revision,now):
    """One same-issue snapshot and pure plan; no live reads or transport."""
    from household.control_contracts import instant
    from household.thermal_model import PreparedProjection
    from household.weather_context import PreparedWeatherContext
    from household.energy_configuration import PreparedEnergyConfiguration
    from household.measured_weather import PreparedMeasuredWeather
    from household.measured_weather_snapshot import bind_measured_weather_snapshot
    from household.energy_model import freeze_energy_inputs,bind_energy_inputs
    from household.capabilities import CapabilityRegistry
    from household.pipeline import seal_pipeline,replay_pipeline
    from thermal_model.provisional_score import validate_delivery
    validate_delivery(capture,receipts)
    fields={'schema','issue','captured_at','power_receipt','energy_configuration','measured_weather','owner_bindings','automatic_actuation'}
    if not isinstance(originals,dict) or set(originals)!=fields or originals['schema']!='earthship-household-cycle-sources/v1' or originals['automatic_actuation'] is not False:
        raise ValueError('closed original cycle sources required')
    issue=instant(capture['issued_at']);now=utc(now)
    if instant(originals['issue'])!=issue or instant(originals['captured_at'])>issue or now<instant(capture['published_at']):
        raise ValueError('original cycle issue or availability differs')
    source=originals['power_receipt']
    if instant(source['snapshot']['as_of'])>issue or instant(source['snapshot']['created_at'])>issue:
        raise ValueError('original source collection completed after issue')
    if not isinstance(thermal,PreparedProjection) or not isinstance(weather,PreparedWeatherContext):
        raise ValueError('independently prepared original models required')
    if thermal.to_dict()['original_capture_sha256']!=capture['capture_sha256'] or canonical(weather.original_capture)!=canonical(capture):
        raise ValueError('original model capture differs')
    if not isinstance(parameter_record,dict) or instant(parameter_record['collected_at'])>issue:
        raise ValueError('original earlier parameters required')
    configuration=PreparedEnergyConfiguration(canonical(originals['energy_configuration']))
    measured=PreparedMeasuredWeather(canonical(originals['measured_weather']))
    snapshot=bind_measured_weather_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],
        weather_context=weather,energy_configuration=configuration,measured_weather=measured,code_revision=code_revision)
    body=snapshot.to_dict();soc=body['domains']['energy']['battery_soc']['value']
    numerical={**parameter_record['record']['household_energy_inputs'],'soc_pct':soc}
    energy=bind_energy_inputs(freeze_energy_inputs(**numerical),snapshot=snapshot)
    registry=CapabilityRegistry(canonical({key:value for key,value in source['registry'].items() if key!='registry_id'}))
    if registry.to_dict()!=source['registry']:raise ValueError('original registry differs')
    preferences=dict(horizon_hours=24,reserve_soc=10.,low_trough_threshold_soc_pct=90.,surplus_weight=1.,reserve_weight=1.,comfort_min_f=65.,comfort_max_f=80.)
    coordination=dict(schema='earthship-shadow-coordination/v1',snapshotId=snapshot.snapshot_id,horizonHours=24,baseline_soc_floor=None,facts={})
    record=seal_pipeline(snapshot=snapshot,registry=registry,energy_inputs=energy,thermal_inputs=thermal,
        thermal_runtime=thermal.to_dict()['executing_runtime'],coordination=coordination,config=preferences,now=now,runtime_manifest=runtime_manifest)
    if record['output']['projections']['thermal']['output']!=capture['output']:
        raise ValueError('original thermal output changed')
    if replay_pipeline(record,runtime_manifest=runtime_manifest,thermal_runtime=thermal.to_dict()['executing_runtime'])!=record:
        raise ValueError('original pipeline replay differs')
    return record


def _retain_original(directory,value,suffix,maximum):
    """Owned, immutable originals; a concurrent destination is never replaced."""
    import os,secrets
    from pathlib import Path
    from hashlib import sha256
    from household_observation import _directory,_private_file
    root=Path(directory).absolute();binding=_directory(root);raw=canonical(value)
    if len(raw)>maximum:raise ValueError('bounded cycle evidence required')
    name=sha256(raw).hexdigest()+suffix;target=root/name
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    temporary='.household-cycle-'+secrets.token_hex(16);created=False
    try:
        info=os.fstat(fd)
        if (info.st_dev,info.st_ino,info.st_mode)!=binding:raise ValueError('original evidence directory changed')
        file_fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=fd);created=True
        with os.fdopen(file_fd,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        try:os.link(temporary,name,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
        except FileExistsError:pass
        os.unlink(temporary,dir_fd=fd);created=False
        if _private_file(Path(name),maximum,directory_fd=fd)[0]!=raw or _directory(root)!=binding:
            raise ValueError('original cycle evidence differs')
        os.fsync(fd)
    finally:
        if created:os.unlink(temporary,dir_fd=fd)
        os.close(fd)
    return target


def complete_cycle(*,publication,collection,parameter_record,runtime_manifest,code_revision,
                   evidence_directory,observation_cache,guard,clock=lambda:datetime.now(timezone.utc)):
    """Use verified original archives before any model or cache publication.

    The caller owns the forecast lock and the configuration/runtime guard.
    Observer refusal propagates to that caller, never to forecast withdrawal.
    """
    from pathlib import Path
    from household_observation import _private_file,materialize
    from household.thermal_model import prepare_projection
    from household.weather_context import prepare_weather_context
    from household_pipeline import verify_source_closure
    from household.pipeline import MAX_BYTES as PIPELINE_BYTES
    from thermal_model.provisional_forecast import digest
    from thermal_model.provisional_score import validate_delivery
    from household.control_contracts import instant
    guard()
    if publication.get('status')!='published' or publication.get('delivery_verified') is not True:
        raise ValueError('verified original publication required')
    if collection.get('status')!='collected':
        return dict(status='observation_unavailable',reason='source_collection_unavailable',automatic_actuation=False)
    origin_path=Path(publication['origin_path']).absolute();delivery_path=Path(publication['delivery_path']).absolute()
    origin=_private_file(origin_path,2*1024*1024);delivery=_private_file(delivery_path,65536)
    capture=loads(origin[0]);delivered=loads(delivery[0])
    fields={'schema','issued_at','capture_path','capture_sha256','artifact_sha256','receipts','delivery_sha256'}
    if not isinstance(delivered,dict) or set(delivered)!=fields or delivered['schema']!='earthship-provisional-thermal-delivery/v1':
        raise ValueError('closed original delivery required')
    if (digest(delivered,'delivery_sha256')!=delivered['delivery_sha256'] or
        delivered['capture_path']!=str(origin_path) or delivered['capture_sha256']!=capture['capture_sha256'] or
        delivered['artifact_sha256']!=capture['candidate']['artifact_sha256'] or
        instant(delivered['issued_at'])!=instant(capture['issued_at']) or
        instant(collection['issue'])!=instant(capture['issued_at']) or
        origin_path.parent!=delivery_path.parent or
        origin_path.name!=capture['capture_sha256']+'.provisional-origin-v1.json' or
        delivery_path.name!=delivered['delivery_sha256']+'.provisional-delivery-v1.json'):
        raise ValueError('original delivery binding differs')
    validate_delivery(capture,delivered['receipts']);guard()
    thermal=prepare_projection(capture,code_revision=code_revision)
    weather=prepare_weather_context(capture,prepared_thermal=thermal)
    record=derive_cycle(originals=collection['originals'],capture=capture,receipts=delivered['receipts'],
        thermal=thermal,weather=weather,parameter_record=parameter_record,runtime_manifest=runtime_manifest,
        code_revision=code_revision,now=clock())
    verify_source_closure(record,runtime_manifest);guard()
    def unchanged():
        guard()
        if _private_file(origin_path,2*1024*1024)!=origin or _private_file(delivery_path,65536)!=delivery:
            raise ValueError('original cycle archive changed')
    unchanged()
    _retain_original(evidence_directory,collection['originals'],'.household-sources-v1.json',MAX_SOURCE_BYTES)
    receipt=_retain_original(evidence_directory,record,'.household-model-plan-v5.json',PIPELINE_BYTES)
    unchanged()
    return materialize(receipt,observation_cache,clock=clock)


class LazyForecastBackend:
    """Construct the original transport at the issue chosen by the publisher."""
    def __init__(self,settings,*,guard):
        self.settings=settings;self.guard=guard;self.parent=None

    def __getattr__(self,name):
        if self.parent is None:raise ValueError('original forecast collection has not started')
        return getattr(self.parent,name)

    def collect(self,*,issue,known_at):
        from thermal_model.provisional_live import backend_settings,delivery_directory,CompressedSourceLiveBackend
        if self.parent is not None:raise ValueError('one original issue per backend required')
        self.guard()
        settings=backend_settings(self.settings)
        settings['evidence_directory']=str(delivery_directory(self.settings,issue))
        self.parent=CompressedSourceLiveBackend(settings,shared_lock_guard=self.guard)
        return self.parent.collect(issue=issue,known_at=known_at)


def run_cycle(config_path,*,code_revision):
    """Caller-owned original lock, original publisher, then observational cache.

    No training is dispatched. Forecast failures retain the original withdrawal
    behavior; household failures report refusal without withdrawing delivery.
    """
    import os,re
    from pathlib import Path
    from hashlib import sha256
    from household_cycle_sources import load_cycle_settings,CycleSourceCollector
    from household_observation import _private_file,_directory
    from household_snapshot import _read
    from thermal_installed_intel import _resource_preflight
    from thermal_model.provisional_live import load_settings,publish_cycle,withdraw
    from thermal_model.capture_guard import SharedScoreLock
    from thermal_model.training_pressure_guard import TrainingHeadroom
    if not isinstance(code_revision,str) or re.fullmatch('[a-f0-9]{40}',code_revision) is None:
        raise ValueError('original source revision required')
    _resource_preflight()
    os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
    config_path=Path(config_path).absolute();configuration=load_cycle_settings(config_path)
    config_original=_private_file(config_path,8192)
    if loads(config_original[0])!=configuration:raise ValueError('original cycle configuration changed')
    forecast_path=Path(configuration['forecast_config']);forecast_original=_private_file(forecast_path,8192)
    settings=load_settings(forecast_path)
    parameter_path=Path(configuration['retained_energy_parameters']);parameter_original=_private_file(parameter_path,262144)
    if sha256(parameter_original[0]).hexdigest()!=configuration['parameters_sha256']:
        raise ValueError('retained original parameter digest differs')
    parameters=loads(parameter_original[0])
    _directory(Path(configuration['evidence_directory']));_directory(Path(configuration['observation_cache']).parent)
    root=Path(__file__).resolve().parent
    own={root/name:_read(root/name,262144) for name in ('household_cycle.py','household_cycle_sources.py','household_observation.py')}
    with SharedScoreLock(settings['shared_lock']) as lock:
        monitor=TrainingHeadroom(max_swapin_bytes_per_second=1048576);monitor.preflight()
        def forecast_guard():
            lock.verify();monitor.check()
            if _private_file(forecast_path,8192)!=forecast_original:
                raise ValueError('original forecast configuration changed')
        def guard():
            forecast_guard()
            if (_private_file(config_path,8192)!=config_original or _private_file(parameter_path,262144)!=parameter_original or
                any(_read(path,262144)!=raw for path,raw in own.items())):
                raise ValueError('original cycle configuration, parameters or driver changed')
        forecast_guard();collector=None
        try:
            guard()
            collector=CycleSourceCollector(token_file=settings['token_file'],openhab_base=settings['openhab_base'],code_revision=code_revision)
        except Exception:
            # A missing observer configuration must not suppress the original
            # forecast. Keep a failing collector inside the adapter boundary.
            pass
        def collect(**request):
            if collector is None:raise ValueError('household source preparation unavailable')
            return collector(**request)
        backend=ObservingBackend(LazyForecastBackend(settings,guard=forecast_guard),collector=collect,guard=guard)
        try:published=publish_cycle(settings,guard=forecast_guard,backend=backend)
        except Exception:
            try:
                result=withdraw(settings,guard=forecast_guard)
                return dict(status='withheld_and_withdrawn',delivery_verified=result.get('delivery_verified',False),automatic_actuation=False)
            except Exception:
                return dict(status='withheld',delivery_verified=False,automatic_actuation=False)
        result=dict(status=published['status'],delivery_verified=published.get('delivery_verified',False),automatic_actuation=False)
        if published['status']!='published':return result
        try:
            result['observation']=complete_cycle(publication=published,collection=backend.collection,parameter_record=parameters,
                runtime_manifest={} if collector is None else collector.runtime,code_revision=code_revision,evidence_directory=configuration['evidence_directory'],
                observation_cache=configuration['observation_cache'],guard=guard)
        except Exception:
            result['observation']=dict(status='observation_refused',reason='original_cycle_verification_failed',automatic_actuation=False)
        return result


def main(argv=None):
    import argparse,json,sys
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path);parser.add_argument('--code-revision',required=True)
    args=parser.parse_args(argv)
    try:result=run_cycle(args.config,code_revision=args.code_revision)
    except BlockingIOError:
        print(json.dumps(dict(status='busy',delivery_verified=False,automatic_actuation=False)));return 75
    except Exception:
        print(json.dumps(dict(status='cycle_refused',delivery_verified=False,automatic_actuation=False)),file=sys.stderr);return 1
    print(json.dumps(result,sort_keys=True))
    return 0 if result['status'] in ('published','deferred') else 1


if __name__=='__main__':raise SystemExit(main())
