"""Original bank/topology lineage binds energy without calibrating capacity."""
import importlib,json
from datetime import timedelta
from pathlib import Path
import pytest
from household.codec import canonical,identity
from household.control_contracts import instant,ContractRefused
from test_household_weather_pipeline import make as weather_snapshot
from test_household_energy_configuration import BANK,TOPOLOGY
from test_household_model_pipeline import run as run_pipeline,RUNTIME


def api():return importlib.import_module('household.energy_source_snapshot')


def make(tmp_path,monkeypatch,*,bank_raw='default',topology_raw='default',source=None,configuration_lag=0):
    from household.energy_configuration import prepare_energy_configuration
    original,weather,prepared,capture=weather_snapshot(tmp_path,monkeypatch);at=instant(prepared.to_dict()['issue'])
    policy=json.loads(json.dumps(TOPOLOGY));start=(at-timedelta(days=1)).isoformat()
    policy['cutover']=start;policy['topology']['effective_from']=start
    context=prepare_energy_configuration(bank_config_raw=json.dumps(BANK) if bank_raw=='default' else bank_raw,
        ac_policy_raw=json.dumps(policy) if topology_raw=='default' else topology_raw,
        bank_available_at=at-timedelta(seconds=2),topology_available_at=at-timedelta(seconds=1),as_of=at,created_at=at+timedelta(seconds=configuration_lag))
    source=original.source_receipt if source is None else source(at)
    snap=api().bind_energy_source_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],
        weather_context=weather,energy_configuration=context,code_revision='e'*40)
    return snap,context,prepared,capture


def test_declared_bank_and_source_bound_household_ac_load_share_original_clock(tmp_path,monkeypatch):
    snap,context,prepared,_=make(tmp_path,monkeypatch);doc=snap.to_dict();energy=doc['domains']['energy']
    assert doc['schema']=='earthship-household-snapshot/v5' and doc['as_of']==prepared.to_dict()['issue']
    assert doc['domains']['thermal']['mass_temperature']==prepared.to_dict()['snapshot']['domains']['thermal']['mass_temperature']
    assert energy['physical_bank_epoch']['value']=='discover_4_module_2026'
    assert energy['nominal_bank_kwh']['value']==20.48 and energy['usable_battery_kwh']['value'] is None
    assert energy['physical_bank_epoch']['evidence']['quality']=='retained_configuration_context'
    load=energy['estimated_load_w'];ac=energy['inverter_output_w']
    assert load['value']==ac['value'] and load['unit']=='W' and load['basis']=='inverter_only_no_bypass_or_generator'
    assert load['evidence']['digest']!=ac['evidence']['digest']
    assert ac['evidence']['digest'] in load['evidence']['parent_digests']
    for key in ('observed_at','received_at','available_at','valid_until','source_epoch'):
        assert load['evidence'][key]==ac['evidence'][key]
    assert context.to_dict()['configuration_sha256'] in load['evidence']['parent_digests']
    assert doc['completeness']['household_ac_load'] is True and doc['completeness']['full_energy'] is False
    assert doc['planner_authority']=='none'


def test_all_original_contexts_and_nominal_energy_binding_replay_without_authority(tmp_path,monkeypatch):
    from household.pipeline import replay_pipeline
    from household.planning import replay_plan
    snap,context,prepared,capture=make(tmp_path,monkeypatch);receipt=run_pipeline(snap,prepared)
    assert receipt['schema']=='earthship-household-model-plan-receipt/v4'
    origin=receipt['inputs']['energy_inputs'];assert origin['schema']=='earthship-household-prepared-energy/v2'
    binding=origin['configuration_binding'];assert binding['status']=='bound' and binding['nominal_bank_kwh']==20.48
    assert binding['configuration_sha256']==context.to_dict()['configuration_sha256']
    assert receipt['output']['projections']['thermal']['output']==capture['output']
    assert receipt['output']['projections']['energy']['input_qualification']=='not_assessed'
    assert receipt['output']['projections']['energy']['collection_binding']['configuration_binding']==binding
    assert receipt['output']['plan_receipt']['schema']=='earthship-household-shadow-plan-receipt/v4'
    assert replay_plan(receipt['output']['plan_receipt'],runtime_manifest=RUNTIME)==receipt['output']['plan_receipt']
    assert replay_pipeline(receipt,runtime_manifest=RUNTIME,thermal_runtime=prepared.to_dict()['executing_runtime'])==receipt
    assert receipt['output']['plan_receipt']['plan']['selected_intent_ids']==[] and receipt['output']['automatic_actuation'] is False


