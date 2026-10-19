"""Preserve the installed irradiance/shade physics with fresh Google/local lineage."""
from dataclasses import replace
from datetime import timedelta
from copy import deepcopy
from pathlib import Path
import importlib,json
import numpy as np
import pytest
from test_native_thermal_model import geometry
from test_installed_shade_dynamics import AT,rows
from test_native_thermal_forecast import ISSUE,originals
from test_installed_shade_inputs import snapshot,START,END

# Independently specified, small physical gains; these are synthetic test
# coefficients, never imported installed weights or a production candidate.
COEFFICIENTS=(.002,.02,.00002,.00001,.000007,.000003,.005,.005,
              .01,.001,.00001,.000005,.000003,.000001)


def model(forcings,*,degrees=30,coefficients=COEFFICIENTS):
    module=importlib.import_module('native_irradiance_shade')
    g=geometry(forcings,degrees=degrees)
    return module.NativeIrradianceShadeDynamics(coefficients,geometry=g,expected_series_sha256=g.sha256)


def test_heat_gain_uses_actual_irradiance_without_low_sun_amplification_and_masks_native_night():
    forcing=tuple(replace(row,radiation_wm2=50,indoor_shade_closed=0,outdoor_shade_present=0) for row in rows())
    low=model(forcing,degrees=2);high=model(forcing,degrees=65);night=model(forcing,degrees=-2)
    def rollout(m):return m.rollout(origin_at=AT,air_f=70,mass_f=69,forcings=forcing)
    assert rollout(low)==rollout(high)
    dark=tuple(replace(row,radiation_wm2=0) for row in forcing)
    assert rollout(night).states==night.rollout(origin_at=AT,air_f=70,mass_f=69,forcings=dark).states
    assert rollout(low).states[-1][0]>rollout(night).states[-1][0]
    module=importlib.import_module('native_irradiance_shade')
    normalized=module.normalize_forcings(origin_at=AT,forcings=forcing,geometry=low.geometry)
    assert all(row[1:5]==(50,0,0,0) for row in normalized)


