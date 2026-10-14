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
