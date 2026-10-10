"""Offline builder authority boundaries; fixtures do not qualify a model."""
import importlib
import sys
import pytest


def module():
    return importlib.import_module('thermal_installed_train')


def test_default_builder_refuses_missing_private_config_without_numerical_imports(tmp_path,capsys,monkeypatch):
    source=module()
    numerical=[]
    original=__import__
    def guarded(name,*args,**kwargs):
        if name.split('.')[0] in {'numpy','scipy'}:
            numerical.append(name)
            pytest.fail('default config check imported numerical fitting code')
        return original(name,*args,**kwargs)
    monkeypatch.setattr('builtins.__import__',guarded)
    assert source.main(['--config',str(tmp_path/'missing.json')])==1
    assert not numerical
    assert 'withheld' in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_fitting_guard_failure_precedes_original_source_reads(tmp_path,capsys,monkeypatch):
    source=module()
    def refuse():raise ValueError('resource guard failure with private diagnostic marker')
    monkeypatch.setattr(source,'_resource_preflight',refuse)
    assert source.main(['--config',str(tmp_path/'missing.json'),'--fit'])==1
    output=capsys.readouterr()
    assert 'withheld' in output.out
    assert 'private diagnostic marker' not in output.out+output.err
    assert not list(tmp_path.iterdir())


def settings(tmp_path):
    import json
    tmp_path.chmod(0o700)
    snapshot=tmp_path/'snapshot.json';snapshot.write_text('not-read-by-config-check');snapshot.chmod(0o600)
    runtime=tmp_path/'runtime';runtime.mkdir(mode=0o700)
    lock=tmp_path/'shared.lock';lock.touch(mode=0o600)
    output=tmp_path/'output';output.mkdir(mode=0o700)
    value=dict(schema='earthship-installed-shade-training-config/v1',snapshot_path=str(snapshot),snapshot_sha256='a'*64,
        runtime_bundle_path=str(runtime),runtime_sha256='b'*64,code_revision='c'*64,
        sensor_epochs={role:str(__import__('uuid').UUID(int=i+1)) for i,role in enumerate(('air','mass','outdoor'))},
        training_start='2026-10-01T00:00:00Z',training_end='2026-10-02T00:00:00Z',initial_coefficients=[0.01]*10,
        output_directory=str(output),shared_lock=str(lock))
    path=tmp_path/'config.json';path.write_text(json.dumps(value));path.chmod(0o600)
    return path,value


def test_valid_default_config_does_not_read_original_snapshot(tmp_path,capsys):
    path,value=settings(tmp_path)
    assert module().main(['--config',str(path)])==0
    output=__import__('json').loads(capsys.readouterr().out)
    assert output==dict(status='configuration_verified',fit_executed=False,release_authorized=False)
    assert not list((tmp_path/'output').iterdir())


@pytest.mark.parametrize('damage',['extra','boolean_coefficient','reverse_interval','public_config','relative_snapshot','duplicate'])
def test_invalid_closed_build_configuration_refuses(tmp_path,capsys,damage):
    import json
    path,value=settings(tmp_path)
    if damage=='extra':value['active']=True
    if damage=='boolean_coefficient':value['initial_coefficients'][0]=True
    if damage=='reverse_interval':value['training_end']=value['training_start']
    if damage=='relative_snapshot':value['snapshot_path']='snapshot.json'
    path.write_text(json.dumps(value))
    if damage=='public_config':path.chmod(0o644)
    if damage=='duplicate':path.write_text(path.read_text().replace('"schema":','"schema": "duplicate", "schema":',1))
    assert module().main(['--config',str(path)])==1
    assert 'withheld' in capsys.readouterr().out


