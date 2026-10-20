from datetime import datetime,timedelta,timezone
from copy import deepcopy
import pytest
from weather_learning.contracts import identity
from household.codec import canonical

ISSUE=datetime(2026,10,20,18,5,15,tzinfo=timezone.utc)


def model(kind,features,intercept):
    names=sorted(features)
    value=dict(schema='earthship-site-calibration/v1',rule='standardized_ridge_residual_v1',kind=kind,feature_names=names,centers=[0.]*len(names),scales=[1.]*len(names),coefficients=[0.]*len(names),intercept=intercept,
        correction_limit=6. if kind=='outdoor_temperature_c' else 600.,ridge=1.,cutoff=(ISSUE-timedelta(days=1)).isoformat(),trained_at=(ISSUE-timedelta(hours=3)).isoformat(),training_start=(ISSUE-timedelta(days=3)).isoformat(),training_end=(ISSUE-timedelta(days=2)).isoformat(),
        sample_count=1,origin_days=1,timezone='America/Denver',training_pair_sha256s=['a'*64],forecast_sha256s=['b'*64],training_data_sha256='c'*64,automatic_actuation=False)
    value['model_sha256']=identity(value);return value


def context(models_out=None):
    from household.thermal_weather_conditioning import capsule
    from weather_learning.irradiance_learning import irradiance_features
    from weather_learning.historical_serving import temperature_features
    from types import SimpleNamespace
    hour=ISSUE.replace(minute=0,second=0);end=hour+timedelta(hours=1)
    outside=model('outdoor_temperature_c',temperature_features(SimpleNamespace(target_at=end,mean_c=11.),origin=ISSUE,origin_bias_c=2.,timezone_name='America/Denver'),2.)
    solar=model('irradiance_w_m2',irradiance_features(500.,lead_hours=1,target=end,position=dict(elevation_degrees=30.,azimuth_degrees=165.,horizon_elevation_degrees=0.)),-100.)
    if models_out is not None:models_out.update({m['kind']:m for m in (outside,solar)})
    admission=dict(schema='earthship-thermal-weather-admission/v1',admitted_at=(ISSUE-timedelta(hours=1)).isoformat(),expires_at=(ISSUE+timedelta(days=13)).isoformat(),
        models={m['kind']:capsule(m) for m in (outside,solar)},source_sensor_epoch='fixture-outdoor-epoch',horizon_profile=[dict(azimuth_degrees=i*7.5,elevation_degrees=0.) for i in range(48)],
        originals=[],runtime_manifest={'helper':'a'*64},source_experiments={'comparison':'b'*64},physical_calibration_qualified=False,automatic_actuation=False)
    admission['admission_sha256']=identity(admission)
    rows=[dict(at=hour.isoformat(),tempF=50.,radiationWm2=0.,windMph=1.,weatherCode=None),dict(at=end.isoformat(),tempF=51.8,radiationWm2=500.,windMph=1.,weatherCode=None)]
    value=dict(schema='earthship-thermal-weather-context/v1',issue=ISSUE.isoformat(),prepared_at=(ISSUE-timedelta(seconds=2)).isoformat(),admission=admission,admission_ref={},
        selection={},forecast_sha256='d'*64,rows=rows,midpoint_positions=[dict(at=(end-timedelta(minutes=30)).isoformat(),elevation_degrees=30.,azimuth_degrees=165.)],geometry_refs=[],native_runtime={},site=dict(latitude=38.3739919,longitude=-105.7744609),timezone='America/Denver',automatic_actuation=False)
    value['context_sha256']=identity(value);return value


def test_partial_hour_conditioning_preserves_raw_inputs_and_actions():
    from household.thermal_weather_conditioning import apply_conditioning
    from thermal_model.installed_shade_dynamics import InstalledShadeForcing
    proof=context();original=deepcopy(proof);at=ISSUE+timedelta(minutes=5)
    raw=InstalledShadeForcing(at,50.3075,500.,.25,0.,1.)
    result=apply_conditioning((raw,),proof,issue=ISSUE,available=ISSUE-timedelta(seconds=1),initial_outdoor_f=53.6)
    assert proof==original and raw.outdoor_f==50.3075 and raw.radiation_wm2==500.
    assert result[0].outdoor_f==pytest.approx(53.76438356164384)
    assert result[0].radiation_wm2==400.
    assert (result[0].indoor_shade_closed,result[0].outdoor_shade_present,result[0].vent_open)==(.25,0.,1.)


