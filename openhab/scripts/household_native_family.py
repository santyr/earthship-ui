"""Draft one coherent private native service family without installing it."""
from pathlib import Path
from hashlib import sha256
import json


def prepare(stage,libraries,output,*,guard):
    import household_cycle_deploy as deploy
    from household_native_geometry_prepare import _library_paths
    from astro_geometry_worker import runtime_identity
    stage,libraries,output=map(deploy._path,(stage,libraries,output))
    guard();record=deploy.verify_stage(stage)
    if record['schema']!='earthship-household-cycle-deployment/v2':
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
    files=_render(stage,config,libraries)
    guard()
    if deploy._bytes(libraries,private=True)!=original or deploy.verify_stage(stage)!=record:
        raise ValueError('native family original configuration changed')
    if output.exists() or output.is_symlink():raise ValueError('distinct private native family output required')
    deploy._directory(output.parent);output.mkdir(mode=0o700)
    for name,raw in files.items():deploy._write(output/name,raw)
    family=_metadata(stage,libraries,original,actual,record,files)
    deploy._write(output/'family.json',deploy._encode(family));guard()
    if (deploy._bytes(libraries,private=True)!=original or deploy.verify_stage(stage)!=record or
        any(deploy._bytes(output/name,private=True)!=raw for name,raw in files.items())):
        raise ValueError('native family draft readback differs')
    return dict(status='native_family_staged',artifact_sha256=family['artifact_sha256'],runtime_sha256=family['runtime_sha256'],
        live_units_changed=False,automatic_actuation=False)


def _render(stage,config,libraries):
    import household_cycle_deploy as deploy
    scripts=stage/'sources/openhab/scripts'
    environment='Environment="PYTHONPATH='+str(scripts)+':/home/sat/Solar_PV/analytics/src"\n'
    caps='\n'.join(key+'='+value for key,value in deploy.LIMITS.items())+'\n'
    service=('[Unit]\nDescription=Prepare the selected native thermal forecast geometry\n\n[Service]\nType=oneshot\n'
        'Environment=EARTHSHIP_QUALIFICATION_FIT=0 EARTHSHIP_REMOTE_QUALIFICATION_FIT=0\n'
        'Environment=OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1\n'+environment+
        'ExecStart=/usr/bin/python3 '+str(scripts/'household_native_geometry_prepare.py')+' --config '+str(config)+
        ' --libraries '+str(libraries)+' --stage '+str(stage)+'\n'+caps+'OOMPolicy=kill\nUMask=0077\n')
    timer=('[Unit]\nDescription=Prepare native geometry before the existing forecast warm slot\n\n[Timer]\n'
        'OnCalendar=*-*-* *:03/5:05 UTC\nAccuracySec=1s\nRandomizedDelaySec=0\nPersistent=false\n'
        'Unit=thermal-native-geometry-prepare.service\n\n[Install]\nWantedBy=timers.target\n')
    score=('[Service]\n'+environment+'ExecStart=\nExecStart=/usr/bin/python3 '+str(scripts/'household_forecast_score.py')+
        ' --config '+str(config)+' --stage '+str(stage)+'\n')
    score_timer=('[Timer]\nOnCalendar=\nOnCalendar=*-*-* *:01/5:00 UTC\nOnCalendar=*-*-* *:02/5:00 UTC\n')
    files={'forecast.conf':deploy._bytes(stage/'service.conf',private=True),
        'score.conf':score.encode(),'score-timer.conf':score_timer.encode(),
        'thermal-native-geometry-prepare.service':service.encode(),'thermal-native-geometry-prepare.timer':timer.encode()}
    return files


def _metadata(stage,libraries,original,actual,record,files):
    import household_cycle_deploy as deploy
    return dict(schema='earthship-native-thermal-service-family/v1',stage=str(stage),
        deployment_sha256=sha256(deploy._bytes(stage/'deployment.json',private=True)).hexdigest(),
        libraries_path=str(libraries),libraries_sha256=sha256(original).hexdigest(),native_library_runtime=actual,
        artifact_sha256=record['artifact_sha256'],runtime_sha256=record['runtime_sha256'],
        file_sha256={name:sha256(raw).hexdigest() for name,raw in files.items()},
        original_forecast_warm_clock='*-*-* *:04/5:45 UTC',score_service_timeout_seconds=60,
        schedule=dict(score_offsets_seconds=[60,120],preparer_offset_seconds=185,preparer_timeout_seconds=90,
            forecast_warm_offset_seconds=285,issue_offset_seconds=315),
        live_units_changed=False,automatic_actuation=False)


def verify(output,*,guard):
    """Reconstruct the draft from pinned originals, rather than trusting its hashes."""
    import household_cycle_deploy as deploy
    from household_native_geometry_prepare import _library_paths
    from astro_geometry_worker import runtime_identity
    output=deploy._directory(output);guard()
    raw=deploy._bytes(output/'family.json',private=True);family=json.loads(raw)
    stage=deploy._path(family['stage']);libraries=deploy._path(family['libraries_path'])
    record=deploy.verify_stage(stage)
    if record['schema']!='earthship-household-cycle-deployment/v2':
        raise ValueError('explicit native deployment stage required')
    original=deploy._bytes(libraries,private=True);paths=_library_paths(original)
    cycle=json.loads(deploy._bytes(stage/'cycle.json',private=True));config=deploy._path(cycle['forecast_config'])
    settings=json.loads(deploy._bytes(config,private=True))
    if settings['artifact_sha256']!=record['artifact_sha256'] or settings['runtime_sha256']!=record['runtime_sha256']:
        raise ValueError('native family model selection differs')
    geometry=json.loads(deploy._bytes(record['native_originals']['geometry']['path'],private=True,maximum=4*1024*1024))
    actual=runtime_identity(paths,binding_version=geometry['native_runtime']['binding_version'],guard=guard)
    if actual!=geometry['native_runtime']:raise ValueError('native family libraries differ from fitted geometry')
    files=_render(stage,config,libraries)
    expected=_metadata(stage,libraries,original,actual,record,files)
    if family!=expected or {path.name for path in output.iterdir()}!=set(files)|{'family.json'}:
        raise ValueError('native family metadata or membership differs')
    if any(deploy._bytes(output/name,private=True)!=content for name,content in files.items()):
        raise ValueError('native family service contract differs')
    guard()
    if (deploy._bytes(output/'family.json',private=True)!=raw or
        deploy._bytes(libraries,private=True)!=original or deploy.verify_stage(stage)!=record or
        any(deploy._bytes(output/name,private=True)!=content for name,content in files.items())):
        raise ValueError('native family originals changed during verification')
    return family
