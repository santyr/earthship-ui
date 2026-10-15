"""Optional trajectory-based shadow receipts preserve every deployed output."""
from household.codec import canonical,loads
from test_household_native_weather import originals
import pytest


@pytest.mark.parametrize('failure',[False,True])
def test_new_shadow_domain_retains_an_original_or_isolates_failure_without_changing_v6_and_v1(tmp_path,monkeypatch,originals,failure):
    from test_household_energy_forecast import fixture
    from test_household_cycle_coordinator import setup
    import household_trajectory_plan as shadow
    _,source,plan=fixture(tmp_path,monkeypatch,originals);cycle,args,_=setup(tmp_path,monkeypatch)
    args['clock']=lambda:source['now'];args['collection']['originals']=dict(schema='earthship-household-cycle-sources/v8',load_topology_source=source['topology_source'],
        pv_system_source=source['system_source'],solar_horizon_source=source['horizon_source'],ac_load_source=None)
    monkeypatch.setattr(cycle,'derive_cycle',lambda **kw:plan)
    if failure:
        def refused(**kw):raise ValueError('optional trajectory shadow refused')
        monkeypatch.setattr(shadow,'seal_trajectory_plan',refused)
    result=cycle.complete_cycle(**args)
    assert result['status']=='observation_written' and result['energy_observation_status']=='written' and result['profiled_observation_status']=='written'
    directory=args['evidence_directory']
    assert next(directory.glob('*.household-model-plan-v6.json')).read_bytes()==canonical(plan)
    assert len(list(directory.glob('*.household-energy-forecast-v1.json')))==1
    assert len(list(directory.glob('*.household-profiled-energy-v1.json')))==1
    assert result['trajectory_shadow_status']==('unavailable' if failure else 'retained')
    paths=list(directory.glob('*.household-trajectory-shadow-v1.json'))
    assert len(paths)==(0 if failure else 1)
    if not failure:
        receipt=loads(paths[0].read_bytes());assert receipt['inputs']['plan_receipt_sha256']==plan['receipt_sha256']
        assert receipt['output']['plan_receipt']['plan']['selected_intent_ids']==[]
        assert receipt['output']['energy_projection']['basis']=='constant_load_pv'
        assert paths[0].stat().st_mode&0o777==0o600
