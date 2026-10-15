"""Scheduled PV observation retains originals without altering existing plans."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import subprocess
import pytest
from household.codec import loads,canonical
from household.control_contracts import instant
from test_household_pv_model import source as system_source
from test_household_solar_horizon import source as horizon_source


def test_collector_retains_and_brackets_original_array_and_terrain_files(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    from test_forecast_pre_dusk import NOW
    system=system_source(NOW);horizon=horizon_source(NOW)
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch,pv_system_raw=system['raw'],solar_horizon_raw=horizon['raw'])
    out=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert out['schema']=='earthship-household-cycle-sources/v8'
    assert out['pv_system_source']['raw']==system['raw'] and out['solar_horizon_source']['raw']==horizon['raw']
    reader=collector.owner_reader
    def changed(*a,**kw):
        result=reader(*a,**kw);(tmp_path/'solar_horizon_path.json').write_text(horizon['raw']+' ');return result
    collector.owner_reader=changed
    with pytest.raises(ValueError):collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)


def test_bad_optional_array_or_map_preserves_other_source_domains(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch,pv_system_raw='{',solar_horizon_raw='{')
    out=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert out['pv_system_source'] is None and out['solar_horizon_source'] is None
    assert out['power_receipt']['snapshot']['domains']['energy']['inverter_output_w']['value']==1000


def test_new_sources_leave_original_plan_and_battery_baseline_identical(tmp_path,monkeypatch):
    from test_household_cycle import derived_fixture
    from test_household_energy_persistence import metric
    from test_household_power_flows import declaration
    from household_cycle import derive_cycle
    args,capture=derived_fixture(tmp_path,monkeypatch);at=instant(capture['issued_at'])
    args['originals'].update(schema='earthship-household-cycle-sources/v6',daily_energy_source=None,owner_source=None,policy_source=None,
        energy_persistence_source=metric(at-timedelta(seconds=2)),load_topology_source=declaration(at))
    old=derive_cycle(**args)
    args['originals'].update(schema='earthship-household-cycle-sources/v7',pv_system_source=system_source(at-timedelta(seconds=2)),solar_horizon_source=horizon_source(at-timedelta(seconds=2)))
    assert derive_cycle(**args)==old
    args['originals']['solar_horizon_source']['available_at']=at.isoformat()
    with pytest.raises(ValueError):derive_cycle(**args)


def test_complete_cycle_retains_original_plan_flows_and_exact_replayable_PV_receipt(tmp_path,monkeypatch,originals):
    from test_household_energy_forecast import fixture
    from test_household_cycle_coordinator import setup
    import household_energy_forecast as forecast
    _,original_args,plan=fixture(tmp_path,monkeypatch,originals)
    cycle,args,_=setup(tmp_path,monkeypatch)
    args['clock']=lambda:original_args['now']
    args['collection']['originals']=dict(schema='earthship-household-cycle-sources/v7',load_topology_source=original_args['topology_source'],
        pv_system_source=original_args['system_source'],solar_horizon_source=original_args['horizon_source'])
    monkeypatch.setattr(cycle,'derive_cycle',lambda **kw:plan)
    out=cycle.complete_cycle(**args);assert out['status']=='observation_written'
    path=next(args['evidence_directory'].glob('*.household-energy-forecast-v1.json'));receipt=loads(path.read_bytes())
    assert receipt['output']['array_pv']['terrain_status']=='unvalidated_map_estimate'
    assert receipt['output']['nominal_storage']['status']=='conditional_nominal_simulation'
    assert forecast.replay_energy_forecast(receipt,plan_receipt=plan,runtime_manifest=forecast.forecast_runtime_manifest())==receipt
    saved=next(args['evidence_directory'].glob('*.household-model-plan-v6.json'))
    assert saved.read_bytes()==canonical(plan) and path.stat().st_mode&0o777==0o600
    assert len(list(args['evidence_directory'].glob('*.household-power-flow-v1.json')))==1


@pytest.mark.parametrize('name',['household-pv-system.json','household-solar-horizon.json'])
def test_committed_packaging_binds_array_and_map_configuration(tmp_path,name):
    from test_household_cycle_deploy import fixture,api,write
    args,_=fixture(tmp_path);repo=args['repo_root'];source=repo/'openhab'/name
    write(source,b'{"original":"provisional configuration"}',0o644)
    subprocess.run(['git','-C',str(repo),'add',str(source)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','solar config'],check=True,capture_output=True)
    args['code_revision']=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    api().stage_deployment(**args);staged=args['stage']/'sources/openhab'/name
    assert staged.read_bytes()==source.read_bytes()
    staged.write_bytes(b'{}')
    with pytest.raises(ValueError):api().verify_stage(args['stage'])


from test_household_native_weather import originals
