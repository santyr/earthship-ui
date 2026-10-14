"""Draft one coherent private native service family without installing it."""
from pathlib import Path
from hashlib import sha256
import json


def prepare(stage,libraries,output,*,guard,deployment_sha256=None):
    import household_cycle_deploy as deploy
    from household_native_geometry_prepare import _library_paths
    from astro_geometry_worker import runtime_identity
    stage,libraries,output=map(deploy._path,(stage,libraries,output))
    guard();record=_stage_record(stage,deployment_sha256)
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
    if serving:
        from household_forecast_score import read_score_dispatch
        read_score_dispatch(stage,deployment_sha256=deployment_sha256,guard=guard)
    files=_render(stage,config,libraries,deployment_sha256=deployment_sha256 if serving else None)
    guard()
    if deploy._bytes(libraries,private=True)!=original or _stage_record(stage,deployment_sha256)!=record:
        raise ValueError('native family original configuration changed')
    if output.exists() or output.is_symlink():raise ValueError('distinct private native family output required')
    deploy._directory(output.parent);output.mkdir(mode=0o700)
    for name,raw in files.items():deploy._write(output/name,raw)
    family=_metadata(stage,libraries,original,actual,record,files)
    deploy._write(output/'family.json',deploy._encode(family));guard()
    if (deploy._bytes(libraries,private=True)!=original or _stage_record(stage,deployment_sha256)!=record or
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


def _render(stage,config,libraries,*,deployment_sha256=None):
    import household_cycle_deploy as deploy
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
    if deployment_sha256 is not None and _forecast_cpu_quota(stage)=='100%':
        forecast+=b'CPUQuota=100%\n'
    files={'forecast.conf':forecast,
        'score.conf':score.encode(),'score-timer.conf':score_timer.encode(),
        'thermal-native-geometry-prepare.service':service.encode(),'thermal-native-geometry-prepare.timer':timer.encode()}
    return files


def _metadata(stage,libraries,original,actual,record,files):
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
    return result


def _stage_record(stage,pin=None):
    import household_cycle_deploy as deploy
    if pin is None:return deploy.verify_stage(stage)
    from thermal_model.graduation_policy import _sha
    if sha256(deploy._bytes(stage/'deployment.json',private=True)).hexdigest()!=_sha(pin):raise ValueError('external native family deployment pin differs')
    return deploy.verify_stage(stage,expected_deployment_sha256=pin)


def verify(output,*,guard):
    """Reconstruct the draft from pinned originals, rather than trusting its hashes."""
    import household_cycle_deploy as deploy
    from household_native_geometry_prepare import _library_paths
    from astro_geometry_worker import runtime_identity
    output=deploy._directory(output);guard()
    raw=deploy._bytes(output/'family.json',private=True);family=json.loads(raw)
    stage=deploy._path(family['stage']);libraries=deploy._path(family['libraries_path'])
    pin=family.get('deployment_sha256') if family.get('schema')=='earthship-native-thermal-service-family/v2' else None
    record=_stage_record(stage,pin)
    if record['schema'] not in ('earthship-household-cycle-deployment/v2','earthship-household-cycle-deployment/v3'):
        raise ValueError('explicit native deployment stage required')
    original=deploy._bytes(libraries,private=True);paths=_library_paths(original)
    cycle=json.loads(deploy._bytes(stage/'cycle.json',private=True));config=deploy._path(cycle['forecast_config'])
    settings=json.loads(deploy._bytes(config,private=True))
    if settings['artifact_sha256']!=record['artifact_sha256'] or settings['runtime_sha256']!=record['runtime_sha256']:
        raise ValueError('native family model selection differs')
    geometry=json.loads(deploy._bytes(record['native_originals']['geometry']['path'],private=True,maximum=4*1024*1024))
    actual=runtime_identity(paths,binding_version=geometry['native_runtime']['binding_version'],guard=guard)
    if actual!=geometry['native_runtime']:raise ValueError('native family libraries differ from fitted geometry')
    if record['schema']=='earthship-household-cycle-deployment/v3':
        from household_forecast_score import read_score_dispatch
        read_score_dispatch(stage,deployment_sha256=pin,guard=guard)
    files=_render(stage,config,libraries,deployment_sha256=pin)
    expected=_metadata(stage,libraries,original,actual,record,files)
    if family!=expected or {path.name for path in output.iterdir()}!=set(files)|{'family.json'}:
        raise ValueError('native family metadata or membership differs')
    if any(deploy._bytes(output/name,private=True)!=content for name,content in files.items()):
        raise ValueError('native family service contract differs')
    guard()
    if (deploy._bytes(output/'family.json',private=True)!=raw or
        deploy._bytes(libraries,private=True)!=original or _stage_record(stage,pin)!=record or
        any(deploy._bytes(output/name,private=True)!=content for name,content in files.items())):
        raise ValueError('native family originals changed during verification')
    return family


def prepare_score_dispatch(*,legacy_stage,legacy_deployment_sha256,historical_selections,output,guard):
    """Bind retained selections without embedding a final stage's own digest."""
    import household_cycle_deploy as deploy
    from household.codec import loads
    from thermal_model.graduation_policy import _sha
    from copy import deepcopy
    legacy_stage=deploy._directory(legacy_stage);output=deploy._path(output)
    deploy._directory(output.parent)
    if output.exists() or output.is_symlink():raise ValueError('distinct owned score dispatch output required')
    if type(historical_selections) is not tuple or len(historical_selections)>31:
        raise ValueError('bounded explicit historical score selection tuple required')
    references=[]
    def retained(stage,pin,schema):
        guard();stage=deploy._directory(stage);pin=_sha(pin)
        raw=deploy._bytes(stage/'deployment.json',private=True,maximum=131072)
        if sha256(raw).hexdigest()!=pin:raise ValueError('retained scoring stage pin differs')
        record=deploy.verify_stage(stage,expected_deployment_sha256=pin)
        if record['schema']!=schema:raise ValueError('explicit retained scoring stage profile required')
        references.append((stage/'deployment.json',raw))
        return record
    retained(legacy_stage,legacy_deployment_sha256,'earthship-household-cycle-deployment/v1')
    cycle_raw=deploy._bytes(legacy_stage/'cycle.json',private=True,maximum=8192)
    config=deploy._path(loads(cycle_raw)['forecast_config']);config_raw=deploy._bytes(config,private=True,maximum=8192)
    if loads(config_raw).get('schema')!='earthship-provisional-thermal-live-config/v1':
        raise ValueError('retained legacy configuration profile required')
    references.extend(((legacy_stage/'cycle.json',cycle_raw),(config,config_raw)))
    historical=[];seen={str(legacy_stage)}
    for reference in deepcopy(historical_selections):
        if not isinstance(reference,dict) or set(reference)!={'stage','deployment_sha256'}:
            raise ValueError('closed explicit historical deployment pin required')
        stage=deploy._directory(reference['stage'])
        if str(stage) in seen:raise ValueError('unique retained scoring stages required')
        seen.add(str(stage));retained(stage,reference['deployment_sha256'],'earthship-household-cycle-deployment/v3')
        historical.append(dict(stage=str(stage),deployment_sha256=reference['deployment_sha256']))
    record=dict(schema='earthship-native-score-dispatch/v1',current='current',
        legacy=dict(stage=str(legacy_stage),deployment_sha256=legacy_deployment_sha256,config=str(config),
            config_sha256=sha256(config_raw).hexdigest()),historical=historical)
    raw=deploy._encode(record)
    if len(raw)>131072:raise ValueError('bounded owned score dispatch record required')
    def unchanged():
        guard()
        if any(deploy._bytes(path,private=True,maximum=131072)!=original for path,original in references):
            raise ValueError('retained score selection changed during package preparation')
        retained(legacy_stage,legacy_deployment_sha256,'earthship-household-cycle-deployment/v1')
        for selection in historical:retained(selection['stage'],selection['deployment_sha256'],'earthship-household-cycle-deployment/v3')
    unchanged();deploy._write(output,raw);unchanged()
    if deploy._bytes(output,private=True,maximum=131072)!=raw:raise ValueError('score dispatch readback differs')
    return dict(status='native_score_dispatch_staged',path=str(output),sha256=sha256(raw).hexdigest(),
        live_units_changed=False,automatic_actuation=False)