def test_configuration_context_cannot_authorize_physical_action(tmp_path,monkeypatch):
    from household.intents import build_intent,EFFECT_UNITS
    snap,_,_,_=make(tmp_path,monkeypatch);doc=snap.to_dict();at=instant(doc['created_at'])
    body=dict(schema='earthship-household-intent/v1',type='RUN_GREYWATER_CYCLE',createdAt=at.isoformat(),
        expiresAt=(at+timedelta(seconds=120)).isoformat(),snapshotId=snap.snapshot_id,
        evidenceRefs=[doc['domains']['energy']['nominal_bank_kwh']['evidence']['digest']],
        predictedEffects={key:None for key in EFFECT_UNITS},confidence='unavailable',reasonCodes=['unqualified_effect'],shadowOnly=True,parameters={})
    with pytest.raises(ContractRefused) as error:build_intent(body,snapshot=snap,now=at)
    assert error.value.reason_code=='source_unavailable'


def test_frozen_configuration_pipeline_replay_has_no_live_reads(tmp_path,monkeypatch):
    snap,_,prepared,_=make(tmp_path,monkeypatch);receipt=run_pipeline(snap,prepared)
    import builtins,psycopg2
    def forbidden(*args,**kwargs):pytest.fail('I/O within frozen energy source boundary')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden);monkeypatch.setattr(psycopg2,'connect',forbidden)
    from household.pipeline import replay_pipeline
    assert replay_pipeline(receipt,runtime_manifest=RUNTIME,thermal_runtime=prepared.to_dict()['executing_runtime'])==receipt


def test_missing_topology_retains_bank_without_claiming_load_basis(tmp_path,monkeypatch):
    snap,_,_,_=make(tmp_path,monkeypatch,topology_raw=None);energy=snap.to_dict()['domains']['energy']
    assert energy['physical_bank_epoch']['value']=='discover_4_module_2026'
    assert energy['estimated_load_w']['value'] is None and energy['estimated_load_w']['basis'] is None
    assert snap.to_dict()['completeness']['household_ac_load'] is False


def test_configuration_completion_is_included_in_snapshot_availability(tmp_path,monkeypatch):
    snap,_,prepared,_=make(tmp_path,monkeypatch,configuration_lag=10)
    assert instant(snap.to_dict()['created_at'])==instant(prepared.to_dict()['issue'])+timedelta(seconds=10)


def test_operational_energy_source_closure_and_cli_restore(tmp_path,monkeypatch):
    import subprocess,sys,os
    from household_pipeline import pipeline_runtime_manifest,verify_source_closure
    from household.power_snapshot import compile_power_inputs
    from household_outcomes import original_plan_runtime,outcome_runtime_manifest
    snap,context,prepared,_=make(tmp_path,monkeypatch);runtime=pipeline_runtime_manifest(expanded=True,configured=True)
    original=snap.source_receipt['inputs']
    source=compile_power_inputs(original['bundle'],managed=original['managed'],ownership=original['ownership'],
        code_revision=original['code_revision'],runtime_manifest=runtime)
    snap=api().bind_energy_source_snapshot(source_receipt=source,source_runtime_manifest=runtime,weather_context=snap.weather,
        energy_configuration=context,code_revision='e'*40)
    receipt=run_pipeline(snap,prepared,runtime_manifest=runtime)
    verify_source_closure(receipt,runtime)
    assert original_plan_runtime(receipt,actual=outcome_runtime_manifest())==runtime
    assert 'openhab/scripts/advisory_windows.py' in runtime
    environment={**os.environ,'PYTHONPATH':os.pathsep.join(value for value in sys.path if value)}
    for name,record in [('household_pipeline.py',receipt),('household_plan.py',receipt['output']['plan_receipt'])]:
        path=tmp_path/(name+'.json');path.write_bytes(canonical(record));path.chmod(0o600)
        result=subprocess.run([sys.executable,str(Path(__file__).with_name(name)),'--receipt',str(path)],capture_output=True,text=True,timeout=60,env=environment)
        assert result.returncode==0,result.stderr
        assert json.loads(result.stdout)==record
    partial={k:v for k,v in runtime.items() if k!='openhab/scripts/advisory_windows.py'}
    with pytest.raises(ValueError):original_plan_runtime(receipt,actual=partial)


