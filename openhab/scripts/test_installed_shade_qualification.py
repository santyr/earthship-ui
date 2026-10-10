"""Installed-domain registration and decision boundaries, no real qualification."""
from datetime import timedelta,datetime,timezone
import json
import pytest
from test_installed_shade_origin import candidate,prepared,original,ISSUE,outcome,cycles
from test_installed_shade_inputs import EPOCHS
from test_thermal_graduation_policy import inputs as policy_inputs
from thermal_model import policy_registration as registration
from thermal_model.graduation_policy import derive_policy,RECORD_FIELDS
from thermal_model.installed_shade_origin import write_issued_capture,score_issued_capture
from thermal_model.installed_shade_artifact import _digest


def module():
    from thermal_model import installed_shade_qualification
    return installed_shade_qualification


@pytest.fixture
def source_case(tmp_path,original):
    tmp_path.chmod(0o700);path=write_issued_capture(tmp_path,original)
    packet=dict(origin_path=str(path),publication=dict(time=int((ISSUE+timedelta(seconds=2)).timestamp()*1000),state=json.dumps(original['output'])),horizon_hours=1,outcome=dict(target_at=(ISSUE+timedelta(hours=1)).isoformat(),receipt=outcome(ISSUE+timedelta(hours=1))),recent_cycle_grid=cycles(1))
    assessed=ISSUE+timedelta(hours=2)
    scored=score_issued_capture(original,**{k:v for k,v in packet.items() if k!='origin_path'},assessed_at=assessed)['scored_pair']
    policy=dict(candidate=dict(sensor_epochs=EPOCHS),development=[{key:scored[key] for key in RECORD_FIELDS}])
    return packet,policy,assessed


def numerical_policy():
    values=policy_inputs();values['candidate'].update(active_parameter_count=10,sensor_epochs=EPOCHS)
    return derive_policy(**values)


def test_installed_registration_replays_actual_original_packet(source_case):
    packet,policy,assessed=source_case
    result=registration._score_sources([packet],policy,assessed,version=3)
    assert result[packet['origin_path']]['schema']=='earthship-installed-shade-origin/v1'
    with pytest.raises(ValueError):registration._score_sources([packet],policy,assessed,version=2)


def test_altered_development_baseline_cannot_be_sealed(source_case):
    packet,policy,assessed=source_case;policy['development'][0]['recent_cycle_error_f']+=1
    with pytest.raises(ValueError):registration._score_sources([packet],policy,assessed,version=3)


def test_explicit_registration_seal_roundtrip_and_legacy_refusal(tmp_path,original,source_case,monkeypatch):
    # Clock/copy/receipt classification test: source replay independently uses
    # the real original packet above. This mocked seal is not release evidence.
    packet,_,_=source_case;policy=numerical_policy();tmp_path.chmod(0o700)
    monkeypatch.setattr(registration,'_clock',lambda:datetime(2026,7,17,12,tzinfo=timezone.utc))
    def sealed_source(sources,*args,**kwargs):
        name=sources[0]['origin_path']
        if kwargs.get('root') is not None:name=str(kwargs['root']/name)
        return {name:original}
    monkeypatch.setattr(registration,'_score_sources',sealed_source)
    path=registration.register_installed_shade_policy(tmp_path,policy,[packet])
    record=registration.read_installed_shade_registered_policy(path)
    assert record['schema']=='earthship-installed-shade-policy-registration/v1'
    assert record['candidate_schema']=='earthship-installed-shade-candidate/v1'
    assert record['sensor_epoch_semantics']=='declared_hardware_phase' and record['release_authorized'] is False
    assert path.stat().st_mode&0o777==0o600
    with pytest.raises(ValueError):registration.read_sensor_registered_policy(path)
    with pytest.raises(ValueError):registration.read_registered_policy(path)


def test_installed_policy_rejects_wrong_parameter_contract(tmp_path,source_case,monkeypatch):
    packet,_,_=source_case;values=policy_inputs();values['candidate']['sensor_epochs']=EPOCHS
    policy=derive_policy(**values);tmp_path.chmod(0o700)
    monkeypatch.setattr(registration,'_clock',lambda:datetime(2026,7,17,12,tzinfo=timezone.utc))
    with pytest.raises(ValueError):registration.register_installed_shade_policy(tmp_path,policy,[packet])


def test_missing_original_components_close_release_gates():
    report=module().qualify_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=ISSUE)
    assert report['schema']=='earthship-installed-shade-qualification-report/v1'
    assert report['forecast_qualified'] is False and report['advisory_qualified'] is False
    assert report['recommended_stage']=='unavailable'
    assert not any(report['gates'].values())
    assert report['automatic_actuation_authorized'] is False


