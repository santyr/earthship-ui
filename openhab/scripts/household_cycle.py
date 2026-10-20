"""Observe the unchanged forecast cycle under its caller-owned lock.

This module is outside both producer source manifests. Original forecast inputs,
transport and numerical outputs are delegated unchanged; no model fitting or
device request is introduced by observation.
"""
from datetime import datetime,timedelta,timezone
import math,time
from household.codec import canonical,loads
from household.evidence import utc
from household_cycle_deadline import observation_deadline,ObservationDeadline,MAX_OBSERVATION_SECONDS

FORECAST_CPU_QUOTA = '100%'

MAX_SOURCE_BYTES=1048576
MAX_COLLECTION_SECONDS=MAX_OBSERVATION_SECONDS
ISSUE_MARGIN=timedelta(seconds=3)


class ObservingBackend:
    def __init__(self,parent,*,collector,guard,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,
                 sleep=time.sleep,near_issue=False):
        self.parent=parent;self.collector=collector;self.guard=guard
        self.clock=clock;self.monotonic=monotonic;self.sleep=sleep;self.near_issue=near_issue
        self.collection=dict(status='unavailable',reason='not_collected')

    def __getattr__(self,name):
        return getattr(self.parent,name)

    def collect(self,*,issue,known_at):
        # Parent exceptions are authoritative forecast failures, not observer
        # failures. Do not catch or replace its exact original input object.
        inputs=self.parent.collect(issue=issue,known_at=known_at)
        issue=utc(issue);now=utc(self.clock())
        if self.near_issue:
            # Native acquisition is fast under the production CPU profile.
            # Read short-lived household power late enough to survive the
            # measured post-issue derivation; never renew the source's TTL.
            target=issue-timedelta(seconds=7)
            waiting=(target-now).total_seconds()
            deadline=self.monotonic()+max(0,waiting)+1
            try:
                if waiting>60:raise ValueError('bounded pre-issue wait required')
                while now<target:
                    self.guard()
                    self.sleep(min(.5,(target-now).total_seconds()))
                    previous=now;now=utc(self.clock())
                    if now<previous or self.monotonic()>deadline:
                        raise ValueError('household waiting clock changed')
            except Exception:
                self.collection=dict(status='unavailable',reason='source_collection_failed')
                return inputs
        budget=min(MAX_COLLECTION_SECONDS,(issue-ISSUE_MARGIN-now).total_seconds())
        if not math.isfinite(budget) or budget<=0:
            self.collection=dict(status='unavailable',reason='insufficient_preissue_budget')
            return inputs
        deadline=self.monotonic()+budget
        def remaining():
            # The collector checks its explicit guard at each source access.
            # Budget inspection itself must not repeat that expensive check.
            value=min(deadline-self.monotonic(),(issue-ISSUE_MARGIN-utc(self.clock())).total_seconds())
            if not math.isfinite(value) or not 0<value<=MAX_COLLECTION_SECONDS:
                raise ValueError('household pre-issue budget elapsed')
            return value
        try:
            with observation_deadline(budget):
                self.guard();remaining()
                originals=self.collector(issue=issue,remaining=remaining,guard=self.guard)
                self.guard();remaining()
                if not isinstance(originals,dict):raise ValueError('closed original source object required')
                raw=canonical(originals)
                if len(raw)>MAX_SOURCE_BYTES:raise ValueError('bounded household originals required')
                self.guard();remaining()
                captured=utc(self.clock())
                if captured<now:raise ValueError('household collection clock moved backward')
                self.collection=dict(status='collected',reason=None,issue=issue.isoformat(),
                    captured_at=captured.isoformat(),originals=loads(raw))
        except ObservationDeadline:
            self.collection=dict(status='unavailable',reason='source_collection_timed_out')
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
    if capture.get('schema') in ('earthship-provisional-thermal-origin/v2','earthship-provisional-thermal-origin/v3'):
        from native_thermal_score import validate_delivery
        from astro_geometry import _instant
        instant=_instant
        if (not isinstance(thermal,PreparedProjection) or not isinstance(weather,PreparedWeatherContext) or
            thermal.to_dict()['schema'] not in ('earthship-household-prepared-thermal/v2','earthship-household-prepared-thermal/v3') or
            weather.to_dict()['schema'] not in ('earthship-household-prepared-weather/v2','earthship-household-prepared-weather/v3','earthship-household-prepared-weather/v4')):
            raise ValueError('native issue requires separately prepared native models')
    elif capture.get('schema')=='earthship-provisional-thermal-origin/v1':
        from thermal_model.provisional_score import validate_delivery
    else:
        raise ValueError('explicit original cycle capture version required')
    validate_delivery(capture,receipts)
    fields={'schema','issue','captured_at','power_receipt','energy_configuration','measured_weather','owner_bindings','automatic_actuation'}
    daily_source_version=isinstance(originals,dict) and originals.get('schema') in ('earthship-household-cycle-sources/v2','earthship-household-cycle-sources/v3','earthship-household-cycle-sources/v4','earthship-household-cycle-sources/v5','earthship-household-cycle-sources/v6','earthship-household-cycle-sources/v7','earthship-household-cycle-sources/v8')
    if daily_source_version:fields.add('daily_energy_source')
    owner_source_version=isinstance(originals,dict) and originals.get('schema') in ('earthship-household-cycle-sources/v3','earthship-household-cycle-sources/v4','earthship-household-cycle-sources/v5','earthship-household-cycle-sources/v6','earthship-household-cycle-sources/v7','earthship-household-cycle-sources/v8')
    if owner_source_version:fields.add('owner_source')
    policy_source_version=isinstance(originals,dict) and originals.get('schema') in ('earthship-household-cycle-sources/v4','earthship-household-cycle-sources/v5','earthship-household-cycle-sources/v6','earthship-household-cycle-sources/v7','earthship-household-cycle-sources/v8')
    if policy_source_version:fields.add('policy_source')
    persistence_version=isinstance(originals,dict) and originals.get('schema') in ('earthship-household-cycle-sources/v5','earthship-household-cycle-sources/v6','earthship-household-cycle-sources/v7','earthship-household-cycle-sources/v8')
    flow_version=isinstance(originals,dict) and originals.get('schema') in ('earthship-household-cycle-sources/v6','earthship-household-cycle-sources/v7','earthship-household-cycle-sources/v8')
    pv_version=isinstance(originals,dict) and originals.get('schema') in ('earthship-household-cycle-sources/v7','earthship-household-cycle-sources/v8')
    if pv_version:fields.update(('pv_system_source','solar_horizon_source'))
    load_version=isinstance(originals,dict) and originals.get('schema')=='earthship-household-cycle-sources/v8'
    if load_version:fields.add('ac_load_source')
    if flow_version:fields.add('load_topology_source')
    if persistence_version:fields.add('energy_persistence_source')
    if not isinstance(originals,dict) or set(originals)!=fields or originals['schema'] not in ('earthship-household-cycle-sources/v1','earthship-household-cycle-sources/v2','earthship-household-cycle-sources/v3','earthship-household-cycle-sources/v4','earthship-household-cycle-sources/v5','earthship-household-cycle-sources/v6','earthship-household-cycle-sources/v7','earthship-household-cycle-sources/v8') or originals['automatic_actuation'] is not False:
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
    if not daily_source_version and (not isinstance(parameter_record,dict) or instant(parameter_record['collected_at'])>issue):
        raise ValueError('original earlier parameters required')
    configuration=PreparedEnergyConfiguration(canonical(originals['energy_configuration']))
    measured=PreparedMeasuredWeather(canonical(originals['measured_weather']))
    snapshot=bind_measured_weather_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],
        weather_context=weather,energy_configuration=configuration,measured_weather=measured,code_revision=code_revision)
    body=snapshot.to_dict();soc=body['domains']['energy']['battery_soc']['value']
    energy=None
    if pv_version and capture['inputs']['forecast']['source']=='weathernext3':
        from household.trajectory_energy import prepare_inputs
        energy=prepare_inputs(snapshot=snapshot,system_source=originals['pv_system_source'],
            topology_source=originals['load_topology_source'],horizon_source=originals['solar_horizon_source'])
    elif daily_source_version:
        from household.daily_energy_source import daily_inputs,ZONE
        daily_source=originals['daily_energy_source']
        if daily_source is not None:
            if instant(daily_source['collected_at'])>instant(originals['captured_at']):
                raise ValueError('daily energy source arrived after collection was frozen')
            # A valid daily source can expire across local midnight between
            # collection and issue. Validate its original provenance first;
            # expiry removes only energy, while corruption still refuses.
            daily=daily_inputs(daily_source,as_of=instant(daily_source['collected_at']))
            if daily_source['prediction_day']==issue.astimezone(ZONE).date().isoformat():
                numerical={**daily,'soc_pct':soc}
                energy=bind_energy_inputs(freeze_energy_inputs(**numerical),snapshot=snapshot,daily_source=daily_source)
    else:
        numerical={**parameter_record['record']['household_energy_inputs'],'soc_pct':soc}
        energy=bind_energy_inputs(freeze_energy_inputs(**numerical),snapshot=snapshot)
    registry=CapabilityRegistry(canonical({key:value for key,value in source['registry'].items() if key!='registry_id'}))
    if registry.to_dict()!=source['registry']:raise ValueError('original registry differs')
    preferences=dict(horizon_hours=24,reserve_soc=10.,low_trough_threshold_soc_pct=90.,surplus_weight=1.,reserve_weight=1.,comfort_min_f=65.,comfort_max_f=80.)
    coordination=dict(schema='earthship-shadow-coordination/v1',snapshotId=snapshot.snapshot_id,horizonHours=24,baseline_soc_floor=None,facts={})
    if owner_source_version:
        from household.owner_sources import coordination_from_rules
        owner_source=originals['owner_source']
        if owner_source is not None and instant(owner_source['received_at'])>instant(originals['captured_at']):
            raise ValueError('owner observation arrived after frozen source collection')
        coordination=coordination_from_rules(owner_source,snapshot_id=snapshot.snapshot_id,registry=registry,
            horizon_hours=preferences['horizon_hours'],as_of=issue)
    if policy_source_version:
        from household.owner_sources import coordination_from_policy
        policy_source=originals['policy_source']
        if policy_source is not None and instant(policy_source['rule_after']['received_at'])>instant(originals['captured_at']):
            raise ValueError('policy observation arrived after frozen source collection')
        coordination=coordination_from_policy(originals['owner_source'],policy_source,snapshot_id=snapshot.snapshot_id,
            registry=registry,horizon_hours=preferences['horizon_hours'],as_of=issue)
    if flow_version:
        source=originals['load_topology_source']
        if source is not None and instant(source['available_at'])>instant(originals['captured_at']):
            raise ValueError('load topology arrived after frozen source collection')
    if pv_version:
        for key in ('pv_system_source','solar_horizon_source'):
            source=originals[key]
            if source is not None and instant(source['available_at'])>instant(originals['captured_at']):
                raise ValueError('PV or horizon source arrived after frozen collection')
    if load_version:
        source=originals['ac_load_source']
        if source is not None and instant(source['available_at'])>instant(originals['captured_at']):
            raise ValueError('load model arrived after frozen collection')
    persistence={}
    if persistence_version:
        source=originals['energy_persistence_source']
        if source is not None and instant(source['available_at'])>instant(originals['captured_at']):
            raise ValueError('energy metric source arrived after frozen collection')
        persistence['energy_persistence_source']=source
    record=seal_pipeline(snapshot=snapshot,registry=registry,energy_inputs=energy,thermal_inputs=thermal,
        thermal_runtime=thermal.to_dict()['executing_runtime'],coordination=coordination,config=preferences,now=now,runtime_manifest=runtime_manifest,**persistence)
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


