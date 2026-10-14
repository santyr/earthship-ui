"""Keep independently verified performance visible across a missing outcome.

This outside-fitted coordinator preserves the original scorer and single-job
semantics. It never invents measurements, changes model parameters or acts.
"""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import time
from contextlib import contextmanager

SCORE_LIFETIME_SECONDS = 120
SCORE_CPU_QUOTA = '100%'
SCORE_CURRENT_PERIOD_MINUTES = 10
PUBLICATION_POLICY_SHA256 = '092dab2595bb8f8478fd0519118e1e277ab8aa61d887d5ff2fc38d4ea7717f70'
_production_policy = None


def production_resource_preflight(*,leaf=None):
    """Load the pinned one-core publication policy from this coordinator's stage."""
    global _production_policy
    import importlib.util
    from hashlib import sha256
    from thermal_model.origin_capture import _source_bytes
    path=Path(__file__).resolve().with_name('household_cycle_resources.py')
    if sha256(_source_bytes(path,maximum=262144)).hexdigest()!=PUBLICATION_POLICY_SHA256:
        raise ValueError('score publication policy source differs')
    if _production_policy is None or Path(_production_policy.__file__).resolve()!=path:
        spec=importlib.util.spec_from_file_location('_earthship_score_publication_policy',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        _production_policy=module
    _production_policy.publication_resource_preflight(leaf=leaf)


@contextmanager
def production_score_policy():
    """Explicitly use current admission for an archived scoring invocation only."""
    import thermal_installed_intel as installed
    import household_cycle_resources as resources
    production_resource_preflight()
    hooks=[(installed,'_resource_preflight'),(resources,'publication_resource_preflight')]
    # Native archives also bind this policy at import time. Override admission
    # only; their numerical functions and source/receipt validation stay original.
    if Path(installed.__file__).with_name('native_thermal_live.py').is_file():
        import native_thermal_live as native
        if hasattr(native,'_resource_preflight'):
            hooks.append((native,'_resource_preflight'))
    originals=[(module,name,getattr(module,name)) for module,name in hooks]
    try:
        for module,name,_ in originals:setattr(module,name,production_resource_preflight)
        yield
    finally:
        for module,name,original in reversed(originals):setattr(module,name,original)


def score_with_report(settings,*,guard,clock=lambda:datetime.now(timezone.utc),queue=False,serving_model=None,historical_selections=()):
    if settings.get('schema')=='earthship-provisional-thermal-live-config/v3':
        from native_thermal_live import score_jobs
        if serving_model is None:raise ValueError('owned serving score context required')
        from household_native_score_queries import RecentCycleWindowReader
        from thermal_model.installed_shade_score_inputs import COMPRESSED_SOURCE_SCHEMA
        from thermal_model.provisional_live import _phase_directory
        from thermal_model.forcing_capture import _private_directory
        guard()
        folder=_phase_directory(_private_directory(Path(settings['evidence_directory'])),'scores',clock())
        config={key:settings[key] for key in ('token_file','native_db_config','native_policy','openhab_base')}
        config.update(schema=COMPRESSED_SOURCE_SCHEMA,output_directory=str(folder))
        reader=RecentCycleWindowReader(config,shared_lock_guard=guard)
        guard();return score_jobs(settings,guard=guard,reader=reader,serving_model=serving_model,historical_selections=historical_selections)
    if serving_model is not None or historical_selections:raise ValueError('receipt context requires explicit serving profile')
    if settings.get('schema')=='earthship-provisional-thermal-live-config/v2':
        from native_thermal_live import score_jobs
        guard()
        return score_jobs(settings,guard=guard)
    from thermal_model import provisional_monitor as monitor
    guard();now=clock();runtime=monitor.current_runtime()
    candidate=monitor.read_candidate(Path(settings['candidate_path']),assessed_at=now,runtime=runtime)
    score_jobs=monitor.score_jobs
    if queue:
        from household_score_queue import score_jobs
    try:return score_jobs(settings,guard=guard)
    except ValueError as error:
        if str(error)!='original mature outcome unavailable':raise
    # Original refresh replays pair validation and checks every retained source
    # fingerprint. Missing/corrupt completed originals cannot become a report.
    guard()
    report=monitor.refresh_report(settings,artifact_sha256=candidate['artifact_sha256'],now=clock(),guard=guard)
    guard()
    return dict(status='monitoring_refreshed',scored=0,
        current_revision_scored=sum(row['model']['count'] for row in report['by_horizon'].values()),
        pending_reason='mature_outcome_unavailable',automatic_actuation=False)


def run(config,*,stage=None,deployment_sha256=None,retained_native=False,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic):
    import os
    _resource_preflight=production_resource_preflight
    from thermal_model.provisional_live import load_settings,_next_issue
    from thermal_model.capture_guard import SharedScoreLock
    from thermal_model.training_pressure_guard import TrainingHeadroom
    from thermal_model.policy_registration import _read_private
    from household_observation import _private_file
    deadline=monotonic()+SCORE_LIFETIME_SECONDS
    _resource_preflight()
    os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
    config=Path(config).absolute();original=_private_file(config,8192)
    from household.codec import loads
    declared=loads(original[0])
    if isinstance(declared,dict) and declared.get('schema') in ('earthship-provisional-thermal-live-config/v2','earthship-provisional-thermal-live-config/v3'):
        from native_thermal_live import load_settings
    settings=load_settings(config)
    receipt_profile=settings.get('schema')=='earthship-provisional-thermal-live-config/v3'
    if retained_native and not receipt_profile:raise ValueError('retained native execution requires explicit serving profile')
    if receipt_profile and (stage is None or deployment_sha256 is None):raise ValueError('external serving score stage pin required')
    own=Path(__file__).read_bytes();now=clock();issue=_next_issue(now)
    if issue-now<timedelta(seconds=90):raise BlockingIOError('forecast preparation window reserved')
    verifier=None;binding=None
    if stage is not None:
        from household_cycle_deploy import verify_stage
        stage=Path(stage).absolute()
        if receipt_profile:
            def verifier(actual):return verify_stage(actual,expected_deployment_sha256=deployment_sha256)
        else:verifier=verify_stage
        binding=verifier(stage)
        if Path(__file__).resolve()!=stage/'sources/openhab/scripts/household_forecast_score.py':
            raise ValueError('staged score coordinator execution required')
    dispatch=None
    if receipt_profile:
        def selection_guard():
            _resource_preflight()
            if monotonic()>=deadline or _private_file(config,8192)!=original or Path(__file__).read_bytes()!=own:
                raise ValueError('score source or selection changed before dispatch')
        dispatch=read_score_dispatch(stage,deployment_sha256=deployment_sha256,guard=selection_guard)
        role='current' if retained_native else score_role(now)
        if role=='reserved':return dict(status='waiting',scored=0,pending_reason='forecast_slot_reserved',automatic_actuation=False)
        if role=='legacy':
            selection_guard()
            if verifier(stage)!=binding:raise ValueError('staged score selection changed before dispatch')
            return execute_legacy_score(dispatch['legacy'])
        target='current' if retained_native else native_score_selection(dispatch,now)
        if target!='current':
            selection_guard()
            archived=verify_stage(Path(target['stage']),expected_deployment_sha256=target['deployment_sha256'])
            selection_guard()
            compatible=(archived['runtime_sha256']==binding['runtime_sha256'] and
                archived['model_verification']['helper']['sha256']==binding['model_verification']['helper']['sha256'])
            if not compatible:
                if verifier(stage)!=binding:raise ValueError('staged historical score selection changed before dispatch')
                return execute_retained_native_score(target)
            # Compatible owned history is re-read below and scored with its
            # original model association, without restarting the lifetime.

    with SharedScoreLock(settings['shared_lock']) as lock:
        if settings.get('schema') in ('earthship-provisional-thermal-live-config/v2','earthship-provisional-thermal-live-config/v3'):
            from native_inference_pressure import NativeInferenceHeadroom
            pressure=NativeInferenceHeadroom();pressure.preflight()
        else:
            pressure=TrainingHeadroom(max_swapin_bytes_per_second=1048576)
        def guard():
            lock.verify();pressure.check()
            if monotonic()>=deadline or clock()>=issue-timedelta(seconds=135):raise ValueError('score lifetime elapsed')
            if _private_file(config,8192)!=original or _read_private(config)!=settings or Path(__file__).read_bytes()!=own:
                raise ValueError('score source or configuration changed')
        if receipt_profile:
            from native_model_serving_receipt import load_serving_selection,read_serving_model
            selected=load_serving_selection(stage,expected_deployment_sha256=deployment_sha256,assessed_at=clock(),guard=guard)
            model=read_serving_model(selected,assessed_at=clock(),guard=guard)
            historical=[]
            for ref in ([] if retained_native else dispatch['historical']):
                guard()
                archived=verify_stage(Path(ref['stage']),expected_deployment_sha256=ref['deployment_sha256'])
                # Different source revisions execute only in their sealed worker.
                if (archived['runtime_sha256']!=binding['runtime_sha256'] or
                    archived['model_verification']['helper']['sha256']!=binding['model_verification']['helper']['sha256']):continue
                historical.append(load_serving_selection(Path(ref['stage']),expected_deployment_sha256=ref['deployment_sha256'],
                    assessed_at=clock(),guard=guard))
            historical=tuple(historical)
            result=score_with_report(settings,guard=guard,clock=clock,queue=True,serving_model=model,historical_selections=historical)
        else:result=score_with_report(settings,guard=guard,clock=clock,queue=True)
        guard()
        if verifier is not None and verifier(stage)!=binding:raise ValueError('staged score runtime changed')
        return result


def failure_reason(error):
    """Only fixed categories reach logs; exception messages may contain secrets."""
    if isinstance(error,TimeoutError):return 'deadline'
    if isinstance(error,OSError):return 'io_unavailable'
    if not isinstance(error,ValueError):return 'unexpected_failure'
    message=str(error).removeprefix('training host pressure or memory reserve unavailable: ')
    reasons={
        'interval memory pressure exceeded':'memory_pressure',
        'memory pressure exceeded':'memory_pressure',
        'publication memory pressure unavailable':'memory_pressure',
        'host swap-read activity exceeded bounded allowance':'host_swap_read',
        'swap-out activity or OOM counter changed':'swap_out_or_oom',
        'publication host OOM or worker memory-limit counters changed':'oom_or_worker_limit',
        'memory reserve unavailable':'memory_headroom',
        'publication memory headroom unavailable':'memory_headroom',
        'verified publication resources required':'resource_admission',
        'strict serial installed publication resource limits required':'resource_limits',
        'score lifetime elapsed':'deadline',
        'native scoring deadline exceeded':'deadline',
        'capture read deadline exceeded':'deadline',
        'capture request pacing exceeds deadline':'deadline',
        'native query deadline elapsed or too short':'deadline',
        'bounded native connection deadline unavailable':'deadline',
    }
    return reasons.get(message,'validation_refused')


def failure_site(error):
    """Return only the innermost repository source name and line, never locals."""
    import re
    from pathlib import PurePosixPath
    trace=error.__traceback__
    if trace is None:return None
    while trace.tb_next is not None:trace=trace.tb_next
    filename=trace.tb_frame.f_code.co_filename
    marker='/openhab/scripts/'
    if marker not in filename:return None
    relative=filename.rsplit(marker,1)[1]
    path=PurePosixPath(relative)
    if (len(relative)>200 or re.fullmatch(r'[A-Za-z0-9_./-]+\.py',relative) is None or
            path.is_absolute() or '..' in path.parts or str(path)!=relative or
            not 1<=trace.tb_lineno<=100000):return None
    return dict(source=relative,line=trace.tb_lineno)


def run_retained_worker(script,config,*,stage,deployment_sha256,retained_native):
    """Use archived code/dependencies, with this release's error reporting only."""
    import runpy
    from hashlib import sha256
    import household_cycle_deploy as deploy
    stage=deploy._path(stage);script=deploy._path(script)
    source='openhab/scripts/household_forecast_score.py'
    if script!=stage/'sources'/source:raise ValueError('owned retained score path required')
    def read_manifest():
        # The v1 archive predates the helper's maximum keyword.
        raw=deploy._bytes(stage/'deployment.json',private=True)
        if len(raw)>131072:raise ValueError('bounded retained manifest required')
        return raw
    manifest=read_manifest()
    if sha256(manifest).hexdigest()!=deployment_sha256:raise ValueError('retained worker deployment changed')
    if Path(deploy.__file__).resolve()!=stage/'sources/openhab/scripts/household_cycle_deploy.py':
        raise ValueError('retained worker dependency context differs')
    record=deploy.verify_stage(stage,**({'expected_deployment_sha256':deployment_sha256} if retained_native else {}))
    original=deploy._bytes(script)
    if sha256(original).hexdigest()!=record['source_manifest'].get(source):
        raise ValueError('retained worker source changed')
    namespace=runpy.run_path(str(script),run_name='retained_score_worker')
    if deploy._bytes(script)!=original or read_manifest()!=manifest:
        raise ValueError('retained worker changed before execution')
    options=dict(stage=stage)
    if retained_native:options.update(deployment_sha256=deployment_sha256,retained_native=True)
    with production_score_policy():
        result=namespace['run'](config,**options)
    if deploy._bytes(script)!=original or read_manifest()!=manifest:
        raise ValueError('retained worker changed during execution')
    return result


def main(argv=None):
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path);parser.add_argument('--stage',type=Path);parser.add_argument('--deployment-sha256');parser.add_argument('--retained-native',action='store_true')
    parser.add_argument('--worker-script',type=Path);parser.add_argument('--worker-deployment-sha256')
    args=parser.parse_args(argv)
    try:
        selected={} if args.deployment_sha256 is None else dict(deployment_sha256=args.deployment_sha256)
        if args.retained_native:selected['retained_native']=True
        if args.worker_script is not None:
            result=run_retained_worker(args.worker_script,args.config,stage=args.stage,
                deployment_sha256=args.worker_deployment_sha256,retained_native=args.retained_native)
        else:
            result=run(args.config,stage=args.stage,**selected)
    except BlockingIOError:print(json.dumps(dict(status='busy',fit_executed=False,automatic_actuation=False)));return 75
    except Exception as error:
        result=dict(status='score_withheld',reason=failure_reason(error),fit_executed=False,automatic_actuation=False)
        site=failure_site(error)
        if site is not None:result['site']=site
        print(json.dumps(result));return 1
    print(json.dumps(result));return 0 if result.get('status') in ('scored','waiting','monitoring_refreshed') else 1