def test_derived_load_reference_expires_at_finite_topology_end(tmp_path,monkeypatch):
    from test_installed_shade_origin import ISSUE
    from household.intents import build_intent,EFFECT_UNITS
    policy=json.loads(json.dumps(TOPOLOGY));end=ISSUE+timedelta(seconds=5)
    policy['topology']['effective_until']=end.isoformat()
    snap,_,_,_=make(tmp_path,monkeypatch,topology_raw=json.dumps(policy));doc=snap.to_dict()
    load=doc['domains']['energy']['estimated_load_w'];ac=doc['domains']['energy']['inverter_output_w']
    assert instant(load['evidence']['valid_until'])==end<instant(ac['evidence']['valid_until'])
    at=ISSUE+timedelta(seconds=6)
    body=dict(schema='earthship-household-intent/v1',type='RUN_GREYWATER_CYCLE',createdAt=at.isoformat(),
        expiresAt=(at+timedelta(seconds=120)).isoformat(),snapshotId=snap.snapshot_id,
        evidenceRefs=[load['evidence']['digest']],predictedEffects={key:None for key in EFFECT_UNITS},
        confidence='unavailable',reasonCodes=['unqualified_effect'],shadowOnly=True,parameters={})
    with pytest.raises(ContractRefused) as error:build_intent(body,snapshot=snap,now=at)
    assert error.value.reason_code=='source_stale'


def test_expired_ac_remains_unavailable_after_topology_binding(tmp_path,monkeypatch):
    from test_household_model_snapshot import source_at
    snap,_,_,_=make(tmp_path,monkeypatch,source=lambda at:source_at(at-timedelta(seconds=31)))
    energy=snap.to_dict()['domains']['energy']
    assert energy['estimated_load_w']['value'] is None and energy['estimated_load_w']['reason']=='expired_source'
    assert snap.to_dict()['completeness']['household_ac_load'] is False


def test_missing_bank_retains_original_load_and_explicit_unbound_energy(tmp_path,monkeypatch):
    snap,_,prepared,_=make(tmp_path,monkeypatch,bank_raw=None);doc=snap.to_dict();receipt=run_pipeline(snap,prepared)
    assert doc['domains']['energy']['physical_bank_epoch']['value'] is None
    assert doc['completeness']['household_ac_load'] is True
    assert receipt['inputs']['energy_inputs']['configuration_binding']['status']=='unavailable'
    assert receipt['output']['projections']['energy']['input_qualification']=='not_assessed'


def test_mismatched_or_legacy_energy_binding_cannot_bypass_nominal_configuration(tmp_path,monkeypatch):
    from household.energy_model import freeze_energy_inputs,bind_energy_inputs,PreparedEnergyInputs
    snap,_,prepared,_=make(tmp_path,monkeypatch);receipt=run_pipeline(snap,prepared)
    numerical=receipt['inputs']['energy_inputs']['numerical_inputs']['inputs']
    with pytest.raises(ValueError):bind_energy_inputs(freeze_energy_inputs(**{**numerical,'bank_kwh':40.}),snapshot=snap)
    origin=receipt['inputs']['energy_inputs'];origin.pop('configuration_binding');origin['schema']='earthship-household-prepared-energy/v1'
    with pytest.raises(ValueError):run_pipeline(snap,prepared,energy_inputs=PreparedEnergyInputs(canonical(origin)))


