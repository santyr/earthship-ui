"""Stage immutable household sources without modifying the live service.

Runtime qualification and service handoff are separate guarded operations.
Private configurations, credentials and fitted artifacts are never committed or
printed by this tool. Source archiving uses the standard library; native headers reuse schema validation.
"""
from hashlib import sha256
import json,os,re,stat,subprocess
from pathlib import Path

LIMITS={'TimeoutStartSec':'90','CPUQuota':'20%','MemoryMax':'256M','MemorySwapMax':'0','TasksMax':'24',
        'Nice':'15','IOSchedulingClass':'idle','IOWeight':'10'}
REGISTRY=('openhab/managed-resources.json','openhab/file-config/ownership.json')
NATIVE_WORKER='openhab/scripts/astro_geometry_worker.py'
JAVA_SOURCE='scripts/java/NativeSolarGeometry.java'
LOAD_TOPOLOGY_SOURCE='openhab/household-energy-topology.json'
PV_SOURCES=('openhab/household-pv-system.json','openhab/household-solar-horizon.json')
MAX_BYTES=2*1024*1024


def _encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def _path(value):
    path=Path(value).absolute()
    if path.resolve()!=path or re.fullmatch(r'/[A-Za-z0-9_./-]+',str(path)) is None:
        raise ValueError('resolved deployment path required')
    return path


def _bytes(path,*,private=False,maximum=MAX_BYTES):
    path=_path(path)
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except OSError:raise ValueError('owned deployment original unavailable') from None
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_size>maximum or
            private and stat.S_IMODE(info.st_mode)!=0o600):raise ValueError('bounded owned deployment original required')
        raw=os.read(fd,maximum+1);after=os.fstat(fd)
        metadata=lambda row:(row.st_dev,row.st_ino,row.st_mode,row.st_size,row.st_mtime_ns,row.st_ctime_ns)
        if len(raw)>maximum or metadata(info)!=metadata(after):raise ValueError('deployment original changed while reading')
        return raw
    finally:os.close(fd)


def _directory(path):
    path=_path(path);info=path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError('owned private deployment directory required')
    return path


def _write(path,raw,mode=0o600):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


def _git(repo,*args):
    return subprocess.check_output(['git','-C',str(repo),*args],timeout=5)


def _service_contract(raw,config):
    # This override can replace only the existing capped provisional publisher.
    text=raw.decode();rows={}
    for line in text.splitlines():
        if line.startswith('#') or '=' not in line:continue
        key,value=line.split('=',1);rows.setdefault(key,[]).append(value)
    if any(rows.get(key)!=[value] for key,value in LIMITS.items()):raise ValueError('original service limits differ')
    import shlex
    command=rows.get('ExecStart',[])
    if len(command)!=1:raise ValueError('one original publisher required')
    parts=shlex.split(command[0])
    if len(parts)!=5 or parts[0]!='/usr/bin/python3' or not parts[1].endswith('/provisional_thermal.py') or parts[2:]!=['--config',str(config),'--publish']:
        raise ValueError('original provisional publisher contract differs')



NATIVE_CONFIG_SCHEMA='earthship-provisional-thermal-live-config/v2'
SERVING_CONFIG_SCHEMA='earthship-provisional-thermal-live-config/v3'
from native_thermal_live import NATIVE_SCHEMAS,SERVING_SCHEMAS,GOOGLE_SCHEMAS,configuration_fields

NATIVE_DEPLOYMENT_FIELDS={'native_runtime_sources','native_originals','artifact_sha256','runtime_sha256'}