def test_four_regimes_preserve_monotone_shade_gain_and_fourteen_parameter_sensitivities():
    temperatures={}
    for indoor,outdoor in ((0,0),(1,0),(0,1),(1,1)):
        forcing=tuple(replace(row,radiation_wm2=300,indoor_shade_closed=indoor,outdoor_shade_present=outdoor) for row in rows())
        m=model(forcing);temperatures[indoor,outdoor]=m.rollout(origin_at=AT,air_f=70,mass_f=69,forcings=forcing).states[-1][0]
    assert temperatures[0,0]>temperatures[1,0]>temperatures[1,1]
    assert temperatures[0,0]>temperatures[0,1]>temperatures[1,1]
    forcing=tuple(replace(row,indoor_shade_closed=float(i%2),outdoor_shade_present=float(i//2%2)) for i,row in enumerate(rows()))
    baseline=model(forcing).rollout(origin_at=AT,air_f=70,mass_f=69,forcings=forcing)
    jac=np.asarray(baseline.sensitivities[-1]);epsilon=1e-8
    for index in range(14):
        values=list(COEFFICIENTS);values[index]+=epsilon
        altered=model(forcing,coefficients=tuple(values)).rollout(origin_at=AT,air_f=70,mass_f=69,forcings=forcing)
        difference=(np.asarray(altered.states[-1])-baseline.states[-1])/epsilon
        assert np.allclose(difference,jac[:,index],rtol=1e-4,atol=1e-4)
    assert baseline.states and jac.shape==(2,14)
    assert model(forcing).automatic_actuation is False and model(forcing).release_authorized is False


def test_family_and_nominal_shade_context_are_explicit_not_a_relabelled_old_fit():
    import native_thermal_artifact as artifact
    from native_joint_shade import shade_contract
    from native_irradiance_shade import RULE
    context=shade_contract()
    assert context['nominal_shade_rejection_fraction']==.65
    assert [z['id'] for z in context['outdoor_zones']]==['kitchen','living_room','bedroom_bathroom']
    assert context['automatic_reinstallation'] is False
    profile=artifact.fit_profile({'schema':'earthship-native-solar-provisional-fit/v3'})
    assert profile['rule']==RULE and profile['count']==14 and profile['irradiance'] is True
    assert profile['solar_feature']()['solar_feature_units']=='W/m2'
    assert artifact.fit_profile({'schema':'earthship-native-solar-provisional-fit/v1'})['count']==10


def fresh_candidate(tmp_path,monkeypatch):
    from test_native_thermal_inputs import build
    import native_thermal_artifact as artifact
    from native_thermal_fit import fit_native_development
    from household.codec import canonical
    tmp_path.mkdir(mode=0o700,exist_ok=True)
    record=snapshot(initial_outdoor='removed');data=build(record);g=data.geometry
    runtime=artifact.current_native_runtime()
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1')
    fit=fit_native_development(data,expected_dataset_sha256=data.sha256,training_start=START,training_end=END,
        initial=COEFFICIENTS,joint=True,irradiance=True,guard=lambda:None,timeout_seconds=20)
    assert artifact.current_native_runtime()==runtime
    evidence=dict(schema='earthship-native-development-fit-evidence/v4',created_at=(END+timedelta(seconds=5)).isoformat(),
        code_revision='e'*40,fit_runtime=runtime,fit=fit,release_authorized=False,production_model_changed=False)
    paths={}
    for role,value in (('snapshot',record),('dataset',data.to_dict()),('geometry',g.to_dict()),('fit_evidence',evidence)):
        name=record['snapshot_sha256']+'.training-inputs-v2.json' if role=='snapshot' else role+'.json'
        path=tmp_path/name;path.write_bytes(canonical(value));path.chmod(0o600);paths[role]=path
    at=END+timedelta(seconds=8)
    candidate=artifact.build_native_candidate(originals=paths,runtime=runtime,created_at=at)
    assert candidate['schema']=='earthship-provisional-thermal-candidate/v4'
    assert len(canonical(candidate))<=16384
    path=artifact.write_native_candidate(tmp_path,candidate,assessed_at=at,runtime=runtime,expected_artifact_sha256=candidate['artifact_sha256'])
    assert artifact.read_native_candidate(path,assessed_at=at,runtime=runtime,expected_artifact_sha256=candidate['artifact_sha256'])==candidate
    return candidate,runtime,paths


def test_fresh_irradiance_fit_retains_local_evidence_regime_support_and_full_model_source_pins(tmp_path,monkeypatch):
    candidate,runtime,paths=fresh_candidate(tmp_path,monkeypatch)
    fit=candidate['fit']
    assert len(fit['coefficients'])==14 and fit['regime_support']['unshaded']['endpoint_count']>0
    assert fit['regime_support']['unshaded']['status']=='observed_unqualified'
    assert fit['graduated'] is False and fit['automatic_actuation'] is False
    for name in ('native_joint_shade.py','native_irradiance_shade.py'):
        assert 'openhab/scripts/'+name in runtime['native_source_manifest']
    assert 'openhab/thermal-shade-context.json' in runtime['native_source_manifest']
    import native_thermal_artifact as artifact
    changed=deepcopy(runtime);changed['native_source_manifest']['openhab/scripts/native_irradiance_shade.py']='f'*64
    changed['native_code_revision']=artifact.digest(changed['native_source_manifest'])
    with pytest.raises(ValueError):artifact._fit_environment(runtime,changed,joint=True,irradiance=True)


def test_google_source_and_removed_shades_reach_genuine_frozen_irradiance_projection(tmp_path,monkeypatch,originals):
    candidate,runtime,paths=fresh_candidate(tmp_path/'fit',monkeypatch)
    from test_native_serving_forecast import context
    source_directory=tmp_path/'sources';source_directory.mkdir(mode=0o700)
    import test_native_model_serving_receipt as receipt_fixture
    import native_model_serving_receipt as receipt,native_thermal_artifact as artifacts
    candidate_path=tmp_path/'fit'/(candidate['artifact_sha256']+'.native-provisional-candidate-v4.json')
    receipt_directory=tmp_path/'receipts';receipt_directory.mkdir(mode=0o700)
    monkeypatch.setattr(receipt_fixture,'prepared',lambda *a:(receipt,artifacts,candidate,candidate_path,paths,runtime,END+timedelta(seconds=8),receipt_directory))
    _,_,_,serving_model,inputs,kwargs,_=context(source_directory,originals,monkeypatch)
    inputs['action_snapshot']['actions']['outdoor_shade']['state']='removed'
    from weather_learning.native_forecast import make_native_forecast
    from weather_learning.tests.learning_fixtures import full_snapshot,SITE
    inputs['forecast']=make_native_forecast(full_snapshot(ISSUE.replace(minute=0,second=0,microsecond=0)-timedelta(hours=8)),
        origin=ISSUE,available_by=ISSUE,horizon_hours=24,site=SITE)
    import native_thermal_forecast as forecast
    capture=forecast.build_capture(candidate,inputs,runtime=runtime,expected_artifact_sha256=candidate['artifact_sha256'],**kwargs)
    assert forecast.build_serving_capture(serving_model,inputs,**kwargs)==capture
    assert capture['output']['model_rule']=='earthship-native-irradiance-shade-dynamics/v4'
    assert capture['output']['origin_actions']['outdoor_shade_present']==0
    from household.weather_context import prepare_native_cycle_contexts
    from household.thermal_model import project
    thermal,weather=prepare_native_cycle_contexts(capture,code_revision='e'*40,runtime=runtime,
        expected_artifact_sha256=candidate['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])
    assert project(thermal)['output']==capture['output']
    import native_thermal_score as scores
    from test_installed_shade_origin import outcome
    from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM
    receipt_values=((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,forecast.publication(capture)))
    receipts={name:dict(item=name,time=int((ISSUE+timedelta(seconds=3+i)).timestamp()*1000),state=json.dumps(value)) for i,(name,value) in enumerate(receipt_values)}
    pair=scores.score(capture,receipts,outcome(ISSUE+timedelta(hours=1)),horizon_hours=1,
        assessed_at=ISSUE+timedelta(hours=1,minutes=10),recent={'status':'unavailable','prediction_f':None},
        runtime=runtime,expected_artifact_sha256=candidate['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])
    assert pair['model_rule']==capture['output']['model_rule']
    assert scores.summarize([pair])['by_horizon']['1']['model']['count']==1
    from native_thermal_model import RULE as ORIGINAL_RULE
    bad=deepcopy(pair);bad['capture_sha256']='f'*64;bad['model_rule']=ORIGINAL_RULE;bad['pair_sha256']=scores.digest(bad,'pair_sha256')
    with pytest.raises(ValueError,match='model rule'):scores.summarize([pair,bad])
    with monkeypatch.context() as patch:
        patch.setattr(Path,'read_bytes',lambda *a,**kw:pytest.fail('frozen projection performed filesystem IO'))
        assert project(thermal)['output']==capture['output']


def test_operational_helpers_load_pinned_current_sources_and_recognize_preserved_model_family(monkeypatch):
    import household_forecast_score as coordinator,native_thermal_score as scores
    monkeypatch.setattr(coordinator,'_production_report_reuse',None)
    module=coordinator.production_retained_runner()
    assert Path(module.__file__).resolve()==Path(coordinator.__file__).with_name('household_retained_native_score.py').resolve()
    assert coordinator.production_report_replay(scores) is not scores.reconcile_serving_source_report


@pytest.mark.parametrize('operation',['publish','prepare'])
def test_google_execution_refuses_older_model_family_before_collection_or_geometry(tmp_path,monkeypatch,originals,operation):
    from test_native_thermal_live_publication import fixture
    live,settings,backend,clock,candidate,g,runtime=fixture(tmp_path,monkeypatch,originals)
    # The production fixture now uses the preserved family. Construct the
    # genuinely older fitted artifact explicitly for this refusal case.
    from test_native_thermal_forecast import context
    import native_thermal_artifact as artifacts
    from thermal_model.forcing_capture import _canonical
    folder=tmp_path/'older-model';folder.mkdir(mode=0o700)
    candidate,_,kwargs=context(folder,monkeypatch,originals)
    runtime=deepcopy(kwargs['runtime'])
    runtime['native_source_manifest']['openhab/scripts/native_thermal_live.py']='d'*64
    runtime['native_code_revision']=artifacts.digest(runtime['native_source_manifest'])
    candidate=artifacts.build_native_candidate(originals={role:Path(ref['path']) for role,ref in candidate['originals'].items()},
        runtime=runtime,created_at=candidate['created_at'])
    assert len(candidate['fit']['coefficients'])==10
    path=folder/'candidate.json';path.write_bytes(_canonical(candidate));path.chmod(0o600)
    settings.update(schema=live.GOOGLE_LIVE_SCHEMA,candidate_path=str(path),
        artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'])
    monkeypatch.setattr(live,'current_runtime',lambda **kw:deepcopy(runtime))
    if operation=='publish':
        backend.collect=lambda **kw:pytest.fail('older model reached Google collection')
        with pytest.raises(ValueError,match='irradiance'):live.publish_cycle(settings,geometry=g,backend=backend,guard=lambda:None)
    else:
        folder=tmp_path/'geometry';folder.mkdir(mode=0o700);settings['geometry_directory']=str(folder)
        clock[0]=ISSUE-timedelta(seconds=100)
        import astro_geometry_worker as worker
        monkeypatch.setattr(worker,'capture_batch',lambda *a,**kw:pytest.fail('older model reached geometry worker'))
        with pytest.raises(ValueError,match='irradiance'):live.prepare_geometry(settings,issue=ISSUE,library_paths={},guard=lambda:None)


def test_google_deployment_refuses_the_older_candidate_family(tmp_path):
    from test_native_household_deploy import native_fixture,api,write,encode
    from test_google_native_selection import source,GOOGLE_LIVE
    from weather_learning.archive import Archive
    args,files,candidate,settings=native_fixture(tmp_path)
    settings.update(schema=GOOGLE_LIVE,weather_source=source(Archive(tmp_path/'google').root))
    import native_thermal_artifact as artifacts
    # Deliberately corrupt package-only family metadata, keeping transport
    # identities coherent. Genuine older-model refusal is tested above.
    candidate['schema']=artifacts.SCHEMA
    candidate['artifact_sha256']=artifacts.digest(candidate,'artifact_sha256')
    settings['artifact_sha256']=candidate['artifact_sha256']
    write(Path(settings['candidate_path']),encode(candidate))
    write(args['forecast_config'],encode(settings))
    with pytest.raises(ValueError,match='irradiance'):api().stage_deployment(**args)
