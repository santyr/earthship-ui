"""Expanded source/model identity survives intents and nested plan replay."""
from datetime import timedelta
import pytest
from household.codec import canonical,identity
from household.control_contracts import instant,ContractRefused
from household.snapshot import HouseholdSnapshot
from household.model_snapshot import bind_model_snapshot
from household.energy_model import freeze_energy_inputs,bind_energy_inputs
from household.legacy_pipeline import seal_pipeline,replay_pipeline
from household.legacy_planning import replay_plan
from household.intents import build_intent,intent_to_request,EFFECT_UNITS
from test_household_model_snapshot import make,source_at,NOW
from test_household_pipeline import config,pipeline
from test_household_models import FIXTURE
from test_household_planning import setup

RUNTIME={'household/pipeline.py':'a'*64,'fixture.py':'d'*64}


def run(snapshot,thermal=None,**changes):
    doc=snapshot.to_dict();now=instant(doc['created_at']);_,registry=setup()
    numerical=freeze_energy_inputs(**{**FIXTURE['cases'][0]['inputs'],'soc_pct':doc['domains']['energy']['battery_soc']['value'],
        'resource_kwh':20.,'overnight_drops_pct':[15.]})
    args=dict(snapshot=snapshot,registry=registry,energy_inputs=bind_energy_inputs(numerical,snapshot=snapshot),
        thermal_inputs=thermal,thermal_runtime=None if thermal is None else thermal.to_dict()['executing_runtime'],
        coordination=dict(schema='earthship-shadow-coordination/v1',snapshotId=snapshot.snapshot_id,horizonHours=24,baseline_soc_floor=None,facts={}),
        config=config(),now=now,runtime_manifest=RUNTIME)
    args.update(changes);return seal_pipeline(**args)


def model_free():
    source=source_at(NOW)
    return bind_model_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],thermal_inputs=None,code_revision='e'*40)


def test_expanded_energy_intents_and_nested_plan_restore_original_source():
    snap=model_free();result=run(snap);out=result['output']
    assert result['schema']=='earthship-household-model-plan-receipt/v2'
    assert set(result['inputs']['source_contexts'])=={snap.snapshot_id}
    assert out['candidate_intents'] and all(item['snapshotId']==snap.snapshot_id for item in out['candidate_intents'])
    plan=out['plan_receipt'];assert plan['schema']=='earthship-household-shadow-plan-receipt/v2'
    assert set(plan['inputs']['source_contexts'])=={snap.snapshot_id}
    assert replay_plan(plan,runtime_manifest=RUNTIME)==plan
    assert replay_pipeline(result,runtime_manifest=RUNTIME,thermal_runtime=None)==result
    assert out['plan_receipt']['plan']['selected_intent_ids']==[] and out['automatic_actuation'] is False


def test_expanded_thermal_replay_keeps_original_low_confidence_and_trajectory(tmp_path,monkeypatch):
    from household.thermal_model import project
    snap,_,thermal,_=make(tmp_path,monkeypatch);result=run(snap,thermal)
    assert result['output']['projections']['thermal']==project(thermal)
    assert result['output']['projections']['thermal']['output']['confidence']=='low'
    assert replay_pipeline(result,runtime_manifest=RUNTIME,thermal_runtime=thermal.to_dict()['executing_runtime'])==result
    with pytest.raises(ValueError):run(snap,None)
    # Retained metadata has no independent artifact qualification. A resealed
    # descriptor must still match the separately prepared original model.
    from household.model_snapshot import ModelSnapshot
    changed=snap.to_dict();changed.pop('snapshot_id')
    changed['thermal_context']['artifact_sha256']='f'*64
    changed['domains']['thermal']['thermal_artifact_identity']['value']='f'*64
    other=ModelSnapshot(canonical(changed),snap.original_source)
    with pytest.raises(ValueError):run(other,thermal)