def _native_header(candidate,settings):
    from native_thermal_artifact import SCHEMA,FIELDS,validate_native_runtime,digest,LIMITS
    from thermal_model.provisional_live import FIELDS as CONFIG_FIELDS
    if (not isinstance(candidate,dict) or set(candidate)!=FIELDS or candidate['schema']!=SCHEMA or
        set(settings)!=configuration_fields(settings.get('schema')) or
        settings['schema'] not in NATIVE_SCHEMAS):
        raise ValueError('explicit closed native candidate and configuration required')
    runtime=validate_native_runtime(candidate['runtime'])
    if (candidate['artifact_sha256']!=settings['artifact_sha256'] or
        candidate['runtime_sha256']!=settings['runtime_sha256'] or
        digest(candidate,'artifact_sha256')!=candidate['artifact_sha256'] or
        digest(runtime)!=candidate['runtime_sha256']):
        raise ValueError('external native model or runtime identity differs')
    _directory(_path(settings['geometry_directory']));_directory(_path(settings['evidence_directory']))
    info=dict(native_runtime_sources=runtime['native_source_manifest'],native_originals=candidate['originals'],
        artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'])
    _verify_native_originals(info)
    return runtime['base_runtime']['source_manifest'],info


def _verify_native_originals(info):
    from native_thermal_artifact import LIMITS
    refs=info['native_originals']
    if not isinstance(refs,dict) or set(refs)!=set(LIMITS):
        raise ValueError('complete retained native dependencies required')
    for role,ref in refs.items():
        if (not isinstance(ref,dict) or set(ref)!={'path','sha256'} or
            not isinstance(ref['sha256'],str) or re.fullmatch('[a-f0-9]{64}',ref['sha256']) is None):
            raise ValueError('closed original native reference required')
        path=_path(ref['path']);_directory(path.parent)
        if sha256(_bytes(path,private=True,maximum=LIMITS[role])).hexdigest()!=ref['sha256']:
            raise ValueError('retained native original differs')


def stage_deployment(*,repo_root,stage,forecast_config,parameters,parameters_sha256,observation_cache,service_file,code_revision,service_forecast_config=None,model_receipt_path=None,model_receipt_sha256=None,score_dispatch_path=None,score_dispatch_sha256=None):
    repo,stage,config,parameters,cache,service=map(_path,(repo_root,stage,forecast_config,parameters,observation_cache,service_file))
    if re.fullmatch('[a-f0-9]{40}',code_revision or '') is None or re.fullmatch('[a-f0-9]{64}',parameters_sha256 or '') is None:
        raise ValueError('original code and parameter identities required')
    if _git(repo,'rev-parse','HEAD').decode().strip()!=code_revision or _git(repo,'status','--porcelain','--untracked-files=no').strip():
        raise ValueError('clean exact committed source required')
    _directory(cache.parent)
    config_raw=_bytes(config,private=True);settings=json.loads(config_raw)
    serving=settings.get('schema') in SERVING_SCHEMAS
    serving_refs={}
    if serving:
        for role,path,pin in (('receipt',model_receipt_path,model_receipt_sha256),('dispatch',score_dispatch_path,score_dispatch_sha256)):
            if path is None or not isinstance(pin,str) or re.fullmatch('[a-f0-9]{64}',pin) is None:
                raise ValueError('explicit externally pinned model receipt and score dispatch required')
            path=_path(path);_directory(path.parent);raw=_bytes(path,private=True,maximum=131072)
            if sha256(raw).hexdigest()!=pin:raise ValueError('receipt-serving input pin differs')
            serving_refs[role]=dict(path=str(path),sha256=pin)
        if settings.get('model_receipt_path')!=str(model_receipt_path) or settings.get('model_receipt_sha256')!=model_receipt_sha256:
            raise ValueError('serving config cannot select another model receipt')
    elif any(value is not None for value in (model_receipt_path,model_receipt_sha256,score_dispatch_path,score_dispatch_sha256)):
        raise ValueError('receipt inputs require explicit serving configuration')
    candidate=_path(settings['candidate_path']);candidate_raw=_bytes(candidate,private=True)
    declared=json.loads(candidate_raw);native=settings.get('schema') in NATIVE_SCHEMAS or declared.get('schema')=='earthship-provisional-thermal-candidate/v2'
    protected,native_info=_native_header(declared,settings) if native else (declared['runtime']['source_manifest'],None)
    baseline_candidate=None;baseline_candidate_raw=None
    parameter_raw=_bytes(parameters,private=True);service_raw=_bytes(service)
    if sha256(parameter_raw).hexdigest()!=parameters_sha256:raise ValueError('original retained parameters differ')
    baseline=config if service_forecast_config is None else _path(service_forecast_config)
    baseline_raw=config_raw if baseline==config else _bytes(baseline,private=True)
    if baseline!=config:
        previous=json.loads(baseline_raw)
        allowed={'candidate_path'} if not native else {'schema','candidate_path','artifact_sha256','runtime_sha256','geometry_directory','evidence_directory'}|({'model_receipt_path','model_receipt_sha256'} if serving else set())
        if settings.get('schema') in GOOGLE_SCHEMAS:allowed=allowed|{'forecast_dsn_file','weather_source'}
        if (not isinstance(settings,dict) or not isinstance(previous,dict) or
            {k:v for k,v in settings.items() if k not in allowed}!={k:v for k,v in previous.items() if k not in allowed} or
            settings.get('candidate_path')==previous.get('candidate_path')):
            raise ValueError('only explicit model selection may change from the original service configuration')
        if native:
            from thermal_model.provisional_live import FIELDS as CONFIG_FIELDS,SCHEMA as LEGACY_SCHEMA
            previous_fields=CONFIG_FIELDS if previous.get('schema')==LEGACY_SCHEMA else configuration_fields(previous.get('schema'))
            if previous.get('schema') not in (LEGACY_SCHEMA,)+NATIVE_SCHEMAS or set(previous)!=previous_fields:
                raise ValueError('closed original baseline configuration required')
            baseline_candidate=_path(previous['candidate_path']);baseline_candidate_raw=_bytes(baseline_candidate,private=True)
            previous_model=json.loads(baseline_candidate_raw);base=previous_model['runtime']
            if previous.get('schema') in NATIVE_SCHEMAS:base=base['base_runtime']
            if settings.get('schema') not in GOOGLE_SCHEMAS and _encode(base)!=_encode(declared['runtime']['base_runtime']):
                raise ValueError('native selection must preserve original fitted base runtime')
    _service_contract(service_raw,baseline)
    # Archive the immutable commit object, not the mutable index/worktree. A
    # concurrent edit after the cleanliness check cannot acquire this identity.
    import io,tarfile
    extra_paths=[name for name in (JAVA_SOURCE,LOAD_TOPOLOGY_SOURCE,*PV_SOURCES)
        if _git(repo,'ls-tree','--name-only',code_revision,'--',name).strip()]
    archived=_git(repo,'archive','--format=tar',code_revision,'--','openhab/scripts',*REGISTRY,*extra_paths)
    if len(archived)>32*1024*1024:raise ValueError('bounded committed source archive required')
    sources={}
    with tarfile.open(fileobj=io.BytesIO(archived),mode='r:') as archive:
        for member in archive:
            wanted=(member.name in (*REGISTRY,JAVA_SOURCE,LOAD_TOPOLOGY_SOURCE,*PV_SOURCES) or member.name.startswith('openhab/scripts/') and member.name.endswith('.py') and not Path(member.name).name.startswith('test_'))
            if not wanted:continue
            if member.name in sources or not member.isfile() or member.size>MAX_BYTES:raise ValueError('unique committed regular source required')
            sources[member.name]=archive.extractfile(member).read(MAX_BYTES+1)
    if not set(REGISTRY)<=set(sources) or not 4<=len(sources)<=400:raise ValueError('bounded complete committed source set required')
    if NATIVE_WORKER in sources and JAVA_SOURCE not in sources:
        raise ValueError('native geometry worker requires its original Java source')
    if not isinstance(protected,dict) or not 2<=len(protected)<=72:raise ValueError('original fitted source manifest required')
    for name,digest in protected.items():
        key='openhab/scripts/'+name
        if key not in sources or sha256(sources[key]).hexdigest()!=digest:raise ValueError('original fitted runtime source differs')
    if native_info is not None:
        for name,digest in native_info['native_runtime_sources'].items():
            if name not in sources or sha256(sources[name]).hexdigest()!=digest:
                raise ValueError('native runtime source differs from committed archive')
    if serving:
        helper='openhab/scripts/native_model_serving_receipt.py'
        if helper not in sources:raise ValueError('complete model serving helper source required')
        helper_sha=sha256(sources[helper]).hexdigest()
        for name in ('native_thermal_forecast.py','native_thermal_live.py','native_thermal_score.py'):
            raw=sources.get('openhab/scripts/'+name,b'')
            if ("SERVING_RECEIPT_SOURCE_SHA256='"+helper_sha+"'").encode() not in raw:
                raise ValueError('runtime adapter serving helper source pin differs')
    bindings={str(path):sha256(raw).hexdigest() for path,raw in ((config,config_raw),(candidate,candidate_raw),(parameters,parameter_raw),(service,service_raw))}
    for ref in serving_refs.values():bindings[ref['path']]=ref['sha256']
    bindings[str(baseline)]=sha256(baseline_raw).hexdigest()
    if baseline_candidate is not None:bindings[str(baseline_candidate)]=sha256(baseline_candidate_raw).hexdigest()
    # Recheck before creating anything; malformed inputs leave no staged output.
    if any(_bytes(repo/name)!=raw for name,raw in sources.items()) or _git(repo,'rev-parse','HEAD').decode().strip()!=code_revision:
        raise ValueError('source changed during package preparation')
    if native_info is not None:_verify_native_originals(native_info)
    if any(sha256(_bytes(ref['path'],private=True,maximum=131072)).hexdigest()!=ref['sha256'] for ref in serving_refs.values()):
        raise ValueError('receipt-serving originals changed during staging')
    stage.mkdir(mode=0o700)
    root=stage/'sources';root.mkdir(mode=0o700)
    for name,raw in sources.items():
        destination=root/name;destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        _write(destination,raw,0o644)
    (stage/'evidence').mkdir(mode=0o700)
    cycle=dict(schema='earthship-household-cycle-config/v1',forecast_config=str(config),retained_energy_parameters=str(parameters),
        parameters_sha256=parameters_sha256,evidence_directory=str(stage/'evidence'),observation_cache=str(cache))
    _write(stage/'cycle.json',_encode(cycle))
    scripts=root/'openhab/scripts'
    dropin=('[Service]\nEnvironment="PYTHONPATH='+str(scripts)+':/home/sat/Solar_PV/analytics/src"\n'
        'ExecStart=\nExecStart=/usr/bin/python3 '+str(scripts/'household_cycle.py')+' --config '+str(stage/'cycle.json')+' --forecast-config '+str(config)+' --code-revision '+code_revision+(' --stage '+str(stage) if serving else '')+'\n')
    _write(stage/'service.conf',dropin.encode())
    record=dict(schema='earthship-household-cycle-deployment/v1',code_revision=code_revision,stage=str(stage),service_file=str(service),
        original_bindings=bindings,source_manifest={name:sha256(raw).hexdigest() for name,raw in sources.items()},
        protected_runtime_sources=protected,cycle_sha256=sha256(_bytes(stage/'cycle.json',private=True)).hexdigest(),
        dropin_sha256=sha256(dropin.encode()).hexdigest(),automatic_actuation=False)
    if native_info is not None:record.update(schema='earthship-household-cycle-deployment/v2',**native_info)
    if serving:
        record.update(schema='earthship-household-cycle-deployment/v3',
            model_verification=dict(receipt=serving_refs['receipt'],helper=dict(path=str(root/helper),sha256=helper_sha)),
            score_dispatch=serving_refs['dispatch'])
    _write(stage/'deployment.json',_encode(record))
    if serving:verify_stage(stage,expected_deployment_sha256=sha256(_bytes(stage/'deployment.json',private=True)).hexdigest())
    else:verify_stage(stage)
    return dict(status='deployment_staged',code_revision=code_revision,source_count=len(sources),automatic_actuation=False)


def verify_stage(stage,*,expected_deployment_sha256=None):
    stage=_directory(stage);raw=_bytes(stage/'deployment.json',private=True);record=json.loads(raw)
    serving=record.get('schema')=='earthship-household-cycle-deployment/v3'
    if serving:
        from thermal_model.origin_capture import _object,_source_bytes
        def nonfinite(_):raise ValueError('finite serving stage JSON required')
        record=json.loads(raw,object_pairs_hook=_object,parse_constant=nonfinite)
        if not isinstance(expected_deployment_sha256,str) or re.fullmatch('[a-f0-9]{64}',expected_deployment_sha256) is None or sha256(raw).hexdigest()!=expected_deployment_sha256:
            raise ValueError('external serving deployment pin differs')
    fields={'schema','code_revision','stage','service_file','original_bindings','source_manifest','protected_runtime_sources','cycle_sha256','dropin_sha256','automatic_actuation'}
    native=record.get('schema') in ('earthship-household-cycle-deployment/v2','earthship-household-cycle-deployment/v3')
    if native:fields|=NATIVE_DEPLOYMENT_FIELDS
    if serving:fields|={'model_verification','score_dispatch'}
    if set(record)!=fields or record['schema'] not in ('earthship-household-cycle-deployment/v1','earthship-household-cycle-deployment/v2','earthship-household-cycle-deployment/v3') or record['stage']!=str(stage) or record['automatic_actuation'] is not False:
        raise ValueError('closed original deployment record required')
    sources=record['source_manifest'];root=_directory(stage/'sources')
    if NATIVE_WORKER in sources and JAVA_SOURCE not in sources:
        raise ValueError('native geometry worker source closure is incomplete')
    actual={str(path.relative_to(root)) for path in root.rglob('*') if not path.is_dir()}
    if actual!=set(sources):raise ValueError('closed staged source set differs')
    if any(sha256(_bytes(root/name)).hexdigest()!=digest for name,digest in sources.items()):raise ValueError('staged source changed')
    if serving and any(sha256(_source_bytes(root/name,maximum=MAX_BYTES)).hexdigest()!=digest for name,digest in sources.items()):raise ValueError('serving source permissions or bytes changed')
    for name,digest in record['protected_runtime_sources'].items():
        if sources.get('openhab/scripts/'+name)!=digest:raise ValueError('original protected source binding differs')
    if native:
        if not isinstance(record['native_runtime_sources'],dict):raise ValueError('native staged source closure required')
        for name,digest in record['native_runtime_sources'].items():
            if sources.get(name)!=digest:raise ValueError('native staged source binding differs')
        _verify_native_originals(record)
        cycle=json.loads(_bytes(stage/'cycle.json',private=True));settings=json.loads(_bytes(cycle['forecast_config'],private=True))
        protected,info=_native_header(json.loads(_bytes(settings['candidate_path'],private=True)),settings)
        if protected!=record['protected_runtime_sources'] or any(info[key]!=record[key] for key in NATIVE_DEPLOYMENT_FIELDS):
            raise ValueError('native staged model declaration differs')
    for name,digest in record['original_bindings'].items():
        if sha256(_bytes(name,private=name!=record['service_file'])).hexdigest()!=digest:raise ValueError('original deployment input changed')
    if (sha256(_bytes(stage/'cycle.json',private=True)).hexdigest()!=record['cycle_sha256'] or
        sha256(_bytes(stage/'service.conf',private=True)).hexdigest()!=record['dropin_sha256']):
        raise ValueError('staged configuration changed')
    if serving:
        if (not isinstance(record['model_verification'],dict) or set(record['model_verification'])!={'receipt','helper'}):
            raise ValueError('closed model verification references required')
        for reference in (*record['model_verification'].values(),record['score_dispatch']):
            if (not isinstance(reference,dict) or set(reference)!={'path','sha256'} or
                not isinstance(reference['sha256'],str) or re.fullmatch('[a-f0-9]{64}',reference['sha256']) is None):
                raise ValueError('closed serving stage reference required')
            path=_path(reference['path'])
            if sha256(_bytes(path,private=reference is not record['model_verification']['helper'],maximum=131072)).hexdigest()!=reference['sha256']:
                raise ValueError('serving stage reference changed')
        helper=record['model_verification']['helper']
        if helper['path']!=str(root/'openhab/scripts/native_model_serving_receipt.py') or sources.get('openhab/scripts/native_model_serving_receipt.py')!=helper['sha256']:
            raise ValueError('complete serving helper source closure required')
        if settings['schema'] not in SERVING_SCHEMAS or settings['model_receipt_path']!=record['model_verification']['receipt']['path'] or settings['model_receipt_sha256']!=record['model_verification']['receipt']['sha256']:
            raise ValueError('explicit serving profile receipt differs')
    return record


EFFECTIVE_LIMITS={'CPUQuotaPerSecUSec':'200ms','MemoryMax':'268435456','MemorySwapMax':'0','TasksMax':'24','Nice':'15','IOSchedulingClass':'3','IOWeight':'10'}


def _systemctl(*args):
    return subprocess.check_output(['systemctl','--user',*args],timeout=5).decode().strip()


def _service_state(service):
    raw=_systemctl('show',service.name,*['--property='+key for key in ('ActiveState','MainPID','ExecStart',*EFFECTIVE_LIMITS)])
    return dict(row.split('=',1) for row in raw.splitlines() if '=' in row)


def _inactive_capped(state):
    if state.get('ActiveState') not in ('inactive','failed') or state.get('MainPID')!='0':raise ValueError('original publisher still active')
    if (state.get('CPUQuotaPerSecUSec') not in ('200ms','1s') or
        any(state.get(key)!=value for key,value in EFFECTIVE_LIMITS.items() if key!='CPUQuotaPerSecUSec')):
        raise ValueError('effective original limits differ')


def _qualify(stage,*,deployment_sha256=None):
    if deployment_sha256 is None:verify_stage(stage)
    else:verify_stage(stage,expected_deployment_sha256=deployment_sha256)
    command=['systemd-run','--user','--scope','-p','CPUQuota=20%','-p','MemoryMax=256M','-p','MemorySwapMax=0',
        '-p','TasksMax=24','-p','IOWeight=10','nice','-n','15','ionice','-c','3','timeout','45s','env',
        'OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1','PYTHONDONTWRITEBYTECODE=1',
        'PYTHONPATH='+str(stage/'sources/openhab/scripts')+':/home/sat/Solar_PV/analytics/src','/usr/bin/python3',
        str(stage/'sources/openhab/scripts/household_cycle_deploy.py'),'--stage',str(stage),'--verify-runtime']
    if deployment_sha256 is not None:command+=['--deployment-sha256',deployment_sha256]
    raw=subprocess.check_output(command,timeout=55)
    result=json.loads(raw)
    expected=sha256(_bytes(stage/'deployment.json',private=True)).hexdigest()
    if (set(result)!={'status','deployment_sha256','automatic_actuation'} or result['status']!='runtime_verified' or
        result['deployment_sha256']!=expected or result['automatic_actuation'] is not False):
        raise ValueError('exact capped runtime qualification required')


def verify_runtime(stage,*,deployment_sha256=None):
    from datetime import datetime,timedelta,timezone
    from thermal_installed_intel import _resource_preflight
    _resource_preflight()
    def selected_record():
        return verify_stage(stage) if deployment_sha256 is None else verify_stage(stage,expected_deployment_sha256=deployment_sha256)
    record=selected_record();stage=_directory(stage)
    scripts=stage/'sources/openhab/scripts'
    if Path(__file__).resolve()!=scripts/'household_cycle_deploy.py':raise ValueError('staged verifier execution required')
    from household_cycle_sources import load_cycle_settings,CycleSourceCollector
    from thermal_model.provisional_live import load_settings,current_runtime,_next_issue
    from thermal_model.provisional_artifact import read_candidate
    from thermal_model.capture_guard import SharedScoreLock
    cycle=load_cycle_settings(stage/'cycle.json');native=record['schema'] in ('earthship-household-cycle-deployment/v2','earthship-household-cycle-deployment/v3')
    serving=record['schema']=='earthship-household-cycle-deployment/v3'
    if native:
        from native_thermal_live import load_settings
    settings=load_settings(cycle['forecast_config'])
    now=datetime.now(timezone.utc);issue=_next_issue(now)
    if issue-now<timedelta(seconds=90):raise BlockingIOError('original publisher preparation window reserved')
    with SharedScoreLock(settings['shared_lock']) as lock:
        if native:
            import time
            from native_thermal_artifact import current_native_runtime,read_native_candidate,digest
            from native_inference_pressure import NativeInferenceHeadroom
            pressure=NativeInferenceHeadroom();pressure.preflight();deadline=time.monotonic()+40
            def guard():
                lock.verify();pressure.check()
                if time.monotonic()>=deadline or datetime.now(timezone.utc)>=issue-timedelta(seconds=35):
                    raise ValueError('native staged qualification lifetime elapsed')
            runtime=current_native_runtime(guard=guard)
            if digest(runtime)!=settings['runtime_sha256'] or digest(runtime)!=record['runtime_sha256']:
                raise ValueError('native staged executing runtime differs from external pins')
            if serving:
                from native_model_serving_receipt import load_serving_selection,read_serving_model
                selection=load_serving_selection(stage,expected_deployment_sha256=deployment_sha256,assessed_at=now,guard=guard)
                model=read_serving_model(selection,assessed_at=now,guard=guard)
                if model.runtime!=runtime:raise ValueError('serving model executing runtime differs')
            else:read_native_candidate(settings['candidate_path'],assessed_at=now,runtime=runtime,
                expected_artifact_sha256=settings['artifact_sha256'],guard=guard)
        else:
            runtime=current_runtime();read_candidate(settings['candidate_path'],assessed_at=now,runtime=runtime)
            guard=lock.verify
        collector=CycleSourceCollector(token_file=settings['token_file'],openhab_base=settings['openhab_base'],code_revision=record['code_revision'])
        collector.verify_unchanged();guard()
        executing=current_native_runtime(guard=guard) if native else current_runtime()
        if serving:model.verify_bindings(assessed_at=datetime.now(timezone.utc),guard=guard)
        if selected_record()!=record or executing!=runtime:raise ValueError('staged runtime changed during qualification')
        guard()
    return dict(status='runtime_verified',deployment_sha256=sha256(_bytes(stage/'deployment.json',private=True)).hexdigest(),automatic_actuation=False)


def apply_stage(stage):
    stage=_directory(stage);record=verify_stage(stage);service=_path(record['service_file'])
    if service.name!='thermal-provisional-forecast.service':raise ValueError('fixed original forecast service required')
    before=_service_state(service);_inactive_capped(before)
    cycle=json.loads(_bytes(stage/'cycle.json',private=True))
    if '/provisional_thermal.py --config '+cycle['forecast_config']+' --publish' not in before.get('ExecStart',''):
        raise ValueError('effective original publisher differs')
    _qualify(stage)
    if verify_stage(stage)!=record:raise ValueError('original stage changed after qualification')
    _inactive_capped(_service_state(service))
    folder=service.parent/(service.name+'.d');target=folder/'zzzz-household-cycle.conf'
    if target.exists() or target.is_symlink():raise ValueError('existing service handoff must be reconciled separately')
    folder.mkdir(mode=0o700,exist_ok=True);_directory(folder)
    raw=_bytes(stage/'service.conf',private=True);_write(target,raw)
    try:
        _systemctl('daemon-reload')
        effective=_service_state(service)
        if any(effective.get(key)!=value for key,value in EFFECTIVE_LIMITS.items()):raise ValueError('installed effective limits differ')
        if str(stage/'sources/openhab/scripts/household_cycle.py') not in effective.get('ExecStart',''):
            raise ValueError('installed source entry point differs')
        verify_stage(stage)
    except Exception:
        # Remove only our exact new override; do not overwrite a concurrent edit.
        if _bytes(target,private=True)==raw:
            target.unlink();_systemctl('daemon-reload')
        raise
    return dict(status='deployment_installed',code_revision=record['code_revision'],service_restarted=False,automatic_actuation=False)



def _entry_matches(state,raw):
    lines=[line[len('ExecStart='):] for line in raw.decode().splitlines() if line.startswith('ExecStart=') and line!='ExecStart=']
    if len(lines)!=1:raise ValueError('one staged publisher required')
    actual=state.get('ExecStart','');command=lines[0]
    if actual==command:return True
    entries=re.findall(r'\{ path=([^ ;]+) ; argv\[\]=(.*?) ;[^{}]*\}',actual)
    return len(entries)==1 and len(re.findall(r'\bpath=',actual))==1 and actual.count('argv[]=')==1 and entries[0]==('/usr/bin/python3',command)


def _move_no_replace(directory_fd,source,target):
    import ctypes
    rename=getattr(ctypes.CDLL(None,use_errno=True),'renameat2',None)
    if rename is None:raise ValueError('no-clobber override replacement unavailable')
    rename.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint)
    rename.restype=ctypes.c_int
    if rename(directory_fd,os.fsencode(source),directory_fd,os.fsencode(target),1):
        code=ctypes.get_errno();raise OSError(code,os.strerror(code))


