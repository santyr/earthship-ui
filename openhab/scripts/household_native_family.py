"""Draft one coherent private native service family without installing it."""
from pathlib import Path
from hashlib import sha256
import json,os,stat


def prepare(stage,libraries,output,*,guard,deployment_sha256=None,interpreter=None):
    import household_cycle_deploy as deploy
    from household_native_geometry_prepare import _library_paths
    from astro_geometry_worker import runtime_identity
    stage,libraries,output=map(deploy._path,(stage,libraries,output))
    guard();interpreter=_interpreter_reference(interpreter);record=_stage_record(stage,deployment_sha256)
    if record['schema'] not in ('earthship-household-cycle-deployment/v2','earthship-household-cycle-deployment/v3'):
        raise ValueError('explicit native deployment stage required')
    original=deploy._bytes(libraries,private=True);paths=_library_paths(original)
    cycle=json.loads(deploy._bytes(stage/'cycle.json',private=True));config=deploy._path(cycle['forecast_config'])
    settings=json.loads(deploy._bytes(config,private=True))
    if settings['artifact_sha256']!=record['artifact_sha256'] or settings['runtime_sha256']!=record['runtime_sha256']:
        raise ValueError('native family model selection differs')
    geometry=json.loads(deploy._bytes(record['native_originals']['geometry']['path'],private=True,maximum=4*1024*1024))
    expected=geometry['native_runtime']
    actual=runtime_identity(paths,binding_version=expected['binding_version'],guard=guard)
    if actual!=expected:raise ValueError('native family libraries differ from fitted geometry')
    serving=record['schema']=='earthship-household-cycle-deployment/v3'
    _model_interpreter(settings,interpreter,serving=serving)
    if serving:
        from household_forecast_score import read_score_dispatch
        read_score_dispatch(stage,deployment_sha256=deployment_sha256,guard=guard)
    files=_render(stage,config,libraries,deployment_sha256=deployment_sha256 if serving else None,interpreter=interpreter)
    guard()
    if deploy._bytes(libraries,private=True)!=original or _stage_record(stage,deployment_sha256)!=record:
        raise ValueError('native family original configuration changed')
    if output.exists() or output.is_symlink():raise ValueError('distinct private native family output required')
    deploy._directory(output.parent);output.mkdir(mode=0o700)
    for name,raw in files.items():deploy._write(output/name,raw)
    family=_metadata(stage,libraries,original,actual,record,files,interpreter=interpreter)
    deploy._write(output/'family.json',deploy._encode(family));guard()
    if (_interpreter_reference(interpreter)!=interpreter or deploy._bytes(libraries,private=True)!=original or _stage_record(stage,deployment_sha256)!=record or
        any(deploy._bytes(output/name,private=True)!=raw for name,raw in files.items())):
        raise ValueError('native family draft readback differs')
    return dict(status='native_family_staged',artifact_sha256=family['artifact_sha256'],runtime_sha256=family['runtime_sha256'],
        live_units_changed=False,automatic_actuation=False)


def _extended_score_window(stage):
    # The caller verifies the complete immutable stage first. Old sealed stages
    # retain their exact original family bytes during an owned upgrade.
    import household_cycle_deploy as deploy
    source=stage/'sources/openhab/scripts/household_forecast_score.py'
    return b'\nSCORE_LIFETIME_SECONDS = 120\n' in b'\n'+deploy._bytes(source)


def _forecast_cpu_quota(stage):
    # The staged driver explicitly opts into the production CPU profile. Keep
    # earlier sealed families byte-identical during upgrade verification.
    import household_cycle_deploy as deploy
    source=stage/'sources/openhab/scripts/household_cycle.py'
    return '100%' if b"\nFORECAST_CPU_QUOTA = '100%'\n" in b'\n'+deploy._bytes(source) else '20%'


def _score_cpu_quota(stage):
    import household_cycle_deploy as deploy
    source=stage/'sources/openhab/scripts/household_forecast_score.py'
    return '100%' if b"\nSCORE_CPU_QUOTA = '100%'\n" in b'\n'+deploy._bytes(source) else '20%'


def _frequent_current_scores(stage):
    import household_cycle_deploy as deploy
    source=stage/'sources/openhab/scripts/household_forecast_score.py'
    return b'\nSCORE_CURRENT_PERIOD_MINUTES = 10\n' in b'\n'+deploy._bytes(source)


