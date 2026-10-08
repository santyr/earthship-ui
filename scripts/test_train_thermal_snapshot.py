"""CLI guard/routing checks; fit entrypoint is always replaced locally."""
import importlib.util
from pathlib import Path
import json
from types import SimpleNamespace
import pytest
from test_thermal_training_inputs import inputs,module as input_module
from test_thermal_origin_capture import capture_inputs


def cli():
    spec=importlib.util.spec_from_file_location('snapshot_train_cli',Path(__file__).with_name('train-thermal-snapshot.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def snapshot(tmp_path):
    record=input_module().capture_training_inputs(**inputs())
    return input_module().write_training_inputs(tmp_path,record)


def test_verify_only_reads_snapshot_without_fitting(tmp_path,monkeypatch,capsys):
    path=snapshot(tmp_path);command=cli()
    def prohibited(*args,**kwargs):pytest.fail('verification reached fitting')
    monkeypatch.setattr(command,'run_snapshot_training',prohibited)
    assert command.main(['--snapshot',str(path),'--verify-only'])==0
    value=json.loads(capsys.readouterr().out)
    assert value['status']=='inputs_verified' and value['release_authorized'] is False


def test_fit_without_workload_optin_refuses_before_reading_snapshot(monkeypatch,tmp_path,capsys):
    command=cli();monkeypatch.delenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT',raising=False)
    def prohibited(*args,**kwargs):pytest.fail('unapproved workload reached input loading')
    monkeypatch.setattr(command,'read_training_inputs',prohibited)
    assert command.main(['--snapshot','/unread','--fit','--state-dir',str(tmp_path),'--fit-evidence-dir',str(tmp_path)])==2
    assert capsys.readouterr().out==''


def test_explicit_fit_uses_new_private_isolated_directories(tmp_path,monkeypatch,capsys):
    path=snapshot(tmp_path);command=cli();state=tmp_path/'state';proof=tmp_path/'proof'
    state.mkdir(mode=0o700);proof.mkdir(mode=0o700);monkeypatch.setenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT','1')
    calls=[]
    def train(record,**kwargs):
        assert kwargs['registry'].directory==state
        assert kwargs['fit_evidence_directory']==proof
        calls.append(record['snapshot_sha256']);return SimpleNamespace(artifact=capture_inputs()['artifact'])
    monkeypatch.setattr(command,'run_snapshot_training',train)
    assert command.main(['--snapshot',str(path),'--fit','--state-dir',str(state),'--fit-evidence-dir',str(proof)])==0
    assert len(calls)==1 and json.loads(capsys.readouterr().out)['release_authorized'] is False


@pytest.mark.parametrize('damage',['same','nested','nonempty','exposed'])
def test_bad_fit_directories_refuse_before_training(tmp_path,monkeypatch,damage):
    path=snapshot(tmp_path);command=cli();state=tmp_path/'state';proof=tmp_path/'proof'
    state.mkdir(mode=0o700);proof.mkdir(mode=0o700);monkeypatch.setenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT','1')
    if damage=='same':proof=state
    elif damage=='nested':proof=state/'proof';proof.mkdir(mode=0o700)
    elif damage=='nonempty':(state/'accepted.json').write_text('existing')
    else:proof.chmod(0o755)
    def prohibited(*args,**kwargs):pytest.fail('unsafe destination reached fitting')
    monkeypatch.setattr(command,'run_snapshot_training',prohibited)
    assert command.main(['--snapshot',str(path),'--fit','--state-dir',str(state),'--fit-evidence-dir',str(proof)])==2


def test_fit_revision_binds_snapshot_wrapper_and_cli_sources(monkeypatch):
    command=cli();seen=[];content=[b'unchanged source']
    def read(path,maximum):seen.append(str(path.relative_to(command.ROOT)));return content[0]
    monkeypatch.setattr(command,'_source_bytes',read)
    first=command._fit_code_revision()
    assert {'openhab/scripts/thermal_model/training_inputs.py','openhab/scripts/thermal_model/offline_training.py','scripts/train-thermal-snapshot.py'}<=set(seen)
    content[0]=b'changed source'
    assert command._fit_code_revision()!=first


@pytest.mark.parametrize('helper',['rollback','training_assembly','environment_bundle'])
def test_fit_revision_changes_when_executed_lineage_helper_changes(monkeypatch,helper):
    command=cli();changed=[False]
    def read(path,maximum):
        return b'changed helper' if changed[0] and path.name==helper+'.py' else b'original source'
    monkeypatch.setattr(command,'_source_bytes',read)
    before=command._fit_code_revision();changed[0]=True
    assert command._fit_code_revision()!=before


def test_verify_assembled_lineage_without_fitting(tmp_path,monkeypatch,capsys):
    from test_thermal_training_assembly import parts,module as assembly_module
    data,parents=parts();source=assembly_module()
    record,binding=source.assemble_training_inputs(parents,journal=data['journal'],clock=lambda:data['end'],revision_reader=lambda:'c'*64)
    path=input_module().write_training_inputs(tmp_path,record)
    binding_path=source.write_training_assembly(tmp_path,record,binding,parents)
    parent_paths=[input_module().write_training_inputs(tmp_path,parent) for parent in parents]
    command=cli();monkeypatch.setattr(command,'run_snapshot_training',lambda *args,**kwargs:pytest.fail('verification reached fitting'))
    arguments=['--snapshot',str(path),'--verify-only','--assembly-binding',str(binding_path)]
    for parent in parent_paths:arguments+=['--input-part',str(parent)]
    assert command.main(arguments)==0
    assert json.loads(capsys.readouterr().out)['assembly_binding_sha256']==binding['binding_sha256']
    damaged=json.loads(binding_path.read_text());damaged['input_snapshot_sha256s'][0]='d'*64
    from thermal_model.training_inputs import _digest
    damaged['binding_sha256']=_digest({key:value for key,value in damaged.items() if key!='binding_sha256'})
    wrong=tmp_path/(damaged['binding_sha256']+'.training-assembly-v1.json');wrong.write_text(json.dumps(damaged));wrong.chmod(0o600)
    arguments[arguments.index(str(binding_path))]=str(wrong)
    assert command.main(arguments)==2