def score_role(at):
    from astro_geometry import _instant
    at=_instant(at)
    if at.minute%10==1:return 'current'
    if at.minute%20==6:return 'legacy'
    if at.minute%20==16:return 'historical'
    return 'reserved'


def read_score_dispatch(stage,*,deployment_sha256,guard):
    import household_cycle_deploy as deploy
    from hashlib import sha256
    from household.codec import loads
    from thermal_model.graduation_policy import _sha
    stage=deploy._path(stage);pin=_sha(deployment_sha256);guard()
    record=deploy.verify_stage(stage,expected_deployment_sha256=pin)
    if record['schema']!='earthship-household-cycle-deployment/v3':raise ValueError('receipt-serving score dispatch required')
    ref=record['score_dispatch'];path=deploy._path(ref['path'])
    raw=deploy._bytes(path,private=True,maximum=131072)
    if sha256(raw).hexdigest()!=_sha(ref['sha256']):raise ValueError('owned score dispatch bytes differ')
    value=loads(raw)
    if (not isinstance(value,dict) or set(value)!={'schema','current','legacy','historical'} or
        value['schema']!='earthship-native-score-dispatch/v1' or value['current']!='current'):
        raise ValueError('closed explicit score dispatch required')
    legacy=value['legacy']
    if not isinstance(legacy,dict) or set(legacy)!={'stage','deployment_sha256','config','config_sha256'}:
        raise ValueError('explicit retained legacy score selection required')
    retained=deploy._path(legacy['stage']);config=deploy._path(legacy['config'])
    if retained==stage:raise ValueError('legacy score stage must be retained separately')
    def pinned_stage(selected,identity):
        manifest=deploy._bytes(selected/'deployment.json',private=True,maximum=131072)
        if sha256(manifest).hexdigest()!=_sha(identity):raise ValueError('retained score deployment changed')
        result=deploy.verify_stage(selected,expected_deployment_sha256=identity)
        if deploy._bytes(selected/'deployment.json',private=True,maximum=131072)!=manifest:
            raise ValueError('retained score deployment changed during readback')
        return result
    original=pinned_stage(retained,legacy['deployment_sha256'])
    if original['schema']!='earthship-household-cycle-deployment/v1':raise ValueError('legacy score profile required')
    original_config=deploy._bytes(config,private=True,maximum=8192)
    if sha256(original_config).hexdigest()!=_sha(legacy['config_sha256']):raise ValueError('retained legacy configuration changed')
    cycle=loads(deploy._bytes(retained/'cycle.json',private=True,maximum=8192))
    if cycle.get('forecast_config')!=str(config) or loads(original_config).get('schema')!='earthship-provisional-thermal-live-config/v1':
        raise ValueError('retained legacy cycle configuration differs')
    historical=value['historical']
    if not isinstance(historical,list) or len(historical)>31:raise ValueError('bounded explicit historical score selections required')
    seen={str(stage)}
    for selection in historical:
        guard()
        if not isinstance(selection,dict) or set(selection)!={'stage','deployment_sha256'}:raise ValueError('closed historical serving stage pin required')
        selected=deploy._path(selection['stage'])
        if str(selected) in seen:raise ValueError('unique historical serving stages required')
        seen.add(str(selected))
        if pinned_stage(selected,selection['deployment_sha256'])['schema']!='earthship-household-cycle-deployment/v3':
            raise ValueError('retained historical serving profile required')
    guard()
    if (deploy._bytes(path,private=True,maximum=131072)!=raw or deploy._bytes(config,private=True,maximum=8192)!=original_config or
        deploy.verify_stage(stage,expected_deployment_sha256=pin)!=record):
        raise ValueError('owned score selection changed during dispatch read')
    return value