def _native_only_scores(stage):
    # Sealed earlier families retain their original legacy routing metadata.
    import household_cycle_deploy as deploy
    source=stage/'sources/openhab/scripts/household_forecast_score.py'
    return b'\nSCORE_HISTORY_PERIOD_MINUTES = 10\n' in b'\n'+deploy._bytes(source)


def _independent_battery_slot(stage):
    import household_cycle_deploy as deploy
    scripts=stage/'sources/openhab/scripts';raw=b'\n'+deploy._bytes(scripts/'household_forecast_score.py')
    if b'\nBATTERY_SCORE_PERIOD_MINUTES = 10\n' not in raw:return False
    if (b'\nBATTERY_SCORE_OFFSET_MINUTE = 8\n' not in raw or b'\nBATTERY_SCORE_OFFSET_SECOND = 20\n' not in raw
        or not (scripts/'household_battery_score.py').is_file()):raise ValueError('complete independent battery opportunity required')
    return True


def _shared_job_pool(stage):
    import household_cycle_deploy as deploy
    scripts=stage/'sources/openhab/scripts'
    policy=scripts/'household_cycle_resources.py'
    if not policy.exists() or b'\nSHARED_PRODUCTION_POOL = True\n' not in b'\n'+deploy._bytes(policy):
        return False
    for name in ('run','launch','pool','budget','start'):
        if not (scripts/('household_job_'+name+'.py')).is_file():
            raise ValueError('complete sealed shared launcher required')
    return True


def _shared_command(raw, scripts, seconds):
    rows=raw.decode().splitlines()
    commands=[i for i,line in enumerate(rows) if line.startswith('ExecStart=') and line!='ExecStart=']
    if len(commands)!=1:raise ValueError('one shared worker command required')
    i=commands[0]
    rows[i]='ExecStart=/usr/bin/python3 '+str(scripts/'household_job_run.py')+(
        ' --production --minimum-mib 256 --preferred-mib 512 --tasks 24 --seconds '+str(seconds)+' -- ')+rows[i][10:]
    return ('\n'.join(rows)+'\n').encode()



def _interpreter_reference(value):
    import household_cycle_deploy as deploy
    if value is None:return None
    if not isinstance(value,dict) or set(value)!={'path','sha256'}:raise ValueError('closed original native interpreter required')
    from thermal_model.graduation_policy import _sha
    path=deploy._path(value['path']);_sha(value['sha256']);info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode&0o222 or
            not info.st_mode&stat.S_IXUSR or info.st_size>64000000 or sha256(deploy._bytes(path,maximum=64000000)).hexdigest()!=value['sha256']):
        raise ValueError('unchanged owned retained native interpreter required')
    return dict(path=str(path),sha256=value['sha256'])


def _model_interpreter(settings,interpreter,*,serving):
    if interpreter is None:return
    import household_cycle_deploy as deploy
    if not serving:raise ValueError('explicit receipt-serving model required for retained interpreter')
    candidate=json.loads(deploy._bytes(settings['candidate_path'],private=True))
    if candidate['runtime']['base_runtime']['interpreter_sha256']!=interpreter['sha256']:
        raise ValueError('retained interpreter differs from admitted model')


