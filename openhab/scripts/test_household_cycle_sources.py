"""Private cycle configuration cannot choose arbitrary execution or leak data."""
import importlib,json,os
from pathlib import Path
import pytest

def api():return importlib.import_module('household_cycle_sources')

def config(tmp_path):
    return {'schema':'earthship-household-cycle-config/v1',
        'forecast_config':str(tmp_path/'forecast.json'),
        'retained_energy_parameters':str(tmp_path/'original-parameters.json'),
        'parameters_sha256':'a'*64,
        'evidence_directory':str(tmp_path/'private'),
        'observation_cache':str(tmp_path/'private'/'observation.json')}

def test_owned_configuration_preserves_original_parameters_and_explicit_cache(tmp_path):
    original=config(tmp_path);path=tmp_path/'cycle.json'
    path.write_text(json.dumps(original));path.chmod(0o600)
    assert api().load_cycle_settings(path)==original
    assert json.loads(path.read_text())==original

@pytest.mark.parametrize('damage',['schema','extra','digest','relative','mode','symlink'])
def test_unsafe_configuration_refuses_before_any_live_collection(damage,tmp_path):
    original=config(tmp_path)
    if damage=='schema':original['schema']='future/v99'
    if damage=='extra':original['command']='operator-only payload'
    if damage=='digest':original['parameters_sha256']='invalid'
    if damage=='relative':original['forecast_config']='relative/config.json'
    path=tmp_path/'cycle.json';path.write_text(json.dumps(original));path.chmod(0o644 if damage=='mode' else 0o600)
    if damage=='symlink':
        alias=tmp_path/'alias.json';alias.symlink_to(path);path=alias
    with pytest.raises(ValueError):api().load_cycle_settings(path)