@pytest.mark.parametrize('damage',['late_model','late_context','hash','raw_temperature'])
def test_conditioning_rejects_noncausal_or_changed_original_context(damage):
    from household.thermal_weather_conditioning import apply_conditioning
    from thermal_model.installed_shade_dynamics import InstalledShadeForcing
    proof=context();raw=InstalledShadeForcing(ISSUE+timedelta(minutes=5),50.3075,500.,1.,0.,0.)
    if damage=='late_model':
        m=proof['admission']['models']['outdoor_temperature_c'];m['trained_at']=(ISSUE+timedelta(seconds=1)).isoformat();m['capsule_sha256']=identity({k:v for k,v in m.items() if k!='capsule_sha256'});proof['admission']['admission_sha256']=identity({k:v for k,v in proof['admission'].items() if k!='admission_sha256'})
    elif damage=='late_context':proof['prepared_at']=(ISSUE+timedelta(seconds=1)).isoformat()
    elif damage=='hash':proof['rows'][1]['radiationWm2']=501.
    else:raw=InstalledShadeForcing(raw.at,60.,500.,1.,0.,0.)
    if damage!='hash':proof['context_sha256']=identity({k:v for k,v in proof.items() if k!='context_sha256'})
    with pytest.raises(ValueError):apply_conditioning((raw,),proof,issue=ISSUE,available=ISSUE-timedelta(seconds=1),initial_outdoor_f=53.6)


def bound_fixture(tmp_path,monkeypatch,*,forecast=None,geometry=None,sensor_epoch=None):
    # Synthetic geometry is isolated from kernel admission; real guards have their own suite.
    monkeypatch.setattr("household_cycle_resources.publication_resource_preflight",lambda:None)
    from household_native_training import directory,save
    from thermal_weather_source import conditioning_runtime
    from daily_pv_worker import day_geometry
    from astro_geometry import build_cache
    from weather_learning.config import Site
    from test_native_thermal_forecast import future
    from test_native_thermal_inputs import RUNTIME
    from hashlib import sha256
    root=directory(tmp_path);models={};proof=context(models);admission=proof['admission'];admission['runtime_manifest']=conditioning_runtime()
    if sensor_epoch is not None:admission['source_sensor_epoch']=sensor_epoch
    if forecast is None:forecast={'rows':proof['rows']}
    for kind,value in models.items():
        path=root/(kind+'.json');save(path,value);admission['originals'].append(dict(path=str(path),sha256=sha256(path.read_bytes()).hexdigest(),maximum=4194304,source=False))
    admission.pop('admission_sha256');admission['admission_sha256']=identity(admission);path=root/'admission.json';save(path,admission)
    selection=dict(schema='earthship-thermal-weather-selection/v1',admission_path=str(path),admission_file_sha256=sha256(path.read_bytes()).hexdigest(),available_at=(ISSUE-timedelta(minutes=30)).isoformat(),automatic_actuation=False);selection['selection_sha256']=identity(selection);selected=root/'selection.json';save(selected,selection)
    cache=directory(root/'geometry');site=Site(38.3739919,-105.7744609,'America/Denver')
    def capture(request,source,**kw):return build_cache(request,source,native_output=''.join(at+'\t30.0\t165.0\n' for at in request['instants']).encode(),computed_at=ISSUE-timedelta(minutes=10))
    from zoneinfo import ZoneInfo
    days=sorted({(datetime.fromisoformat(row['at'])-timedelta(minutes=30)).astimezone(ZoneInfo(site.timezone)).date().isoformat() for row in forecast['rows'] if datetime.fromisoformat(row['at'])>ISSUE})
    for day in days:day_geometry(cache,day,site=site,native_runtime=RUNTIME,libraries={},guard=lambda:None,clock=lambda:ISSUE-timedelta(minutes=10),capture=capture)
    # One-hour source fixture requires one midpoint; full production uses 24 h.
    return dict(selection=selected,geometry_root=cache,forecast=forecast,geometry=future(ISSUE,hours=1) if geometry is None else geometry,issue=ISSUE,sensor_epoch=admission['source_sensor_epoch'],clock=lambda:ISSUE-timedelta(seconds=2),guard=lambda:None),models


def test_bound_context_uses_existing_native_cache_and_detects_changed_model(tmp_path,monkeypatch):
    from thermal_weather_source import collect_context,verify_bindings
    args,models=bound_fixture(tmp_path,monkeypatch);proof=collect_context(**args)
    assert proof['midpoint_positions'][0]['azimuth_degrees']==165.
    assert proof['prepared_at']==(ISSUE-timedelta(seconds=2)).isoformat()
    verify_bindings(proof,guard=lambda:None)
    path=tmp_path/'outdoor_temperature_c.json';path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='source'):verify_bindings(proof,guard=lambda:None)


def test_missing_or_late_cached_geometry_never_starts_native_acquisition(tmp_path,monkeypatch):
    from thermal_weather_source import collect_context
    import astro_geometry_worker
    args,_=bound_fixture(tmp_path,monkeypatch)
    def unexpected(*a,**kw):raise AssertionError('cold geometry acquisition in serving')
    monkeypatch.setattr(astro_geometry_worker,'capture_batch',unexpected)
    for p in args['geometry_root'].glob('*.geometry.json'):p.unlink()
    with pytest.raises(FileNotFoundError):collect_context(**args)


from test_native_thermal_artifact import originals