def pipeline(tmp_path,monkeypatch,*,stable=True):
    from types import SimpleNamespace
    import thermal_model.installed_shade_training as source
    import thermal_model.installed_shade_artifact as artifacts
    import thermal_model.installed_shade_fit as fitter
    import thermal_model.training_inputs as inputs
    import thermal_model.runtime_bundle as runtime
    import thermal_model.origin_capture as origins
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    from hashlib import sha256
    import json
    _,values=settings(tmp_path)
    binding={'code_revision':values['code_revision']}
    values['runtime_sha256']=sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    monkeypatch.setattr(runtime,'read_runtime_bundle',lambda path:dict(runtime=binding,revision_paths=sorted(RAW_RUNTIME_PATHS)))
    monkeypatch.setattr(origins,'build_runtime_binding',lambda root,paths:binding.copy())
    monkeypatch.setattr(inputs,'read_training_inputs_v2',lambda path:dict(snapshot_sha256=values['snapshot_sha256']))
    durations=[]
    def fit(record,**kwargs):
        durations.append(kwargs['timeout_seconds'])
        return SimpleNamespace(stability=SimpleNamespace(assessed=stable))
    monkeypatch.setattr(fitter,'fit_development_inputs',fit)
    def build(record,report,**kwargs):
        durations.append(kwargs['timeout_seconds'])
        return dict(artifact={'artifact_sha256':'d'*64},fit_evidence={'fit_gates_passed':stable})
    monkeypatch.setattr(artifacts,'build_candidate_bundle',build)
    writes=[]
    def write(root,bundle,record,**kwargs):
        durations.append(kwargs['timeout_seconds']);writes.append(bundle)
        return tmp_path/'output'/('d'*64+'.installed-shade-candidate-v1.json')
    monkeypatch.setattr(artifacts,'write_candidate_bundle',write)
    def read(path,**kwargs):
        durations.append(kwargs['timeout_seconds'])
        return dict(artifact={'artifact_sha256':'d'*64},fit_evidence={'fit_gates_passed':stable})
    monkeypatch.setattr(artifacts,'read_candidate_bundle',read)
    return source,values,durations,writes


def test_unassessed_stability_never_writes_a_bootstrap_candidate(tmp_path,monkeypatch):
    source,values,_,writes=pipeline(tmp_path,monkeypatch,stable=False)
    with pytest.raises(ValueError,match='stability'):source.run_candidate_training(values,guard=lambda:None)
    assert not writes


def test_one_deadline_covers_fit_proof_write_and_readback(tmp_path,monkeypatch):
    import os
    source,values,durations,writes=pipeline(tmp_path,monkeypatch)
    ticks=iter(range(100))
    monkeypatch.setattr(source,'_monotonic',lambda:next(ticks))
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','0')
    result=source.run_candidate_training(values,guard=lambda:None)
    assert result['status']=='development_candidate' and result['release_authorized'] is False
    assert len(writes)==1 and len(durations)==4
    assert all(0<b<a<=85 for a,b in zip(durations,durations[1:]))
    assert os.environ['EARTHSHIP_QUALIFICATION_FIT']=='0'


def test_changed_runtime_before_persistence_refuses_candidate(tmp_path,monkeypatch):
    source,values,_,writes=pipeline(tmp_path,monkeypatch)
    from thermal_model import origin_capture
    count=[0]
    def changed(root,paths):
        count[0]+=1
        return dict(code_revision=values['code_revision'] if count[0]==1 else 'e'*64)
    monkeypatch.setattr(origin_capture,'build_runtime_binding',changed)
    with pytest.raises(ValueError,match='runtime'):source.run_candidate_training(values,guard=lambda:None)
    assert not writes


def test_exhausted_shared_deadline_never_persists_candidate(tmp_path,monkeypatch):
    import os
    source,values,_,writes=pipeline(tmp_path,monkeypatch)
    ticks=[0]
    monkeypatch.setattr(source,'_monotonic',lambda:ticks[0])
    from thermal_model import installed_shade_fit
    def exhausted(*args,**kwargs):
        ticks[0]=86
        return __import__('types').SimpleNamespace(stability=__import__('types').SimpleNamespace(assessed=True))
    monkeypatch.setattr(installed_shade_fit,'fit_development_inputs',exhausted)
    monkeypatch.delenv('EARTHSHIP_QUALIFICATION_FIT',raising=False)
    with pytest.raises(ValueError,match='deadline'):source.run_candidate_training(values,guard=lambda:None)
    assert not writes and 'EARTHSHIP_QUALIFICATION_FIT' not in os.environ


