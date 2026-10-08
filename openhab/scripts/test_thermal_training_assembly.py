"""Measurement assembly preserves raw inputs and uses a fresh full journal view."""
from datetime import timedelta
from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_thermal_training_inputs import inputs
from thermal_model.training_inputs import capture_training_inputs,restore_training_inputs
from thermal_model.schema import ActionEvent


def module():
    from thermal_model import training_assembly
    return training_assembly


def record(left,right,*,mixed=False,missing=False):
    data=inputs(mixed=mixed,missing=missing);reader=data['series_reader'];legacy=reader.legacy_reader
    reader.legacy_reader=lambda item,start,end:[(at,value) for at,value in legacy(item,start,end) if start<=at<end]
    data.update(start=left,end=right)
    return capture_training_inputs(**data)


def parts(*,damage=None,missing=False):
    data=inputs();start=data['start'];mid=start+timedelta(minutes=10);end=data['end']
    left=record(start,mid,missing=missing)
    right_start=mid+timedelta(minutes=5) if damage=='gap' else mid-timedelta(minutes=5) if damage=='overlap' else mid
    right=record(right_start,end,mixed=damage=='cutover')
    if damage=='revision':
        from thermal_model.training_inputs import _digest
        right['collection_code_revision']='b'*64;right['snapshot_sha256']=_digest({key:value for key,value in right.items() if key!='snapshot_sha256'})
    return data,[left,right]


def fresh_journal(data,calls):
    current=ActionEvent('fresh-correction','fresh-receipt',data['end'],data['start'],'indoor_shade','closed','historical_reconstruction',.35,supersedes='original-action')
    def actions(start,end):calls.append(('actions',start,end));return [current]
    def modes(start,end):calls.append(('modes',start,end));return data['journal'].effective_modes(start,end)
    return SimpleNamespace(effective_events=actions,effective_modes=modes)


def test_assembly_uses_fresh_whole_window_journal_and_preserves_measurements():
    data,records=parts();calls=[]
    assembled,binding=module().assemble_training_inputs(records,journal=fresh_journal(data,calls),clock=lambda:data['end']+timedelta(hours=1),revision_reader=lambda:'c'*64)
    assert calls==[('actions',data['start'],data['end']),('modes',data['start'],data['end'])]
    assert assembled['events'][0]['event_id']=='fresh-correction' and assembled['events'][0]['confidence']==.35
    assert assembled['events'][0]['source']=='historical_reconstruction'
    assert assembled['series_by_role']['air']==records[0]['series_by_role']['air']+records[1]['series_by_role']['air']
    assert assembled['temperature_grids']['mass']==records[0]['temperature_grids']['mass']+records[1]['temperature_grids']['mass']
    assert binding['input_snapshot_sha256s']==[record['snapshot_sha256'] for record in records]
    assert binding['assembled_snapshot_sha256']==assembled['snapshot_sha256']
    module().verify_training_assembly(assembled,binding,records)
    assert len(restore_training_inputs(assembled).samples)==4


@pytest.mark.parametrize('damage',['gap','overlap','cutover','revision'])
def test_incompatible_parts_refuse_before_journal_read(damage):
    data,records=parts(damage=damage)
    forbidden=lambda *args:pytest.fail('incompatible parts reached journal')
    journal=SimpleNamespace(effective_events=forbidden,effective_modes=forbidden)
    with pytest.raises(ValueError):module().assemble_training_inputs(records,journal=journal,clock=lambda:data['end'],revision_reader=lambda:'c'*64)