def _render(stage,config,libraries,*,deployment_sha256=None,interpreter=None):
    import household_cycle_deploy as deploy
    interpreter=_interpreter_reference(interpreter)
    scripts=stage/'sources/openhab/scripts'
    pin='' if deployment_sha256 is None else ' --deployment-sha256 '+deployment_sha256
    environment='Environment="PYTHONPATH='+str(scripts)+':/home/sat/Solar_PV/analytics/src"\n'
    caps='\n'.join(key+'='+value for key,value in deploy.LIMITS.items())+'\n'
    service=('[Unit]\nDescription=Prepare the selected native thermal forecast geometry\n\n[Service]\nType=oneshot\n'
        'Environment=EARTHSHIP_QUALIFICATION_FIT=0 EARTHSHIP_REMOTE_QUALIFICATION_FIT=0\n'
        'Environment=OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1\n'+environment+
        'ExecStart=/usr/bin/python3 '+str(scripts/'household_native_geometry_prepare.py')+' --config '+str(config)+
        ' --libraries '+str(libraries)+' --stage '+str(stage)+pin+'\n'+caps+'OOMPolicy=kill\nUMask=0077\n')
    timer=('[Unit]\nDescription=Prepare native geometry before the existing forecast warm slot\n\n[Timer]\n'
        'OnCalendar=*-*-* *:03/5:05 UTC\nAccuracySec=1s\nRandomizedDelaySec=0\nPersistent=false\n'
        'Unit=thermal-native-geometry-prepare.service\n\n[Install]\nWantedBy=timers.target\n')
    score=('[Service]\n'+environment+'ExecStart=\nExecStart=/usr/bin/python3 '+str(scripts/'household_forecast_score.py')+
        ' --config '+str(config)+' --stage '+str(stage)+pin+'\n')
    score_timer=('[Timer]\nOnCalendar=\nOnCalendar=*-*-* *:01/5:00 UTC\nOnCalendar=*-*-* *:02/5:00 UTC\n')
    forecast=deploy._bytes(stage/'service.conf',private=True)
    if deployment_sha256 is not None:
        from thermal_model.graduation_policy import _sha
        _sha(deployment_sha256)
        rows=forecast.decode().splitlines()
        commands=[index for index,line in enumerate(rows) if line.startswith('ExecStart=') and line!='ExecStart=']
        if len(commands)!=1 or '--deployment-sha256' in rows[commands[0]]:
            raise ValueError('one inert receipt-serving forecast template required')
        if ' --stage '+str(stage) not in rows[commands[0]]:raise ValueError('serving stage template binding required')
        rows[commands[0]]+=pin;forecast=('\n'.join(rows)+'\n').encode()
        score_timer=('[Timer]\nOnCalendar=\n'+''.join('OnCalendar=*-*-* *:'+minute+'/5:10 UTC\n' for minute in ('00','01','02','03')))
    if deployment_sha256 is not None and _extended_score_window(stage):
        score+='TimeoutStartSec=130\n'
        score_timer='[Timer]\nOnCalendar=\nOnCalendar=*-*-* *:01/5:00 UTC\n'
        if _independent_battery_slot(stage):score_timer+='OnCalendar=*-*-* *:08/10:20 UTC\n'
    if deployment_sha256 is not None and _forecast_cpu_quota(stage)=='100%':
        forecast+=b'CPUQuota=100%\n'
    if deployment_sha256 is not None and _score_cpu_quota(stage)=='100%':
        score+='CPUQuota=100%\n'
    files={'forecast.conf':forecast,
        'score.conf':score.encode(),'score-timer.conf':score_timer.encode(),
        'thermal-native-geometry-prepare.service':service.encode(),'thermal-native-geometry-prepare.timer':timer.encode()}
    if interpreter is not None:
        for name in ('forecast.conf','score.conf','thermal-native-geometry-prepare.service'):
            rows=files[name].decode().splitlines()
            commands=[i for i,line in enumerate(rows) if line.startswith('ExecStart=') and line!='ExecStart=']
            if len(commands)!=1 or not rows[commands[0]].startswith('ExecStart=/usr/bin/python3 '):
                raise ValueError('one original inner numerical worker required')
            rows[commands[0]]='ExecStart='+interpreter['path']+' '+rows[commands[0]][len('ExecStart=/usr/bin/python3 '):]
            files[name]=('\n'.join(rows)+'\n').encode()
    if deployment_sha256 is not None and _shared_job_pool(stage):
        for name,seconds in (('forecast.conf',90),('score.conf',120 if _extended_score_window(stage) else 60),
                ('thermal-native-geometry-prepare.service',90)):
            files[name]=_shared_command(files[name],scripts,seconds)
    return files


