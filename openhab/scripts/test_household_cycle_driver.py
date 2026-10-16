"""Private CLI orchestration without a live device or forecast write."""
from hashlib import sha256
from pathlib import Path
import pytest
from household.codec import canonical


def setup(tmp_path,monkeypatch):
    import household_cycle as cycle
    import household_cycle_sources as sources
    import thermal_model.provisional_live as forecast
    import thermal_model.capture_guard as locks
    import household_cycle_pressure as pressure
    import thermal_installed_intel as installed
    calls=[]
    params=tmp_path/'params.json';params.write_bytes(canonical({'collected_at':'2026-10-11T00:00:00+00:00','record':{'household_energy_inputs':{}}}));params.chmod(0o600)
    forecast_path=tmp_path/'forecast.json';forecast_path.write_bytes(b'{}');forecast_path.chmod(0o600)
    evidence=tmp_path/'evidence';evidence.mkdir(mode=0o700)
    config=tmp_path/'cycle.json'
    settings=dict(schema='earthship-household-cycle-config/v1',forecast_config=str(forecast_path),retained_energy_parameters=str(params),
        parameters_sha256=sha256(params.read_bytes()).hexdigest(),evidence_directory=str(evidence),observation_cache=str(tmp_path/'observation.json'))
    config.write_bytes(canonical(settings));config.chmod(0o600)
    forecast_settings={'shared_lock':str(tmp_path/'lock'),'token_file':str(tmp_path/'token'),'openhab_base':'http://127.0.0.1:8080/rest'}
    monkeypatch.setattr(forecast,'load_settings',lambda path:forecast_settings)
    monkeypatch.setattr(installed,'_resource_preflight',lambda:calls.append('resources'))
    import household_cycle_resources
    monkeypatch.setattr(household_cycle_resources,'publication_resource_preflight',lambda:calls.append('resources'))
    class Lock:
        def __init__(self,path):assert path==forecast_settings['shared_lock']
        def __enter__(self):calls.append('locked');return self
        def verify(self):calls.append('lock_verified')
        def __exit__(self,*args):calls.append('unlocked')
    monkeypatch.setattr(locks,'SharedScoreLock',Lock)
    class Monitor:
        def __init__(self,**kw):pass
        def preflight(self):calls.append('headroom')
        def check(self):calls.append('checked')
    monkeypatch.setattr(pressure,'PublicationHeadroom',Monitor)
    class Collector:
        def __init__(self,**kw):self.runtime={'source':'a'*64};calls.append('collector_ready')
        def __call__(self,**kw):raise AssertionError('publisher boundary is mocked in orchestration tests')
    monkeypatch.setattr(sources,'CycleSourceCollector',Collector)
    def publish(settings,*,guard,backend):
        guard();calls.append('published');backend.collection={'status':'collected'}
        return {'status':'published','delivery_verified':True,'origin_path':'private-origin','delivery_path':'private-delivery'}
    monkeypatch.setattr(forecast,'publish_cycle',publish)
    monkeypatch.setattr(forecast,'withdraw',lambda *a,**kw:calls.append('withdrawn') or {'status':'withdrawn'})
    def complete(**kw):
        calls.append('observation');assert kw['runtime_manifest']=={'source':'a'*64}
        kw['guard']()
        return {'status':'observation_written','receipt_sha256':'b'*64,'automatic_actuation':False}
    monkeypatch.setattr(cycle,'complete_cycle',complete)
    return cycle,config,params,calls


def test_driver_owns_original_lock_and_keeps_private_paths_off_report(tmp_path,monkeypatch):
    cycle,config,_,calls=setup(tmp_path,monkeypatch)
    result=cycle.run_cycle(config,code_revision='e'*40)
    assert result['status']=='published'
    assert result['observation']['status']=='observation_written'
    assert calls.index('locked')<calls.index('published')<calls.index('observation')<calls.index('unlocked')
    assert b'private-origin' not in canonical(result)
    assert b'private-delivery' not in canonical(result)
    assert 'withdrawn' not in calls


