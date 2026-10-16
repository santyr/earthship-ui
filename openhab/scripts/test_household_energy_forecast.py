"""Original-plan-bound PV/storage scenarios preserve independent source failures."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import importlib,json
import pytest
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from test_household_native_weather import made,originals
from test_household_pv_model import source as system_source
from test_household_power_flows import declaration


def fixture(tmp_path,monkeypatch,originals):
    from test_household_energy_configuration import BANK,TOPOLOGY
    from test_household_model_snapshot import source_at
    from test_household_model_pipeline import run
    from test_household_energy_persistence import metric
    from test_household_measured_weather import sources
    from household.energy_configuration import prepare_energy_configuration
    from household.measured_weather import prepare_measured_weather
    from household.measured_weather_snapshot import bind_measured_weather_snapshot
    from household.power_snapshot import compile_power_inputs
    from household.weather_snapshot import bind_weather_snapshot
    from household_pipeline import pipeline_runtime_manifest
    capture,_,thermal,weather=made(tmp_path,monkeypatch,originals);issue=instant(capture['issued_at']);at=issue-timedelta(seconds=1)
    runtime=pipeline_runtime_manifest(expanded=True,configured=True,measured=True)
    original=source_at(at)['inputs'];bundle=deepcopy(original['bundle'])
    bundle['base_inputs']['sources'][0]['source_identity']='BMS_SOC_Evidence_JSON'
    power=compile_power_inputs(bundle,managed=original['managed'],ownership=original['ownership'],code_revision=original['code_revision'],runtime_manifest=runtime)
    policy=deepcopy(TOPOLOGY);start=(at-timedelta(days=1)).isoformat();policy['cutover']=start;policy['topology']['effective_from']=start
    config=prepare_energy_configuration(bank_config_raw=canonical(BANK).decode(),ac_policy_raw=canonical(policy).decode(),bank_available_at=at,topology_available_at=at,as_of=at,created_at=at)
    measured=prepare_measured_weather(sources=sources(at),as_of=at,created_at=at)
    snap=bind_measured_weather_snapshot(source_receipt=power,source_runtime_manifest=runtime,weather_context=weather,energy_configuration=config,measured_weather=measured,code_revision='e'*40)
    plan=run(snap,thermal,runtime_manifest=runtime,energy_persistence_source=metric(at))
    api=importlib.import_module('household_energy_forecast')
    from test_household_solar_horizon import source as horizon_source
    args=dict(horizon_source=horizon_source(issue),plan_receipt=plan,system_source=system_source(issue),topology_source=declaration(issue),now=instant(plan['inputs']['now']),runtime_manifest=api.forecast_runtime_manifest())
    return api,args,plan


def test_original_native_weather_and_qualified_AC_feed_distinct_PV_storage_trajectories(tmp_path,monkeypatch,originals):
    api,args,plan=fixture(tmp_path,monkeypatch,originals);before=canonical(plan)
    out=api.seal_energy_forecast(**args)
    assert out['output']['array_pv']['status']=='projected_provisional_array_potential'
    storage=out['output']['nominal_storage']
    assert storage['status']=='conditional_nominal_simulation',storage['reason']
    assert storage['household_ac_load_w_assumption']==1000
    assert len(storage['trajectory'])==24
    assert canonical(plan)==before
    assert out['inputs']['plan_receipt_sha256']==plan['receipt_sha256']
    assert api.replay_energy_forecast(out,plan_receipt=plan,runtime_manifest=api.forecast_runtime_manifest())==out
    assert storage['balance_closed'] is False and storage['automatic_actuation'] is False


def test_missing_household_topology_keeps_PV_while_withholding_storage(tmp_path,monkeypatch,originals):
    api,args,_=fixture(tmp_path,monkeypatch,originals);args['topology_source']=None
    out=api.seal_energy_forecast(**args)['output']
    assert out['array_pv']['status']=='projected_provisional_array_potential'
    assert out['nominal_storage']['status']=='unavailable'
    assert out['nominal_storage']['reason']=='household_AC_load_unavailable'


def test_stale_soc_and_load_do_not_zero_or_restrict_the_independent_solar_model(tmp_path,monkeypatch,originals):
    api,args,_=fixture(tmp_path,monkeypatch,originals);args['now']+=timedelta(seconds=121)
    out=api.seal_energy_forecast(**args)['output']
    assert out['array_pv']['status']=='projected_provisional_array_potential'
    assert out['nominal_storage']['status']=='unavailable'
    assert out['nominal_storage']['trajectory']==[]


@pytest.mark.parametrize('damage',['source','output','plan','verifier','horizon'])
def test_changed_originals_or_executing_verifier_cannot_reseal_the_forecast(tmp_path,monkeypatch,originals,damage):
    api,args,plan=fixture(tmp_path,monkeypatch,originals);record=api.seal_energy_forecast(**args);runtime=api.forecast_runtime_manifest()
    if damage=='source':record['inputs']['system_source']['raw']+=' '
    if damage=='output':record['output']['array_pv']['potential_pv_kwh']+=1
    if damage=='plan':plan=deepcopy(plan);plan['inputs']['now']=(args['now']+timedelta(seconds=1)).isoformat();plan['receipt_sha256']=identity({k:v for k,v in plan.items() if k!='receipt_sha256'})
    if damage=='horizon':record['inputs']['horizon_source']['raw']+=' '
    if damage=='verifier':runtime.pop('openhab/scripts/household_outcomes.py');record['runtime_manifest']=runtime
    record['receipt_sha256']=identity({k:v for k,v in record.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):api.replay_energy_forecast(record,plan_receipt=plan,runtime_manifest=runtime)


def test_file_only_cli_replays_both_original_documents(tmp_path,monkeypatch,originals,capsys):
    api,args,plan=fixture(tmp_path,monkeypatch,originals);record=api.seal_energy_forecast(**args)
    receipt=tmp_path/'energy.json';original=tmp_path/'plan.json'
    for path,value in ((receipt,record),(original,plan)):path.write_bytes(canonical(value));path.chmod(0o600)
    assert api.main(['--receipt',str(receipt),'--plan',str(original)])==0
    assert loads(capsys.readouterr().out)==record
    original.write_bytes(b'{}')
    assert api.main(['--receipt',str(receipt),'--plan',str(original)])==1
    assert 'replay refused' in capsys.readouterr().err


def test_energy_receipt_replay_uses_no_live_readers_or_provider_and_keeps_external_plan(tmp_path,monkeypatch,originals):
    api,args,plan=fixture(tmp_path,monkeypatch,originals);record=api.seal_energy_forecast(**args);before=canonical(plan)
    import socket,urllib.request,psycopg2
    # Receipt verification hashes local executing sources. The frozen numerical
    # model has a separate no-file-I/O contract; this adapter forbids live data.
    def forbidden(*a,**kw):pytest.fail('live reader or provider during original receipt replay')
    monkeypatch.setattr(socket,'create_connection',forbidden);monkeypatch.setattr(urllib.request,'urlopen',forbidden);monkeypatch.setattr(psycopg2,'connect',forbidden)
    assert api.replay_energy_forecast(record,plan_receipt=plan,runtime_manifest=args['runtime_manifest'])==record
    assert canonical(plan)==before
