"""Original publication capture is optional and never revokes an accepted write."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_thermal_origin_capture import capture_inputs,runtime_tree,NOW
from thermal_model.origin_capture import read_origin_capture
from thermal_model.runtime_bundle import read_runtime_bundle


def setup(tmp_path,monkeypatch):
    import thermal_intel
    import thermal_model.runtime_bundle as bundles
    root,_=runtime_tree(tmp_path,monkeypatch)
    helper=root/'thermal_model/runtime_bundle.py'
    helper.write_bytes(Path(bundles.__file__).read_bytes());helper.chmod(0o600)
    monkeypatch.setattr(thermal_intel,'__file__',str(root/'thermal_intel.py'))
    monkeypatch.setattr(thermal_intel,'RUNTIME_REVISION_PATHS',('thermal_intel.py',))
    data=capture_inputs();proofs=[]
    monkeypatch.setattr(thermal_intel.forecast_intel,'load_site_settings',lambda:None)
    def current(now,*,origin_observer=None):
        if origin_observer is not None:origin_observer(deepcopy(data['origin_temperatures']));proofs.append(True)
        return deepcopy(data['current'])
    monkeypatch.setattr(thermal_intel,'_current_states',current)
    monkeypatch.setattr(thermal_intel.forecast_intel,'fetch_forecast',lambda:deepcopy(data['snapshot']))
    monkeypatch.setattr(thermal_intel,'_forecast_rows',lambda *_:deepcopy(data['rows']))
    def predict(**kwargs):
        kwargs['artifact_observer'](data['artifact']);return deepcopy(data['output'])
    monkeypatch.setattr(thermal_intel,'run_shadow',predict)
    monkeypatch.delenv('THERMAL_SHADOW_CAPTURE_DIR',raising=False)
    monkeypatch.delenv('THERMAL_ORIGIN_CAPTURE_DIR',raising=False)
    archive=tmp_path/'origins';archive.mkdir(mode=0o700)
    return thermal_intel,data,archive,proofs


def publish(thermal_intel,tmp_path,*,enabled=True):
    accepted=[]
    status=thermal_intel._shadow(SimpleNamespace(output=tmp_path/'shadow.json',publish=enabled),NOW,
        put_state=lambda *args:accepted.append(args),decision_clock=lambda:NOW+timedelta(seconds=1),
        published_clock=lambda:NOW+timedelta(seconds=2))
    return status,accepted


def test_capture_is_default_off_and_nonpublished_runs_collect_nothing(tmp_path,monkeypatch):
    thermal,data,archive,proofs=setup(tmp_path,monkeypatch)
    status,accepted=publish(thermal,tmp_path)
    assert status==0 and len(accepted)==1 and proofs==[]
    monkeypatch.setenv('THERMAL_ORIGIN_CAPTURE_DIR',str(archive))
    status,accepted=publish(thermal,tmp_path,enabled=False)
    assert status==0 and accepted==[] and proofs==[]
    assert list(archive.iterdir())==[]


def test_published_original_input_proof_has_retained_runtime_and_native_epochs(tmp_path,monkeypatch):
    thermal,data,archive,proofs=setup(tmp_path,monkeypatch)
    monkeypatch.setenv('THERMAL_ORIGIN_CAPTURE_DIR',str(archive))
    status,accepted=publish(thermal,tmp_path)
    assert status==0 and len(accepted)==1 and proofs==[True]
    records=list(archive.glob('*/*-origin-v1.json.gz'));assert len(records)==1
    record=read_origin_capture(records[0])
    assert record['issued_at']==(NOW+timedelta(seconds=1)).isoformat()
    assert record['published_at']==(NOW+timedelta(seconds=2)).isoformat()
    assert record['origin_temperatures']['assessed_at']==NOW.isoformat()
    assert record['known_actions'] is None
    bundles=list((archive/'runtime-bundles').iterdir())
    runtime=[path for path in bundles if path.is_dir()];assert len(runtime)==1
    assert read_runtime_bundle(runtime[0])['runtime']==record['runtime']


@pytest.mark.parametrize('failure',['missing_native','archive','runtime_drift'])
def test_capture_failure_keeps_accepted_publication_and_reports_gap(tmp_path,monkeypatch,capsys,failure):
    thermal,data,archive,proofs=setup(tmp_path,monkeypatch)
    monkeypatch.setenv('THERMAL_ORIGIN_CAPTURE_DIR',str(archive))
    if failure=='missing_native':monkeypatch.setattr(thermal,'_current_states',lambda *args,**kwargs:deepcopy(data['current']))
    elif failure=='archive':archive.chmod(0o755)
    elif failure=='runtime_drift':
        real=thermal.forecast_intel.fetch_forecast
        def fetch():
            Path(thermal.__file__).write_bytes(b'# changed during prediction\n');return real()
        monkeypatch.setattr(thermal.forecast_intel,'fetch_forecast',fetch)
    status,accepted=publish(thermal,tmp_path)
    assert status==0 and len(accepted)==1
    assert list(archive.glob('*/*-origin-v1.json.gz'))==[]
    assert 'thermal origin capture gap' in capsys.readouterr().err


def test_default_publication_never_calls_optional_archive_clock(tmp_path,monkeypatch):
    thermal,data,archive,proofs=setup(tmp_path,monkeypatch)
    def unexpected():raise AssertionError('archive clock called with capture disabled')
    status=thermal._shadow(SimpleNamespace(output=tmp_path/'shadow.json',publish=True),NOW,
        put_state=lambda *_:None,published_clock=unexpected)
    assert status==0


def test_unavailable_optional_capture_module_does_not_change_publication(tmp_path,monkeypatch,capsys):
    thermal,data,archive,proofs=setup(tmp_path,monkeypatch)
    monkeypatch.setenv('THERMAL_ORIGIN_CAPTURE_DIR',str(archive))
    def missing():raise ImportError('capture dependency unavailable')
    monkeypatch.setattr(thermal,'_origin_runtime_binding',missing)
    status,accepted=publish(thermal,tmp_path)
    assert status==0 and len(accepted)==1
    assert 'thermal origin capture gap' in capsys.readouterr().err
