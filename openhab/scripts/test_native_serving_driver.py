"""Routing-only doubles: numerical admission is covered by genuine receipt tests."""
import inspect,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_household_native_cycle_driver import native_setup


def setup(tmp_path,monkeypatch):
    import household_cycle as cycle
    assert 'deployment_sha256' in inspect.signature(cycle.run_cycle).parameters, 'externally pinned serving driver is missing'
    cycle,native,config,calls=native_setup(tmp_path,monkeypatch)
    stage=tmp_path/'stage';scripts=stage/'sources/openhab/scripts';scripts.mkdir(parents=True)
    original=Path(cycle.__file__).parent
    for name in ('household_cycle.py','household_cycle_sources.py','household_cycle_deadline.py','household_cycle_pressure.py','household_cycle_resources.py','household_observation.py'):
        (scripts/name).write_bytes((original/name).read_bytes())
    monkeypatch.setattr(cycle,'__file__',str(scripts/'household_cycle.py'))
    forecast=Path(json.loads(config.read_bytes())['forecast_config']);forecast.write_text(json.dumps({'schema':native.SERVING_SCHEMA}))
    settings=dict(schema=native.SERVING_SCHEMA,shared_lock=str(tmp_path/'lock'),token_file=str(tmp_path/'token'),openhab_base='http://127.0.0.1:8080/rest',artifact_sha256='a'*64,runtime_sha256='c'*64)
    available=tmp_path/'available-geometry';available.mkdir(mode=0o700);settings['geometry_directory']=str(available)
    packet=native.geometry_path(settings,native._next_issue(native._clock()));packet.write_bytes(b'{}');packet.chmod(0o600)
    monkeypatch.setattr(native,'load_settings',lambda *a,**kw:settings)
    import native_model_serving_receipt as receipt
    selected=object();model=SimpleNamespace(runtime={'selected_runtime':'c'*64},candidate={'artifact_sha256':'a'*64})
    def load(actual,*,expected_deployment_sha256,assessed_at,guard):
        assert Path(actual)==stage and expected_deployment_sha256=='d'*64;guard();calls.append('selected');return selected
    def read(actual,*,assessed_at,guard):
        assert actual is selected;guard();calls.append('admitted');return model
    monkeypatch.setattr(receipt,'load_serving_selection',load);monkeypatch.setattr(receipt,'read_serving_model',read)
    def publish(value,*,guard,backend,serving_model):
        native._resource_preflight()
        assert serving_model is model and value==settings;guard();calls.append('serving_published');backend.collection={'status':'collected'}
        return dict(status='published',delivery_verified=True,capture_sha256='b'*64)
    monkeypatch.setattr(native,'publish_cycle',publish)
    def complete(**kwargs):
        assert kwargs['serving_model'] is model and kwargs['runtime']==model.runtime;kwargs['guard']();calls.append('serving_observed')
        return {'status':'observation_written'}
    monkeypatch.setattr(cycle,'complete_cycle',complete)
    return cycle,receipt,native,config,stage,calls,model


def test_pinned_driver_mints_once_and_passes_same_context_through_publication_and_observation(tmp_path,monkeypatch):
    cycle,receipt,native,config,stage,calls,model=setup(tmp_path,monkeypatch)
    result=cycle.run_cycle(config,code_revision='e'*40,stage=stage,deployment_sha256='d'*64)
    assert result['status']=='published' and result['observation']['status']=='observation_written'
    assert calls.count('selected')==calls.count('admitted')==1
    assert calls.index('locked')<calls.index('admitted')<calls.index('serving_published')<calls.index('serving_observed')<calls.index('unlocked')
    assert 'published' not in calls


def test_failed_receipt_admission_cannot_publish_or_fall_back_to_legacy_model(tmp_path,monkeypatch):
    cycle,receipt,native,config,stage,calls,model=setup(tmp_path,monkeypatch)
    monkeypatch.setattr(receipt,'read_serving_model',lambda *a,**kw:(_ for _ in ()).throw(ValueError('receipt refused')))
    result=cycle.run_cycle(config,code_revision='e'*40,stage=stage,deployment_sha256='d'*64)
    assert result['status'] in ('withheld','withheld_and_withdrawn')
    assert 'serving_published' not in calls and 'native_published' not in calls and 'published' not in calls


