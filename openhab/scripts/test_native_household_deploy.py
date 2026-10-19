"""Native package metadata/source checks; numerical qualification is separate."""
import thermal_model.native_operational_io as native_io
import json,subprocess
from pathlib import Path
from hashlib import sha256
import pytest
from test_household_cycle_deploy import api,fixture,write,encode


def native_fixture(tmp_path):
    from native_thermal_artifact import REQUIRED_SOURCES,OPTIONAL_SOURCES,digest
    args,files=fixture(tmp_path);repo=args['repo_root'];baseline=args['forecast_config']
    for name in REQUIRED_SOURCES|OPTIONAL_SOURCES|{'openhab/scripts/thermal_intel.py','openhab/scripts/thermal_model/origin_capture.py'}:
        raw=b'// native package fixture\n' if name.endswith('.java') else b'# native package fixture\n'
        files[name]=raw;write(repo/name,raw,0o644)
    subprocess.run(['git','-C',str(repo),'add','.'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','native fixture'],check=True,capture_output=True)
    args['code_revision']=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    original=json.loads(Path(json.loads(baseline.read_bytes())['candidate_path']).read_bytes())
    protected={**original['runtime']['source_manifest'],**{name.removeprefix('openhab/scripts/'):sha256(files[name]).hexdigest()
        for name in ('openhab/scripts/thermal_intel.py','openhab/scripts/thermal_model/origin_capture.py')}}
    base=dict(schema='earthship-thermal-runtime-binding/v1',code_revision='a'*64,
        observer_revision=protected['thermal_model/origin_capture.py'],interpreter_sha256='b'*64,
        python_version='3.12.3',dependencies={'numpy':'1.26.4','scipy':'1.11.4','psycopg2':'2.9.9'},source_manifest=protected)
    write(Path(json.loads(baseline.read_bytes())['candidate_path']),encode({'runtime':base}))
    manifest={name:sha256(files[name]).hexdigest() for name in REQUIRED_SOURCES|OPTIONAL_SOURCES}
    runtime=dict(schema='earthship-native-thermal-runtime-binding/v1',base_runtime=base,native_source_manifest=manifest,native_code_revision=digest(manifest))
    refs={}
    for role in ('snapshot','dataset','geometry','fit_evidence'):
        path=baseline.parent/(role+'.json');write(path,encode({'fixture_role':role}))
        refs[role]={'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}
    candidate=dict(schema='earthship-provisional-thermal-candidate/v2',created_at='2026-10-13T14:00:00+00:00',runtime=runtime,
        runtime_sha256=digest(runtime),originals=refs,fit={})
    candidate['artifact_sha256']=digest(candidate,'artifact_sha256')
    model=baseline.parent/'native-model.json';write(model,encode(candidate))
    sources={key:str(baseline.parent/(key+'.txt')) for key in ('token_file','journal_dsn_file','forecast_dsn_file','native_db_config','native_policy','shared_lock')}
    for path in sources.values():write(Path(path),b'synthetic noncredential input')
    evidence=baseline.parent/'old-evidence';evidence.mkdir(mode=0o700)
    old=dict(schema='earthship-provisional-thermal-live-config/v1',candidate_path=json.loads(baseline.read_bytes())['candidate_path'],
        openhab_base='http://127.0.0.1:8080/rest',evidence_directory=str(evidence),native_cutover='2026-09-23T00:00:00+00:00',**sources)
    write(baseline,encode(old))
    geom=baseline.parent/'native-geometry';geom.mkdir(mode=0o700)
    origins=baseline.parent/'native-origins';origins.mkdir(mode=0o700)
    settings={**old,'schema':'earthship-weathernext-thermal-live-config/v1','candidate_path':str(model),
        'artifact_sha256':candidate['artifact_sha256'],'runtime_sha256':candidate['runtime_sha256'],
        'geometry_directory':str(geom),'evidence_directory':str(origins)}
    config=baseline.parent/'native-config.json';write(config,encode(settings))
    args.update(forecast_config=config,service_forecast_config=baseline)
    from test_google_native_selection import irradiance_package_candidate,source,GOOGLE_LIVE
    from weather_learning.archive import Archive
    settings.pop('forecast_dsn_file')
    settings.update(schema=GOOGLE_LIVE,weather_source=source(Archive(tmp_path/'google').root))
    # Package-only metadata; numerical qualification uses fresh_candidate.
    candidate=irradiance_package_candidate(args,settings)
    for name in set(candidate['runtime']['native_source_manifest'])|{'openhab/scripts/'+p for p in candidate['runtime']['base_runtime']['source_manifest']}:
        files[name]=(repo/name).read_bytes()
    write(config,encode(settings))
    return args,files,candidate,settings


def test_native_stage_seals_base_native_sources_and_retained_originals(tmp_path):
    args,files,candidate,settings=native_fixture(tmp_path);before=args['service_file'].read_bytes()
    result=api().stage_deployment(**args);record=api().verify_stage(args['stage'])
    assert result['status']=='deployment_staged'
    assert record['schema']=='earthship-household-cycle-deployment/v2'
    assert record['protected_runtime_sources']==candidate['runtime']['base_runtime']['source_manifest']
    assert record['native_runtime_sources']==candidate['runtime']['native_source_manifest']
    assert record['native_originals']==candidate['originals']
    assert record['artifact_sha256']==settings['artifact_sha256'] and record['runtime_sha256']==settings['runtime_sha256']
    assert args['service_file'].read_bytes()==before
    assert json.loads((args['stage']/'cycle.json').read_bytes())['forecast_config']==str(args['forecast_config'])


@pytest.mark.parametrize('field',['artifact_sha256','runtime_sha256','token_file','shared_lock','openhab_base'])
def test_native_model_switch_refuses_wrong_pins_or_changed_original_sources(tmp_path,field):
    args,files,candidate,settings=native_fixture(tmp_path)
    settings[field]='f'*64 if field.endswith('_sha256') else '/changed' if field!='openhab_base' else 'http://unapproved/rest'
    write(args['forecast_config'],encode(settings))
    with pytest.raises(ValueError):api().stage_deployment(**args)
    assert not args['stage'].exists()


@pytest.mark.parametrize('damage',['native_source','native_manifest','original','base_source'])
def test_native_stage_refuses_resealed_incomplete_source_closure(tmp_path,damage):
    args,files,candidate,settings=native_fixture(tmp_path)
    if damage=='original':Path(candidate['originals']['dataset']['path']).write_bytes(b'changed')
    else:
        from native_thermal_artifact import digest
        runtime=candidate['runtime']
        if damage=='native_source':runtime['native_source_manifest']['openhab/scripts/native_thermal_live.py']='f'*64
        elif damage=='native_manifest':runtime['native_source_manifest'].pop('scripts/java/NativeSolarGeometry.java')
        else:runtime['base_runtime']['source_manifest']['provisional_thermal.py']='f'*64
        runtime['native_code_revision']=digest(runtime['native_source_manifest']);candidate['runtime_sha256']=digest(runtime)
        candidate['artifact_sha256']=digest(candidate,'artifact_sha256')
        settings.update(artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'])
        write(Path(settings['candidate_path']),encode(candidate));write(args['forecast_config'],encode(settings))
    with pytest.raises(ValueError):api().stage_deployment(**args)
    assert not args['stage'].exists()


def test_native_stage_rechecks_originals_after_packaging(tmp_path):
    args,files,candidate,settings=native_fixture(tmp_path);api().stage_deployment(**args)
    Path(candidate['originals']['geometry']['path']).unlink()
    with pytest.raises((OSError,ValueError)):api().verify_stage(args['stage'])


def test_native_config_cannot_select_a_legacy_candidate(tmp_path):
    args,files,candidate,settings=native_fixture(tmp_path)
    old=json.loads(args['service_forecast_config'].read_bytes());settings['candidate_path']=old['candidate_path']
    write(args['forecast_config'],encode(settings))
    with pytest.raises(ValueError):api().stage_deployment(**args)
    assert not args['stage'].exists()


def test_native_runtime_probe_uses_external_pins_and_original_pressure_guard(tmp_path,monkeypatch):
    args,files,candidate,settings=native_fixture(tmp_path);api().stage_deployment(**args)
    import native_thermal_live as native
    import native_thermal_artifact as artifact
    import thermal_model.provisional_live as legacy
    import native_inference_pressure as pressure
    import thermal_model.serial_publication_caps as installed
    import household_cycle_sources as collection
    from datetime import timedelta
    calls=[];m=api();stage=args['stage']
    monkeypatch.setattr(m,'__file__',str(stage/'sources/openhab/scripts/household_cycle_deploy.py'))
    monkeypatch.setattr(installed,'_resource_preflight',lambda:None)
    monkeypatch.setattr(native_io,'_next_issue',lambda now:now+timedelta(minutes=5))
    monkeypatch.setattr(legacy,'load_settings',lambda *a,**kw:pytest.fail('native runtime probe used legacy loader'))
    monkeypatch.setattr(legacy,'current_runtime',lambda *a,**kw:pytest.fail('native runtime probe used legacy runtime'))
    monkeypatch.setattr(native,'load_settings',lambda path:settings if Path(path)==args['forecast_config'] else pytest.fail('wrong native config'))
    class Headroom:
        def __init__(self,**kw):assert not kw
        def preflight(self):calls.append('preflight')
        def check(self):calls.append('pressure')
    monkeypatch.setattr(pressure,'NativeInferenceHeadroom',Headroom)
    def runtime(*,guard):guard();calls.append('runtime');return candidate['runtime']
    def read(path,*,assessed_at,runtime,expected_artifact_sha256,guard):
        assert path==settings['candidate_path'] and runtime==candidate['runtime']
        assert expected_artifact_sha256==settings['artifact_sha256'];guard();calls.append('native_reader');return candidate
    monkeypatch.setattr(artifact,'current_native_runtime',runtime);monkeypatch.setattr(artifact,'read_native_candidate',read)
    class Collector:
        def __init__(self,**kw):assert kw['code_revision']==args['code_revision'];calls.append('collector')
        def verify_unchanged(self):calls.append('collector_verified')
    monkeypatch.setattr(collection,'CycleSourceCollector',Collector)
    result=m.verify_runtime(stage)
    assert result['status']=='runtime_verified' and result['automatic_actuation'] is False
    assert 'preflight' in calls and 'pressure' in calls and calls.count('native_reader')==1
