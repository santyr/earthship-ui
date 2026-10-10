"""Original-source v2 assembly and strict lineage without numerical fitting."""
from copy import deepcopy
from datetime import datetime,timedelta
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest
from test_thermal_sensor_epoch_training import inputs_v2
from test_thermal_sensor_epoch_history import EPOCHS
from test_thermal_training_assembly import fresh_journal
import thermal_model.training_inputs as inputs
import thermal_model.training_assembly as assembly


def parts_v2():
    data=inputs_v2();mid=data['start']+timedelta(minutes=10);records=[]
    for left,right in ((data['start'],mid),(mid,data['end'])):
        part=inputs_v2();reader=part['series_reader'];legacy=reader.legacy_reader
        reader.legacy_reader=lambda item,start,end,legacy=legacy:[(at,value) for at,value in legacy(item,start,end) if start<=at<end]
        part.update(start=left,end=right)
        records.append(inputs.capture_training_inputs_v2(**part))
    return data,records


def assembled():
    data,records=parts_v2()
    record,binding=assembly.assemble_training_inputs_v2(records,journal=data['journal'],clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    return data,records,record,binding


def test_v2_assembly_preserves_original_sessions_phases_and_fresh_journal(tmp_path):
    data,records=parts_v2();calls=[]
    record,binding=assembly.assemble_training_inputs_v2(records,journal=fresh_journal(data,calls),clock=lambda:data['end']+timedelta(hours=1),revision_reader=lambda:'c'*64)
    assert binding['schema']=='earthship-thermal-training-assembly/v2'
    assert record['schema']=='earthship-thermal-training-inputs/v2'
    assert calls==[('actions',data['start'],data['end']),('modes',data['start'],data['end'])]
    assert record['events'][0]['source']=='historical_reconstruction'
    assert binding['input_snapshot_sha256s']==[row['snapshot_sha256'] for row in records]
    for role,native in record['temperature_grids'].items():
        assert native==records[0]['temperature_grids'][role]+records[1]['temperature_grids'][role]
        assert {value['sensorEpoch'] for _,value in native}=={EPOCHS[role]}
        assert len({value['streamEpoch'] for _,value in native})==2
    assert len(inputs.restore_training_inputs_v2(record).samples)==4
    path=assembly.write_training_assembly_v2(tmp_path,record,binding,records)
    assert path.name.endswith('.training-assembly-v2.json') and path.stat().st_mode&0o777==0o600
    assert assembly.read_training_assembly_v2(path,record,records)==binding
    with pytest.raises(ValueError):assembly.verify_training_assembly(record,binding,records)
    with pytest.raises(ValueError):assembly.assemble_training_inputs(records,journal=data['journal'],clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    with pytest.raises(ValueError):assembly.read_training_assembly(path,record,records)


@pytest.mark.parametrize('damage',['gap','overlap','revision','mixed_version','phase'])
def test_v2_incompatible_parts_refuse_before_journal(damage):
    data,records=parts_v2()
    if damage=='gap':records[1]['start']=(data['start']+timedelta(minutes=15)).isoformat()
    elif damage=='overlap':records[1]['start']=(data['start']+timedelta(minutes=5)).isoformat()
    elif damage=='revision':records[1]['collection_code_revision']='d'*64
    elif damage=='mixed_version':records[1]['schema']=inputs.SCHEMA
    else:
        records[1]['temperature_evidence']['roles']['air']['sensor_epoch']=EPOCHS['mass']
        for _,value in records[1]['temperature_grids']['air']:value['sensorEpoch']=EPOCHS['mass']
        encoded=''.join(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n' for row in records[1]['temperature_grids']['air']).encode()
        records[1]['temperature_evidence']['roles']['air']['grid_sha256']=sha256(encoded).hexdigest()
    records[1]['snapshot_sha256']=inputs._digest({key:value for key,value in records[1].items() if key!='snapshot_sha256'})
    if damage=='phase':inputs.restore_training_inputs_v2(records[1])
    journal=SimpleNamespace(effective_events=lambda *args:pytest.fail('invalid parents read journal'),effective_modes=lambda *args:pytest.fail('invalid parents read journal'))
    with pytest.raises(ValueError):assembly.assemble_training_inputs_v2(records,journal=journal,clock=lambda:data['end'],revision_reader=lambda:'c'*64)


def test_rehashed_v2_binding_cannot_replace_original_parent():
    data,records,record,binding=assembled()
    binding['input_snapshot_sha256s'][0]='d'*64
    binding['binding_sha256']=inputs._digest({key:value for key,value in binding.items() if key!='binding_sha256'})
    with pytest.raises(ValueError):assembly.verify_training_assembly_v2(record,binding,records)


def test_v2_part_loader_is_explicit_and_retains_private_originals(tmp_path):
    tmp_path.chmod(0o700);data,records=parts_v2()
    paths=[inputs.write_training_inputs_v2(tmp_path,record) for record in records]
    assert assembly.read_training_parts_v2(paths)==records
    with pytest.raises(ValueError):assembly.read_training_parts(paths)


def test_v2_journal_callback_cannot_mutate_frozen_native_parents():
    data,records=parts_v2();original=deepcopy(records)
    def actions(*args):
        records[0]['temperature_grids']['air'][0][1]['temperatureF']+=10
        return data['journal'].effective_events(*args)
    journal=SimpleNamespace(effective_events=actions,effective_modes=data['journal'].effective_modes)
    record,binding=assembly.assemble_training_inputs_v2(records,journal=journal,clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    assert record['temperature_grids']['air'][0]==original[0]['temperature_grids']['air'][0]
    assembly.verify_training_assembly_v2(record,binding,original)


def test_offline_assembled_v2_persists_originals_and_versioned_binding_before_candidate(tmp_path,monkeypatch):
    from functools import partial
    import thermal_model.offline_training as offline
    import thermal_model.pipeline as pipeline
    import thermal_model.fit_evidence as fit_evidence
    from test_thermal_pipeline import RecordingRegistry,multihorizon_fit_result,warm_behavior,backtest_report
    data,parents,record,binding=assembled();registry=RecordingRegistry();writes=[]
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1')
    monkeypatch.setattr(fit_evidence,'build_fit_evidence',lambda artifact,fitted:dict(release_authorized=False))
    def proof(root,value,artifact):
        assert registry.calls==['report']
        original_paths=list(root.glob('*.training-inputs-v2.json'))
        assert len(original_paths)==3
        retained=[inputs.read_training_inputs_v2(path) for path in original_paths]
        assert {row['snapshot_sha256'] for row in retained}=={record['snapshot_sha256'],*[row['snapshot_sha256'] for row in parents]}
        assembly_path=next(root.glob('*.training-assembly-v2.json'))
        assert assembly.read_training_assembly_v2(assembly_path,record,parents)==binding
        phase_binding=json.loads(next(root.glob('*.training-input-binding-v4.json')).read_text())
        assert phase_binding['schema']=='earthship-thermal-training-input-binding/v4'
        assert phase_binding['sensor_epochs']==EPOCHS and phase_binding['release_authorized'] is False
        assert phase_binding['assembly_binding_sha256']==binding['binding_sha256']
        writes.append('proof')
    monkeypatch.setattr(offline,'write_fit_evidence',proof)
    monkeypatch.setattr(offline,'run_training',partial(pipeline.run_training,dynamics_fitter=lambda rows,**kwargs:multihorizon_fit_result(),behavior_fitter=lambda rows:warm_behavior(),evaluator=lambda rows,fitter:backtest_report(eligible=True),artifact_validator=lambda artifact:artifact))
    result=offline.run_snapshot_training(record,registry=registry,fit_evidence_directory=tmp_path,clock=lambda:data['end'],revision_reader=lambda:'b'*64,assembly_binding=binding,assembly_inputs=parents)
    assert result.artifact.schema=='earthship-thermal-model/v6' and writes==['proof']


def test_training_cli_v2_verifies_assembly_without_fitting(tmp_path,monkeypatch,capsys):
    from test_train_thermal_snapshot import cli
    tmp_path.chmod(0o700);data,parents,record,binding=assembled()
    path=inputs.write_training_inputs_v2(tmp_path,record)
    parent_paths=[inputs.write_training_inputs_v2(tmp_path,row) for row in parents]
    bind_path=assembly.write_training_assembly_v2(tmp_path,record,binding,parents)
    command=cli();monkeypatch.setattr(command,'run_snapshot_training',lambda *args,**kwargs:pytest.fail('verification fitted'))
    args=['--snapshot',str(path),'--receipt-version','2','--verify-only','--assembly-binding',str(bind_path)]
    for parent in parent_paths:args+=['--input-part',str(parent)]
    assert command.main(args)==0
    assert json.loads(capsys.readouterr().out)['assembly_binding_sha256']==binding['binding_sha256']


def test_assembly_cli_v2_worker_writes_lineage_before_input(tmp_path,monkeypatch):
    from test_assemble_thermal_inputs import cli,context
    command=cli();_,_,_,dsn,out,args=context(tmp_path)
    data,parents=parts_v2();paths=[inputs.write_training_inputs_v2(tmp_path,row) for row in parents]
    args=['--journal-dsn-file',str(dsn),'--destination',str(out),'--receipt-version','2']
    for path in paths:args+=['--part',str(path)]
    import thermal_model.capture_backends as backend
    for key in ('EARTHSHIP_THERMAL_INPUT_CAPTURE','EARTHSHIP_GUARDED_CAPTURE_WORKER'):monkeypatch.setenv(key,'1')
    for key in ('EARTHSHIP_REMOTE_QUALIFICATION_FIT','EARTHSHIP_QUALIFICATION_FIT'):monkeypatch.setenv(key,'0')
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None);monkeypatch.setattr(command.os,'getpriority',lambda *args:15)
    monkeypatch.setattr(command,'_assembly_revision',lambda:'c'*64)
    monkeypatch.setattr(backend,'configured_capture_journal',lambda **kwargs:data['journal'])
    original=inputs.write_training_inputs_v2
    def write(root,record):
        assert list(root.glob('*.training-assembly-v2.json'))
        return original(root,record)
    monkeypatch.setattr(inputs,'write_training_inputs_v2',write)
    digest=command._context(paths,dsn,out)[-1]
    assert command.main(args+['--worker','--expected-context-digest',digest])==0
    receipt=json.loads((out/'assembly-receipt.json').read_text())
    assert receipt['fitting_executed'] is False and receipt['release_authorized'] is False
    record=inputs.read_training_inputs_v2(out/(receipt['snapshot_sha256']+'.training-inputs-v2.json'))
    binding_path=out/(receipt['binding_sha256']+'.training-assembly-v2.json')
    assembly.read_training_assembly_v2(binding_path,record,parents)


def test_assembly_v2_parent_propagates_version_to_guarded_worker(tmp_path,monkeypatch):
    from test_assemble_thermal_inputs import cli,context
    command=cli();_,_,_,dsn,out,_=context(tmp_path);data,parents=parts_v2()
    paths=[inputs.write_training_inputs_v2(tmp_path,row) for row in parents]
    args=['--journal-dsn-file',str(dsn),'--destination',str(out),'--receipt-version','2']
    for path in paths:args+=['--part',str(path)]
    calls=[];monkeypatch.setenv('EARTHSHIP_THERMAL_INPUT_CAPTURE','1')
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    def fail(argv,**kwargs):calls.append((argv,kwargs));return 2
    monkeypatch.setattr(command,'run_guarded_capture',fail)
    assert command.main(args)==2
    argv,limits=calls[0]
    assert argv[argv.index('--receipt-version')+1]=='2' and limits=={'seconds':90}


@pytest.mark.parametrize('flag',['EARTHSHIP_QUALIFICATION_FIT','EARTHSHIP_REMOTE_QUALIFICATION_FIT'])
def test_assembly_worker_refuses_either_fit_flag_before_sources(tmp_path,monkeypatch,flag):
    from test_assemble_thermal_inputs import cli,context
    command=cli();_,_,_,_,_,args=context(tmp_path)
    for key in ('EARTHSHIP_THERMAL_INPUT_CAPTURE','EARTHSHIP_GUARDED_CAPTURE_WORKER'):monkeypatch.setenv(key,'1')
    for key in ('EARTHSHIP_REMOTE_QUALIFICATION_FIT','EARTHSHIP_QUALIFICATION_FIT'):monkeypatch.setenv(key,'0')
    monkeypatch.setenv(flag,'1')
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None);monkeypatch.setattr(command.os,'getpriority',lambda *args:15)
    monkeypatch.setattr(command,'_context',lambda *args,**kwargs:pytest.fail('fit-enabled assembly inspected sources'))
    assert command.main(args+['--receipt-version','2','--worker'])==2


@pytest.mark.parametrize('damage',['exposed','wrong_address','duplicate','nonfinite','positive_flag'])
def test_v2_binding_reader_refuses_invalid_private_evidence(tmp_path,damage):
    data,parents,record,binding=assembled()
    path=assembly.write_training_assembly_v2(tmp_path,record,binding,parents)
    if damage=='exposed':path.chmod(0o644)
    elif damage=='wrong_address':
        new=tmp_path/('d'*64+'.training-assembly-v2.json');path.rename(new);path=new
    elif damage=='duplicate':path.write_text(path.read_text()[:-1]+',"release_authorized":false}')
    elif damage=='nonfinite':path.write_text(path.read_text()[:-1]+',"unexpected":NaN}')
    else:
        binding['release_authorized']=True
        binding['binding_sha256']=inputs._digest({key:value for key,value in binding.items() if key!='binding_sha256'})
        path.write_text(json.dumps(binding))
    with pytest.raises(ValueError):assembly.read_training_assembly_v2(path,record,parents)


def test_v2_reader_retains_null_barriers_across_assembly():
    data,parents=parts_v2();parent=parents[0];at=parent['temperature_grids']['air'][1][0]
    parent['temperature_grids']['air'][1][1]=None
    parent['series_by_role']['air'][1][1]=None
    evidence=parent['temperature_evidence']['roles']['air'];evidence['qualified']-=1;evidence['missing']+=1
    evidence['grid_sha256']=sha256(''.join(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n' for row in parent['temperature_grids']['air']).encode()).hexdigest()
    from thermal_model.dataset import build_samples,dataset_manifest
    reader=inputs._Series(parent);journal=inputs._Journal(parent)
    start,end=datetime.fromisoformat(parent['start']),datetime.fromisoformat(parent['end'])
    series={role:reader(item,start,end) for role,item in inputs.ITEMS.items()}
    events=journal.effective_events(start,end);modes=journal.effective_modes(start,end)
    parent['dataset_manifest']=dataset_manifest(build_samples(series,events,modes,start,end),events,modes)
    parent['snapshot_sha256']=inputs._digest({key:value for key,value in parent.items() if key!='snapshot_sha256'})
    inputs.restore_training_inputs_v2(parent)
    record,binding=assembly.assemble_training_inputs_v2(parents,journal=data['journal'],clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    assert record['temperature_grids']['air'][1]==[at,None]
    assert record['series_by_role']['air'][1]==[at,None]
    assert len(inputs.restore_training_inputs_v2(record).samples)==3


def test_v2_lineage_failure_prevents_fitting(tmp_path,monkeypatch):
    import thermal_model.offline_training as offline
    data,parents,record,binding=assembled();binding['input_snapshot_sha256s'].reverse()
    binding['binding_sha256']=inputs._digest({key:value for key,value in binding.items() if key!='binding_sha256'})
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1')
    monkeypatch.setattr(offline,'run_training',lambda **kwargs:pytest.fail('invalid lineage fitted'))
    with pytest.raises(ValueError):offline.run_snapshot_training(record,registry=None,fit_evidence_directory=tmp_path,clock=lambda:data['end'],revision_reader=lambda:'c'*64,assembly_binding=binding,assembly_inputs=parents)


def test_pressure_aware_assembly_routes_strict_native_v2_worker(tmp_path,monkeypatch):
    from test_assemble_thermal_inputs import cli,context
    command=cli();_,_,_,dsn,out,_=context(tmp_path);data,parents=parts_v2()
    paths=[inputs.write_training_inputs_v2(tmp_path,row) for row in parents]
    args=['--journal-dsn-file',str(dsn),'--destination',str(out),'--receipt-version','2','--pressure-aware']
    for path in paths:args+=['--part',str(path)]
    calls=[];monkeypatch.setenv('EARTHSHIP_THERMAL_INPUT_CAPTURE','1')
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(command,'_pressure_preflight',lambda:None)
    monkeypatch.setattr(command,'run_guarded_capture',lambda *a,**k:pytest.fail('used legacy admission'))
    def stopped(argv,**kwargs):calls.append((argv,kwargs));return 2
    monkeypatch.setattr(command,'_run_pressure_worker',stopped)
    assert command.main(args)==2
    argv,limits=calls[0]
    assert '--pressure-aware' in argv and argv[argv.index('--receipt-version')+1]=='2'
    assert limits=={'seconds':90}