def test_actual_source_pair_remains_visible_without_fake_calibration(source_case):
    packet,_,assessed=source_case
    result=module()._score_packets([packet],assessed_at=assessed)
    assert len(result['rows'])==1 and result['calibrated_intervals'] is False
    assert result['rows'][0]['interval_covered'] is None
    assert result['bindings'][0]['original_capture_sha256']


def test_duplicate_or_mixed_source_pairs_are_refused(source_case):
    packet,_,assessed=source_case
    with pytest.raises(ValueError):module()._score_packets([packet,packet],assessed_at=assessed)


def test_manual_active_or_interval_pass_cannot_replace_missing_evidence():
    m=module();report=m.qualify_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=ISSUE)
    report['gates']['calibrated_intervals']=True;report['forecast_qualified']=True;report['recommended_stage']='forecast_active'
    report['report_sha256']=_digest({key:value for key,value in report.items() if key!='report_sha256'})
    with pytest.raises(ValueError):m.validate_installed_shade_qualification_report(report)


def test_unknown_legacy_report_reader_refuses_new_domain():
    from thermal_model.graduation_decision import validate_sensor_qualification_report
    report=module().qualify_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=ISSUE)
    with pytest.raises(ValueError):validate_sensor_qualification_report(report)



def test_mixed_candidate_binding_cannot_enter_release_statistics(source_case):
    packet,_,assessed=source_case
    frozen=dict(artifact_sha256='a'*64,runtime_sha256='b'*64,sensor_epochs=EPOCHS)
    with pytest.raises(ValueError):module()._score_packets([packet],assessed_at=assessed,candidate=frozen)



def test_source_replay_keeps_short_fit_and_uncalibrated_forecast_gates_closed(source_case,candidate,monkeypatch):
    # Component orchestration test: candidate/runtime/registration loaders are
    # controlled seams, while source replay uses the actual captured packet.
    packet,_,assessed=source_case;bundle,_,runtime=candidate;m=module()
    values=policy_inputs();a=bundle['artifact']
    values['candidate']=dict(artifact_sha256=a['artifact_sha256'],runtime_sha256=a['runtime_revision'],trained_through=a['trained_through'],created_at=a['created_at'],active_parameter_count=10,sensor_epochs=EPOCHS)
    declared=ISSUE+timedelta(hours=2)
    values['declared_at']=declared.isoformat()
    values['intervals'].update(holdout_start=(declared+timedelta(days=1)).isoformat(),holdout_end=(declared+timedelta(days=40)).isoformat(),prospective_start=(declared+timedelta(days=1)).isoformat())
    policy=derive_policy(**values)
    monkeypatch.setattr(m,'read_installed_shade_registered_policy',lambda _:dict(policy=policy,registration_sha256='a'*64))
    monkeypatch.setattr(m,'read_candidate_bundle',lambda *args,**kwargs:bundle)
    monkeypatch.setattr(m,'read_runtime_bundle',lambda _:dict(runtime=runtime))
    report=m.qualify_installed_shade_candidate(registration_path='/controlled/registration',candidate_path='/controlled/candidate',runtime_bundle_path='/controlled/runtime',original_pairs=[packet],now=assessed)
    assert report['gates']['original_source_pairs'] is True
    assert report['gates']['qualified_training_sources'] is True
    assert report['gates']['measured_fit'] is False
    assert report['gates']['calibrated_intervals'] is False
    assert report['gates']['predictive_skill'] is False and report['forecast_qualified'] is False
    assert report['support']['1']['independent_days']==1
    assert 'calibrated_intervals' in report['source_errors']


def test_latest_prospective_regression_cannot_be_hidden_by_good_pooled_history():
    from test_thermal_graduation_statistics import extended_operational_history
    policy,rows,now=extended_operational_history(recent_loss=True)
    result=module().assess_predictive_skill(policy,rows,now=now)
    assert result['statistical_forecast_gates_passed'] is False
    assert result['historical_assessment']['statistical_forecast_gates_passed'] is True
    assert result['recent_prospective']['24']['gates']['persistence_skill'] is False


def test_human_report_and_actual_cli_keep_missing_evidence_unavailable(tmp_path):
    import subprocess,sys
    from pathlib import Path
    m=module();report=m.qualify_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=ISSUE)
    text=m.render_installed_shade_qualification_report(report)
    assert 'unavailable' in text and 'calibrated_intervals' in text and 'Automatic actuation: disabled' in text
    tmp_path.chmod(0o700)
    script=Path(__file__).resolve().parents[2]/'scripts'/'qualify-installed-shade.py'
    result=subprocess.run([sys.executable,str(script),'--output-dir',str(tmp_path)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    paths=list(tmp_path.glob('*.installed-shade-qualification-v1.json'))
    assert len(paths)==1 and paths[0].stat().st_mode&0o777==0o600
    actual=json.loads(paths[0].read_text())
    assert actual['forecast_qualified'] is False and actual['recommended_stage']=='unavailable'
