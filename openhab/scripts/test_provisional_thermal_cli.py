"""Explicit provisional operations preserve guards and keep fitting isolated."""
import pytest


def module():
    import provisional_thermal
    return provisional_thermal


def test_failed_caps_precede_any_private_configuration_read(tmp_path,monkeypatch,capsys):
    def refuse():raise ValueError('resource failure')
    monkeypatch.setattr(module(),'_resource_preflight',refuse)
    assert module().main(['--config',str(tmp_path/'missing'),'--publish'])==1
    assert 'withheld' in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_train_dispatch_uses_supervisor_without_parent_fit(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(module(),'_resource_preflight',lambda:None)
    from thermal_model import training_pressure_guard as guard
    monkeypatch.setattr(guard.TrainingHeadroom,'preflight',lambda self:None)
    calls=[]
    def run(argv,**kwargs):calls.append(argv);return 1,b'{"status":"withheld"}'
    monkeypatch.setattr(guard,'run_training_worker',run)
    assert module().main(['--config',str(tmp_path/'missing'),'--train'])==1
    assert calls and '_train_worker' in calls[0][2]
    assert 'withheld' in capsys.readouterr().out