def test_cli_failure_after_fit_dispatch_does_not_claim_fit_never_ran(tmp_path,capsys,monkeypatch):
    source=module();path,_=settings(tmp_path)
    from thermal_model import installed_shade_training
    from thermal_installed_score import SharedScoreLock
    monkeypatch.setattr(source,'_resource_preflight',lambda:None)
    def failed(*args,**kwargs):raise ValueError('failure after partial numerical work')
    monkeypatch.setattr(installed_shade_training,'run_candidate_training',failed)
    assert source._fit(path)==1
    result=__import__('json').loads(capsys.readouterr().out)
    assert result['fit_executed'] is None


def test_completed_builder_retains_private_execution_receipt(tmp_path,monkeypatch):
    import json
    source,values,_,_=pipeline(tmp_path,monkeypatch)
    result=source.run_candidate_training(values,guard=lambda:None)
    receipt=__import__('pathlib').Path(result['build_receipt_path'])
    record=json.loads(receipt.read_text())
    assert record['schema']=='earthship-installed-shade-build-receipt/v1'
    assert record['release_authorized'] is False and record['production_installed'] is False
    assert record['snapshot_sha256']==values['snapshot_sha256']
    assert record['artifact_sha256']==result['artifact_sha256']
    assert set(record['builder_sources'])=={'thermal_installed_train.py','thermal_model/installed_shade_training.py','thermal_model/training_pressure_guard.py'}
    assert receipt.stat().st_mode&0o777==0o600


def test_retained_native_snapshot_is_replayed_before_insufficient_stability_refusal(tmp_path,monkeypatch):
    from thermal_model import training_inputs,installed_shade_fit
    real_read=training_inputs.read_training_inputs_v2
    source,values,_,writes=pipeline(tmp_path,monkeypatch)
    monkeypatch.setattr(training_inputs,'read_training_inputs_v2',real_read)
    from test_installed_shade_inputs import snapshot,START,EPOCHS
    from thermal_model.installed_shade_inputs import build_development_inputs
    record=snapshot(steps=300)
    path=training_inputs.write_training_inputs_v2(tmp_path,record)
    values.update(snapshot_path=str(path),snapshot_sha256=record['snapshot_sha256'],sensor_epochs=EPOCHS,
        training_start=START.isoformat(),training_end=record['end'])
    def validate_original(original,**kwargs):
        data=build_development_inputs(original,expected_snapshot_sha256=kwargs['expected_snapshot_sha256'],
            sensor_epochs=kwargs['sensor_epochs'],assessed_at=kwargs['assessed_at'])
        assert data.source_snapshot_sha256==record['snapshot_sha256']
        return __import__('types').SimpleNamespace(stability=__import__('types').SimpleNamespace(assessed=False))
    monkeypatch.setattr(installed_shade_fit,'fit_development_inputs',validate_original)
    with pytest.raises(ValueError,match='stability'):source.run_candidate_training(values,guard=lambda:None)
    assert not writes and not list((tmp_path/'output').iterdir())


def test_config_swapped_for_symlink_after_validation_is_refused(tmp_path,monkeypatch,capsys):
    from thermal_model import installed_shade_training as training
    path,_=settings(tmp_path)
    substitute=tmp_path/'substitute.json';substitute.write_bytes(path.read_bytes());substitute.chmod(0o600)
    original=training._path
    def swapped(value,**kwargs):
        result=original(value,**kwargs)
        if result==path:
            path.unlink();path.symlink_to(substitute)
        return result
    monkeypatch.setattr(training,'_path',swapped)
    assert module().main(['--config',str(path)])==1
    assert 'withheld' in capsys.readouterr().out