def execute_legacy_score(selection):
    """Replace this invocation with its exact retained worker under the same unit."""
    import os
    from hashlib import sha256
    import household_cycle_deploy as deploy
    stage=deploy._path(selection['stage']);config=deploy._path(selection['config'])
    original=deploy._bytes(stage/'deployment.json',private=True,maximum=131072)
    if sha256(original).hexdigest()!=selection['deployment_sha256']:raise ValueError('retained score deployment changed before execution')
    record=deploy.verify_stage(stage,expected_deployment_sha256=selection['deployment_sha256'])
    source='openhab/scripts/household_forecast_score.py';script=stage/'sources'/source
    if record['schema']!='earthship-household-cycle-deployment/v1' or source not in record['source_manifest']:
        raise ValueError('retained legacy score source closure required')
    if (sha256(deploy._bytes(config,private=True,maximum=8192)).hexdigest()!=selection['config_sha256'] or
        deploy._bytes(stage/'deployment.json',private=True,maximum=131072)!=original or
        sha256(deploy._bytes(script)).hexdigest()!=record['source_manifest'][source]):
        raise ValueError('retained score source or config changed before execution')
    command=['/usr/bin/python3','-P',str(Path(__file__).resolve()),'--worker-script',str(script),
        '--worker-deployment-sha256',selection['deployment_sha256'],'--config',str(config),'--stage',str(stage)]
    environment=dict(os.environ,PYTHONPATH=str(stage/'sources/openhab/scripts')+':/home/sat/Solar_PV/analytics/src')
    os.execve(command[0],command,environment)