@pytest.mark.parametrize('damage',['configuration','projection','binding','candidate_context','unused_snapshot'])
def test_resealed_configured_receipt_cannot_detach_originals_or_candidates(damage,tmp_path,monkeypatch):
    from household.pipeline import replay_pipeline
    snap,_,prepared,_=make(tmp_path,monkeypatch);receipt=run_pipeline(snap,prepared)
    if damage=='configuration':receipt['inputs']['source_contexts'][snap.snapshot_id]['energy_configuration']['bank_source']['raw']='invalid'
    elif damage=='projection':receipt['output']['projections']['energy_configuration']['bank']['nominal_usable_kwh']=40.
    elif damage=='binding':receipt['inputs']['energy_inputs']['configuration_binding']['configuration_sha256']='f'*64
    elif damage=='candidate_context':receipt['output']['plan_receipt']['inputs']['candidates'][0]['validation_snapshot_id']='f'*64
    else:receipt['output']['plan_receipt']['inputs']['validation_snapshots']['f'*64]=snap.to_dict()
    receipt['receipt_sha256']=identity({k:v for k,v in receipt.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):replay_pipeline(receipt,runtime_manifest=RUNTIME,thermal_runtime=prepared.to_dict()['executing_runtime'])


def test_earlier_pipeline_versions_keep_their_original_shapes(tmp_path,monkeypatch):
    from test_household_pipeline import pipeline
    from test_household_model_pipeline import model_free
    old,_,prepared,_=weather_snapshot(tmp_path,monkeypatch)
    assert pipeline()['schema']=='earthship-household-model-plan-receipt/v1'
    assert run_pipeline(model_free())['schema']=='earthship-household-model-plan-receipt/v2'
    result=run_pipeline(old,prepared);assert result['schema']=='earthship-household-model-plan-receipt/v3'
    assert set(result['output']['projections'])=={'energy','thermal','weather'}
    assert result['inputs']['energy_inputs']['schema']=='earthship-household-prepared-energy/v1'


@pytest.mark.parametrize('raw',[None,'invalid receipt'])
def test_absent_or_invalid_ac_does_not_discard_bank_or_invent_parent_digest(raw,tmp_path,monkeypatch):
    from hashlib import sha256
    from test_installed_shade_origin import ISSUE
    from test_household_model_snapshot import source_at
    from household.power_snapshot import compile_power_inputs
    def altered(at):
        original=source_at(at);value=original['inputs']
        for row in value['bundle']['power_sources']:
            if row['kind']=='inverter_ac':
                row['raw']=raw;row['expected_sha256']=None if raw is None else sha256(raw.encode()).hexdigest()
        return compile_power_inputs(value['bundle'],managed=value['managed'],ownership=value['ownership'],
            code_revision=value['code_revision'],runtime_manifest=original['runtime_manifest'])
    policy=json.loads(json.dumps(TOPOLOGY));policy['topology']['effective_until']=(ISSUE+timedelta(seconds=5)).isoformat()
    snap,_,_,_=make(tmp_path,monkeypatch,topology_raw=json.dumps(policy),source=altered)
    energy=snap.to_dict()['domains']['energy'];load=energy['estimated_load_w']
    assert energy['physical_bank_epoch']['value']=='discover_4_module_2026'
    assert load['value'] is None and load['reason'] in ('missing_source','source_unqualified')
    assert all(isinstance(value,str) and len(value)==64 for value in load['evidence']['parent_digests'])
    if raw is None:assert load['evidence']['digest'] is None


def test_pre_topology_observation_cannot_become_household_load(tmp_path,monkeypatch):
    from test_installed_shade_origin import ISSUE
    from test_household_model_snapshot import source_at
    policy=json.loads(json.dumps(TOPOLOGY));start=(ISSUE-timedelta(seconds=1)).isoformat()
    policy['cutover']=start;policy['topology']['effective_from']=start
    snap,_,_,_=make(tmp_path,monkeypatch,topology_raw=json.dumps(policy),source=lambda at:source_at(at-timedelta(seconds=2)))
    doc=snap.to_dict();energy=doc['domains']['energy']
    assert energy['inverter_output_w']['value'] is not None
    assert energy['estimated_load_w']['value'] is None
    assert energy['estimated_load_w']['reason']=='observation_outside_topology'
    assert doc['completeness']['household_ac_load'] is False
    assert energy['physical_bank_epoch']['value']=='discover_4_module_2026'


def test_omitted_inverter_source_and_policy_age_preserve_bank(tmp_path,monkeypatch):
    from test_household_model_snapshot import source_at
    from household.power_snapshot import compile_power_inputs
    def without_inverter(at):
        receipt=source_at(at);original=receipt['inputs'];bundle=original['bundle']
        bundle['power_sources']=[row for row in bundle['power_sources'] if row['kind']!='inverter_ac']
        bundle['power_policy']['max_age_seconds'].pop('inverter_output_w')
        return compile_power_inputs(bundle,managed=original['managed'],ownership=original['ownership'],
            code_revision=original['code_revision'],runtime_manifest=receipt['runtime_manifest'])
    snap,_,_,_=make(tmp_path,monkeypatch,source=without_inverter);doc=snap.to_dict()
    assert doc['domains']['energy']['physical_bank_epoch']['value']=='discover_4_module_2026'
    assert doc['domains']['energy']['estimated_load_w']['value'] is None
    assert doc['completeness']['household_ac_load'] is False
    assert 'estimated_load_w' not in doc['temporal_policy']['max_age_seconds']
