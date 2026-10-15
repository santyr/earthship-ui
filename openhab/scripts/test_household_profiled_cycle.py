"""Optional learned-load scenarios preserve the original scheduled forecasts."""
from datetime import timedelta
from household.codec import canonical,loads
from household.control_contracts import instant
from test_household_native_weather import originals
from test_household_pv_model import source as system_source
from test_household_solar_horizon import source as horizon_source
import pytest


def test_missing_load_artifact_is_explicit_and_keeps_all_existing_collector_domains(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    import household_ac_load_store as store
    def missing(*a,**kw):raise FileNotFoundError('no scheduled load model yet')
    monkeypatch.setattr(store,'read_current',missing)
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch)
    value=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert value['schema']=='earthship-household-cycle-sources/v8' and value['ac_load_source'] is None
    assert value['power_receipt']['snapshot']['domains']['energy']['inverter_output_w']['value']==1000


def test_new_load_original_does_not_change_existing_plan_or_v1_projections(tmp_path,monkeypatch):
    from test_household_cycle import derived_fixture
    from test_household_energy_persistence import metric
    from test_household_power_flows import declaration
    from household_cycle import derive_cycle
    args,capture=derived_fixture(tmp_path,monkeypatch);at=instant(capture['issued_at'])
    args['originals'].update(schema='earthship-household-cycle-sources/v7',daily_energy_source=None,owner_source=None,policy_source=None,
        energy_persistence_source=metric(at-timedelta(seconds=2)),load_topology_source=declaration(at),pv_system_source=system_source(at-timedelta(seconds=2)),solar_horizon_source=horizon_source(at-timedelta(seconds=2)))
    previous=derive_cycle(**args)
    args['originals'].update(schema='earthship-household-cycle-sources/v8',ac_load_source=None)
    assert derive_cycle(**args)==previous
    args['originals']['ac_load_source']={'available_at':at.isoformat()}
    with pytest.raises(ValueError):derive_cycle(**args)


@pytest.mark.parametrize('optional_failure',[False,True])
def test_cycle_keeps_original_energy_and_observation_while_retaining_separate_load_receipt(tmp_path,monkeypatch,originals,optional_failure):
    from test_household_energy_forecast import fixture
    from test_household_cycle_coordinator import setup
    import household_profiled_forecast as profiled
    _,source,plan=fixture(tmp_path,monkeypatch,originals);cycle,args,_=setup(tmp_path,monkeypatch)
    args['clock']=lambda:source['now'];args['collection']['originals']=dict(schema='earthship-household-cycle-sources/v8',load_topology_source=source['topology_source'],
        pv_system_source=source['system_source'],solar_horizon_source=source['horizon_source'],ac_load_source=None)
    monkeypatch.setattr(cycle,'derive_cycle',lambda **kw:plan)
    if optional_failure:
        def failed(**kw):raise ValueError('optional profiled model refused')
        monkeypatch.setattr(profiled,'seal_profiled_forecast',failed)
    value=cycle.complete_cycle(**args)
    assert value['status']=='observation_written' and value['energy_observation_status']=='written'
    assert len(list(args['evidence_directory'].glob('*.household-energy-forecast-v1.json')))==1
    assert next(args['evidence_directory'].glob('*.household-model-plan-v6.json')).read_bytes()==canonical(plan)
    if optional_failure:
        assert value['profiled_energy_status']=='unavailable'
    else:
        path=next(args['evidence_directory'].glob('*.household-profiled-energy-v1.json'));receipt=loads(path.read_bytes())
        assert receipt['output']['reason']=='load_model_unavailable' and value['profiled_energy_status']=='retained'
        assert path.stat().st_mode&0o777==0o600


def test_profile_observation_uses_its_separate_owned_cache(tmp_path,monkeypatch,originals):
    from test_household_energy_forecast import fixture
    from test_household_cycle_coordinator import setup
    _,source,plan=fixture(tmp_path,monkeypatch,originals);cycle,args,_=setup(tmp_path,monkeypatch)
    args['clock']=lambda:source['now'];args['collection']['originals']=dict(schema='earthship-household-cycle-sources/v8',load_topology_source=source['topology_source'],
        pv_system_source=source['system_source'],solar_horizon_source=source['horizon_source'],ac_load_source=None)
    monkeypatch.setattr(cycle,'derive_cycle',lambda **kw:plan)
    value=cycle.complete_cycle(**args)
    assert value['profiled_observation_status']=='written'
    path=args['observation_cache'].parent/'profiled-energy-observation.json';view=loads(path.read_bytes())
    assert view['status']=='unavailable' and view['reason']=='load_model_unavailable'
    assert view['cohort_id'] is None and path.stat().st_mode&0o777==0o600
