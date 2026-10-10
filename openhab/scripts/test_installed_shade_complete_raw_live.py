"""Complete raw live orchestration with synthetic ports, not household delivery."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
from pathlib import Path
import pytest
from test_installed_shade_complete_raw_publication import candidate,release_case,raw_release_math
from test_installed_shade_live import FakeBackend
from thermal_model.forcing_capture import _canonical
from thermal_model.installed_shade_artifact import _digest


@pytest.fixture
def raw_cycle(raw_release_math,tmp_path,monkeypatch):
    from thermal_model import installed_shade_live as live
    from thermal_model import installed_shade_publication as publisher
    from thermal_model import installed_shade_published_origin as captures
    from thermal_model.graduation_statistics import assess_current_predictive_skill
    artifact,report,numeric,_=raw_release_math;issue=datetime.fromisoformat(numeric['issued_at'])
    live._test_time=issue-timedelta(seconds=45);tmp_path.chmod(0o700)
    monkeypatch.setattr(live,'_clock',lambda:live._test_time)
    monkeypatch.setattr(live,'_wait_until',lambda at:setattr(live,'_test_time',at))
    report=deepcopy(report);report['assessed_at']=live._test_time.isoformat()
    report['statistics']=assess_current_predictive_skill(report['policy'],report['scored_pairs'],now=report['assessed_at'])
    report['report_sha256']=_digest({key:value for key,value in report.items() if key!='report_sha256'})
    prepared=publisher.PreparedRawInstalledQualification(_canonical(report),_canonical(artifact),True,False,
        ('thermal_intel.py','thermal_model/installed_shade_publication.py'))
    monkeypatch.setattr(live,'prepare_raw_installed_qualification',lambda _:prepared,raising=False)
    monkeypatch.setattr(live,'build_runtime_binding',lambda *args:artifact['runtime'])
    monkeypatch.setattr(publisher,'_clock',lambda:live._test_time)
    monkeypatch.setattr(publisher,'build_runtime_binding',lambda *args:artifact['runtime'])
    monkeypatch.setattr(captures,'_clock',lambda:live._test_time)
    return live,tmp_path,issue,prepared


def test_raw_live_cycle_retains_v4_numeric_v5_main_and_v5_qualification(raw_cycle):
    from thermal_model.installed_shade_published_origin import read_raw_publication_capture
    live,root,issue,_=raw_cycle;backend=FakeBackend(live,issue)
    result=live.run_raw_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='published' and result['mode']=='forecast_active'
    assert [item for item,_ in backend.puts]==['Thermal_OriginalForecast_JSON','Thermal_Model_JSON']
    assert backend.puts[0][1]['schema']=='earthship-installed-shade-forecast/v3'
    assert backend.puts[1][1]['schema']=='earthship-installed-shade-publication/v2'
    assert backend.puts[1][1]['version']==5
    record=read_raw_publication_capture(Path(result['capture_path']))
    assert record['schema']=='earthship-installed-shade-origin/v5'
    assert record['numeric_capture']['schema']=='earthship-installed-shade-origin/v4'
    assert record['numeric_publication']==backend.rows['Thermal_OriginalForecast_JSON']
    assert record['publication']==backend.rows['Thermal_Model_JSON']
    assert list(root.glob('*.installed-shade-qualification-v5.json'))
    assert result['automatic_actuation'] is False


@pytest.mark.parametrize('damage',['late_collection','config_drift','numeric_receipt','main_receipt','numeric_delay','main_delay','failed_withdrawal'])
def test_raw_live_failure_withdraws_v2_without_fabricated_capture(raw_cycle,damage):
    live,root,issue,_=raw_cycle;backend=FakeBackend(live,issue,damage)
    result=live.run_raw_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']==('unverified_failure' if damage=='failed_withdrawal' else 'withdrawn')
    assert not list(root.glob('*.installed-shade-origin-v5.json'))
    assert sum(item=='Thermal_OriginalForecast_JSON' for item,_ in backend.puts)<=1
    assert backend.puts[-1][1]['status']=='unavailable' and backend.puts[-1][1]['version']==5


def test_raw_live_rejects_legacy_prepared_type_before_collecting_inputs(raw_cycle,monkeypatch):
    from thermal_model.installed_shade_publication import PreparedInstalledQualification
    live,root,issue,prepared=raw_cycle
    weak=PreparedInstalledQualification(prepared.report_json,prepared.candidate_json,True,False,prepared.runtime_paths,True)
    monkeypatch.setattr(live,'prepare_raw_installed_qualification',lambda _:weak)
    backend=FakeBackend(live,issue)
    result=live.run_raw_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='withdrawn' and backend.collected is False
    assert [item for item,_ in backend.puts]==['Thermal_Model_JSON']
    assert backend.puts[0][1]['version']==5


def test_raw_live_duplicate_issue_never_reposts_numeric_forecast(raw_cycle):
    live,root,issue,_=raw_cycle
    (root/(issue.strftime('%Y%m%dT%H%M%SZ')+'.attempt.json')).write_text('{}')
    backend=FakeBackend(live,issue)
    result=live.run_raw_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='duplicate_attempt' and backend.puts==[]


def test_raw_explicit_withdrawal_proves_v2_receipt_and_never_touches_numeric(raw_cycle):
    live,root,issue,_=raw_cycle;backend=FakeBackend(live,issue)
    result=live.withdraw_raw_live_publication(archive=root,backend=backend,reason='qualification withdrawn')
    assert result['status']=='withdrawn' and result['delivery_verified'] is True
    assert [item for item,_ in backend.puts]==['Thermal_Model_JSON']
    assert backend.puts[0][1]['version']==5
    record=json.loads(Path(result['receipt_path']).read_text())
    assert record['schema']=='earthship-installed-shade-withdrawal/v2'
    assert record['publication']==backend.rows['Thermal_Model_JSON']
