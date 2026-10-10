"""Guarded assembly routing with original synthetic snapshots and fake journal."""
import importlib.util
from pathlib import Path
import json
import pytest
from test_thermal_training_assembly import parts
from thermal_model.training_inputs import write_training_inputs


def cli():
    spec=importlib.util.spec_from_file_location('assemble_cli',Path(__file__).with_name('assemble-thermal-inputs.py'))
    command=importlib.util.module_from_spec(spec);spec.loader.exec_module(command);return command


def context(tmp_path):
    tmp_path.chmod(0o700);data,records=parts();paths=[write_training_inputs(tmp_path,record) for record in records]
    dsn=tmp_path/'journal';dsn.write_text('host=127.0.0.1 dbname=openhab user=synthetic_reader password=synthetic');dsn.chmod(0o600)
    out=tmp_path/'assembled';out.mkdir(mode=0o700)
    args=['--journal-dsn-file',str(dsn),'--destination',str(out)]
    for path in paths:args+=['--part',str(path)]
    return data,records,paths,dsn,out,args


def test_assembly_check_only_never_queries_or_launches(tmp_path,monkeypatch,capsys):
    command=cli();data,records,paths,dsn,out,args=context(tmp_path)
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(command,'run_guarded_capture',lambda *args,**kwargs:pytest.fail('check launched'))
    assert command.main(args+['--check-only'])==0
    assert json.loads(capsys.readouterr().out)['status']=='assembly_paths_verified'
    assert list(out.iterdir())==[]


def test_assembly_requires_intent_before_guard(tmp_path,monkeypatch):
    command=cli();data,records,paths,dsn,out,args=context(tmp_path)
    monkeypatch.delenv('EARTHSHIP_THERMAL_INPUT_CAPTURE',raising=False)
    monkeypatch.setattr(command,'run_guarded_capture',lambda *args,**kwargs:pytest.fail('unapproved launch'))
    assert command.main(args)==2


def test_assembly_worker_persists_binding_before_snapshot(tmp_path,monkeypatch):
    command=cli();data,records,paths,dsn,out,args=context(tmp_path)
    import thermal_model.capture_backends as backend
    monkeypatch.setenv('EARTHSHIP_THERMAL_INPUT_CAPTURE','1');monkeypatch.setenv('EARTHSHIP_GUARDED_CAPTURE_WORKER','1');monkeypatch.setenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT','0')
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None);monkeypatch.setattr(command.os,'getpriority',lambda *args:15)
    monkeypatch.setattr(command,'_assembly_revision',lambda:'c'*64)
    monkeypatch.setattr(backend,'configured_capture_journal',lambda **kwargs:data['journal'])
    digest=command._context(paths,dsn,out)[-1]
    assert command.main(args+['--worker','--expected-context-digest',digest])==0
    receipt=json.loads((out/'assembly-receipt.json').read_text())
    assert receipt['release_authorized'] is False and receipt['fitting_executed'] is False
    from thermal_model.training_inputs import read_training_inputs
    from thermal_model.training_assembly import verify_training_assembly
    record=read_training_inputs(out/(receipt['snapshot_sha256']+'.training-inputs-v1.json'))
    binding=json.loads((out/(receipt['binding_sha256']+'.training-assembly-v1.json')).read_text())
    verify_training_assembly(record,binding,records)


def test_changed_context_refuses_before_worker(tmp_path,monkeypatch):
    command=cli();data,records,paths,dsn,out,args=context(tmp_path)
    for key in ('EARTHSHIP_THERMAL_INPUT_CAPTURE','EARTHSHIP_GUARDED_CAPTURE_WORKER'):monkeypatch.setenv(key,'1')
    monkeypatch.setenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT','0');monkeypatch.setattr(command.os,'getpriority',lambda *args:15)
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(command,'_worker',lambda *args:pytest.fail('changed context assembled'))
    assert command.main(args+['--worker','--expected-context-digest','0'*64])==2


def test_binding_failure_prevents_snapshot_persistence(tmp_path,monkeypatch):
    command=cli();data,records,paths,dsn,out,args=context(tmp_path)
    import thermal_model.capture_backends as backend
    import thermal_model.training_assembly as assembly
    import thermal_model.training_inputs as snapshot
    for key in ('EARTHSHIP_THERMAL_INPUT_CAPTURE','EARTHSHIP_GUARDED_CAPTURE_WORKER'):monkeypatch.setenv(key,'1')
    monkeypatch.setenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT','0');monkeypatch.setattr(command.os,'getpriority',lambda *args:15)
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None);monkeypatch.setattr(command,'_assembly_revision',lambda:'c'*64)
    monkeypatch.setattr(backend,'configured_capture_journal',lambda **kwargs:data['journal'])
    def failure(*args):raise OSError('synthetic binding failure')
    monkeypatch.setattr(assembly,'write_training_assembly',failure)
    monkeypatch.setattr(snapshot,'write_training_inputs',lambda *args:pytest.fail('snapshot persisted before lineage'))
    digest=command._context(paths,dsn,out)[-1]
    assert command.main(args+['--worker','--expected-context-digest',digest])==2
    assert list(out.iterdir())==[]


@pytest.mark.parametrize('target',['openhab/scripts/thermal_model/training_assembly.py','scripts/assemble-thermal-inputs.py'])
def test_assembly_revision_binds_executed_sources(monkeypatch,target):
    command=cli();changed=[False]
    import thermal_model.origin_capture as origin
    def source(path,maximum):return b'changed' if changed[0] and str(path.relative_to(command.ROOT))==target else b'original'
    monkeypatch.setattr(origin,'_source_bytes',source)
    first=command._assembly_revision();changed[0]=True
    assert command._assembly_revision()!=first