def load_cycle_delivery(publication,*,issue,guard,runtime=None,expected_artifact_sha256=None,expected_capture_sha256=None,serving_model=None):
    """Replay versioned private archives under separately supplied native pins."""
    from pathlib import Path
    from copy import deepcopy
    from household_observation import _private_file
    from thermal_model.provisional_forecast import digest
    from household.control_contracts import instant
    publication,runtime=deepcopy(publication),deepcopy(runtime)
    if serving_model is not None:
        from native_model_serving_receipt import _require_model
        _require_model(serving_model)
        selected_runtime=serving_model.runtime;selected_artifact=serving_model.candidate['artifact_sha256']
        if (runtime is not None and canonical(runtime)!=canonical(selected_runtime) or
                expected_artifact_sha256 is not None and expected_artifact_sha256!=selected_artifact):
            raise ValueError('serving cycle external model pins differ')
        runtime=selected_runtime;expected_artifact_sha256=selected_artifact
    guard()
    if publication.get('status')!='published' or publication.get('delivery_verified') is not True:
        raise ValueError('verified original publication required')
    origin_path=Path(publication['origin_path']).absolute();delivery_path=Path(publication['delivery_path']).absolute()
    delivery=_private_file(delivery_path,65536);delivered=loads(delivery[0])
    fields={'schema','issued_at','capture_path','capture_sha256','artifact_sha256','receipts','delivery_sha256'}
    native=isinstance(delivered,dict) and delivered.get('schema')=='earthship-provisional-thermal-delivery/v2'
    if native:
        from native_thermal_forecast import MAX_CAPTURE_BYTES,validate_capture
        from native_thermal_score import validate_delivery
        from astro_geometry import _instant
        maximum=MAX_CAPTURE_BYTES;fields=fields|{'runtime_sha256','geometry_series_sha256'}
        origin_suffix='.native-provisional-origin-v2.json';delivery_suffix='.native-provisional-delivery-v2.json'
        instant=_instant
        if runtime is None or expected_artifact_sha256 is None or expected_capture_sha256 is None:
            raise ValueError('separate native runtime, artifact and capture pins required')
    else:
        if serving_model is not None:raise ValueError('receipt serving requires native original delivery')
        from thermal_model.provisional_score import validate_delivery
        maximum=2*1024*1024;origin_suffix='.provisional-origin-v1.json';delivery_suffix='.provisional-delivery-v1.json'
    if not isinstance(delivered,dict) or set(delivered)!=fields or delivered['schema']!=('earthship-provisional-thermal-delivery/v2' if native else 'earthship-provisional-thermal-delivery/v1'):
        raise ValueError('closed original delivery required')
    origin=_private_file(origin_path,maximum);capture=loads(origin[0])
    if (digest(delivered,'delivery_sha256')!=delivered['delivery_sha256'] or
        delivered['capture_path']!=str(origin_path) or delivered['capture_sha256']!=capture['capture_sha256'] or
        delivered['artifact_sha256']!=capture['candidate']['artifact_sha256'] or
        instant(delivered['issued_at'])!=instant(capture['issued_at']) or instant(issue)!=instant(capture['issued_at']) or
        origin_path.parent!=delivery_path.parent or
        origin_path.name!=capture['capture_sha256']+origin_suffix or
        delivery_path.name!=delivered['delivery_sha256']+delivery_suffix):
        raise ValueError('original delivery binding differs')
    if native:
        if serving_model is None:
            capture=validate_capture(capture,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
                expected_capture_sha256=expected_capture_sha256,check_budget=guard)
        else:
            from native_thermal_forecast import validate_serving_capture
            capture=validate_serving_capture(capture,serving_model,expected_capture_sha256=expected_capture_sha256,check_budget=guard)
        if (delivered['runtime_sha256']!=capture['candidate']['runtime_sha256'] or
            delivered['geometry_series_sha256']!=capture['geometry_series_sha256']):
            raise ValueError('original native delivery runtime or geometry differs')
    validate_delivery(capture,delivered['receipts'])
    def unchanged():
        guard()
        if serving_model is not None:serving_model.verify_bindings(assessed_at=instant(issue),guard=guard)
        if _private_file(origin_path,maximum)!=origin or _private_file(delivery_path,65536)!=delivery:
            raise ValueError('original cycle archive changed')
    unchanged()
    return dict(capture=capture,receipts=deepcopy(delivered['receipts']),native=native,verify_unchanged=unchanged)


