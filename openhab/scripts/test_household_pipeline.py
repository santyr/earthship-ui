"""Models and generated decisions replay from one frozen household state."""
import importlib,json
from pathlib import Path
import pytest
from test_household_models import FIXTURE


def energy_api():
    return importlib.import_module('household.energy_model')


@pytest.mark.parametrize('case',FIXTURE['cases'])
def test_frozen_energy_inputs_rederive_exact_production_output(case):
    mod=energy_api();assert hasattr(mod,'freeze_energy_inputs'),'frozen energy boundary missing'
    frozen=mod.freeze_energy_inputs(**case['inputs']);result=mod.project_energy(frozen)
    assert result['output']==case['output']
    assert result['input_qualification']=='not_assessed'
    assert result['action_effects_qualified'] is False and result['automatic_actuation'] is False


def test_energy_inputs_freeze_caller_lists_and_returned_documents():
    mod=energy_api();assert hasattr(mod,'freeze_energy_inputs'),'frozen energy boundary missing'
    args={**FIXTURE['cases'][0]['inputs'],'overnight_drops_pct':[2.]}
    frozen=mod.freeze_energy_inputs(**args);args['overnight_drops_pct'].append(999)
    document=frozen.to_dict();document['inputs']['bank_kwh']=999
    assert frozen.to_dict()['inputs']['overnight_drops_pct']==[2.]
    assert frozen.to_dict()['inputs']['bank_kwh']!=999


@pytest.mark.parametrize('field,value',[('bank_kwh',0),('eta_rt',0),('soc_pct',101),
    ('tomorrow_cloud_pct',True),('overnight_drops_pct',[1.]*4),('resource_kwh',float('inf'))])
def test_frozen_energy_refuses_bad_numeric_context(field,value):
    mod=energy_api();assert hasattr(mod,'freeze_energy_inputs'),'frozen energy boundary missing'
    with pytest.raises(ValueError):mod.freeze_energy_inputs(**{**FIXTURE['cases'][0]['inputs'],field:value})


def test_production_worker_retains_exact_energy_argument_record():
    import ast
    tree=ast.parse(Path(__file__).with_name('forecast_intel.py').read_text())
    main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='main')
    assert any(isinstance(node,ast.Name) and node.id=='energy_projection_inputs' for node in ast.walk(main)),'exact original energy arguments missing'
    assert any(isinstance(node,ast.Constant) and node.value=='household_energy_inputs' for node in ast.walk(main)),'prediction state lacks exact energy input record'