def test_changed_retained_parameters_withhold_only_observation(tmp_path,monkeypatch):
    cycle,config,params,calls=setup(tmp_path,monkeypatch)
    params.write_bytes(b'{}')
    result=cycle.run_cycle(config,code_revision='e'*40,forecast_config=tmp_path/'forecast.json')
    assert result['status']=='published'
    assert result['observation']['status']=='observation_unavailable'
    assert 'published' in calls
    assert 'withdrawn' not in calls


def test_household_failure_does_not_withdraw_verified_forecast(tmp_path,monkeypatch):
    cycle,config,_,calls=setup(tmp_path,monkeypatch)
    def failed(**kw):raise ValueError('private source payload')
    monkeypatch.setattr(cycle,'complete_cycle',failed)
    result=cycle.run_cycle(config,code_revision='e'*40)
    assert result['status']=='published'
    assert result['delivery_verified'] is True
    assert result['observation']['status']=='observation_refused'
    assert b'private source' not in canonical(result)
    assert 'withdrawn' not in calls


def test_forecast_failure_uses_existing_withdrawal_behavior(tmp_path,monkeypatch):
    import thermal_model.provisional_live as forecast
    cycle,config,_,calls=setup(tmp_path,monkeypatch)
    def failed(*args,**kw):raise ValueError('original forecast failure')
    monkeypatch.setattr(forecast,'publish_cycle',failed)
    result=cycle.run_cycle(config,code_revision='e'*40)
    assert result['status']=='withheld_and_withdrawn'
    assert 'observation' not in calls
    assert 'withdrawn' in calls


def test_observer_initialization_failure_still_runs_original_publisher(tmp_path,monkeypatch):
    import household_cycle_sources as sources
    cycle,config,_,calls=setup(tmp_path,monkeypatch)
    def failed(**kw):raise ValueError('private collector configuration')
    monkeypatch.setattr(sources,'CycleSourceCollector',failed)
    result=cycle.run_cycle(config,code_revision='e'*40)
    assert result['status']=='published'
    assert result['delivery_verified'] is True
    assert 'withdrawn' not in calls
    assert b'private collector' not in canonical(result)


def test_observer_parameter_drift_does_not_abort_original_publication(tmp_path,monkeypatch):
    import thermal_model.provisional_live as forecast
    cycle,config,params,calls=setup(tmp_path,monkeypatch)
    def publish(settings,*,guard,backend):
        params.write_bytes(b'{}');guard();calls.append('published')
        backend.collection={'status':'collected'}
        return {'status':'published','delivery_verified':True,'origin_path':'private-origin','delivery_path':'private-delivery'}
    monkeypatch.setattr(forecast,'publish_cycle',publish)
    result=cycle.run_cycle(config,code_revision='e'*40)
    assert result['status']=='published'
    assert result['observation']['status']=='observation_refused'
    assert 'withdrawn' not in calls

@pytest.mark.parametrize('damage',['missing_parameters','invalid_parameters','cache_parent','missing_cycle_config','invalid_cycle_config'])
def test_household_startup_failure_keeps_independent_original_forecast(damage,tmp_path,monkeypatch):
    import json
    cycle,config,params,calls=setup(tmp_path,monkeypatch)
    if damage=='missing_parameters':params.unlink()
    if damage=='invalid_parameters':
        params.write_bytes(b'{')
        value=json.loads(config.read_bytes());value['parameters_sha256']=sha256(params.read_bytes()).hexdigest();config.write_bytes(canonical(value))
    if damage=='cache_parent':
        value=json.loads(config.read_bytes());value['observation_cache']=str(tmp_path/'missing-parent/observation.json');config.write_bytes(canonical(value))
    if damage=='missing_cycle_config':config.unlink()
    if damage=='invalid_cycle_config':config.write_bytes(b'{')
    result=cycle.run_cycle(config,code_revision='e'*40,forecast_config=tmp_path/'forecast.json')
    assert result['status']=='published'
    assert result['delivery_verified'] is True
    assert result['observation']['status']=='observation_unavailable'
    assert 'withdrawn' not in calls
