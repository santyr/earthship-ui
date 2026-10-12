"""Operator inspection is curated only after complete original replay."""
import importlib,json
from datetime import timedelta
from pathlib import Path
import pytest
from household.codec import identity
from household.control_contracts import instant
from test_household_pipeline import pipeline,NOW

RUNTIME={'household/pipeline.py':'a'*64}


def api():return importlib.import_module('household_observation')


def observe(record=None,at=NOW):
    return api().observe_pipeline(pipeline() if record is None else record,runtime_manifest=RUNTIME,thermal_runtime=None,observed_at=at)


def test_no_selected_action_remains_inspectable_without_policy_agreement():
    record=pipeline();view=observe(record)
    assert view['schema']=='earthship-household-observation/v1'
    assert view['receipt_sha256']==record['receipt_sha256']
    assert view['snapshot_id']==record['inputs']['snapshot']['snapshot_id']
    assert view['planner_mode']=='shadow' and view['authority']=='none' and view['automatic_actuation'] is False
    assert len(view['proposals'])==2 and all(row['selected'] is False for row in view['proposals'])
    assert view['policy_comparison']=={'status':'unavailable','reason':'source_unavailable'}
    assert view['effects_qualified'] is False


def test_proposal_checks_effects_and_model_identity_come_from_replayed_plan():
    record=pipeline();view=observe(record);original=record['output']
    assert {row['type'] for row in view['proposals']}=={'RUN_GREYWATER_CYCLE','SET_NIGHT_LOAD_OVERRIDE'}
    for row in view['proposals']:
        assert row['confidence']=='unavailable'
        assert all(value is None for value in row['expected_effects'].values())
        assert row['hard_checks'] and any(check['status']=='unknown' for check in row['hard_checks'])
    assert view['model_identities'][0]['projection_sha256']==original['projections']['energy']['projection_sha256']
    assert view['candidate_generation']['input_qualification']=='not_assessed'


def test_later_reverification_preserves_original_expiry_and_marks_unavailable():
    record=pipeline();early=observe(record);later=observe(record,at=NOW+timedelta(minutes=10))
    assert later['planner_mode']=='unavailable' and early['planner_mode']=='shadow'
    assert later['snapshot_as_of']==early['snapshot_as_of'] and later['decision_at']==early['decision_at']
    assert later['valid_until']==early['valid_until']
    assert instant(later['verified_at'])==NOW+timedelta(minutes=10)
    assert later['proposals']==early['proposals']


def test_missing_models_and_empty_generation_remain_inspectable():
    view=observe(pipeline(energy_inputs=None))
    assert view['model_identities']==[] and view['proposals']==[]
    assert view['candidate_generation']['reason']=='source_unavailable'
    assert view['policy_comparison']['status']=='unavailable'


@pytest.mark.parametrize('damage',['energy','proposal','extra'])
def test_resealed_derived_corruption_cannot_be_published(damage):
    record=pipeline()
    if damage=='energy':record['output']['projections']['energy']['output']['trough_pred']=0
    elif damage=='proposal':record['output']['candidate_intents']=[]
    else:record['operator_approval']=True
    record['receipt_sha256']=identity({k:v for k,v in record.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):observe(record)


def test_public_view_excludes_raw_sources_registry_scripts_and_private_paths():
    record=pipeline();view=observe(record);encoded=json.dumps(view)
    assert 'source_contexts' not in encoded and 'ownerSource' not in encoded and 'raw' not in view
    assert 'registry' not in view and 'inputs' not in view
    assert '/home/' not in encoded and '/tmp/' not in encoded
    assert len(encoded.encode())<=32768


def test_verified_inspection_performs_no_live_or_file_reads(monkeypatch):
    record=pipeline();mod=api()
    import builtins,psycopg2
    def forbidden(*a,**k):pytest.fail('I/O in pure observation')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden);monkeypatch.setattr(psycopg2,'connect',forbidden)
    assert mod.observe_pipeline(record,runtime_manifest=RUNTIME,thermal_runtime=None,observed_at=NOW)['receipt_sha256']==record['receipt_sha256']


def test_observation_clock_cannot_precede_original_decision():
    with pytest.raises(ValueError):observe(at=NOW-timedelta(seconds=1))


def test_source_backed_v6_thermal_identity_is_public_without_original_context(tmp_path,monkeypatch):
    from test_household_measured_weather_pipeline import make
    from test_household_model_pipeline import run,RUNTIME as MODEL_RUNTIME
    snap,_,prepared,_,_=make(tmp_path,monkeypatch);record=run(snap,prepared)
    view=api().observe_pipeline(record,runtime_manifest=MODEL_RUNTIME,thermal_runtime=prepared.to_dict()['executing_runtime'],observed_at=instant(record['inputs']['now']))
    thermal=next(row for row in view['model_identities'] if row['domain']=='thermal')
    assert thermal['artifact_sha256']==prepared.to_dict()['artifact_sha256']
    assert thermal['runtime_sha256']==prepared.to_dict()['runtime_sha256'] and thermal['confidence']=='low'
    assert {row['role'] for row in view['source_quality']} >= {'light_lux','rain_counter_in','solar_radiation_proxy_wm2'}
    encoded=json.dumps(view)
    assert 'policy_raw' not in encoded and 'source_contexts' not in encoded and 'ownerSource' not in encoded


