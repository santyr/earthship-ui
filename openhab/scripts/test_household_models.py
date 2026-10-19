"""Pure model extraction must preserve frozen original production outputs."""
import importlib,json
from pathlib import Path
import pytest

FIXTURE=json.loads((Path(__file__).parent/'household/fixtures/energy-production-v1.json').read_text())


def energy_api():
    assert importlib.util.find_spec('household.energy_model') is not None,'pure energy boundary missing'
    return importlib.import_module('household.energy_model')


@pytest.mark.parametrize('case',FIXTURE['cases'])
def test_production_energy_parity(case):
    assert energy_api().daily_energy_projection(**case['inputs'])==case['output']


def thermal_api():
    assert importlib.util.find_spec('household.thermal_model') is not None,'frozen thermal boundary missing'
    return importlib.import_module('household.thermal_model')


def prepared_thermal(tmp_path,monkeypatch):
    # Mathematical fixtures use an owned, non-group-writable copy of the same
    # interpreter bytes. Hosted tool-cache permissions are not release evidence.
    import sys,shutil
    interpreter=tmp_path/'runtime-interpreter'
    shutil.copyfile(Path(sys.executable).resolve(),interpreter)
    interpreter.chmod(0o700)
    monkeypatch.setattr(sys,'executable',str(interpreter))
    from test_provisional_thermal_forecast import context,module,ISSUE
    from datetime import timedelta
    candidate,inputs=context(tmp_path,monkeypatch)
    monkeypatch.setattr(module(),'replay_binding',lambda *args,**kwargs:None)
    capture=module().build_capture(candidate,inputs,issue=ISSUE,available=ISSUE,published=ISSUE+timedelta(seconds=2))
    return thermal_api().prepare_projection(capture,code_revision='a'*40),capture


def test_frozen_thermal_projection_matches_original_provisional_trajectory(tmp_path,monkeypatch):
    prepared,original=prepared_thermal(tmp_path,monkeypatch)
    output=thermal_api().project(prepared)
    assert output['output']==original['output']
    assert output['snapshot']['planner_authority']=='none'
    assert output['snapshot']['domains']['energy']['battery_soc']['value'] is None
    assert output['snapshot']['domains']['water']['water_inventory']['value'] is None
    assert output['action_effects_qualified'] is False and output['automatic_actuation'] is False
    assert output['original_capture_sha256']==original['capture_sha256']


def test_prepared_projection_and_returned_snapshots_are_immutable(tmp_path,monkeypatch):
    prepared,original=prepared_thermal(tmp_path,monkeypatch);mod=thermal_api();first=mod.project(prepared)
    original['candidate']['fit']['coefficients'][0]=999
    first['snapshot']['domains']['thermal']['air_temperature']['value']=999
    assert mod.project(prepared)['output']['initial']['air_f']!=999
    assert mod.project(prepared)['snapshot']['domains']['thermal']['air_temperature']['value']!=999


def test_pure_projection_performs_no_original_or_live_reads(tmp_path,monkeypatch):
    import builtins,psycopg2
    prepared,_=prepared_thermal(tmp_path,monkeypatch)
    def forbidden(*args,**kwargs):pytest.fail('read attempted inside frozen model boundary')
    monkeypatch.setattr(builtins,'open',forbidden)
    monkeypatch.setattr(Path,'read_bytes',forbidden)
    monkeypatch.setattr(Path,'read_text',forbidden)
    monkeypatch.setattr(psycopg2,'connect',forbidden)
    assert len(thermal_api().project(prepared)['output']['trajectory'])==24


def test_preparation_refuses_tampered_original_trajectory(tmp_path,monkeypatch):
    _,original=prepared_thermal(tmp_path,monkeypatch)
    original['output']['trajectory'][0]['air_f']+=1
    with pytest.raises(ValueError):thermal_api().prepare_projection(original,code_revision='a'*40)


def test_measured_mass_is_not_relabelled_as_latent_model_state(tmp_path,monkeypatch):
    prepared,original=prepared_thermal(tmp_path,monkeypatch);output=thermal_api().project(prepared)
    measured=original['inputs']['origin_temperatures']['roles']['mass']['grid'][-1][1]['temperatureF']
    assert output['snapshot']['domains']['thermal']['mass_temperature']['value']==measured
    assert output['initial_mass_semantics']=='existing_latent_observer_state'


def test_household_execution_runtime_is_distinct_from_original_artifact_runtime(tmp_path,monkeypatch):
    prepared,original=prepared_thermal(tmp_path,monkeypatch)
    output=thermal_api().project(prepared)
    assert output['output']['runtime_sha256']==original['candidate']['runtime_sha256']
    actual=prepared.to_dict()['executing_runtime']
    assert 'household/thermal_model.py' in actual['household_source_manifest']
    assert 'thermal_model/installed_shade_dynamics.py' in actual['thermal_runtime']['source_manifest']
    from household.codec import identity
    assert output['executing_runtime_sha256']==identity(actual)


def test_shared_writable_interpreter_is_isolated_for_mathematical_fixture(tmp_path,monkeypatch):
    import sys,shutil
    shared=tmp_path/'shared-python';shutil.copyfile(Path(sys.executable).resolve(),shared);shared.chmod(0o775)
    monkeypatch.setattr(sys,'executable',str(shared))
    prepared,_=prepared_thermal(tmp_path,monkeypatch)
    actual=prepared.to_dict()['executing_runtime']['thermal_runtime']
    from hashlib import sha256
    assert actual['interpreter_sha256']==sha256(shared.read_bytes()).hexdigest()
