"""Package/command integrity only; fitted numerical qualification is separate."""
from pathlib import Path
from hashlib import sha256
import inspect,json,subprocess,shlex
import pytest
from test_native_household_deploy import native_fixture
from test_household_cycle_deploy import write,encode


def fixture(tmp_path,monkeypatch):
    import household_cycle_deploy as deploy,native_thermal_artifact as artifacts
    assert 'model_receipt_path' in inspect.signature(deploy.stage_deployment).parameters,'receipt package profile missing'
    args,files,candidate,settings=native_fixture(tmp_path);repo=args['repo_root']
    helper='openhab/scripts/native_model_serving_receipt.py';files[helper]=b'# package-only helper fixture\n';write(repo/helper,files[helper],0o644)
    helper_sha=sha256(files[helper]).hexdigest()
    for name in artifacts.OPTIONAL_SOURCES:
        files[name]+= ("SERVING_RECEIPT_SOURCE_SHA256='"+helper_sha+"'\n").encode();write(repo/name,files[name],0o644)
    for name in ('household_forecast_score.py','household_native_geometry_prepare.py'):
        path='openhab/scripts/'+name;files[path]=b'# package-only driver fixture\n';write(repo/path,files[path],0o644)
    subprocess.run(['git','-C',str(repo),'add','.'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','serving package fixture'],check=True,capture_output=True)
    args['code_revision']=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    runtime=candidate['runtime'];runtime['native_source_manifest']={name:sha256(files[name]).hexdigest() for name in artifacts.REQUIRED_SOURCES|artifacts.OPTIONAL_SOURCES}
    runtime['native_code_revision']=artifacts.digest(runtime['native_source_manifest'])
    import astro_geometry_worker as worker
    native_runtime={'binding_version':'5.2.3','libraries':{role:'a'*64 for role in worker.ROLES},'collector_sha256':'b'*64}
    geometry=Path(candidate['originals']['geometry']['path']);write(geometry,encode({'native_runtime':native_runtime}))
    candidate['originals']['geometry']['sha256']=sha256(geometry.read_bytes()).hexdigest()
    candidate['runtime_sha256']=artifacts.digest(runtime);candidate['artifact_sha256']=artifacts.digest(candidate,'artifact_sha256')
    write(Path(settings['candidate_path']),encode(candidate))
    receipt=tmp_path/'original/model-receipt.json';write(receipt,encode({'package_fixture_only':True}))
    legacy_args={k:v for k,v in args.items() if k!='service_forecast_config'}
    legacy_args.update(stage=tmp_path/'legacy',forecast_config=args['service_forecast_config'])
    deploy.stage_deployment(**legacy_args)
    dispatch=tmp_path/'original/score-dispatch.json'
    write(dispatch,encode({'schema':'earthship-native-score-dispatch/v1','current':'current','legacy':{
        'stage':str(legacy_args['stage']),'deployment_sha256':sha256((legacy_args['stage']/'deployment.json').read_bytes()).hexdigest(),
        'config':str(legacy_args['forecast_config']),'config_sha256':sha256(legacy_args['forecast_config'].read_bytes()).hexdigest()},'historical':[]}))
    settings.update(schema='earthship-provisional-thermal-live-config/v3',artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'],model_receipt_path=str(receipt),model_receipt_sha256=sha256(receipt.read_bytes()).hexdigest())
    write(args['forecast_config'],encode(settings))
    args.update(model_receipt_path=receipt,model_receipt_sha256=settings['model_receipt_sha256'],score_dispatch_path=dispatch,score_dispatch_sha256=sha256(dispatch.read_bytes()).hexdigest())
    libraries=tmp_path/'libraries.json';paths={role:str(tmp_path/(role+'.jar')) for role in worker.ROLES}
    write(libraries,encode({'schema':'earthship-native-geometry-libraries/v1','library_paths':paths}))
    monkeypatch.setattr(worker,'runtime_identity',lambda actual,**kw:native_runtime if actual=={k:Path(v) for k,v in paths.items()} else pytest.fail('wrong native library selection'))
    return deploy,args,settings,helper_sha,libraries


def stage(tmp_path,monkeypatch):
    deploy,args,settings,helper_sha,libraries=fixture(tmp_path,monkeypatch)
    deploy.stage_deployment(**args);pin=sha256((args['stage']/'deployment.json').read_bytes()).hexdigest()
    return deploy,args,settings,helper_sha,libraries,pin


def test_helper_and_receipt_in_complete_source_closure(tmp_path,monkeypatch):
    deploy,args,settings,helper_sha,libraries,pin=stage(tmp_path,monkeypatch)
    record=deploy.verify_stage(args['stage'],expected_deployment_sha256=pin)
    assert record['schema']=='earthship-household-cycle-deployment/v3'
    assert record['model_verification']['receipt']=={'path':str(args['model_receipt_path']),'sha256':args['model_receipt_sha256']}
    assert record['model_verification']['helper']=={'path':str(args['stage']/'sources/openhab/scripts/native_model_serving_receipt.py'),'sha256':helper_sha}
    assert record['source_manifest']['openhab/scripts/native_model_serving_receipt.py']==helper_sha
    assert record['score_dispatch']=={'path':str(args['score_dispatch_path']),'sha256':args['score_dispatch_sha256']}
    assert '--deployment-sha256' not in (args['stage']/'service.conf').read_text()
    assert pin not in (args['model_receipt_path'].read_text()+args['score_dispatch_path'].read_text())


@pytest.mark.parametrize('damage',['manifest','config'])
def test_resealed_stage_or_config_cannot_replace_effective_selection(tmp_path,monkeypatch,damage):
    deploy,args,settings,helper_sha,libraries,pin=stage(tmp_path,monkeypatch)
    manifest=args['stage']/'deployment.json';record=json.loads(manifest.read_bytes())
    if damage=='manifest':record['code_revision']='f'*40
    else:
        settings['model_receipt_sha256']='f'*64;write(args['forecast_config'],encode(settings))
        record['original_bindings'][str(args['forecast_config'])]=sha256(args['forecast_config'].read_bytes()).hexdigest()
        record['model_verification']['receipt']['sha256']='f'*64
    write(manifest,encode(record))
    assert sha256(manifest.read_bytes()).hexdigest()!=pin
    with pytest.raises(ValueError):deploy.verify_stage(args['stage'],expected_deployment_sha256=pin)


def test_all_three_effective_commands_pin_one_final_stage(tmp_path,monkeypatch):
    deploy,args,settings,helper_sha,libraries,pin=stage(tmp_path,monkeypatch)
    import household_native_family as family
    output=tmp_path/'family'
    family.prepare(args['stage'],libraries,output,guard=lambda:None,deployment_sha256=pin)
    record=family.verify(output,guard=lambda:None)
    commands=[]
    for name in ('forecast.conf','score.conf','thermal-native-geometry-prepare.service'):
        rows=[line[10:] for line in (output/name).read_text().splitlines() if line.startswith('ExecStart=') and line!='ExecStart=']
        assert len(rows)==1;commands.append(shlex.split(rows[0]))
    assert {parts[parts.index('--deployment-sha256')+1] for parts in commands}=={pin}
    assert all(parts[parts.index('--stage')+1]==str(args['stage']) for parts in commands)
    assert record['model_verification']['receipt']['sha256']==args['model_receipt_sha256']
    assert record['score_dispatch']['sha256']==args['score_dispatch_sha256']
    assert (output/'forecast.conf').read_bytes()!=(args['stage']/'service.conf').read_bytes()
    clocks=[line.removeprefix('OnCalendar=') for line in (output/'score-timer.conf').read_text().splitlines() if line.startswith('OnCalendar=') and line!='OnCalendar=']
    assert clocks==['*-*-* *:'+minute+'/5:10 UTC' for minute in ('00','01','02','03')]
    original=(output/'forecast.conf').read_bytes();(output/'forecast.conf').write_bytes(original.replace(pin.encode(),b'f'*64))
    with pytest.raises(ValueError):family.verify(output,guard=lambda:None)