def complete_cycle(*,publication,collection,parameter_record,runtime_manifest,code_revision,
                   evidence_directory,observation_cache,guard,clock=lambda:datetime.now(timezone.utc),
                   runtime=None,expected_artifact_sha256=None,expected_capture_sha256=None,serving_model=None):
    """Use verified original archives before any model or cache publication.

    The caller owns the forecast lock and the configuration/runtime guard.
    Observer refusal propagates to that caller, never to forecast withdrawal.
    """
    from household_observation import materialize
    from household.weather_context import prepare_cycle_contexts
    from household_pipeline import verify_source_closure
    from household.pipeline import MAX_BYTES as PIPELINE_BYTES
    guard()
    if publication.get('status')!='published' or publication.get('delivery_verified') is not True:
        raise ValueError('verified original publication required')
    if collection.get('status')!='collected':
        known={'not_collected','insufficient_preissue_budget','source_collection_timed_out','source_collection_failed'}
        reason=collection.get('reason')
        if not isinstance(reason,str) or reason not in known:reason='unclassified_collection_failure'
        return dict(status='observation_unavailable',reason='source_collection_unavailable',collection_reason=reason,automatic_actuation=False)
    archived=load_cycle_delivery(publication,issue=collection['issue'],guard=guard,runtime=runtime,
        expected_artifact_sha256=expected_artifact_sha256,expected_capture_sha256=expected_capture_sha256,serving_model=serving_model)
    capture=archived['capture'];receipts=archived['receipts']
    if archived['native']:
        if serving_model is not None:
            from household.weather_context import prepare_serving_native_cycle_contexts
            thermal,weather=prepare_serving_native_cycle_contexts(capture,serving_model,code_revision=code_revision,
                expected_capture_sha256=expected_capture_sha256,check_budget=guard)
        else:
            from household.weather_context import prepare_native_cycle_contexts
            thermal,weather=prepare_native_cycle_contexts(capture,code_revision=code_revision,runtime=runtime,
                expected_artifact_sha256=expected_artifact_sha256,expected_capture_sha256=expected_capture_sha256,check_budget=guard)
    else:
        thermal,weather=prepare_cycle_contexts(capture,code_revision=code_revision)
    record=derive_cycle(originals=collection['originals'],capture=capture,receipts=receipts,
        thermal=thermal,weather=weather,parameter_record=parameter_record,runtime_manifest=runtime_manifest,
        code_revision=code_revision,now=clock())
    verify_source_closure(record,runtime_manifest);guard()
    unchanged=archived['verify_unchanged']
    unchanged()
    _retain_original(evidence_directory,collection['originals'],'.household-sources-v1.json',MAX_SOURCE_BYTES)
    suffix='.household-model-plan-v6.json' if record.get('schema')=='earthship-household-model-plan-receipt/v6' else '.household-model-plan-v5.json'
    receipt=_retain_original(evidence_directory,record,suffix,PIPELINE_BYTES)
    if collection['originals'].get('schema') in ('earthship-household-cycle-sources/v6','earthship-household-cycle-sources/v7','earthship-household-cycle-sources/v8'):
        from household_power_flows import seal_flow_receipt,flow_runtime_manifest,MAX_BYTES as FLOW_BYTES
        unchanged()
        flow=seal_flow_receipt(plan_receipt=record,topology_source=collection['originals']['load_topology_source'],
            now=clock(),runtime_manifest=flow_runtime_manifest())
        unchanged()
        _retain_original(evidence_directory,flow,'.household-power-flow-v1.json',FLOW_BYTES)
    if collection['originals'].get('schema') in ('earthship-household-cycle-sources/v7','earthship-household-cycle-sources/v8'):
        from household_energy_forecast import seal_energy_forecast,forecast_runtime_manifest,MAX_BYTES as ENERGY_BYTES
        unchanged()
        energy=seal_energy_forecast(plan_receipt=record,system_source=collection['originals']['pv_system_source'],
            horizon_source=collection['originals']['solar_horizon_source'],topology_source=collection['originals']['load_topology_source'],
            now=clock(),runtime_manifest=forecast_runtime_manifest())
        unchanged()
        _retain_original(evidence_directory,energy,'.household-energy-forecast-v1.json',ENERGY_BYTES)
    profiled_status=None
    if collection['originals'].get('schema')=='earthship-household-cycle-sources/v8':
        from household_profiled_forecast import seal_profiled_forecast,profiled_runtime_manifest
        from household_ac_load_artifact import runtime_manifest as load_runtime
        try:
            source=collection['originals']['ac_load_source']
            profiled=seal_profiled_forecast(energy_receipt=energy,plan_receipt=record,load_source=source,now=clock(),
                runtime_manifest=profiled_runtime_manifest(),energy_runtime_manifest=forecast_runtime_manifest(),
                load_runtime_manifest={} if source is None else load_runtime())
            unchanged()
            _retain_original(evidence_directory,profiled,'.household-profiled-energy-v1.json',262144)
            profiled_status='retained'
        except (OSError,ValueError):
            profiled_status='unavailable'
    unchanged()
    result=materialize(receipt,observation_cache,clock=clock,publication_guard=unchanged)
    if profiled_status is not None:result['profiled_energy_status']=profiled_status
    if collection['originals'].get('schema') in ('earthship-household-cycle-sources/v7','earthship-household-cycle-sources/v8'):
        from household_energy_state import project_energy_observation,publish_owned
        from pathlib import Path
        try:
            view=project_energy_observation(energy,plan_receipt=record,generated_at=clock())
            publish_owned(Path(observation_cache).parent/'energy-observation.json',view,guard=unchanged)
            result['energy_observation_status']='written'
        except (OSError,ValueError):
            result['energy_observation_status']='unavailable'
        unchanged()
    if collection['originals'].get('schema')=='earthship-household-cycle-sources/v8':
        from household_profiled_state import project_observation as profile_view,publish_owned as publish_profile
        result['profiled_observation_status']='unavailable'
        if profiled_status=='retained':
            try:
                view=profile_view(profiled,energy_receipt=energy,generated_at=clock())
                publish_profile(Path(observation_cache).parent/'profiled-energy-observation.json',view,guard=unchanged)
                result['profiled_observation_status']='written'
            except (OSError,ValueError):
                pass
        unchanged()
        from household_trajectory_plan import seal_trajectory_plan,trajectory_runtime_manifest,MAX_BYTES as SHADOW_BYTES
        result['trajectory_shadow_status']='unavailable'
        try:
            shadow_runtime=trajectory_runtime_manifest()
            retained_profile=profiled if profiled_status=='retained' else None
            lr={} if retained_profile is None or retained_profile['inputs']['load_source'] is None else load_runtime()
            shadow=seal_trajectory_plan(plan_receipt=record,energy_receipt=energy,profiled_receipt=retained_profile,now=clock(),
                runtime_manifest=shadow_runtime,thermal_runtime=None if record['inputs']['thermal_inputs'] is None else record['inputs']['thermal_inputs']['executing_runtime'],
                load_runtime_manifest=lr)
            unchanged()
            if trajectory_runtime_manifest()!=shadow_runtime or lr and load_runtime()!=lr:raise ValueError('trajectory shadow runtime changed')
            _retain_original(evidence_directory,shadow,'.household-trajectory-shadow-v1.json',SHADOW_BYTES)
            result['trajectory_shadow_status']='retained'
        except (OSError,ValueError):
            pass
        unchanged()
    return result


