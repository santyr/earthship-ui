"""Explicit native base shadow bootstrap; synthetic ports, no release proof."""
from copy import deepcopy
from datetime import timedelta
import json
import pytest
from test_installed_shade_origin import candidate,ISSUE
from test_installed_shade_live import FakeBackend
from thermal_model.forcing_capture import _canonical


@pytest.fixture
def bootstrap(candidate,tmp_path,monkeypatch):
    from thermal_model import installed_shade_live as live,installed_shade_publication as publisher,installed_shade_published_origin as captures
    from thermal_model.installed_shade_qualification import qualify_raw_published_installed_shade_candidate
    bundle,_,runtime=candidate;tmp_path.chmod(0o700);live._test_time=ISSUE-timedelta(seconds=45)
    report=qualify_raw_published_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=live._test_time)
    prepared=publisher.PreparedInstalledQualification(_canonical(report),_canonical(bundle['artifact']),True,True,tuple(runtime['source_manifest']),True)
    monkeypatch.setattr(live,'_clock',lambda:live._test_time)
    monkeypatch.setattr(live,'_wait_until',lambda at:setattr(live,'_test_time',at))
    monkeypatch.setattr(live,'prepare_installed_qualification',lambda _:prepared)
    monkeypatch.setattr(live,'build_runtime_binding',lambda *args:runtime)
    monkeypatch.setattr(publisher,'_clock',lambda:live._test_time)
    monkeypatch.setattr(publisher,'build_runtime_binding',lambda *args:runtime)
    monkeypatch.setattr(captures,'_clock',lambda:live._test_time)
    return live,tmp_path,prepared


def test_native_base_bootstrap_retains_shadow_receipts_for_raw_calibration(bootstrap):
    from thermal_model.installed_shade_published_origin import read_publication_capture
    live,root,_=bootstrap;backend=FakeBackend(live,ISSUE)
    result=live.run_bootstrap_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='published' and result['mode']=='shadow'
    record=read_publication_capture(result['capture_path'])
    assert record['numeric_capture']['candidate']['schema']=='earthship-installed-shade-candidate/v1'
    assert backend.puts[-1][1]['release']['forecastQualified'] is False
    assert backend.puts[-1][1]['release']['automaticActuation'] is False


@pytest.mark.parametrize('damage',['registered','receipt_only','calibrated'])
def test_bootstrap_refuses_any_nonbase_or_registered_profile_before_numeric(bootstrap,monkeypatch,damage):
    from dataclasses import replace
    live,root,prepared=bootstrap
    if damage=='registered':prepared=replace(prepared,registration_absent=False)
    elif damage=='receipt_only':prepared=replace(prepared,require_raw_sources=False)
    else:
        artifact=json.loads(prepared.candidate_json);artifact['schema']='earthship-installed-shade-candidate/v2'
        prepared=replace(prepared,candidate_json=_canonical(artifact))
    monkeypatch.setattr(live,'prepare_installed_qualification',lambda _:prepared)
    backend=FakeBackend(live,ISSUE)
    result=live.run_bootstrap_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='withdrawn' and backend.collected is False
    assert [item for item,_ in backend.puts]==['Thermal_Model_JSON']