def test_model_metadata_cannot_be_used_as_physical_action_evidence(tmp_path,monkeypatch):
    snap,_,_,_=make(tmp_path,monkeypatch);doc=snap.to_dict();at=instant(doc['created_at'])
    body=dict(schema='earthship-household-intent/v1',type='RUN_GREYWATER_CYCLE',createdAt=at.isoformat(),
        expiresAt=(at+timedelta(seconds=120)).isoformat(),snapshotId=snap.snapshot_id,
        evidenceRefs=[doc['domains']['thermal']['thermal_artifact_identity']['evidence']['digest']],
        predictedEffects={key:None for key in EFFECT_UNITS},confidence='unavailable',reasonCodes=['unqualified_effect'],shadowOnly=True,parameters={})
    with pytest.raises(ContractRefused) as error:build_intent(body,snapshot=snap,now=at)
    assert error.value.reason_code=='source_unavailable'


def test_generic_snapshot_cannot_impersonate_model_bound_context():
    snap=model_free();forged=HouseholdSnapshot(snap.content)
    with pytest.raises((ValueError,ContractRefused)):run(forged)


@pytest.mark.parametrize('damage',['source','missing','extra','projection','runtime'])
def test_resealed_expanded_pipeline_refuses_original_or_derived_drift(damage):
    snap=model_free();result=run(snap)
    if damage=='source':result['inputs']['source_contexts'][snap.snapshot_id]['snapshot']['domains']['energy']['battery_soc']['value']=0
    elif damage=='missing':result['inputs']['source_contexts']={}
    elif damage=='extra':result['inputs']['source_contexts']['f'*64]=snap.source_receipt
    elif damage=='projection':result['output']['projections']['energy']['output']['trough_pred']=0
    else:result['runtime_manifest']['household/pipeline.py']='f'*64
    result['receipt_sha256']=identity({k:v for k,v in result.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):replay_pipeline(result,runtime_manifest=RUNTIME,thermal_runtime=None)


def test_expanded_stale_sources_do_not_generate_proposals():
    snap=model_free();result=run(snap,now=NOW+timedelta(seconds=101))
    assert result['output']['candidate_intents']==[] and result['output']['candidate_generation']['reason']=='source_stale'


def test_v1_pipeline_keeps_original_receipt_version_and_input_shape():
    result=pipeline()
    assert result['schema']=='earthship-household-model-plan-receipt/v1'
    assert set(result['inputs'])=={'snapshot','registry','energy_inputs','thermal_inputs','coordination','config','now'}
    assert result['output']['plan_receipt']['schema']=='earthship-household-shadow-plan-receipt/v1'
    assert replay_pipeline(result,runtime_manifest=result['runtime_manifest'],thermal_runtime=None)==result


def test_translator_stays_disabled_for_expanded_intents():
    snap=model_free();result=run(snap);from household.intents import parse_intent
    item=parse_intent(canonical(result['output']['no_action_intent']).decode(),snapshot=snap,now=NOW)
    with pytest.raises(ContractRefused) as error:intent_to_request(item)
    assert error.value.reason_code=='planner_authority_disabled'


def test_original_source_runtime_must_match_executing_planner():
    with pytest.raises(ValueError):run(model_free(),runtime_manifest={'household/pipeline.py':'a'*64})


def test_expanded_replay_performs_no_file_or_database_reads(monkeypatch):
    import builtins,psycopg2
    from pathlib import Path
    result=run(model_free())
    def forbidden(*args,**kwargs):pytest.fail('read inside expanded replay')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden);monkeypatch.setattr(psycopg2,'connect',forbidden)
    assert replay_pipeline(result,runtime_manifest=RUNTIME,thermal_runtime=None)==result