def _override_file(directory_fd,name):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory_fd)
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or
            stat.S_IMODE(info.st_mode)!=0o600 or info.st_size>MAX_BYTES):raise ValueError('owned private override required')
        raw=os.read(fd,MAX_BYTES+1);after=os.fstat(fd)
        metadata=lambda row:(row.st_dev,row.st_ino,row.st_mode,row.st_size,row.st_mtime_ns)
        if len(raw)>MAX_BYTES or metadata(after)!=metadata(info) or after.st_ctime_ns!=info.st_ctime_ns:
            raise ValueError('override changed while reading')
        return raw,metadata(info)
    finally:os.close(fd)


def _replace_owned(target,expected,replacement):
    """Preserve displaced files and install/restore without clobbering names."""
    import secrets
    parent=_directory(target.parent);identity=lambda row:(row.st_dev,row.st_ino,row.st_mode)
    original_directory=identity(parent.stat())
    directory_fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    temp='.household-upgrade-'+secrets.token_hex(16);backup='.household-displaced-'+secrets.token_hex(16)
    created=False;displaced=False;published=False
    def guard_parent():
        if identity(os.fstat(directory_fd))!=original_directory or identity(_directory(target.parent).stat())!=original_directory:
            raise ValueError('override parent changed')
    try:
        guard_parent();original=_override_file(directory_fd,target.name)
        if original[0]!=expected or _bytes(target,private=True)!=expected:raise ValueError('owned override changed')
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory_fd);created=True
        with os.fdopen(fd,'wb') as stream:stream.write(replacement);stream.flush();os.fsync(stream.fileno())
        guard_parent()
        _move_no_replace(directory_fd,target.name,backup);displaced=True
        if _override_file(directory_fd,backup)!=original:raise ValueError('displaced override changed')
        guard_parent()
        try:os.link(temp,target.name,src_dir_fd=directory_fd,dst_dir_fd=directory_fd,follow_symlinks=False)
        except FileExistsError:raise ValueError('override name changed') from None
        os.unlink(temp,dir_fd=directory_fd);created=False
        guard_parent()
        if _override_file(directory_fd,target.name)[0]!=replacement:raise ValueError('override replacement readback differs')
        os.fsync(directory_fd);published=True
    finally:
        try:
            if displaced:
                if published:os.unlink(backup,dir_fd=directory_fd)
                else:
                    try:_move_no_replace(directory_fd,backup,target.name)
                    except FileExistsError:pass # Retain displaced contents privately when name is occupied.
            if created:os.unlink(temp,dir_fd=directory_fd)
        finally:os.close(directory_fd)


