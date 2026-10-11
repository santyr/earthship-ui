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


from datetime import timedelta
from test_household_planning import setup,context
from test_forecast_pre_dusk import NOW
from household.codec import canonical,identity
from household.snapshot import HouseholdSnapshot


def pipeline_api():
    assert importlib.util.find_spec('household.pipeline') is not None,'model-to-plan pipeline missing'
    return importlib.import_module('household.pipeline')


def config():
    return dict(horizon_hours=24,reserve_soc=10.,low_trough_threshold_soc_pct=90.,
        surplus_weight=1.,reserve_weight=1.,comfort_min_f=65.,comfort_max_f=80.)


def energy_inputs(soc=100.,resource=20.):
    frozen=energy_api().freeze_energy_inputs(**{**FIXTURE['cases'][0]['inputs'],
        'soc_pct':soc,'resource_kwh':resource,'overnight_drops_pct':[15.]})
    snap,_=setup()
    return energy_api().bind_energy_inputs(frozen,snapshot=snap)


def pipeline(**changes):
    snap,registry=setup()
    args=dict(snapshot=snap,registry=registry,energy_inputs=energy_inputs(),thermal_inputs=None,
        thermal_runtime=None,coordination=context(snap),config=config(),now=NOW,
        runtime_manifest={'household/pipeline.py':'a'*64})
    args.update(changes);return pipeline_api().seal_pipeline(**args)


def test_models_generate_bounded_typed_proposals_with_unknown_causal_effects():
    result=pipeline();out=result['output']
    assert out['projections']['energy']['output']['curtail']>0
    assert {item['type'] for item in out['candidate_intents']}=={'RUN_GREYWATER_CYCLE','SET_NIGHT_LOAD_OVERRIDE'}
    assert all(item['shadowOnly'] for item in out['candidate_intents'])
    assert all(all(value is None for value in item['predictedEffects'].values()) for item in out['candidate_intents'])
    assert out['plan_receipt']['plan']['selected_intent_ids']==[]
    assert out['no_action_intent']['type']=='NO_ACTION'
    assert out['automatic_actuation'] is False and out['action_effects_qualified'] is False


def test_numerical_energy_reference_cannot_differ_from_shared_current_soc():
    pipeline_api()
    with pytest.raises(ValueError):pipeline(energy_inputs=energy_inputs(soc=50.))


def test_stale_sources_cannot_generate_new_typed_actions():
    result=pipeline(now=NOW+timedelta(seconds=100))
    assert result['output']['candidate_intents']==[]
    assert result['output']['candidate_generation']['reason']=='source_stale'


def test_missing_models_remain_unavailable_without_invented_proposals():
    result=pipeline(energy_inputs=None)
    assert result['output']['projections']=={'energy':None,'thermal':None}
    assert result['output']['candidate_intents']==[]
    assert result['output']['candidate_generation']['reason']=='source_unavailable'


def test_pipeline_rederives_models_candidates_and_complete_plan_without_reads(monkeypatch):
    import builtins,psycopg2
    result=pipeline();mod=pipeline_api()
    def forbidden(*args,**kwargs):pytest.fail('read attempted inside model/plan replay')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden);monkeypatch.setattr(psycopg2,'connect',forbidden)
    assert mod.replay_pipeline(result,runtime_manifest={'household/pipeline.py':'a'*64},thermal_runtime=None)==result


@pytest.mark.parametrize('damage',['trajectory','candidate','utility','extra'])
def test_resealed_pipeline_cannot_preserve_changed_derived_results(damage):
    result=pipeline()
    if damage=='trajectory':result['output']['projections']['energy']['output']['trough_pred']=0
    elif damage=='candidate':result['output']['candidate_intents']=[]
    elif damage=='utility':result['output']['plan_receipt']['plan']['objective']['total']=1e6
    else:result['operator_approval']=True
    result['receipt_sha256']=identity({key:value for key,value in result.items() if key!='receipt_sha256'})
    with pytest.raises(ValueError):pipeline_api().replay_pipeline(result,runtime_manifest={'household/pipeline.py':'a'*64},thermal_runtime=None)


