"""Shared worker commands stay sealed while original families retain their bytes."""
from pathlib import Path
import shlex
import pytest


def fixture(tmp_path):
    stage=tmp_path/'stage';scripts=stage/'sources/openhab/scripts';scripts.mkdir(parents=True)
    (scripts/'household_forecast_score.py').write_text('SCORE_LIFETIME_SECONDS = 120\n')
    (scripts/'household_cycle.py').write_text('# driver\n')
    template=stage/'service.conf'
    template.write_text('[Service]\nExecStart=/usr/bin/python3 driver.py --stage '+str(stage)+'\n')
    template.chmod(0o600)
    return stage,scripts


def enable(scripts):
    (scripts/'household_cycle_resources.py').write_text('SHARED_PRODUCTION_POOL = True\n')
    for name in ('run','launch','pool','budget','start'):
        (scripts/('household_job_'+name+'.py')).write_text('# sealed helper\n')


def test_rendered_workers_share_pool_and_preserve_inner_commands(tmp_path):
    import household_native_family as family
    stage,scripts=fixture(tmp_path)
    before=family._render(stage,stage/'config.json',stage/'libraries.json',deployment_sha256='a'*64)
    enable(scripts)
    after=family._render(stage,stage/'config.json',stage/'libraries.json',deployment_sha256='a'*64)
    for name in ('forecast.conf','score.conf','thermal-native-geometry-prepare.service'):
        command=lambda raw:next(line[10:] for line in raw.decode().splitlines() if line.startswith('ExecStart=') and line!='ExecStart=')
        old=shlex.split(command(before[name]));new=shlex.split(command(after[name]))
        assert new[:2]==['/usr/bin/python3',str(scripts/'household_job_run.py')]
        assert '--production' in new
        assert new[new.index('--minimum-mib')+1]=='256'
        assert new[new.index('--preferred-mib')+1]=='512'
        assert new[new.index('--')+1:]==old
    assert after['score-timer.conf']==before['score-timer.conf']
    assert after['thermal-native-geometry-prepare.timer']==before['thermal-native-geometry-prepare.timer']


def test_incomplete_shared_launcher_refuses_instead_of_using_old_limits(tmp_path):
    import household_native_family as family
    stage,scripts=fixture(tmp_path);enable(scripts)
    (scripts/'household_job_start.py').unlink()
    with pytest.raises(ValueError,match='shared launcher'):
        family._render(stage,stage/'config.json',stage/'libraries.json',deployment_sha256='a'*64)


def test_explicit_retained_interpreter_changes_only_inner_numerical_workers(tmp_path):
    from hashlib import sha256
    import household_native_family as family
    stage,scripts=fixture(tmp_path);enable(scripts)
    binary=tmp_path/'python3.12';binary.write_bytes(b'explicit test interpreter bytes');binary.chmod(0o500)
    ref=dict(path=str(binary),sha256=sha256(binary.read_bytes()).hexdigest())
    files=family._render(stage,stage/'config.json',stage/'libraries.json',deployment_sha256='a'*64,interpreter=ref)
    for name in ('forecast.conf','score.conf','thermal-native-geometry-prepare.service'):
        command=next(line[10:] for line in files[name].decode().splitlines() if line.startswith('ExecStart=') and line!='ExecStart=')
        words=shlex.split(command)
        assert words[:2]==['/usr/bin/python3',str(scripts/'household_job_run.py')]
        assert words[words.index('--')+1]==str(binary)
    assert family._interpreter_reference(ref)==ref
    binary.chmod(0o700);binary.write_bytes(b'changed')
    with pytest.raises(ValueError,match='interpreter'):family._render(stage,stage/'config.json',stage/'libraries.json',interpreter=ref)


def test_retained_interpreter_requires_closed_owned_executable_bytes(tmp_path):
    import household_native_family as family
    binary=tmp_path/'python3.12';binary.write_bytes(b'explicit bytes');binary.chmod(0o500)
    from hashlib import sha256
    ref=dict(path=str(binary),sha256=sha256(binary.read_bytes()).hexdigest())
    assert family._interpreter_reference(ref)==ref
    with pytest.raises(ValueError):family._interpreter_reference(dict(ref,unreviewed=True))
    binary.chmod(0o520)
    with pytest.raises(ValueError):family._interpreter_reference(ref)


def test_retained_interpreter_matches_the_declared_admitted_model_and_serving_mode(tmp_path):
    import json
    from hashlib import sha256
    import household_native_family as family
    binary=tmp_path/'python3.12';binary.write_bytes(b'explicit test interpreter');binary.chmod(0o500)
    ref=dict(path=str(binary),sha256=sha256(binary.read_bytes()).hexdigest())
    candidate=tmp_path/'candidate.json'
    candidate.write_text(json.dumps({'runtime':{'base_runtime':{'interpreter_sha256':ref['sha256']}}}));candidate.chmod(0o600)
    settings=dict(candidate_path=str(candidate))
    family._model_interpreter(settings,ref,serving=True)
    with pytest.raises(ValueError,match='receipt-serving'):family._model_interpreter(settings,ref,serving=False)
    with pytest.raises(ValueError,match='admitted model'):family._model_interpreter(settings,dict(ref,sha256='b'*64),serving=True)


@pytest.mark.parametrize('retained',[False,True])
def test_daily_activation_uses_the_verified_family_interpreter(tmp_path,monkeypatch,retained):
    import household_native_training as training
    stage=tmp_path/'run/final';stage.mkdir(parents=True,mode=0o700)
    ref=dict(path=str(tmp_path/'python3.12'),sha256='a'*64) if retained else None
    monkeypatch.setattr(training,'selected_family_interpreter',lambda *a,**k:ref,raising=False)
    calls=[]
    def run(command,**kwargs):
        calls.append(command);training.save(stage.parent/'activation-result.json',{'status':'activated'})
    import household_native_lifecycle as lifecycle
    from types import SimpleNamespace
    monkeypatch.setattr(lifecycle,'run_activation_child',run)
    runner=object.__new__(training.NativeTraining);runner.guard=lambda:None
    runner.learner_lock=SimpleNamespace(fd=42,verify=lambda:None)
    runner.reservation=SimpleNamespace(directory=tmp_path/'reservation',check=lambda:None)
    if not retained:
        with pytest.raises(ValueError,match='retained verified'):runner.activate(dict(stage=str(stage),deployment_sha256='a'*64),{})
        assert calls==[]
        return
    assert runner.activate(dict(stage=str(stage),deployment_sha256='a'*64),{})=={'status':'activated'}
    assert calls[0][0]==(ref['path'] if retained else '/usr/bin/python3')
