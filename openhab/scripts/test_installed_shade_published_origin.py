"""Actual publication contract math; synthetic fixtures are not release evidence."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
import pytest

from test_installed_shade_publication import release_case,candidate,prepared
from test_installed_shade_origin import outcome
from test_installed_shade_calibration import synthetic_cycle_grid
from thermal_model.installed_shade_artifact import _digest


def module():
    from thermal_model import installed_shade_published_origin
    return installed_shade_published_origin


@pytest.fixture
def issued(tmp_path,release_case,monkeypatch):
    from thermal_model import installed_shade_publication as publisher
    from thermal_model.installed_shade_calibrated_origin import write_calibrated_capture
    artifact,report,original,now=release_case;tmp_path.chmod(0o700)
    path=write_calibrated_capture(tmp_path,original)
    monkeypatch.setattr(publisher,'_clock',lambda:now+timedelta(seconds=1))
    monkeypatch.setattr(publisher,'build_runtime_binding',lambda *args:original['runtime'])
    output=publisher.build_installed_publication(path,prepared(release_case))
    assert output['status']=='forecast_active'
    numeric=dict(item='Thermal_OriginalForecast_JSON',time=int(now.timestamp()*1000),state=json.dumps(original['output']))
    actual=dict(item='Thermal_Model_JSON',time=int((now+timedelta(seconds=1)).timestamp()*1000),state=json.dumps(output))
    m=module();monkeypatch.setattr(m,'_clock',lambda:now+timedelta(seconds=2))
    record=m.build_publication_capture(path,numeric_publication=numeric,publication=actual)
    return record,original,numeric,actual


@pytest.mark.parametrize('hours',[1,6,12,24])
def test_scoring_binds_actual_main_and_numeric_receipts_without_relabeling(issued,hours):
    record,original,numeric,actual=issued;m=module()
    issue=datetime.fromisoformat(original['issued_at']);target=issue+timedelta(hours=hours)
    result=m.score_publication_capture(record,publication=actual,horizon_hours=hours,
        outcome=dict(target_at=target.isoformat(),receipt=outcome(target,73.)),
        recent_cycle_grid=synthetic_cycle_grid(issue,hours),assessed_at=target+timedelta(minutes=10))
    assert result['schema']=='earthship-installed-shade-source-scored-pair/v3'
    assert result['original_capture_sha256']==record['capture_sha256']
    assert result['numeric_capture_sha256']==original['capture_sha256']
    assert result['publication_sha256']==_digest(actual)
    assert result['numeric_publication_sha256']==_digest(numeric)
    assert record['numeric_capture']['output']['status']=='shadow'
    assert json.loads(record['publication']['state'])['status']=='forecast_active'
    assert result['publication_mode']=='forecast_active'
    assert result['scored_pair']['interval_width_f']==pytest.approx(2.)
    assert result['scored_pair']['model_error_f']==pytest.approx(original['output']['trajectory'][hours-1]['air_f']-73.)
    assert result['release_authorized'] is False and result['action_response_qualification_claimed'] is False


@pytest.mark.parametrize('damage',['numeric_receipt','main_receipt','late_main','future_capture','origin_binding','runtime_binding','interval'])
def test_rehashed_changes_cannot_rewrite_real_main_delivery_or_origin_proof(issued,damage):
    record,_,_,_=issued;m=module();record=deepcopy(record)
    output=json.loads(record['publication']['state'])
    if damage=='numeric_receipt':record['numeric_publication']['state']='{}'
    elif damage=='main_receipt':record['publication']['state']=record['numeric_publication']['state']
    elif damage=='late_main':
        record['publication']['time']+=180000
        record['recorded_at']=(datetime.fromisoformat(record['recorded_at'])+timedelta(minutes=3)).isoformat()
    elif damage=='future_capture':record['recorded_at']=record['numeric_capture']['issued_at']
    elif damage=='origin_binding':output['release']['originCaptureSha256']='f'*64
    elif damage=='runtime_binding':output['release']['runtimeSha256']='f'*64
    else:output['forecast']['prediction_intervals'][0]['lower_air_f']-=1
    if damage in ('origin_binding','runtime_binding','interval'):record['publication']['state']=json.dumps(output)
    record['capture_sha256']=_digest({k:v for k,v in record.items() if k!='capture_sha256'})
    with pytest.raises(ValueError):m.validate_publication_capture(record)


def test_main_packet_must_match_immutable_actual_receipt(issued):
    record,original,numeric,_=issued;issue=datetime.fromisoformat(original['issued_at']);target=issue+timedelta(hours=1)
    with pytest.raises(ValueError):module().score_publication_capture(record,publication=numeric,horizon_hours=1,
        outcome=dict(target_at=target.isoformat(),receipt=outcome(target)),recent_cycle_grid=synthetic_cycle_grid(issue,1),
        assessed_at=target+timedelta(minutes=10))


def test_private_capture_retains_original_numeric_address_and_old_readers_refuse(issued,tmp_path):
    from thermal_model.installed_shade_calibrated_origin import read_calibrated_capture
    record,original,_,_=issued;root=tmp_path/'published';root.mkdir(mode=0o700);m=module()
    path=m.write_publication_capture(root,record)
    assert path.stat().st_mode&0o777==0o600
    assert m.read_publication_capture(path)==record
    numeric_path=root/(original['capture_sha256']+'.installed-shade-origin-v2.json')
    assert read_calibrated_capture(numeric_path)==original
    with pytest.raises(ValueError):read_calibrated_capture(path)
    numeric_path.unlink()
    # Self-contained actual source evidence remains intact; no substituted file.
    assert m.read_publication_capture(path)==record


@pytest.mark.parametrize('reader_version',[1,2])
def test_new_source_adapter_binds_actual_delivery_and_old_readers_refuse(issued,tmp_path,reader_version):
    from thermal_model import installed_shade_qualification as q
    record,original,_,actual=issued;m=module();root=tmp_path/'scored';root.mkdir(mode=0o700)
    path=m.write_publication_capture(root,record);issue=datetime.fromisoformat(original['issued_at']);target=issue+timedelta(hours=1)
    packet=dict(origin_path=str(path),publication=actual,horizon_hours=1,
        outcome=dict(target_at=target.isoformat(),receipt=outcome(target)),recent_cycle_grid=synthetic_cycle_grid(issue,1))
    result=q._score_packets([packet],assessed_at=target+timedelta(minutes=10),version=3)
    assert result['calibrated_intervals'] is True
    assert result['bindings'][0]['original_capture_sha256']==record['capture_sha256']
    assert result['bindings'][0]['publication_sha256']==_digest(actual)
    with pytest.raises(ValueError):q._score_packets([packet],assessed_at=target+timedelta(minutes=10),version=reader_version)


def test_numeric_and_main_publications_of_same_origin_cannot_double_count(issued,tmp_path):
    from thermal_model import installed_shade_qualification as q
    record,original,numeric,actual=issued;m=module();root=tmp_path/'scored';root.mkdir(mode=0o700)
    main=m.write_publication_capture(root,record);raw=root/(original['capture_sha256']+'.installed-shade-origin-v2.json')
    issue=datetime.fromisoformat(original['issued_at']);target=issue+timedelta(hours=1)
    shared=dict(horizon_hours=1,outcome=dict(target_at=target.isoformat(),receipt=outcome(target)),recent_cycle_grid=synthetic_cycle_grid(issue,1))
    packets=[dict(origin_path=str(main),publication=actual,**shared),
        dict(origin_path=str(raw),publication={k:numeric[k] for k in ('time','state')},**shared)]
    with pytest.raises(ValueError,match='duplicate'):q._score_packets(packets,assessed_at=target+timedelta(minutes=10),version=3)


def test_published_qualification_version_is_explicit_and_cli_emits_private_unavailable_report(tmp_path):
    from pathlib import Path
    import subprocess,sys
    from thermal_model import installed_shade_qualification as q
    now=datetime(2026,10,8,12,tzinfo=timezone.utc)
    report=q.qualify_published_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=now)
    assert report['schema']=='earthship-installed-shade-qualification-report/v3'
    assert report['candidate_schema']=='earthship-installed-shade-candidate/v2'
    assert report['recommended_stage']=='unavailable' and report['forecast_qualified'] is False
    with pytest.raises(ValueError):q.validate_calibrated_installed_shade_qualification_report(report)
    tmp_path.chmod(0o700)
    command=[sys.executable,str(Path(__file__).resolve().parents[2]/'scripts/qualify-installed-shade.py'),
        '--contract-version','3','--output-dir',str(tmp_path)]
    result=subprocess.run(command,check=True,capture_output=True,text=True)
    summary=json.loads(result.stdout);assert summary['recommended_stage']=='unavailable'
    for name in summary['report_paths']:
        path=Path(name);assert 'qualification-v3' in path.name and path.stat().st_mode&0o777==0o600
    assert 'Frozen evidence' in q.render_published_installed_shade_qualification_report(report)


@pytest.mark.parametrize('key',['numeric_publication','publication'])
def test_item_identity_cannot_be_swapped_in_actual_receipts(issued,key):
    record,*_=issued;changed=deepcopy(record)
    changed[key]['item']='Thermal_Model_JSON' if key=='numeric_publication' else 'Thermal_OriginalForecast_JSON'
    changed['capture_sha256']=_digest({k:v for k,v in changed.items() if k!='capture_sha256'})
    with pytest.raises(ValueError):module().validate_publication_capture(changed)


def test_forecast_gate_uses_explicit_v3_report_without_a_cached_active_override(tmp_path,release_case,monkeypatch):
    from thermal_model import installed_shade_publication as publisher
    from thermal_model import installed_shade_qualification as q
    from thermal_model.installed_shade_calibrated_origin import write_calibrated_capture
    artifact,report,original,now=release_case;tmp_path.chmod(0o700)
    report=deepcopy(report);report['schema']='earthship-installed-shade-qualification-report/v3'
    report['report_sha256']=_digest({k:v for k,v in report.items() if k!='report_sha256'})
    q.validate_published_installed_shade_qualification_report(report)
    source=publisher.PreparedInstalledQualification(json.dumps(report).encode(),json.dumps(artifact).encode(),True,False,
        ('thermal_intel.py','thermal_model/installed_shade_publication.py'))
    path=write_calibrated_capture(tmp_path,original)
    monkeypatch.setattr(publisher,'_clock',lambda:now)
    monkeypatch.setattr(publisher,'build_runtime_binding',lambda *args:original['runtime'])
    value=publisher.build_installed_publication(path,source)
    assert value['status']=='forecast_active' and value['release']['reportSha256']==report['report_sha256']
    assert publisher.build_installed_publication(path,report)['status']=='unavailable'



def test_actual_shadow_capture_before_calibration_has_no_invented_uncertainty(tmp_path,candidate,release_case,monkeypatch):
    from thermal_model import installed_shade_origin as base
    from thermal_model import installed_shade_publication as publisher
    from thermal_model import installed_shade_qualification as q
    from test_installed_shade_origin import native,weather,actions
    from thermal_model.forcing_capture import _canonical
    bundle,inputs,runtime=candidate;issue=datetime.fromisoformat(release_case[2]['issued_at'])
    current,proof=native(issue)
    source=base.PreparedCandidate(_canonical(bundle['artifact']),issue)
    original=base.build_issued_capture(source,issued_at=issue,inputs_available_at=issue,published_at=issue+timedelta(seconds=2),
        runtime=runtime,forecast=weather(issue),current=current,origin_temperatures=proof,action_snapshot=actions(issue))
    tmp_path.chmod(0o700);path=base.write_issued_capture(tmp_path,original)
    report=q.qualify_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=issue)
    ready=publisher.PreparedInstalledQualification(_canonical(report),_canonical(bundle['artifact']),True,True,
        ('thermal_intel.py','thermal_model/installed_shade_publication.py'))
    monkeypatch.setattr(publisher,'_clock',lambda:issue+timedelta(seconds=3))
    monkeypatch.setattr(publisher,'build_runtime_binding',lambda *args:runtime)
    output=publisher.build_installed_publication(path,ready)
    assert output['status']=='shadow' and output['forecast']['prediction_intervals'] is None
    numeric=dict(item='Thermal_OriginalForecast_JSON',time=int((issue+timedelta(seconds=2)).timestamp()*1000),state=json.dumps(original['output']))
    actual=dict(item='Thermal_Model_JSON',time=int((issue+timedelta(seconds=3)).timestamp()*1000),state=json.dumps(output))
    m=module();monkeypatch.setattr(m,'_clock',lambda:issue+timedelta(seconds=4))
    record=m.build_publication_capture(path,numeric_publication=numeric,publication=actual)
    target=issue+timedelta(hours=1)
    result=m.score_publication_capture(record,publication=actual,horizon_hours=1,
        outcome=dict(target_at=target.isoformat(),receipt=outcome(target)),recent_cycle_grid=synthetic_cycle_grid(issue,1),assessed_at=target+timedelta(minutes=10))
    assert result['publication_mode']=='shadow' and result['scored_pair']['interval_covered'] is None
    assert result['scored_pair']['interval_width_f'] is None and result['release_authorized'] is False
    archive=tmp_path/'shadow';archive.mkdir(mode=0o700);written=m.write_publication_capture(archive,record)
    assert base.read_issued_capture(archive/(original['capture_sha256']+'.installed-shade-origin-v1.json'))==original
    assert m.read_publication_capture(written)==record