def _metadata(stage,libraries,original,actual,record,files,*,interpreter=None):
    import household_cycle_deploy as deploy
    result=dict(schema='earthship-native-thermal-service-family/v1',stage=str(stage),
        deployment_sha256=sha256(deploy._bytes(stage/'deployment.json',private=True)).hexdigest(),
        libraries_path=str(libraries),libraries_sha256=sha256(original).hexdigest(),native_library_runtime=actual,
        artifact_sha256=record['artifact_sha256'],runtime_sha256=record['runtime_sha256'],
        file_sha256={name:sha256(raw).hexdigest() for name,raw in files.items()},
        original_forecast_warm_clock='*-*-* *:04/5:45 UTC',score_service_timeout_seconds=60,
        schedule=dict(score_offsets_seconds=[60,120],preparer_offset_seconds=185,preparer_timeout_seconds=90,
            forecast_warm_offset_seconds=285,issue_offset_seconds=315),
        live_units_changed=False,automatic_actuation=False)
    if record['schema']=='earthship-household-cycle-deployment/v3':
        result.update(schema='earthship-native-thermal-service-family/v2',model_verification=record['model_verification'],
            score_dispatch=record['score_dispatch'],score_slot_roles=dict(current=[0,2],legacy=[1,3]))
        result['schedule']['score_offsets_seconds']=[10,70,130,190]
        if _extended_score_window(stage):
            result['score_service_timeout_seconds']=130
            result['score_slot_roles']=dict(current=[1],legacy=[6],period_minutes=10)
            result['schedule'].update(score_offsets_seconds=[60],score_work_timeout_seconds=120,
                score_cycle_period_seconds=300,score_role_period_seconds=600,score_stop_offset_seconds=180)
            if _frequent_current_scores(stage):
                result['score_slot_roles']=dict(current=[1,11],historical=[16],legacy=[6],period_minutes=20)
                result['schedule']['score_role_period_seconds']=1200
            if _native_only_scores(stage):
                result['score_slot_roles']=dict(current=[1,11],historical=[6,16],period_minutes=20)
            if _independent_battery_slot(stage):
                result['score_slot_roles']['battery']=[8,18]
                result['schedule'].update(battery_score_offsets_seconds=[500],battery_score_period_seconds=600,
                    battery_work_timeout_seconds=20,battery_total_timeout_seconds=45)
    if interpreter is not None:
        if record['schema']!='earthship-household-cycle-deployment/v3':raise ValueError('receipt-serving retained interpreter family required')
        result.update(schema='earthship-native-thermal-service-family/v3',interpreter=_interpreter_reference(interpreter))
    return result


def _stage_record(stage,pin=None):
    import household_cycle_deploy as deploy
    if pin is None:return deploy.verify_stage(stage)
    from thermal_model.graduation_policy import _sha
    if sha256(deploy._bytes(stage/'deployment.json',private=True)).hexdigest()!=_sha(pin):raise ValueError('external native family deployment pin differs')
    return deploy.verify_stage(stage,expected_deployment_sha256=pin)


def verify(output,*,guard):
    """Verify an active Google family, including its Google-only score dispatch."""
    return _verify(output,guard=guard)


def verify_handoff_baseline(output,*,expected_deployment_sha256,guard):
    """Check a retired receipt family's ownership bytes without selecting it."""
    from thermal_model.graduation_policy import _sha
    return _verify(output,guard=guard,baseline_deployment_sha256=_sha(expected_deployment_sha256))


def _verify(output,*,guard,baseline_deployment_sha256=None):
    """Reconstruct the draft from pinned originals, rather than trusting its hashes."""
    import household_cycle_deploy as deploy
    from household_native_geometry_prepare import _library_paths
    from astro_geometry_worker import runtime_identity
    output=deploy._directory(output);guard()
    raw=deploy._bytes(output/'family.json',private=True);family=json.loads(raw)
    interpreter=_interpreter_reference(family.get('interpreter'))
    if (family.get('schema')=='earthship-native-thermal-service-family/v3')!=(interpreter is not None):raise ValueError('explicit retained interpreter family schema required')
    stage=deploy._path(family['stage']);libraries=deploy._path(family['libraries_path'])
    pin=family.get('deployment_sha256') if family.get('schema') in ('earthship-native-thermal-service-family/v2','earthship-native-thermal-service-family/v3') else None
    def selected_record():
        if baseline_deployment_sha256 is not None:
            if family.get('schema') not in ('earthship-native-thermal-service-family/v2','earthship-native-thermal-service-family/v3') or pin!=baseline_deployment_sha256:
                raise ValueError('external retired-family deployment pin differs')
            return deploy.verify_handoff_baseline(stage,expected_deployment_sha256=baseline_deployment_sha256)
        return _stage_record(stage,pin)
    record=selected_record()
    if record['schema'] not in ('earthship-household-cycle-deployment/v2','earthship-household-cycle-deployment/v3'):
        raise ValueError('explicit native deployment stage required')
    original=deploy._bytes(libraries,private=True);paths=_library_paths(original)
    cycle=json.loads(deploy._bytes(stage/'cycle.json',private=True));config=deploy._path(cycle['forecast_config'])
    settings=json.loads(deploy._bytes(config,private=True))
    if baseline_deployment_sha256 is not None:
        if (settings.get('schema') in deploy.GOOGLE_SCHEMAS or
                set(settings)!=deploy._baseline_configuration_fields(settings.get('schema'))):
            raise ValueError('closed retired receipt-family configuration required')
    if settings['artifact_sha256']!=record['artifact_sha256'] or settings['runtime_sha256']!=record['runtime_sha256']:
        raise ValueError('native family model selection differs')
    geometry=json.loads(deploy._bytes(record['native_originals']['geometry']['path'],private=True,maximum=4*1024*1024))
    library_runtime=geometry['native_runtime']
    # A retired family contributes frozen ownership metadata, not executable
    # geometry. The new family independently verifies today's collector/JARs.
    if baseline_deployment_sha256 is None:
        actual=runtime_identity(paths,binding_version=library_runtime['binding_version'],guard=guard)
        if actual!=library_runtime:raise ValueError('native family libraries differ from fitted geometry')
    if record['schema']=='earthship-household-cycle-deployment/v3' and baseline_deployment_sha256 is None:
        from household_forecast_score import read_score_dispatch
        read_score_dispatch(stage,deployment_sha256=pin,guard=guard)
    _model_interpreter(settings,interpreter,serving=record['schema']=='earthship-household-cycle-deployment/v3')
    files=_render(stage,config,libraries,deployment_sha256=pin,interpreter=interpreter)
    expected=_metadata(stage,libraries,original,library_runtime,record,files,interpreter=interpreter)
    if family!=expected or {path.name for path in output.iterdir()}!=set(files)|{'family.json'}:
        raise ValueError('native family metadata or membership differs')
    if any(deploy._bytes(output/name,private=True)!=content for name,content in files.items()):
        raise ValueError('native family service contract differs')
    guard()
    if (_interpreter_reference(interpreter)!=interpreter or deploy._bytes(output/'family.json',private=True)!=raw or
        deploy._bytes(libraries,private=True)!=original or selected_record()!=record or
        any(deploy._bytes(output/name,private=True)!=content for name,content in files.items())):
        raise ValueError('native family originals changed during verification')
    return family