def test_missing_native_barrier_survives_assembly():
    data,records=parts(missing=True)
    assembled,binding=module().assemble_training_inputs(records,journal=data['journal'],clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    assert assembled['series_by_role']['air'][1][1] is None
    assert assembled['temperature_grids']['air'][1][1] is None
    assert len(restore_training_inputs(assembled).samples)==3


def test_changed_lineage_binding_refuses_even_when_rehashed():
    data,records=parts()
    assembled,binding=module().assemble_training_inputs(records,journal=data['journal'],clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    binding['input_snapshot_sha256s'][0]='d'*64
    from thermal_model.training_inputs import _digest
    binding['binding_sha256']=_digest({key:value for key,value in binding.items() if key!='binding_sha256'})
    with pytest.raises(ValueError):module().verify_training_assembly(assembled,binding,records)


def test_assembly_limits_parent_count_before_consuming_unbounded_input():
    def records():
        for _ in range(9):yield {}
        pytest.fail('unbounded source consumed')
    with pytest.raises(ValueError):module().assemble_training_inputs(records(),journal=None,clock=lambda:inputs()['end'],revision_reader=lambda:'c'*64)


@pytest.mark.parametrize('bound',['bytes','points','interval'])
def test_assembly_refuses_large_inputs_before_dataset_expansion(monkeypatch,bound):
    source=module();data,records=parts()
    monkeypatch.setattr(source,'restore_training_inputs',lambda *args:pytest.fail('excessive input expanded'))
    if bound=='bytes':monkeypatch.setattr(source,'MAX_BYTES',1)
    if bound=='points':monkeypatch.setattr(source,'MAX_SERIES_POINTS',1)
    if bound=='interval':records[0]['start']=(data['start']-timedelta(days=100)).isoformat()
    with pytest.raises(ValueError):source.assemble_training_inputs(records,journal=None,clock=lambda:data['end'],revision_reader=lambda:'c'*64)


def test_code_drift_during_journal_read_refuses_assembly():
    source=module();data,records=parts();revisions=iter(['c'*64,'d'*64])
    with pytest.raises(ValueError):source.assemble_training_inputs(records,journal=data['journal'],clock=lambda:data['end'],revision_reader=lambda:next(revisions))


def test_binding_write_is_private_immutable_and_idempotent(tmp_path):
    data,records=parts();source=module()
    assembled,binding=source.assemble_training_inputs(records,journal=data['journal'],clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    path=source.write_training_assembly(tmp_path,assembled,binding,records)
    assert path.stat().st_mode&0o777==0o600
    assert source.write_training_assembly(tmp_path,assembled,binding,records)==path
    path.write_text('{}')
    with pytest.raises(ValueError):source.write_training_assembly(tmp_path,assembled,binding,records)


def test_binding_write_cleans_partial_temp_on_failure(tmp_path,monkeypatch):
    data,records=parts();source=module()
    assembled,binding=source.assemble_training_inputs(records,journal=data['journal'],clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    def interrupted(path,raw):path.write_bytes(b'partial');raise OSError('synthetic disk failure')
    monkeypatch.setattr(source,'_write_private',interrupted)
    with pytest.raises(OSError):source.write_training_assembly(tmp_path,assembled,binding,records)
    assert list(tmp_path.iterdir())==[]


def test_reversed_input_order_keeps_chronological_binding():
    source=module();data,records=parts()
    forward=source.assemble_training_inputs(records,journal=data['journal'],clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    reversed_result=source.assemble_training_inputs(reversed(records),journal=data['journal'],clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    assert reversed_result==forward


def test_journal_callback_cannot_mutate_frozen_parent_measurements():
    source=module();data,records=parts();original=deepcopy(records)
    def actions(*args):
        records[0]['series_by_role']['air'][0][1]+=5
        return data['journal'].effective_events(*args)
    journal=SimpleNamespace(effective_events=actions,effective_modes=data['journal'].effective_modes)
    assembled,binding=source.assemble_training_inputs(records,journal=journal,clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    assert assembled['series_by_role']['air'][0]==original[0]['series_by_role']['air'][0]
    source.verify_training_assembly(assembled,binding,original)


def test_rehashed_non_native_measurement_change_cannot_repair_lineage():
    from thermal_model.training_inputs import _digest,_Series,_Journal
    from thermal_model.dataset import build_samples,dataset_manifest
    source=module();data,records=parts()
    assembled,binding=source.assemble_training_inputs(records,journal=data['journal'],clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    assembled['series_by_role']['radiation'][0][1]+=1
    reader=_Series(assembled);journal=_Journal(assembled)
    from thermal_model.training_inputs import ITEMS
    raw={role:reader(item,data['start'],data['end']) for role,item in ITEMS.items()}
    events=journal.effective_events(data['start'],data['end']);modes=journal.effective_modes(data['start'],data['end'])
    assembled['dataset_manifest']=dataset_manifest(build_samples(raw,events,modes,data['start'],data['end']),events,modes)
    assembled['snapshot_sha256']=_digest({key:value for key,value in assembled.items() if key!='snapshot_sha256'})
    binding['assembled_snapshot_sha256']=assembled['snapshot_sha256'];binding['binding_sha256']=_digest({key:value for key,value in binding.items() if key!='binding_sha256'})
    restore_training_inputs(assembled)  # The standalone snapshot is internally consistent.
    with pytest.raises(ValueError):source.verify_training_assembly(assembled,binding,records)
