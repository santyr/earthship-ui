"""CLI preserves the real legacy generation contract; never executes recovery."""
import importlib.util
import json
from pathlib import Path
import pytest
from test_thermal_legacy_recovery import fixture


def cli():
    path=Path(__file__).with_name('prepare-thermal-legacy-recovery.py')
    spec=importlib.util.spec_from_file_location('legacy_prepare_cli',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def configuration(tmp_path):
    values=fixture(tmp_path);values.pop('reason')
    path=tmp_path/'inputs.json';path.write_text(json.dumps(values,default=str));path.chmod(0o600)
    return path


def test_prepare_and_verify_cli_exercise_actual_generation(tmp_path,capsys):
    inputs=configuration(tmp_path);target=tmp_path/'recovery';command=cli()
    assert command.main(['--inputs',str(inputs),'--destination',str(target),'--reason','operator_rollback'])==0
    receipt=json.loads(capsys.readouterr().out)
    assert receipt['installed'] is False and receipt['automatic_actuation'] is False
    assert command.main(['--destination',str(target),'--reason','operator_rollback','--verify-only'])==0
    assert json.loads(capsys.readouterr().out)==receipt
    assert command.main(['--destination',str(target),'--reason','baseline_regression','--verify-only'])==2
    assert capsys.readouterr().out==''


@pytest.mark.parametrize('damage',['duplicate','extra','mode','parent_mode'])
def test_bad_private_inputs_refuse_before_preparation(tmp_path,monkeypatch,capsys,damage):
    path=configuration(tmp_path);command=cli()
    if damage=='duplicate':path.write_text('{"source_root":"/first","source_root":"/second"}')
    elif damage=='extra':
        value=json.loads(path.read_text());value['installed']=True;path.write_text(json.dumps(value))
    elif damage=='mode':path.chmod(0o644)
    else:tmp_path.chmod(0o755)
    def unexpected(*args,**kwargs):pytest.fail('invalid inputs reached preparation')
    monkeypatch.setattr(command,'prepare_legacy_generation',unexpected)
    assert command.main(['--inputs',str(path),'--destination',str(tmp_path/'refused'),'--reason','operator_rollback'])==2
    assert not (tmp_path/'refused').exists() and capsys.readouterr().out==''


def test_input_read_is_paced_before_preparation(tmp_path,monkeypatch,capsys):
    path=configuration(tmp_path);command=cli();events=[]
    class Pace:
        def reserve(self,size):events.append(('reserve',size))
    monkeypatch.setattr(command,'_pacer',lambda rate:Pace())
    original=command._owned_bytes
    def read(path,maximum):
        assert events==[('reserve',maximum)]
        return original(path,maximum)
    monkeypatch.setattr(command,'_owned_bytes',read)
    def refuse(*args,**kwargs):
        assert kwargs['max_read_bytes_per_second']==100
        raise ValueError('stop before archive work')
    monkeypatch.setattr(command,'prepare_legacy_generation',refuse)
    assert command.main(['--inputs',str(path),'--destination',str(tmp_path/'refused'),'--reason','operator_rollback','--max-read-bytes-per-second','100'])==2
    assert events and capsys.readouterr().out==''
