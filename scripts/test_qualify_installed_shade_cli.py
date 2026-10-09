"""Qualification command must expose the raw-source contract without activation."""
import importlib.util
import json
from pathlib import Path
import pytest


def module():
    spec=importlib.util.spec_from_file_location('installed_qualification_cli',Path(__file__).with_name('qualify-installed-shade.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize('version',[4,5])
def test_cli_v4_writes_real_unavailable_report_and_human_gates(tmp_path,monkeypatch,capsys,version):
    tmp_path.chmod(0o700)
    lock=tmp_path/'global.lock';lock.touch(mode=0o600)
    source=module()
    monkeypatch.setattr(source,'_resource_preflight',lambda:None,raising=False)
    assert source.main(['--contract-version',str(version),'--shared-lock',str(lock),'--output-dir',str(tmp_path)])==0
    result=json.loads(capsys.readouterr().out)
    assert result['forecast_qualified'] is False and result['recommended_stage']=='unavailable'
    paths=list(map(Path,result['report_paths']))
    record=json.loads(next(path for path in paths if path.suffix=='.json').read_text())
    assert record['schema']=='earthship-installed-shade-qualification-report/v'+str(version)
    assert record['gates']['raw_native_score_sources'] is False
    if version==5:
        assert record['gates']['raw_calibration_sources'] is False
        assert record['gates']['raw_development_sources'] is False
    assert 'raw_native_score_sources' in next(path for path in paths if path.suffix=='.md').read_text()


@pytest.mark.parametrize('version',[4,5])
def test_v4_preflight_refusal_is_sanitized_and_writes_nothing(tmp_path,monkeypatch,capsys,version):
    source=module()
    def refuse():raise ValueError('private resource diagnostic')
    monkeypatch.setattr(source,'_resource_preflight',refuse,raising=False)
    assert source.main(['--contract-version',str(version),'--shared-lock',str(tmp_path/'missing.lock'),'--output-dir',str(tmp_path)])==1
    output=capsys.readouterr()
    assert 'withheld' in output.out and 'private resource diagnostic' not in output.out+output.err
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('version',[1,2,3])
def test_earlier_cli_profiles_preserve_unavailable_reports(tmp_path,capsys,version):
    tmp_path.chmod(0o700)
    assert module().main(['--contract-version',str(version),'--output-dir',str(tmp_path)])==0
    assert json.loads(capsys.readouterr().out)['forecast_qualified'] is False


@pytest.mark.parametrize('version',[4,5])
def test_v4_lock_contention_never_writes_a_report(tmp_path,monkeypatch,capsys,version):
    from thermal_installed_score import SharedScoreLock
    tmp_path.chmod(0o700);lock=tmp_path/'global.lock';lock.touch(mode=0o600)
    source=module();monkeypatch.setattr(source,'_resource_preflight',lambda:None)
    with SharedScoreLock(lock):
        assert source.main(['--contract-version',str(version),'--shared-lock',str(lock),'--output-dir',str(tmp_path)])==75
    assert json.loads(capsys.readouterr().out)['status']=='busy'
    assert list(tmp_path.iterdir())==[lock]


@pytest.mark.parametrize('version',[4,5])
def test_v4_restores_fitting_environment_after_report(tmp_path,monkeypatch,capsys,version):
    import os
    tmp_path.chmod(0o700);lock=tmp_path/'global.lock';lock.touch(mode=0o600)
    source=module();monkeypatch.setattr(source,'_resource_preflight',lambda:None)
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1')
    monkeypatch.delenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT',raising=False)
    assert source.main(['--contract-version',str(version),'--shared-lock',str(lock),'--output-dir',str(tmp_path)])==0
    assert os.environ['EARTHSHIP_QUALIFICATION_FIT']=='1'
    assert 'EARTHSHIP_REMOTE_QUALIFICATION_FIT' not in os.environ
