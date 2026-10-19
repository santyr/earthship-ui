"""Current energy planning uses retained Google/PV trajectories, not retired daily receipts."""
from copy import deepcopy
import pytest
from household.codec import canonical
from test_household_native_weather import originals


def inputs(tmp_path, monkeypatch, originals):
    from test_household_energy_forecast import fixture
    from household.model_snapshot import restore_snapshot
    api, args, plan = fixture(tmp_path, monkeypatch, originals)
    snapshot = restore_snapshot(plan['inputs']['snapshot'], plan['inputs']['source_contexts'])
    return api, args, plan, snapshot


def test_google_trajectory_drives_current_energy_candidates_without_daily_state(tmp_path, monkeypatch, originals):
    from household.trajectory_energy import prepare_inputs, project
    from household.pipeline import seal_pipeline, replay_pipeline
    from household.capabilities import CapabilityRegistry
    from household.thermal_model import PreparedProjection
    from household_pipeline import pipeline_runtime_manifest
    api, args, old, snapshot = inputs(tmp_path, monkeypatch, originals)
    prepared = prepare_inputs(snapshot=snapshot, system_source=args['system_source'], topology_source=args['topology_source'], horizon_source=args['horizon_source'])
    projection = project(prepared, snapshot=snapshot, now=args['now'])
    assert projection['schema'] == 'earthship-household-trajectory-energy-projection/v1'
    assert projection['output']['status'] == 'conditional_nominal_simulation'
    assert projection['output']['horizon_hours'] == 24
    assert 'trough_pred' not in projection['output'] and 'curtail' not in projection['output']
    assert projection['output']['minimum_nominal_soc_pct'] is not None
    registry = old['inputs']['registry']
    registry = CapabilityRegistry(canonical({k:v for k,v in registry.items() if k!='registry_id'}))
    thermal = PreparedProjection(canonical(old['inputs']['thermal_inputs']))
    runtime = pipeline_runtime_manifest(expanded=True,configured=True,measured=True)
    plan = seal_pipeline(snapshot=snapshot,registry=registry,energy_inputs=prepared,thermal_inputs=thermal,
        thermal_runtime=old['inputs']['thermal_inputs']['executing_runtime'],coordination=old['inputs']['coordination'],config=old['inputs']['config'],
        now=args['now'],runtime_manifest=runtime,energy_persistence_source=old['inputs']['energy_persistence_source'])
    assert plan['output']['candidate_generation']['status'] == 'generated_shadow_only'
    assert plan['output']['candidate_generation']['objective_units']['surplus_weight'].endswith('DC_kWh')
    assert plan['output']['automatic_actuation'] is False
    assert replay_pipeline(plan,runtime_manifest=runtime,thermal_runtime=thermal.to_dict()['executing_runtime']) == plan


def test_missing_array_source_withholds_energy_instead_of_using_legacy_parameters(tmp_path, monkeypatch, originals):
    from household.trajectory_energy import prepare_inputs, project
    _, args, _, snapshot = inputs(tmp_path, monkeypatch, originals)
    prepared = prepare_inputs(snapshot=snapshot,system_source=None,topology_source=args['topology_source'],horizon_source=args['horizon_source'])
    result = project(prepared,snapshot=snapshot,now=args['now'])
    assert result['output']['status'] == 'unavailable'
    assert result['output']['minimum_nominal_soc_pct'] is None