def upgrade_stage(stage,*,previous_stage):
    stage=_directory(stage);previous=_directory(previous_stage)
    if stage==previous:raise ValueError('distinct replacement stage required')
    record=verify_stage(stage);old=verify_stage(previous)
    service=_path(record['service_file'])
    if (service.name!='thermal-provisional-forecast.service' or old['service_file']!=record['service_file'] or
        old['original_bindings']!=record['original_bindings'] or old['protected_runtime_sources']!=record['protected_runtime_sources']):
        raise ValueError('same original forecast and fitted runtime required')
    cycle=json.loads(_bytes(stage/'cycle.json',private=True));old_cycle=json.loads(_bytes(previous/'cycle.json',private=True))
    if {k:v for k,v in cycle.items() if k!='evidence_directory'}!={k:v for k,v in old_cycle.items() if k!='evidence_directory'}:
        raise ValueError('same original cycle inputs and observation cache required')
    target=service.parent/(service.name+'.d')/'zzzz-household-cycle.conf';_directory(target.parent)
    old_raw=_bytes(previous/'service.conf',private=True);raw=_bytes(stage/'service.conf',private=True)
    def original_guard():
        if verify_stage(stage)!=record or verify_stage(previous)!=old:raise ValueError('upgrade stage changed')
        if _bytes(target,private=True)!=old_raw:raise ValueError('exact previous owned override required')
        state=_service_state(service);_inactive_capped(state)
        if not _entry_matches(state,old_raw):raise ValueError('effective previous publisher differs')
    original_guard();_qualify(stage);original_guard()
    _replace_owned(target,old_raw,raw)
    try:
        _systemctl('daemon-reload')
        effective=_service_state(service)
        if any(effective.get(key)!=value for key,value in EFFECTIVE_LIMITS.items()) or not _entry_matches(effective,raw):
            raise ValueError('upgraded entry point or limits differ')
        if verify_stage(stage)!=record or _bytes(target,private=True)!=raw:raise ValueError('installed upgrade changed')
    except Exception:
        # Preserve concurrent edits; restore only this exact replacement.
        if _bytes(target,private=True)==raw:
            _replace_owned(target,raw,old_raw);_systemctl('daemon-reload')
        raise
    return dict(status='deployment_upgraded',code_revision=record['code_revision'],previous_code_revision=old['code_revision'],
        service_restarted=False,automatic_actuation=False)