def native_score_selection(dispatch,at):
    from astro_geometry import _instant
    at=_instant(at)
    role=score_role(at)
    if role not in ('current','historical'):raise ValueError('explicit native scoring opportunity required')
    historical=dispatch['historical']
    if role=='current' or not historical:return 'current'
    # Current feedback every ten minutes stays inside the 15-minute report TTL;
    # the alternate background slots rotate explicit history every twenty.
    slot=int(at.timestamp())//1200
    return historical[slot%len(historical)]



def execute_retained_native_score(selection):
    import os
    from hashlib import sha256
    from household.codec import loads
    import household_cycle_deploy as deploy
    stage=deploy._path(selection['stage']);pin=selection['deployment_sha256']
    manifest=deploy._bytes(stage/'deployment.json',private=True,maximum=131072)
    if sha256(manifest).hexdigest()!=pin:raise ValueError('retained native stage changed before execution')
    record=deploy.verify_stage(stage,expected_deployment_sha256=pin)
    if record['schema']!='earthship-household-cycle-deployment/v3':raise ValueError('explicit retained receipt-serving profile required')
    cycle_raw=deploy._bytes(stage/'cycle.json',private=True,maximum=8192)
    config=deploy._path(loads(cycle_raw)['forecast_config']);source='openhab/scripts/household_forecast_score.py'
    script=stage/'sources'/source
    if (source not in record['source_manifest'] or sha256(deploy._bytes(script)).hexdigest()!=record['source_manifest'][source] or
        deploy._bytes(stage/'deployment.json',private=True,maximum=131072)!=manifest or
        deploy._bytes(stage/'cycle.json',private=True,maximum=8192)!=cycle_raw):
        raise ValueError('retained native executing source changed')
    command=['/usr/bin/python3','-P',str(Path(__file__).resolve()),'--worker-script',str(script),
        '--worker-deployment-sha256',pin,'--config',str(config),'--stage',str(stage),'--retained-native']
    environment=dict(os.environ,PYTHONPATH=str(stage/'sources/openhab/scripts')+':/home/sat/Solar_PV/analytics/src')
    os.execve(command[0],command,environment)

if __name__=='__main__':raise SystemExit(main())