class LazyForecastBackend:
    """Construct the original transport at the issue chosen by the publisher."""
    def __init__(self,settings,*,guard):
        self.settings=settings;self.guard=guard;self.parent=None

    def __getattr__(self,name):
        if self.parent is None:raise ValueError('original forecast collection has not started')
        return getattr(self.parent,name)

    def collect(self,*,issue,known_at):
        from thermal_model.native_operational_io import delivery_directory
        from native_thermal_live import GOOGLE_SCHEMAS,make_forecast_backend
        if self.settings.get('schema') not in ('earthship-weathernext-thermal-live-config/v1','earthship-weathernext-thermal-live-config/v2'):raise ValueError('Google-only native forecast configuration required')
        if self.parent is not None:raise ValueError('one original issue per backend required')
        self.guard()
        self.parent=make_forecast_backend(self.settings,evidence_directory=delivery_directory(self.settings,issue),guard=self.guard)
        return self.parent.collect(issue=issue,known_at=known_at)


def run_cycle(config_path,*,code_revision,forecast_config=None,stage=None,deployment_sha256=None):
    from contextlib import nullcontext
    from household_cycle_resources import publication_native_policy
    with publication_native_policy() if deployment_sha256 is not None else nullcontext():
        return _run_cycle(config_path,code_revision=code_revision,forecast_config=forecast_config,
            stage=stage,deployment_sha256=deployment_sha256)