def test_private_expanded_pipeline_cli_validates_full_source_closure(tmp_path):
    import subprocess,sys
    from pathlib import Path
    from household_pipeline import pipeline_runtime_manifest
    from household.power_snapshot import compile_power_inputs
    source=source_at(NOW);runtime=pipeline_runtime_manifest(expanded=True);original=source['inputs']
    source=compile_power_inputs(original['bundle'],managed=original['managed'],ownership=original['ownership'],
        code_revision=original['code_revision'],runtime_manifest=runtime)
    snap=bind_model_snapshot(source_receipt=source,source_runtime_manifest=runtime,thermal_inputs=None,code_revision='e'*40)
    receipt=run(snap,runtime_manifest=runtime);path=tmp_path/'expanded.json';path.write_bytes(canonical(receipt));path.chmod(0o600)
    cli=Path(__file__).with_name('household_pipeline.py')
    result=subprocess.run([sys.executable,str(cli),'--receipt',str(path)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    import json
    assert json.loads(result.stdout)==receipt
    # A self-consistent partial original producer manifest is still insufficient
    # for operational replay, even when all hashes it retained are correct.
    partial={'openhab/scripts/household/power_snapshot.py':runtime['openhab/scripts/household/power_snapshot.py']}
    source=compile_power_inputs(original['bundle'],managed=original['managed'],ownership=original['ownership'],
        code_revision=original['code_revision'],runtime_manifest=partial)
    snap=bind_model_snapshot(source_receipt=source,source_runtime_manifest=partial,thermal_inputs=None,code_revision='e'*40)
    receipt=run(snap,runtime_manifest=runtime);path.write_bytes(canonical(receipt))
    refused=subprocess.run([sys.executable,str(cli),'--receipt',str(path)],capture_output=True,text=True,timeout=10)
    assert refused.returncode==1 and not refused.stdout


def test_expanded_plan_cli_restores_nested_original_sources(tmp_path):
    import subprocess,sys,json
    from pathlib import Path
    from household_pipeline import pipeline_runtime_manifest
    from household.power_snapshot import compile_power_inputs
    original=source_at(NOW)['inputs'];runtime=pipeline_runtime_manifest(expanded=True)
    source=compile_power_inputs(original['bundle'],managed=original['managed'],ownership=original['ownership'],code_revision=original['code_revision'],runtime_manifest=runtime)
    snap=bind_model_snapshot(source_receipt=source,source_runtime_manifest=runtime,thermal_inputs=None,code_revision='e'*40)
    receipt=run(snap,runtime_manifest=runtime)['output']['plan_receipt'];path=tmp_path/'plan.json';path.write_bytes(canonical(receipt));path.chmod(0o600)
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('household_plan.py')),'--receipt',str(path)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)==receipt


def test_expanded_outcome_entrypoint_checks_enclosing_pipeline_source_closure(tmp_path,monkeypatch):
    from test_household_outcomes import inputs
    from household.outcomes import seal_outcomes
    from household.power_snapshot import compile_power_inputs
    from household_pipeline import pipeline_runtime_manifest
    from household_outcomes import original_plan_runtime,outcome_runtime_manifest
    args=inputs(tmp_path,monkeypatch);thermal=args['origin'].prepared;at=instant(thermal.to_dict()['issue'])
    original=source_at(at)['inputs'];runtime=pipeline_runtime_manifest(expanded=True);actual=outcome_runtime_manifest()
    def outcome(producer):
        source=compile_power_inputs(original['bundle'],managed=original['managed'],ownership=original['ownership'],code_revision=original['code_revision'],runtime_manifest=producer)
        snap=bind_model_snapshot(source_receipt=source,source_runtime_manifest=producer,thermal_inputs=thermal,code_revision='e'*40)
        plan=run(snap,thermal,runtime_manifest=runtime)
        return seal_outcomes(**{**args,'plan_receipt':plan,'plan_runtime_manifest':runtime,'outcome_runtime_manifest':actual})
    valid=outcome(runtime)
    assert valid['inputs']['plan_receipt']['schema']=='earthship-household-model-plan-receipt/v2'
    assert original_plan_runtime(valid['inputs']['plan_receipt'],actual=actual)==runtime
    partial={'openhab/scripts/household/power_snapshot.py':runtime['openhab/scripts/household/power_snapshot.py']}
    incomplete=outcome(partial)
    with pytest.raises(ValueError):original_plan_runtime(incomplete['inputs']['plan_receipt'],actual=actual)