def test_thermal_projection_is_bound_to_shared_measured_rows_and_runtime(tmp_path,monkeypatch):
    mod=pipeline_api()
    from test_household_models import prepared_thermal
    from household.thermal_model import project
    from household.control_contracts import instant
    prepared,capture=prepared_thermal(tmp_path,monkeypatch);value=prepared.to_dict()
    snap=HouseholdSnapshot(canonical({k:v for k,v in value['snapshot'].items() if k!='snapshot_id'}))
    _,registry=setup();ctx={**context(snap),'baseline_soc_floor':None,'facts':{}}
    result=mod.seal_pipeline(snapshot=snap,registry=registry,energy_inputs=None,thermal_inputs=prepared,
        thermal_runtime=value['executing_runtime'],coordination=ctx,config=config(),
        now=instant(value['snapshot']['created_at']),runtime_manifest={'household/pipeline.py':'a'*64})
    assert result['output']['projections']['thermal']==project(prepared)
    assert result['output']['projections']['thermal']['output']==capture['output']
    assert mod.replay_pipeline(result,runtime_manifest={'household/pipeline.py':'a'*64},thermal_runtime=value['executing_runtime'])==result
    wrong=snap.to_dict();wrong['domains']['thermal']['air_temperature']['value']+=1
    wrong_snap=HouseholdSnapshot(canonical({k:v for k,v in wrong.items() if k!='snapshot_id'}))
    with pytest.raises(ValueError):mod.seal_pipeline(snapshot=wrong_snap,registry=registry,energy_inputs=None,thermal_inputs=prepared,
        thermal_runtime=value['executing_runtime'],coordination={**ctx,'snapshotId':wrong_snap.snapshot_id},config=config(),
        now=instant(value['snapshot']['created_at']),runtime_manifest={'household/pipeline.py':'a'*64})
    with pytest.raises(ValueError):mod.replay_pipeline(result,runtime_manifest={'household/pipeline.py':'a'*64},thermal_runtime={})


@pytest.mark.parametrize('damage',['horizon','reserve','weight','comfort','extra'])
def test_pipeline_configuration_is_closed_and_cannot_weaken_constraints(damage):
    bad=config()
    if damage=='horizon':bad['horizon_hours']=48
    elif damage=='reserve':bad['reserve_soc']=0
    elif damage=='weight':bad['surplus_weight']=float('inf')
    elif damage=='comfort':bad['comfort_max_f']=bad['comfort_min_f']
    else:bad['allow_actuation']=True
    with pytest.raises(ValueError):pipeline(config=bad)


def test_private_pipeline_cli_refuses_fifo_and_public_receipt(tmp_path):
    import os,subprocess,sys
    script=Path(__file__).with_name('household_pipeline.py');assert script.exists(),'pipeline replay CLI missing'
    fifo=tmp_path/'fifo';os.mkfifo(fifo,0o600)
    for path in (fifo,tmp_path/'public.json'):
        if path!=fifo:path.write_text(json.dumps(pipeline()));path.chmod(0o644)
        result=subprocess.run([sys.executable,str(script),'--receipt',str(path)],capture_output=True,text=True,timeout=5)
        assert result.returncode==1 and not result.stdout and 'Traceback' not in result.stderr


def test_pipeline_cli_rederives_private_models_and_refuses_changed_runtime(tmp_path):
    import subprocess,sys
    script=Path(__file__).with_name('household_pipeline.py');assert script.exists(),'pipeline replay CLI missing'
    from household_pipeline import pipeline_runtime_manifest
    runtime=pipeline_runtime_manifest();receipt=pipeline(runtime_manifest=runtime)
    source=tmp_path/'receipt.json';source.write_bytes(canonical(receipt));source.chmod(0o600)
    result=subprocess.run([sys.executable,str(script),'--receipt',str(source)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)==receipt
    receipt['runtime_manifest']['openhab/scripts/household_pipeline.py']='f'*64
    receipt['receipt_sha256']=identity({key:value for key,value in receipt.items() if key!='receipt_sha256'})
    source.write_bytes(canonical(receipt))
    refused=subprocess.run([sys.executable,str(script),'--receipt',str(source)],capture_output=True,text=True,timeout=10)
    assert refused.returncode==1 and not refused.stdout


def test_same_soc_cannot_reuse_energy_context_from_different_snapshot():
    first,_=setup();document=first.to_dict();document['config_revision']='c'*64
    other=HouseholdSnapshot(canonical({k:v for k,v in document.items() if k!='snapshot_id'}))
    assert other.to_dict()['domains']['energy']['battery_soc']['value']==first.to_dict()['domains']['energy']['battery_soc']['value']
    with pytest.raises(ValueError):pipeline(snapshot=other,coordination=context(other),energy_inputs=energy_inputs())
