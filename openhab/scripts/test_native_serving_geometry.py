"""Prepared geometry must freshly verify receipt admission, including cache hits."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import inspect,json
import pytest
from test_native_serving_live import fixture,originals
from test_native_thermal_forecast import ISSUE


def prepared(tmp_path,originals,monkeypatch):
    import native_thermal_live as live
    assert 'serving_model' in inspect.signature(live.prepare_geometry).parameters, 'receipt preparer context is missing'
    live,settings,model,backend,g,stage=fixture(tmp_path,originals,monkeypatch)
    clock=[ISSUE-timedelta(seconds=100)]
    monkeypatch.setattr(live,'_clock',lambda:clock[0])
    import astro_geometry_worker as worker
    from astro_geometry import build_cache
    from test_native_thermal_inputs import RUNTIME
    monkeypatch.setattr(worker,'runtime_identity',lambda *args,**kwargs:deepcopy(RUNTIME))
    calls=[]
    def capture(request,source,**kwargs):
        kwargs['guard']();calls.append(request);clock[0]+=timedelta(seconds=5)
        raw=''.join(at+'\t30\t180\n' for at in request['instants']).encode()
        return build_cache(request,source,native_output=raw,computed_at=clock[0])
    monkeypatch.setattr(worker,'capture_batch',capture)
    return live,settings,model,calls


def test_receipt_geometry_preparation_avoids_candidate_replay_and_keeps_all_instants(tmp_path,originals,monkeypatch):
    live,settings,model,calls=prepared(tmp_path,originals,monkeypatch)
    def forbidden(*args,**kwargs):pytest.fail('geometry preparation repeated full candidate numerical replay')
    monkeypatch.setattr(live,'read_native_candidate',forbidden)
    result=live.prepare_geometry(settings,issue=ISSUE,library_paths={},guard=lambda:None,serving_model=model)
    assert result['status']=='prepared'
    assert [len(chunk['instants']) for chunk in calls]==[128,128,32]
    assert live.read_geometry(settings,issue=ISSUE,guard=lambda:None).descriptor()['point_count']==288


def test_existing_geometry_does_not_authorize_a_changed_receipt_selection(tmp_path,originals,monkeypatch):
    live,settings,model,calls=prepared(tmp_path,originals,monkeypatch)
    result=live.prepare_geometry(settings,issue=ISSUE,library_paths={},guard=lambda:None,serving_model=model)
    assert Path(result['path']).exists()
    Path(settings['candidate_path']).write_bytes(b'{}')
    with pytest.raises(ValueError):live.prepare_geometry(settings,issue=ISSUE,library_paths={},guard=lambda:None,serving_model=model)
    assert len(calls)==3