def prepare_score_dispatch(*,historical_selections,output,guard):
    """Bind only Google serving history, without a legacy scorer or self pin."""
    import household_cycle_deploy as deploy
    from household.codec import loads
    from thermal_model.graduation_policy import _sha
    from copy import deepcopy
    output=deploy._path(output);deploy._directory(output.parent)
    if output.exists() or output.is_symlink():raise ValueError('distinct owned score dispatch output required')
    if type(historical_selections) is not tuple or len(historical_selections)>63:
        raise ValueError('bounded explicit historical score selection tuple required')
    references=[];historical=[];seen=set()
    def retained(stage,pin):
        guard();stage=deploy._directory(stage);pin=_sha(pin)
        raw=deploy._bytes(stage/'deployment.json',private=True,maximum=131072)
        if sha256(raw).hexdigest()!=pin:raise ValueError('retained scoring stage pin differs')
        record=deploy.verify_stage(stage,expected_deployment_sha256=pin)
        if record['schema']!='earthship-household-cycle-deployment/v3':raise ValueError('Google receipt-serving history required')
        cycle=deploy._bytes(stage/'cycle.json',private=True,maximum=8192)
        config=deploy._path(loads(cycle)['forecast_config'])
        original=deploy._bytes(config,private=True,maximum=8192)
        if loads(original).get('schema')!='earthship-weathernext-thermal-live-config/v2':
            raise ValueError('Google-only historical model configuration required')
        return ((stage/'deployment.json',raw),(stage/'cycle.json',cycle),(config,original))
    for reference in deepcopy(historical_selections):
        if not isinstance(reference,dict) or set(reference)!={'stage','deployment_sha256'}:
            raise ValueError('closed explicit historical deployment pin required')
        stage=deploy._directory(reference['stage'])
        if str(stage) in seen:raise ValueError('unique retained scoring stages required')
        seen.add(str(stage));references.extend(retained(stage,reference['deployment_sha256']))
        historical.append(dict(stage=str(stage),deployment_sha256=reference['deployment_sha256']))
    record=dict(schema='earthship-native-score-dispatch/v2',current='current',historical=historical)
    raw=deploy._encode(record)
    if len(raw)>131072:raise ValueError('bounded owned score dispatch record required')
    def unchanged():
        guard()
        if any(deploy._bytes(path,private=True,maximum=131072)!=original for path,original in references):
            raise ValueError('retained score selection changed during package preparation')
        for selection in historical:retained(selection['stage'],selection['deployment_sha256'])
    unchanged();deploy._write(output,raw);unchanged()
    if deploy._bytes(output,private=True,maximum=131072)!=raw:raise ValueError('score dispatch readback differs')
    return dict(status='native_score_dispatch_staged',path=str(output),sha256=sha256(raw).hexdigest(),
        live_units_changed=False,automatic_actuation=False)