def materializer_fixture(tmp_path):
    from household_pipeline import pipeline_runtime_manifest
    from household.codec import canonical
    root=tmp_path/'private';root.mkdir(mode=0o700)
    record=pipeline(runtime_manifest=pipeline_runtime_manifest())
    source=root/'receipt.json';source.write_bytes(canonical(record));source.chmod(0o600)
    return source,root/'observation.json',record


def test_private_materializer_writes_only_curated_view(tmp_path):
    source,target,record=materializer_fixture(tmp_path)
    result=api().materialize(source,target,clock=lambda:NOW)
    view=json.loads(target.read_bytes())
    assert result['status']=='observation_written' and result['receipt_sha256']==record['receipt_sha256']
    assert view['receipt_sha256']==record['receipt_sha256'] and 'inputs' not in view
    assert target.stat().st_mode&0o777==0o600 and json.loads(source.read_bytes())==record


@pytest.mark.parametrize('damage',['source_symlink','source_mode','directory_mode','same_path','existing_unknown'])
def test_unsafe_publication_target_or_source_refuses_without_overwrite(damage,tmp_path):
    source,target,_=materializer_fixture(tmp_path)
    if damage=='source_symlink':link=source.parent/'linked.json';link.symlink_to(source);source=link
    elif damage=='source_mode':source.chmod(0o640)
    elif damage=='directory_mode':target.parent.chmod(0o755)
    elif damage=='same_path':target=source
    else:target.write_text('operator-only existing data');target.chmod(0o600)
    before=target.read_bytes() if target.exists() else None
    with pytest.raises(ValueError):api().materialize(source,target,clock=lambda:NOW)
    assert (target.read_bytes() if target.exists() else None)==before


def test_runtime_drift_refuses_before_publication(tmp_path,monkeypatch):
    source,target,_=materializer_fixture(tmp_path);mod=api()
    import household_pipeline
    real=household_pipeline.pipeline_runtime_manifest;calls=0
    def changed(**kw):
        nonlocal calls
        calls+=1;value=real(**kw)
        if calls>1:value['openhab/scripts/forecast_intel.py']='f'*64
        return value
    monkeypatch.setattr(household_pipeline,'pipeline_runtime_manifest',changed)
    with pytest.raises(ValueError):mod.materialize(source,target,clock=lambda:NOW)
    assert not target.exists()


def test_existing_cache_updates_atomically_without_renewing_source_expiry(tmp_path):
    source,target,_=materializer_fixture(tmp_path)
    api().materialize(source,target,clock=lambda:NOW);first=json.loads(target.read_bytes())
    api().materialize(source,target,clock=lambda:NOW+timedelta(minutes=10));last=json.loads(target.read_bytes())
    assert last['receipt_sha256']==first['receipt_sha256'] and last['valid_until']==first['valid_until']
    assert last['planner_mode']=='unavailable' and target.stat().st_nlink==1
    assert list(target.parent.glob('.household-observation-*'))==[]


def test_capture_qualified_reference_cannot_override_unavailable_model_row():
    from test_household_snapshot import build
    from test_household_planning import context
    later=NOW+timedelta(seconds=100);snap=build(as_of=later,created_at=later)
    record=pipeline(snapshot=snap,coordination=context(snap),energy_inputs=None,now=later)
    view=observe(record,at=later)
    source=next(row for row in view['source_quality'] if row['role']=='battery_soc')
    assert source['quality_at_issue']=='unavailable' and source['current_quality']=='unavailable'
    assert source['reason']=='expired_source'
    assert instant(view['valid_until'])>=later

@pytest.mark.parametrize('damage',['target','parent'])
def test_publication_substitution_preserves_unrelated_files(damage,tmp_path,monkeypatch):
    source,target,_=materializer_fixture(tmp_path);mod=api()
    mod.materialize(source,target,clock=lambda:NOW)
    original=mod._existing_view;calls=0;marker=b'operator-only unrelated file'
    def substitute(path):
        nonlocal calls
        value=original(path)
        if path==target:
            calls+=1
            if calls==2:
                if damage=='parent':
                    staged=[(p.name,p.read_bytes()) for p in target.parent.glob('.household-observation-*')]
                    target.parent.rename(tmp_path/'displaced-parent')
                    target.parent.mkdir(mode=0o700)
                    for name,raw in staged:
                        copy=target.parent/name;copy.write_bytes(raw);copy.chmod(0o600)
                else:target.unlink()
                target.write_bytes(marker);target.chmod(0o600)
        return value
    monkeypatch.setattr(mod,'_existing_view',substitute)
    with pytest.raises(ValueError):mod.materialize(source,target,clock=lambda:NOW+timedelta(minutes=10))
    assert target.read_bytes()==marker
