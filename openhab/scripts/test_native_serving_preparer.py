"""Owned receipt selection in the outer preparer; numerical reader tested separately."""
import inspect,json
from pathlib import Path
import pytest
from test_household_native_geometry_prepare import fixture


def setup(tmp_path,monkeypatch):
    import household_native_geometry_prepare as module
    assert 'deployment_sha256' in inspect.signature(module.run).parameters, 'pinned receipt preparer is missing'
    m,config,libraries,settings,now,ticks,calls=fixture(tmp_path,monkeypatch)
    import native_thermal_live as native
    import household_cycle_resources as resources
    monkeypatch.setattr(resources,'publication_resource_preflight',lambda:calls.append('geometry_policy'))
    settings['schema']=native.SERVING_SCHEMA;config.write_text(json.dumps(settings))
    stage=tmp_path/'stage';source=stage/'sources/openhab/scripts/household_native_geometry_prepare.py';source.parent.mkdir(parents=True)
    source.write_bytes(Path(m.__file__).read_bytes());source.chmod(0o600);monkeypatch.setattr(m,'__file__',str(source))
    import household_cycle_deploy as deploy
    def verify(actual,**kwargs):
        assert Path(actual)==stage and kwargs['expected_deployment_sha256']=='d'*64
        return {'schema':'earthship-household-cycle-deployment/v3'}
    monkeypatch.setattr(deploy,'verify_stage',verify)
    import native_model_serving_receipt as receipt
    selected=object();model=object()
    def selection(actual,*,expected_deployment_sha256,assessed_at,guard):
        assert Path(actual)==stage and expected_deployment_sha256=='d'*64;guard();calls.append('selected');return selected
    def read(actual,*,assessed_at,guard):
        assert actual is selected;guard();calls.append('admitted');return model
    monkeypatch.setattr(receipt,'load_serving_selection',selection);monkeypatch.setattr(receipt,'read_serving_model',read)
    def prepare(actual,*,issue,library_paths,guard,serving_model):
        assert serving_model is model and actual==settings;guard();calls.append('prepared');return {'status':'prepared'}
    monkeypatch.setattr(native,'prepare_geometry',prepare)
    return m,receipt,config,libraries,stage,now,ticks,calls


def test_outer_preparer_passes_fresh_context_after_lock_and_pressure_admission(tmp_path,monkeypatch):
    m,receipt,c,l,stage,now,ticks,calls=setup(tmp_path,monkeypatch)
    assert m.run(c,l,stage=stage,deployment_sha256='d'*64,clock=lambda:now[0],monotonic=lambda:ticks[0])['status']=='prepared'
    assert calls.count('selected')==calls.count('admitted')==calls.count('geometry_policy')==1
    assert calls.index('quiet_preflight')<calls.index('admitted')<calls.index('prepared')


def test_outer_preparer_missing_external_pin_cannot_enter_preparation(tmp_path,monkeypatch):
    m,receipt,c,l,stage,now,ticks,calls=setup(tmp_path,monkeypatch)
    with pytest.raises(ValueError):m.run(c,l,clock=lambda:now[0],monotonic=lambda:ticks[0])
    assert 'prepared' not in calls


def test_outer_preparer_refused_receipt_cannot_run_geometry_worker(tmp_path,monkeypatch):
    m,receipt,c,l,stage,now,ticks,calls=setup(tmp_path,monkeypatch)
    def failed(*args,**kwargs):raise ValueError('receipt refused')
    monkeypatch.setattr(receipt,'read_serving_model',failed)
    with pytest.raises(ValueError):m.run(c,l,stage=stage,deployment_sha256='d'*64,clock=lambda:now[0],monotonic=lambda:ticks[0])
    assert 'prepared' not in calls