def test_serving_profile_without_external_stage_pin_is_refused_before_publication(tmp_path,monkeypatch):
    cycle,receipt,native,config,stage,calls,model=setup(tmp_path,monkeypatch)
    with pytest.raises(ValueError):cycle.run_cycle(config,code_revision='e'*40)
    assert 'serving_published' not in calls and 'published' not in calls


def geometry_case(tmp_path,monkeypatch,damage):
    from test_native_thermal_forecast import ISSUE
    from datetime import timedelta
    cycle,receipt,native,config,stage,calls,model=setup(tmp_path,monkeypatch)
    settings=native.load_settings(None);root=tmp_path/'geometry';root.mkdir(mode=0o700);settings['geometry_directory']=str(root)
    monkeypatch.setattr(native,'_clock',lambda:ISSUE-timedelta(seconds=30))
    monkeypatch.setattr(native,'_serving_settings',lambda actual,value,**kw:kw['guard']())
    path=native.geometry_path(settings,ISSUE)
    if damage in ('malformed','other_file','drift'):path.write_bytes(b'{}');path.chmod(0o600)
    elif damage=='symlink':path.symlink_to(tmp_path/'not-present')
    elif damage=='directory':root.rmdir()
    previous=tmp_path/'issued-forecast.json';previous.write_bytes(b'unchanged original issued values and clocks')
    def publish(value,*,guard,backend,serving_model):
        guard()
        if damage=='drift':
            Path(json.loads(config.read_bytes())['forecast_config']).write_bytes(b'{}')
        if damage=='other_file':raise FileNotFoundError(2,'missing original candidate',str(tmp_path/'candidate.json'))
        return native.read_geometry(value,issue=ISSUE,guard=guard)
    monkeypatch.setattr(native,'publish_cycle',publish)
    def withdraw(*a,guard,**kw):
        guard();calls.append('withdrawn');return dict(delivery_verified=True)
    monkeypatch.setattr(native,'withdraw',withdraw)
    return cycle,config,stage,calls,previous


def test_missing_next_geometry_defers_without_withdrawing_or_reclocking_previous_forecast(tmp_path,monkeypatch):
    cycle,config,stage,calls,previous=geometry_case(tmp_path,monkeypatch,'absent')
    result=cycle.run_cycle(config,code_revision='e'*40,stage=stage,deployment_sha256='d'*64)
    assert result['status']=='deferred' and result['reason']=='native_geometry_not_prepared'
    assert result['delivery_verified'] is False and result['automatic_actuation'] is False
    assert 'admitted' in calls and 'withdrawn' not in calls and 'serving_observed' not in calls
    assert previous.read_bytes()==b'unchanged original issued values and clocks'
    assert b'/tmp/' not in __import__('household.codec',fromlist=['canonical']).canonical(result)


@pytest.mark.parametrize('damage',['other_file','malformed','symlink','directory'])
def test_geometry_deferral_cannot_hide_other_missing_invalid_or_aliased_inputs(tmp_path,monkeypatch,damage):
    cycle,config,stage,calls,previous=geometry_case(tmp_path,monkeypatch,damage)
    result=cycle.run_cycle(config,code_revision='e'*40,stage=stage,deployment_sha256='d'*64)
    assert result['status'] in ('withheld','withheld_and_withdrawn')
    assert 'withdrawn' in calls


def test_missing_geometry_deferral_rechecks_original_forecast_configuration(tmp_path,monkeypatch):
    cycle,config,stage,calls,previous=geometry_case(tmp_path,monkeypatch,'drift')
    result=cycle.run_cycle(config,code_revision='e'*40,stage=stage,deployment_sha256='d'*64)
    assert result['status']=='withheld' and result['delivery_verified'] is False
    assert 'serving_observed' not in calls


def test_missing_geometry_cannot_defer_after_model_binding_recheck_fails(tmp_path,monkeypatch):
    cycle,config,stage,calls,previous=geometry_case(tmp_path,monkeypatch,'absent')
    import native_thermal_live as native
    def invalid(*args,**kwargs):raise ValueError('model bindings changed')
    monkeypatch.setattr(native,'_serving_settings',invalid)
    result=cycle.run_cycle(config,code_revision='e'*40,stage=stage,deployment_sha256='d'*64)
    assert result['status']=='withheld_and_withdrawn' and 'withdrawn' in calls
