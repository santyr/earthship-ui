"""Raw release references select fresh v4 gates, never a cached report."""
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import pytest
from thermal_model.forcing_capture import _canonical

NOW=datetime(2026,10,9,20,tzinfo=timezone.utc)
RAW_HELPERS={'weather_temperature_sources.py','forecast_input_capture.py','forecast_temperature_origin.py','thermal_model/installed_shade_raw_score_sources.py'}


def module():
    from thermal_model import installed_shade_publication as p
    assert hasattr(p,'RAW_REFERENCE_SCHEMA'),'missing versioned raw release references'
    return p


def setup(tmp_path,monkeypatch):
    from thermal_model.installed_shade_qualification import qualify_raw_published_installed_shade_candidate
    p=module();tmp_path.chmod(0o700)
    refs=tmp_path/'refs.json';refs.write_text(json.dumps(dict(schema=p.RAW_REFERENCE_SCHEMA,registration_path=None,candidate_path='model.installed-shade-candidate-v2.json',runtime_bundle_path='runtime',original_pairs_path=None)));refs.chmod(0o600)
    runtime={'source_manifest':{n:'a'*64 for n in p.RAW_RUNTIME_PATHS}}
    report=qualify_raw_published_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=NOW)
    monkeypatch.setattr(p,'_clock',lambda:NOW)
    monkeypatch.setattr(p,'read_runtime_bundle',lambda _:dict(runtime=runtime,revision_paths=list(runtime['source_manifest'])))
    monkeypatch.setattr(p,'build_runtime_binding',lambda *args:runtime)
    monkeypatch.setattr(p,'read_calibrated_candidate',lambda *a,**k:dict(artifact={},calibration={'summary':{'complete':True}},fit_evidence={'fit_gates_passed':True}))
    monkeypatch.setattr(p,'qualify_raw_published_installed_shade_candidate',lambda **kwargs:deepcopy(report))
    monkeypatch.setattr(p,'qualify_published_installed_shade_candidate',lambda **kwargs:pytest.fail('raw references selected legacy qualifier'))
    return p,refs,runtime,report


def test_raw_reference_profile_uses_v4_qualification_and_preserves_closed_gate(tmp_path,monkeypatch):
    p,refs,_,_=setup(tmp_path,monkeypatch);prepared=p.prepare_installed_qualification(refs)
    assert prepared.source_ready is True and prepared.require_raw_sources is True
    report=json.loads(prepared.report_json)
    assert report['schema']=='earthship-installed-shade-qualification-report/v4'
    assert report['forecast_qualified'] is False
    assert report['gates']['raw_native_score_sources'] is False


@pytest.mark.parametrize('helper',sorted(RAW_HELPERS))
def test_raw_reference_cannot_prepare_without_each_raw_runtime_helper(tmp_path,monkeypatch,helper):
    p,refs,runtime,_=setup(tmp_path,monkeypatch);runtime['source_manifest'].pop(helper)
    assert p.prepare_installed_qualification(refs).source_ready is False


def test_raw_preparation_refuses_legacy_report_before_current_origin_reads(tmp_path,monkeypatch):
    from thermal_model.installed_shade_qualification import qualify_installed_shade_candidate
    p=module();assert 'require_raw_sources' in p.PreparedInstalledQualification.__dataclass_fields__
    report=qualify_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=NOW)
    prepared=p.PreparedInstalledQualification(_canonical(report),b'{}',True,True,('thermal_intel.py',),require_raw_sources=True)
    monkeypatch.setattr(p,'_read_origin',lambda _:pytest.fail('legacy report reached current origin read'))
    assert p.build_installed_publication(tmp_path/'never-open',prepared)['status']=='unavailable'


def test_live_report_cache_accepts_only_valid_v4_report(tmp_path):
    from thermal_model.installed_shade_qualification import qualify_raw_published_installed_shade_candidate
    from thermal_model.installed_shade_live import _report_cache
    module();tmp_path.chmod(0o700)
    report=qualify_raw_published_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=NOW)
    try:paths=_report_cache(tmp_path,report)
    except KeyError:pytest.fail('live path does not support v4 report cache')
    assert any(p.name.endswith('.installed-shade-qualification-v4.json') for p in paths)
