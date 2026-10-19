"""Google selection reaches native collection and preserves owned serving gates."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import pytest
from weather_learning.archive import Archive
from weather_learning.tests.learning_fixtures import full_snapshot,SITE
from test_native_thermal_forecast import originals,ISSUE

GOOGLE_LIVE='earthship-weathernext-thermal-live-config/v1'
GOOGLE_SERVING='earthship-weathernext-thermal-live-config/v2'


def source(root):
    return dict(schema='earthship-weathernext-native-source/v1',archive_directory=str(root),
        site=dict(latitude=SITE.latitude,longitude=SITE.longitude,timezone=SITE.timezone))


def irradiance_package_candidate(args,settings):
    """Package-only metadata fixture; never a numerical/model qualification."""
    import subprocess
    from hashlib import sha256
    import native_thermal_artifact as artifacts
    repo=args['repo_root']
    from thermal_model.native_operational_io import RUNTIME_PATHS
    # Exercise the complete expanded production inventory, not a tiny fake base.
    for name in sorted(RUNTIME_PATHS):
        path=repo/'openhab/scripts'/name
        if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'# source inventory fixture\n');path.chmod(0o644)
    for name in sorted(artifacts.JOINT_SOURCES|artifacts.IRRADIANCE_SOURCES):
        path=repo/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'{}\n' if name.endswith('.json') else b'# package-only source fixture\n');path.chmod(0o644)
    subprocess.run(['git','-C',str(repo),'add','.'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','preserved family fixture'],check=True,capture_output=True)
    args['code_revision']=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    path=Path(settings['candidate_path']);candidate=json.loads(path.read_bytes())
    candidate['schema']=artifacts.IRRADIANCE_SCHEMA
    runtime=candidate['runtime']
    runtime['base_runtime']['source_manifest']={name:sha256((repo/'openhab/scripts'/name).read_bytes()).hexdigest() for name in RUNTIME_PATHS}
    runtime['base_runtime']['observer_revision']=runtime['base_runtime']['source_manifest']['thermal_model/origin_capture.py']
    runtime['native_source_manifest'].update({name:sha256((repo/name).read_bytes()).hexdigest() for name in artifacts.JOINT_SOURCES|artifacts.IRRADIANCE_SOURCES})
    runtime['native_code_revision']=artifacts.digest(runtime['native_source_manifest'])
    candidate['runtime_sha256']=artifacts.digest(runtime);candidate['artifact_sha256']=artifacts.digest(candidate,'artifact_sha256')
    path.write_text(json.dumps(candidate))
    settings.update(artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'])
    return candidate


@pytest.mark.parametrize('schema',[GOOGLE_LIVE,GOOGLE_SERVING])
def test_closed_google_settings_replace_old_forecast_credential(tmp_path,monkeypatch,originals,schema):
    from test_native_future_geometry import settings_file
    from test_native_thermal_live_publication import fixture
    live,settings,*_=fixture(tmp_path,monkeypatch,originals)
    path,settings=settings_file(tmp_path,settings)
    archive=Archive(tmp_path/'google')
    settings.update(schema=schema,weather_source=source(archive.root))
    if schema==GOOGLE_SERVING:
        receipt=tmp_path/'receipt';receipt.write_text('{}');receipt.chmod(0o600)
        settings.update(model_receipt_path=str(receipt),model_receipt_sha256='a'*64)
    path.write_text(json.dumps(settings))
    assert live.load_settings(path)==settings
    for change in ('old_credential','extra_source','site','archive_alias','source_schema'):
        damaged=deepcopy(settings)
        if change=='old_credential':damaged['forecast_dsn_file']=str(tmp_path/'absent-old-secret')
        elif change=='extra_source':damaged['weather_source']['fallback']='openmeteo'
        elif change=='site':damaged['weather_source']['site']['latitude']=float('nan')
        elif change=='source_schema':damaged['weather_source']['schema']='unknown'
        else:
            link=tmp_path/'alias';link.symlink_to(archive.root,target_is_directory=True)
            damaged['weather_source']['archive_directory']=str(link)
        path.write_text(json.dumps(damaged))
        with pytest.raises((ValueError,OSError)):live.load_settings(path)
    path.write_text(json.dumps(settings));Path(settings['candidate_path']).unlink()
    Path(settings['geometry_directory']).rmdir()
    (archive.root/'index.sqlite3').unlink();(archive.root/'objects').rmdir();archive.root.rmdir()
    assert live.load_settings(path,withdraw=True)==settings
    with pytest.raises((ValueError,OSError)):live.load_settings(path)


def test_readonly_archive_does_not_create_or_modify_collector_state(tmp_path):
    archive=Archive(tmp_path/'google');name=archive.store_snapshot(full_snapshot())
    before={p.name:(p.read_bytes(),p.stat().st_mtime_ns,p.stat().st_mode) for p in archive.root.iterdir() if p.is_file()}
    reader=Archive.open_readonly(archive.root)
    assert reader.read(name)['snapshot_sha256']==name
    selected=reader.eligible_snapshot(ISSUE,ISSUE+timedelta(hours=24),required_variables={'station_head_temperature_2m'})
    # This fixture's retained run need not cover ISSUE; read-only selection still executes.
    assert selected is None or selected['provider']=='weathernext3'
    with pytest.raises(ValueError,match='read.only'):reader.store_snapshot(full_snapshot())
    with reader._connect() as db:
        with pytest.raises(sqlite3.OperationalError):db.execute('DELETE FROM snapshots')
    assert before=={p.name:(p.read_bytes(),p.stat().st_mtime_ns,p.stat().st_mode) for p in archive.root.iterdir() if p.is_file()}
    missing=tmp_path/'not-created'
    with pytest.raises((ValueError,OSError)):Archive.open_readonly(missing)
    assert not missing.exists()


def test_configured_backend_and_lazy_household_backend_use_google_only(tmp_path,monkeypatch):
    import thermal_temperature_runtime
    import native_thermal_live as live
    import household_cycle
    from thermal_model.installed_shade_live_inputs import SOURCE_PATHS
    from test_thermal_sensor_epoch_history import EPOCHS
    from uuid import uuid4
    monkeypatch.setattr(thermal_temperature_runtime,'_configured_sensor_epochs',lambda env:deepcopy(EPOCHS))
    settings=dict(schema=GOOGLE_LIVE)
    for key in SOURCE_PATHS-{'forecast_dsn_file','release_inputs_path'}:
        path=tmp_path/key
        path.write_text('host=127.0.0.1 dbname=openhab user=fixture_reader password='+uuid4().hex if key=='journal_dsn_file' else uuid4().hex)
        path.chmod(0o600);settings[key]=str(path)
    candidate=tmp_path/'candidate';candidate.write_text('{}');candidate.chmod(0o600)
    settings.update(candidate_path=str(candidate),openhab_base='http://127.0.0.1:8080/rest',evidence_directory=str(tmp_path))
    archive=Archive(tmp_path/'google');archive.store_snapshot(full_snapshot())
    settings['weather_source']=source(archive.root)
    monkeypatch.setattr(live,'CompressedSourceLiveBackend',lambda *a,**kw:pytest.fail('incumbent backend selected'),raising=False)
    backend=live.make_forecast_backend(settings,evidence_directory=tmp_path,guard=lambda:None)
    backend.verify_unchanged()
    assert not hasattr(backend,'forecast_dsn') and 'forecast_dsn_file' not in backend.settings
    origin=__import__('weather_learning.tests.learning_fixtures',fromlist=['T']).T+timedelta(hours=8,minutes=15)
    assert backend.forecast_reader(issue=origin,available_by=origin-timedelta(seconds=30),horizon_hours=24)['source']=='weathernext3'
    calls=[]
    monkeypatch.setattr(backend,'collect',lambda **kw:calls.append(kw) or {'selected':'google'})
    monkeypatch.setattr(live,'make_forecast_backend',lambda s,**kw:backend)
    lazy=household_cycle.LazyForecastBackend(settings,guard=lambda:None)
    assert lazy.collect(issue=origin,known_at=origin-timedelta(seconds=30))=={'selected':'google'}
    assert len(calls)==1
    with pytest.raises(ValueError):lazy.collect(issue=origin,known_at=origin)


@pytest.mark.parametrize('schema',[GOOGLE_LIVE,GOOGLE_SERVING])
def test_google_driver_selects_native_mode_and_keeps_receipt_stage_requirement(tmp_path,monkeypatch,schema):
    from test_household_native_cycle_driver import native_setup
    cycle,native,config,calls=native_setup(tmp_path,monkeypatch)
    forecast=Path(json.loads(config.read_bytes())['forecast_config']);forecast.write_text(json.dumps({'schema':schema}))
    settings=dict(schema=schema,shared_lock=str(tmp_path/'lock'),token_file=str(tmp_path/'token'),
        openhab_base='http://127.0.0.1:8080/rest',artifact_sha256='a'*64,runtime_sha256='c'*64)
    monkeypatch.setattr(native,'load_settings',lambda *a,**kw:settings)
    monkeypatch.setattr(native,'publish_cycle',lambda *a,**kw:{'status':'published','delivery_verified':False})
    if schema==GOOGLE_SERVING:
        with pytest.raises(ValueError,match='external serving stage'):cycle.run_cycle(config,code_revision='e'*40)
    else:
        result=cycle.run_cycle(config,code_revision='e'*40)
        assert result['status']=='published' and 'published' not in calls


def test_google_publication_retains_original_source_and_rejects_incumbent_inputs(tmp_path,monkeypatch,originals):
    from test_native_thermal_live_publication import fixture
    from weather_learning.native_forecast import make_native_forecast
    live,settings,backend,clock,candidate,geometry,runtime=fixture(tmp_path,monkeypatch,originals)
    original_collect=backend.collect
    def collect(**kw):
        inputs=original_collect(**kw)
        snapshot=full_snapshot(ISSUE.replace(minute=0,second=0,microsecond=0)-timedelta(hours=8))
        inputs['forecast']=make_native_forecast(snapshot,origin=kw['issue'],available_by=kw['known_at'],horizon_hours=24,site=SITE)
        return inputs
    backend.collect=collect
    result=live.publish_cycle(settings,guard=lambda:None,backend=backend,geometry=geometry)
    capture=json.loads(Path(result['origin_path']).read_bytes())
    assert result['delivery_verified'] is True and capture['inputs']['forecast']['source']=='weathernext3'
    clock[0]=ISSUE-timedelta(seconds=30);backend.puts.clear()
    def retired_collect(**kw):
        from test_google_receipt_retirement import retired
        inputs=original_collect(**kw);inputs['forecast']=retired();return inputs
    backend.collect=retired_collect
    with pytest.raises(ValueError,match='Google weather'):live.publish_cycle(settings,guard=lambda:None,backend=backend,geometry=geometry)
    assert backend.puts==[]


def test_google_receipt_driver_admits_once_and_preserves_refusal(tmp_path,monkeypatch):
    from test_native_serving_driver import setup
    cycle,receipt,native,config,stage,calls,model=setup(tmp_path,monkeypatch)
    settings=native.load_settings('unused');settings['schema']=GOOGLE_SERVING
    forecast=Path(json.loads(config.read_bytes())['forecast_config']);forecast.write_text(json.dumps({'schema':GOOGLE_SERVING}))
    result=cycle.run_cycle(config,code_revision='e'*40,stage=stage,deployment_sha256='d'*64)
    assert result['status']=='published' and calls.count('admitted')==calls.count('selected')==1
    assert 'serving_observed' in calls and 'published' not in calls


def test_google_preparer_keeps_owned_receipt_admission(tmp_path,monkeypatch):
    from test_native_serving_preparer import setup
    import native_thermal_live as native
    m,receipt,config,libraries,stage,now,ticks,calls=setup(tmp_path,monkeypatch)
    settings=native.load_settings(config);settings['schema']=GOOGLE_SERVING;config.write_text(json.dumps(settings))
    assert m.run(config,libraries,stage=stage,deployment_sha256='d'*64,clock=lambda:now[0],monotonic=lambda:ticks[0])['status']=='prepared'
    assert calls.count('selected')==calls.count('admitted')==1


def test_google_native_deployment_seals_source_selection_without_old_secret(tmp_path):
    from test_native_household_deploy import native_fixture,api,write,encode
    args,files,candidate,settings=native_fixture(tmp_path)
    settings.update(schema=GOOGLE_LIVE,weather_source=source(Archive(tmp_path/'google').root))
    write(args['forecast_config'],encode(settings))
    before=args['service_file'].read_bytes()
    result=api().stage_deployment(**args)
    assert result['status']=='deployment_staged'
    record=api().verify_stage(args['stage'])
    assert record['runtime_sha256']==candidate['runtime_sha256']
    assert args['service_file'].read_bytes()==before
    assert len(record['protected_runtime_sources'])==81
    shade=args['stage']/'sources/openhab/thermal-shade-context.json'
    assert shade.is_file() and 'openhab/thermal-shade-context.json' in record['native_runtime_sources']
    shade.write_bytes(b'{"changed_after_fit":true}')
    with pytest.raises(ValueError):api().verify_stage(args['stage'])
    # Staging source bytes is not a production handoff or permission to reuse
    # these synthetic fixture weights. Runtime/model qualification is separate.


def test_google_receipt_deployment_keeps_receipt_and_dispatch_pins(tmp_path,monkeypatch):
    from test_native_serving_selection import fixture
    from test_household_cycle_deploy import write,encode
    deploy,args,settings,helper,libraries=fixture(tmp_path,monkeypatch)
    settings.update(schema=GOOGLE_SERVING,weather_source=source(Archive(tmp_path/'google').root))
    write(args['forecast_config'],encode(settings))
    from hashlib import sha256
    deploy.stage_deployment(**args)
    pin=sha256((args['stage']/'deployment.json').read_bytes()).hexdigest()
    record=deploy.verify_stage(args['stage'],expected_deployment_sha256=pin)
    assert record['schema']=='earthship-household-cycle-deployment/v3'
    assert record['model_verification']['receipt']['sha256']==settings['model_receipt_sha256']
    assert record['score_dispatch']['sha256']==args['score_dispatch_sha256']


@pytest.mark.parametrize('google',[True,False])
def test_score_coordinator_preserves_google_and_retained_old_receipt_profiles(tmp_path,monkeypatch,google):
    from test_native_serving_score_driver import fixture
    import native_thermal_live as native
    coordinator,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,1)
    settings=native.load_settings(config)
    if google:settings['schema']=GOOGLE_SERVING;config.write_text(json.dumps(settings))
    else:
        for name in ('NATIVE_SCHEMAS','SERVING_SCHEMAS','LIVE_SCHEMAS'):monkeypatch.delattr(native,name)
    def score(actual,*,guard,clock,queue,serving_model,historical_selections):
        assert actual==settings and serving_model is model and historical_selections==()
        guard();calls.append('scored');return {'status':'waiting','automatic_actuation':False}
    monkeypatch.setattr(coordinator,'score_with_report',score)
    result=coordinator.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:100)
    assert result['status']=='waiting' and calls.count('read_model')==1 and calls[-1]=='unlocked'


@pytest.mark.parametrize('google',[True,False])
def test_fresh_google_release_has_its_own_source_closure_and_retired_selection_refuses(tmp_path,google):
    from test_native_household_deploy import native_fixture,api,write,encode
    from hashlib import sha256
    args,files,candidate,settings=native_fixture(tmp_path)
    old=json.loads(args['service_forecast_config'].read_bytes())
    old_model=Path(old['candidate_path']);previous=json.loads(old_model.read_bytes())
    previous['runtime']['source_manifest']['thermal_intel.py']=sha256(b'previous committed runtime').hexdigest()
    write(old_model,encode(previous))
    if google:
        settings.update(schema=GOOGLE_LIVE,weather_source=source(Archive(tmp_path/'google').root))
        write(args['forecast_config'],encode(settings))
        assert api().stage_deployment(**args)['status']=='deployment_staged'
        record=api().verify_stage(args['stage'])
        assert record['protected_runtime_sources']==candidate['runtime']['base_runtime']['source_manifest']
    else:
        settings['schema']='earthship-provisional-thermal-live-config/v2'
        write(args['forecast_config'],encode(settings))
        with pytest.raises(ValueError,match='configuration'):api().stage_deployment(**args)
    # This verifies complete source packaging, never real fit qualification or activation.