def test_native_conditioned_capture_replays_and_keeps_original_google_rows(tmp_path,monkeypatch,originals):
    import sys
    import native_thermal_forecast as api
    from thermal_weather_source import collect_context
    from test_native_thermal_forecast import context as native_context,ISSUE as native_issue
    c,inputs,kwargs=native_context(tmp_path,monkeypatch,originals);before=deepcopy(inputs)
    raw=api.build_capture(c,inputs,**kwargs)
    monkeypatch.setattr(sys.modules[__name__],'ISSUE',native_issue)
    args,_=bound_fixture(tmp_path/'weather',monkeypatch,forecast=inputs['forecast'],geometry=kwargs['geometry'],sensor_epoch=c['fit']['sensor_epochs']['outdoor'])
    proof=collect_context(**args)
    value=api.build_capture(c,inputs,weather_conditioning=proof,**kwargs)
    assert value['schema']=='earthship-provisional-thermal-origin/v3'
    assert inputs==before and value['inputs']['forecast']==raw['inputs']['forecast']
    assert value['output']['trajectory']!=raw['output']['trajectory']
    assert value['output']['automatic_actuation'] is False
    replay=api.validate_capture(value,runtime=kwargs['runtime'],expected_artifact_sha256=kwargs['expected_artifact_sha256'],expected_capture_sha256=value['capture_sha256'])
    assert replay==value


def test_conditioned_native_context_freezes_only_thermal_correction(tmp_path,monkeypatch,originals):
    import sys
    import native_thermal_forecast as native
    import native_thermal_artifact
    from thermal_weather_source import collect_context
    from test_native_thermal_forecast import context as native_context,ISSUE as native_issue
    from household.weather_context import prepare_native_cycle_contexts,project_weather,PreparedWeatherContext
    from household.thermal_model import project,PreparedProjection
    c,inputs,kwargs=native_context(tmp_path,monkeypatch,originals)
    monkeypatch.setattr(sys.modules[__name__],'ISSUE',native_issue)
    args,_=bound_fixture(tmp_path/'weather',monkeypatch,forecast=inputs['forecast'],geometry=kwargs['geometry'],sensor_epoch=c['fit']['sensor_epochs']['outdoor'])
    proof=collect_context(**args)
    capture=native.build_capture(c,inputs,weather_conditioning=proof,**kwargs)
    monkeypatch.setattr(native_thermal_artifact,'current_native_runtime',lambda **kw:deepcopy(kwargs['runtime']))
    thermal,weather=prepare_native_cycle_contexts(capture,code_revision='a'*40,runtime=kwargs['runtime'],expected_artifact_sha256=c['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])
    frozen=thermal.to_dict();out=project_weather(weather)
    assert frozen['schema']=='earthship-household-prepared-thermal/v3'
    assert frozen['weather_conditioning']==proof
    assert frozen['inputs_available_at']==capture['inputs_available_at']
    assert out['forcings']==frozen['forcings']
    assert weather.original_capture['inputs']['forecast']==inputs['forecast']
    assert project(thermal)['output']==capture['output']
    from household_pipeline import thermal_execution_runtime
    from pathlib import Path
    assert thermal_execution_runtime(Path(__file__).resolve().parent,frozen)==frozen['executing_runtime']
    import builtins,os
    from pathlib import Path
    def forbidden(*a,**kw):pytest.fail('I/O inside conditioned frozen projection')
    for target,name in ((builtins,'open'),(os,'open'),(Path,'read_bytes')):monkeypatch.setattr(target,name,forbidden)
    assert project(PreparedProjection(canonical(frozen)))['output']==capture['output']
    assert project_weather(PreparedWeatherContext(canonical(weather.to_dict())))==out


def test_conditioned_capture_requires_actual_proof(tmp_path,monkeypatch,originals):
    import native_thermal_forecast as native
    from test_native_thermal_forecast import context as native_context
    c,inputs,kwargs=native_context(tmp_path,monkeypatch,originals)
    capture=native.build_capture(c,inputs,**kwargs)
    capture.update(schema=native.CONDITIONED_CAPTURE_SCHEMA,weather_conditioning=None)
    capture['capture_sha256']=native.digest(capture,'capture_sha256')
    with pytest.raises(ValueError):native.validate_capture(capture,runtime=kwargs['runtime'],expected_artifact_sha256=c['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])


def test_conditioning_runtime_binds_new_target_weight_dependency(tmp_path,monkeypatch):
    import thermal_weather_source as source
    from hashlib import sha256
    from pathlib import Path
    before=source.conditioning_runtime()
    relative='weather_learning/weights.py'
    assert before.get(relative)==sha256((Path(source.__file__).parent/relative).read_bytes()).hexdigest()
    for name in source.RUNTIME_SOURCES:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((Path(source.__file__).parent/name).read_bytes())
    changed=tmp_path/relative;changed.write_bytes(changed.read_bytes()+b'\n# changed numerical support contract\n')
    monkeypatch.setattr(source,'SCRIPTS',tmp_path)
    after=source.conditioning_runtime()
    assert before!=after
    assert before.keys()==after.keys()
    assert {name for name in before if before[name]!=after[name]}=={relative}