def main(argv=None):
    import argparse,sys
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',required=True,type=Path);parser.add_argument('--deployment-sha256')
    modes=parser.add_mutually_exclusive_group();modes.add_argument('--verify-runtime',action='store_true');modes.add_argument('--apply',action='store_true');modes.add_argument('--upgrade-from',type=Path)
    parser.add_argument('--repo-root',type=Path);parser.add_argument('--forecast-config',type=Path);parser.add_argument('--parameters',type=Path)
    parser.add_argument('--parameters-sha256');parser.add_argument('--observation-cache',type=Path);parser.add_argument('--service-file',type=Path);parser.add_argument('--code-revision')
    parser.add_argument('--model-receipt-path',type=Path);parser.add_argument('--model-receipt-sha256')
    parser.add_argument('--score-dispatch-path',type=Path);parser.add_argument('--score-dispatch-sha256')
    parser.add_argument('--service-forecast-config',type=Path)
    args=parser.parse_args(argv)
    try:
        if args.verify_runtime:
            selected={} if args.deployment_sha256 is None else dict(deployment_sha256=args.deployment_sha256)
            result=verify_runtime(args.stage,**selected)
        elif args.apply:result=apply_stage(args.stage)
        elif args.upgrade_from:result=upgrade_stage(args.stage,previous_stage=args.upgrade_from)
        else:
            refs={name:getattr(args,name) for name in ('model_receipt_path','model_receipt_sha256','score_dispatch_path','score_dispatch_sha256','service_forecast_config') if getattr(args,name) is not None}
            result=stage_deployment(repo_root=args.repo_root,stage=args.stage,forecast_config=args.forecast_config,parameters=args.parameters,
                parameters_sha256=args.parameters_sha256,observation_cache=args.observation_cache,service_file=args.service_file,code_revision=args.code_revision,**refs)
    except BlockingIOError:
        print(json.dumps(dict(status='busy',automatic_actuation=False)));return 75
    except Exception:
        print(json.dumps(dict(status='deployment_refused',automatic_actuation=False)),file=sys.stderr);return 1
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
