"""Registry must describe existing ownership without granting authority."""
import importlib
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]


def originals():
    return [json.loads((ROOT/name).read_text()) for name in ('openhab/managed-resources.json','openhab/file-config/ownership.json')]


def api():
    assert importlib.util.find_spec('household.capabilities') is not None,'household capability registry missing'
    return importlib.import_module('household.capabilities')


def test_actual_registry_is_pinned_descriptive_and_immutable():
    managed,ownership=originals();registry=api().build_registry(managed,ownership);view=registry.to_dict()
    assert set(view['capabilities'])=={'feeder-request-v1','greywater-request-v1','night-load-owner-v1'}
    grey=view['capabilities']['greywater-request-v1']
    assert grey['ownerRule']=='hex_southoutlet_cycle'
    assert grey['protectedActuators']==['East_Bed_Socket_Outlet_2_Power','SouthOutlet_Outlet2_Switch']
    assert grey['plannerAuthority']=='none' and view['descriptiveOnly'] is True
    assert grey['requestBindings']==[{'requestItem':'SouthOutlet_ManualRequest','resultItem':'SouthOutlet_ManualResult'}]
    managed['subsets']['greywater']['rule']['uid']='changed'
    view['capabilities'].clear()
    assert registry.to_dict()['capabilities']['greywater-request-v1']['ownerRule']=='hex_southoutlet_cycle'


@pytest.mark.parametrize('damage',['authority','actuator_ingress','wrong_result','duplicate_owner','wrong_safety','ownership_conflict'])
def test_manifest_conflicts_cannot_create_authority(damage):
    managed,ownership=originals()
    contract=managed['subsets']['greywater']['householdContract']
    if damage=='authority':contract['plannerAuthority']='active'
    elif damage=='actuator_ingress':contract['requestBindings'][0]['requestItem']='SouthOutlet_Outlet2_Switch'
    elif damage=='wrong_result':contract['requestBindings'][0]['resultItem']='BMS_SOC'
    elif damage=='duplicate_owner':managed['subsets']['feeder']['rule']['uid']='hex_southoutlet_cycle'
    elif damage=='wrong_safety':contract['safetyInputs'].append('untracked_input')
    else:ownership['resources'].append({**ownership['resources'][0],'state_writer':'conflicting-owner'})
    with pytest.raises(ValueError):api().build_registry(managed,ownership)


@pytest.mark.parametrize('kind,identity',[('rule','hex_southoutlet_cycle'),('item','SouthOutlet_ManualResult')])
def test_registry_refuses_cross_manifest_provider_owner_conflict(kind,identity):
    managed,ownership=originals()
    ownership['resources'].append(dict(kind=kind,id=identity,provider='file',migration='verified',source='conflicting-source',state_writer='conflicting-owner'))
    with pytest.raises(ValueError):api().build_registry(managed,ownership)


def test_different_owner_cannot_redeclare_the_same_correlated_result():
    managed,ownership=originals();grey=managed['subsets']['greywater']
    grey['items'].append(dict(name='GoatFeeder_ManualResult',type='String'))
    grey['householdContract']['requestBindings'][0]['resultItem']='GoatFeeder_ManualResult'
    with pytest.raises(ValueError):api().build_registry(managed,ownership)


def test_greywater_descriptor_matches_observed_installed_two_pump_source():
    from hashlib import sha256
    managed,ownership=originals();subset=managed['subsets']['greywater']
    # Original live GET matched this reviewed historical revision on 2026-10-14.
    assert sha256((ROOT/subset['rule']['source']).read_bytes()).hexdigest()=='4c34780e544d80af8eb36d047a949fa30e0198bb50fa57650285052db3c52d9b'
    grey=api().build_registry(managed,ownership).to_dict()['capabilities']['greywater-request-v1']
    assert 'BMS_SOC_Evidence_JSON' in grey['safetyInputs']
    assert 'BMS_SOC' not in grey['safetyInputs']
    assert set(grey['protectedActuators'])<=set(grey['protectedDependencies'])
    assert grey['safetyInputsComplete'] is False and grey['plannerAuthority']=='none'


@pytest.mark.parametrize('damage',['duplicate_actuator','request_alias'])
def test_east_greywater_pump_is_protected_across_owner_contracts(damage):
    managed,ownership=originals();feeder=managed['subsets']['feeder']
    east='East_Bed_Socket_Outlet_2_Power'
    if damage=='duplicate_actuator':
        feeder['protectedDependencies'].append(east)
        feeder['householdContract']['protectedActuators'].append(east)
    else:
        feeder['items'][0]['name']=east
        feeder['householdContract']['requestBindings'][0]['requestItem']=east
        feeder['rule']['triggers'][0]['configuration']['itemName']=east
    with pytest.raises(ValueError):api().build_registry(managed,ownership)
