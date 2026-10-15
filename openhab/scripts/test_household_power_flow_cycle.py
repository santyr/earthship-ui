"""Production flow observations remain beside, rather than altering, forecast plans."""
from datetime import timedelta
from pathlib import Path
from hashlib import sha256
import json,subprocess
import pytest
from household.codec import canonical,loads
from household.control_contracts import instant
from test_household_power_flows import declaration


def test_collector_retains_original_topology_and_refuses_midcycle_replacement(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    from test_forecast_pre_dusk import NOW
    source=declaration(NOW);raw=source['raw']
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch,load_topology_raw=raw)
    result=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert result['schema']=='earthship-household-cycle-sources/v6'
    assert result['load_topology_source']['raw']==raw
    assert result['load_topology_source']['sha256']==sha256(raw.encode()).hexdigest()
    reader=collector.owner_reader
    def changed(*a,**kw):
        out=reader(*a,**kw);(tmp_path/'household-energy-topology.json').write_text(raw+' ');return out
    collector.owner_reader=changed
    with pytest.raises(ValueError):collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)


def test_new_source_version_preserves_original_plan_and_battery_baseline(tmp_path,monkeypatch):
    from test_household_cycle import derived_fixture
    from test_household_energy_persistence import metric
    from household_cycle import derive_cycle
    args,capture=derived_fixture(tmp_path,monkeypatch);at=instant(capture['issued_at'])
    args['originals'].update(schema='earthship-household-cycle-sources/v5',daily_energy_source=None,owner_source=None,policy_source=None,energy_persistence_source=metric(at-timedelta(seconds=2)))
    old=derive_cycle(**args)
    args['originals'].update(schema='earthship-household-cycle-sources/v6',load_topology_source=declaration(at))
    assert derive_cycle(**args)==old
    args['originals']['load_topology_source']['available_at']=at.isoformat()
    with pytest.raises(ValueError):derive_cycle(**args)


def test_complete_cycle_retains_a_replayable_flow_sidecar_without_changing_plan(tmp_path,monkeypatch):
    from test_household_energy_persistence import pipeline_fixture
    from test_household_cycle_coordinator import setup
    import household_power_flows as flows
    _,plan,_,_=pipeline_fixture(tmp_path,monkeypatch);at=instant(plan['inputs']['snapshot']['as_of'])
    cycle,args,_=setup(tmp_path,monkeypatch)
    args['collection']['originals']=dict(schema='earthship-household-cycle-sources/v6',load_topology_source=declaration(at))
    monkeypatch.setattr(cycle,'derive_cycle',lambda **kw:plan)
    out=cycle.complete_cycle(**args);assert out['status']=='observation_written'
    path=next(iter(args['evidence_directory'].glob('*.household-power-flow-v1.json')))
    receipt=loads(path.read_bytes())
    assert receipt['output']['household_load_w']==1000 and receipt['output']['battery_discharge_w']==500
    assert receipt['inputs']['plan_receipt_sha256']==plan['receipt_sha256']
    assert flows.replay_flow_receipt(receipt,plan_receipt=plan,runtime_manifest=flows.flow_runtime_manifest())==receipt
    saved=next(iter(args['evidence_directory'].glob('*.household-model-plan-v6.json')))
    assert saved.read_bytes()==canonical(plan) and (path.stat().st_mode & 0o777)==0o600


def test_packaging_retains_and_verifies_the_exact_operator_declaration(tmp_path):
    from test_household_cycle_deploy import fixture,api,write
    args,_=fixture(tmp_path);repo=args['repo_root'];source=repo/'openhab/household-energy-topology.json'
    write(source,b'{"original":"operator topology"}',0o644)
    subprocess.run(['git','-C',str(repo),'add',str(source)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','topology'],check=True,capture_output=True)
    args['code_revision']=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    api().stage_deployment(**args);staged=args['stage']/'sources/openhab/household-energy-topology.json'
    assert staged.read_bytes()==source.read_bytes()
    staged.write_bytes(b'{}')
    with pytest.raises(ValueError):api().verify_stage(args['stage'])