def _run_cycle(config_path,*,code_revision,forecast_config=None,stage=None,deployment_sha256=None):
    """Own the original lock; household preparation cannot suppress forecasts.

    Production passes the original forecast configuration independently of the
    optional household configuration. Legacy callers may discover that original
    path from an intact household config before entering the original lock.
    """
    import os,re
    from pathlib import Path
    from hashlib import sha256
    from household_cycle_sources import load_cycle_settings,CycleSourceCollector
    from household_observation import _private_file,_directory
    from household_snapshot import _read
    from thermal_model.capture_guard import SharedScoreLock
    from household_cycle_pressure import PublicationHeadroom
    os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
    config_path=Path(config_path).absolute()
    if forecast_config is None:forecast_config=load_cycle_settings(config_path)['forecast_config']
    forecast_path=Path(forecast_config).absolute();forecast_original=_private_file(forecast_path,8192)
    original_settings=loads(forecast_original[0])
    from native_thermal_live import NATIVE_SCHEMAS,SERVING_SCHEMAS,load_settings,publish_cycle,withdraw,current_runtime
    if not isinstance(original_settings,dict) or original_settings.get('schema') not in ('earthship-weathernext-thermal-live-config/v1','earthship-weathernext-thermal-live-config/v2'):
        raise ValueError('Google-only native forecast configuration required')
    receipt_profile=original_settings['schema'] in SERVING_SCHEMAS
    from household_cycle_resources import publication_resource_preflight
    publication_resource_preflight()
    settings=load_settings(forecast_path)
    if receipt_profile:
        from thermal_model.graduation_policy import _sha
        if stage is None or deployment_sha256 is None:
            raise ValueError('external serving stage selection required')
        stage=Path(stage).absolute();_sha(deployment_sha256)
        if Path(__file__).resolve()!=stage/'sources/openhab/scripts/household_cycle.py':
            raise ValueError('staged serving driver execution required')
    with SharedScoreLock(settings['shared_lock']) as lock:
        monitor=PublicationHeadroom()
        # Native serving needs the warm slot for acquisition. Kernel isolation
        # is already active; check RAM/pressure now and throughout the cycle.
        monitor.check()
        def forecast_guard():
            lock.verify();monitor.check()
            if _private_file(forecast_path,8192)!=forecast_original:
                raise ValueError('original forecast configuration changed')
        forecast_guard();collector=None;ready=False;configuration=None
        try:
            if not isinstance(code_revision,str) or re.fullmatch('[a-f0-9]{40}',code_revision) is None:
                raise ValueError('original household source revision required')
            configuration=load_cycle_settings(config_path);config_original=_private_file(config_path,8192)
            if loads(config_original[0])!=configuration or Path(configuration['forecast_config'])!=forecast_path:
                raise ValueError('original household configuration differs')
            parameter_path=Path(configuration['retained_energy_parameters']);parameter_original=_private_file(parameter_path,262144)
            if sha256(parameter_original[0]).hexdigest()!=configuration['parameters_sha256']:
                raise ValueError('retained original parameter digest differs')
            parameters=loads(parameter_original[0])
            _directory(Path(configuration['evidence_directory']));_directory(Path(configuration['observation_cache']).parent)
            root=Path(__file__).resolve().parent
            own={root/name:_read(root/name,262144) for name in ('household_cycle.py','household_cycle_sources.py','household_cycle_deadline.py','household_cycle_pressure.py','household_cycle_resources.py','household_observation.py')}
            def guard():
                forecast_guard()
                if (_private_file(config_path,8192)!=config_original or _private_file(parameter_path,262144)!=parameter_original or
                    any(_read(path,262144)!=raw for path,raw in own.items())):
                    raise ValueError('original household configuration, parameters or driver changed')
            guard()
            collector=CycleSourceCollector(token_file=settings['token_file'],openhab_base=settings['openhab_base'],code_revision=code_revision)
            ready=True
        except Exception:
            # The original settings/lock/resource guard are independently valid.
            # Preserve that forecast even if the observer cannot initialize.
            pass
        def collect(**request):
            if not ready:raise ValueError('household source preparation unavailable')
            return collector(**request)
        observer_guard=guard if ready else forecast_guard
        backend=ObservingBackend(LazyForecastBackend(settings,guard=forecast_guard),collector=collect,guard=observer_guard,near_issue=True)
        serving_model=None
        try:
            if receipt_profile:
                from datetime import datetime,timezone
                from native_model_serving_receipt import load_serving_selection,read_serving_model
                selected=load_serving_selection(stage,expected_deployment_sha256=deployment_sha256,
                    assessed_at=datetime.now(timezone.utc),guard=forecast_guard)
                serving_model=read_serving_model(selected,assessed_at=datetime.now(timezone.utc),guard=forecast_guard)
                published=publish_cycle(settings,guard=forecast_guard,backend=backend,serving_model=serving_model)
            else:
                published=publish_cycle(settings,guard=forecast_guard,backend=backend)
        except Exception:
            try:
                result=withdraw(settings,guard=forecast_guard)
                return dict(status='withheld_and_withdrawn',delivery_verified=result.get('delivery_verified',False),automatic_actuation=False)
            except Exception:return dict(status='withheld',delivery_verified=False,automatic_actuation=False)
        result=dict(status=published['status'],delivery_verified=published.get('delivery_verified',False),automatic_actuation=False)
        if published['status']!='published':return result
        if not ready:
            result['observation']=dict(status='observation_unavailable',reason='source_preparation_unavailable',automatic_actuation=False)
            return result
        try:
            native_pins=dict(runtime=current_runtime(guard=forecast_guard),
                expected_artifact_sha256=settings['artifact_sha256'],expected_capture_sha256=published['capture_sha256'])
            if receipt_profile:native_pins['serving_model']=serving_model
            result['observation']=complete_cycle(publication=published,collection=backend.collection,parameter_record=parameters,
                runtime_manifest=collector.runtime,code_revision=code_revision,evidence_directory=configuration['evidence_directory'],
                observation_cache=configuration['observation_cache'],guard=guard,**native_pins)
        except Exception:
            result['observation']=dict(status='observation_refused',reason='original_cycle_verification_failed',automatic_actuation=False)
        return result


def main(argv=None):
    import argparse,json,sys
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path);parser.add_argument('--code-revision',required=True)
    parser.add_argument('--forecast-config',required=True,type=Path)
    parser.add_argument('--stage',type=Path);parser.add_argument('--deployment-sha256')
    args=parser.parse_args(argv)
    try:
        selected={} if args.stage is None and args.deployment_sha256 is None else dict(stage=args.stage,deployment_sha256=args.deployment_sha256)
        result=run_cycle(args.config,code_revision=args.code_revision,forecast_config=args.forecast_config,**selected)
    except BlockingIOError:
        print(json.dumps(dict(status='busy',delivery_verified=False,automatic_actuation=False)));return 75
    except Exception:
        print(json.dumps(dict(status='cycle_refused',delivery_verified=False,automatic_actuation=False)),file=sys.stderr);return 1
    print(json.dumps(result,sort_keys=True))
    return 0 if result['status'] in ('published','deferred') else 1


if __name__=='__main__':raise SystemExit(main())
