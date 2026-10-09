"""Publication contracts and source factory orchestration, not release evidence."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
import pytest
from test_installed_shade_calibrated import candidate,mathematical_candidate,runtime
from test_installed_shade_origin import ISSUE,native,weather,actions,outcome
from test_installed_shade_calibration import synthetic_cycle_grid
from thermal_model.installed_shade_artifact import _digest
from thermal_model.forcing_capture import _canonical


def module():
    from thermal_model import installed_shade_publication
    return installed_shade_publication


@pytest.fixture(scope='module')
def release_case(candidate):
    from test_thermal_graduation_statistics import assessment_inputs
    from thermal_model.graduation_policy import derive_policy
    from thermal_model.graduation_statistics import assess_current_predictive_skill
    from thermal_model.installed_shade_qualification import FORECAST_GATES,_support,validate_calibrated_installed_shade_qualification_report
    from thermal_model.installed_shade_calibrated_origin import PreparedCalibratedCandidate,build_calibrated_capture
    artifact=mathematical_candidate(candidate)
    for name in module().RUNTIME_PATHS-artifact['runtime']['source_manifest'].keys():
        artifact['runtime']['source_manifest'][name]='7'*64
    artifact['runtime_revision']=_digest(artifact['runtime'])
    for cell in artifact['calibration']['bands'].values():cell.update(overall=1.,regimes={'warm':1.})
    artifact['artifact_sha256']=_digest({k:v for k,v in artifact.items() if k!='artifact_sha256'})
    policy,rows,oldnow=assessment_inputs();delta=datetime.fromisoformat(artifact['created_at'])-datetime.fromisoformat(policy['candidate']['created_at'])
    development=deepcopy(policy['development'])
    for row in development:
        for key in ('issue_at','target_at'):row[key]=(datetime.fromisoformat(row[key])+delta).isoformat()
    intervals={key:None if value is None else (datetime.fromisoformat(value)+delta).isoformat() for key,value in policy['intervals'].items()}
    metadata=dict(artifact_sha256=artifact['artifact_sha256'],runtime_sha256=artifact['runtime_revision'],trained_through=artifact['trained_through'],
        created_at=artifact['created_at'],active_parameter_count=10,sensor_epochs=artifact['sensor_epochs'])
    policy=derive_policy(development,declared_at=datetime.fromisoformat(policy['declared_at'])+delta,intervals=intervals,candidate=metadata,regimes=['warm'])
    for row in rows:
        for key in ('issue_at','target_at'):row[key]=(datetime.fromisoformat(row[key])+delta).isoformat()
        row.update(artifact_sha256=artifact['artifact_sha256'],runtime_sha256=artifact['runtime_revision'],sensor_epochs=artifact['sensor_epochs'])
    issue=oldnow+delta-timedelta(minutes=5);now=issue+timedelta(seconds=2)
    from thermal_model.graduation_decision import qualification_deadline
    statistics=assess_current_predictive_skill(policy,rows,now=issue)
    report=dict(schema='earthship-installed-shade-qualification-report/v2',candidate_schema='earthship-installed-shade-candidate/v2',
        assessed_at=issue.isoformat(),candidate=metadata,candidate_bundle=dict(artifact=artifact,fit_evidence=dict(fit_gates_passed=True)),
        policy=policy,registration_sha256='1'*64,runtime=dict(runtime=artifact['runtime']),gates={k:True for k in FORECAST_GATES},
        scored_pairs=rows,support=_support(rows),original_pair_bindings=[{} for _ in rows],statistics=statistics,
        qualification_expires_at=qualification_deadline(policy,rows).isoformat(),source_errors={},forecast_qualified=True,
        advisory_qualified=False,recommended_stage='forecast_active',automatic_actuation_authorized=False)
    report['report_sha256']=_digest(report);validate_calibrated_installed_shade_qualification_report(report)
    p=PreparedCalibratedCandidate(_canonical(artifact),issue);current,proof=native(issue)
    capture=build_calibrated_capture(p,issued_at=issue,inputs_available_at=issue,published_at=now,runtime=artifact['runtime'],
        forecast=weather(issue),current=current,origin_temperatures=proof,action_snapshot=actions(issue))
    # Positive numerical/report fixture only. Genuine source readers are tested
    # separately; these mock boundaries do not prove training or qualification.
    return artifact,report,capture,now


@pytest.fixture(autouse=True)
def mathematical_runtime_port(monkeypatch,release_case):
    # This file uses synthetic runtime/report math, never a release claim.
    monkeypatch.setattr(module(),'build_runtime_binding',lambda *args:release_case[0]['runtime'])


def prepared(case,report=None,ready=True):
    artifact,original,_,_=case;m=module()
    selected=original if report is None else report
    return m.PreparedInstalledQualification(_canonical(selected),_canonical(artifact),ready,selected['policy'] is None,('thermal_intel.py','thermal_model/installed_shade_publication.py'))


def test_explicit_production_publication_keeps_original_numeric_forecast(tmp_path,release_case,monkeypatch):
    from thermal_model.installed_shade_calibrated_origin import write_calibrated_capture
    artifact,report,capture,now=release_case;tmp_path.chmod(0o700);path=write_calibrated_capture(tmp_path,capture)
    m=module();monkeypatch.setattr(m,'_clock',lambda:now)
    value=m.build_installed_publication(path,prepared(release_case))
    assert value['version']==4 and value['schema']=='earthship-installed-shade-publication/v1'
    assert value['status']=='forecast_active' and value['confidence']['grade']=='high'
    assert value['forecast']==capture['output']
    assert value['release']['originCaptureSha256']==capture['capture_sha256']
    assert value['release']['artifactSha256']==artifact['artifact_sha256']
    assert value['release']['advisoryQualified'] is False and value['release']['automaticActuation'] is False
    assert datetime.fromisoformat(value['validUntil'])<=now+timedelta(minutes=10)
    m.validate_installed_publication(value)


@pytest.mark.parametrize('damage',['cached_dict','source_failure','expired','sensor_expired','identity','runtime','manual_flag','advice'])
def test_failed_source_or_freshness_gates_never_publish_active(tmp_path,release_case,monkeypatch,damage):
    from thermal_model.installed_shade_calibrated_origin import write_calibrated_capture
    artifact,report,capture,now=release_case;tmp_path.chmod(0o700);path=write_calibrated_capture(tmp_path,capture);m=module()
    source=prepared(release_case);at=now
    if damage=='cached_dict':source=report
    elif damage=='source_failure':source=prepared(release_case,ready=False)
    elif damage=='expired':at=datetime.fromisoformat(report['qualification_expires_at'])
    elif damage=='sensor_expired':at=now+timedelta(minutes=3)
    else:
        changed=deepcopy(report)
        if damage=='identity':changed['candidate']['artifact_sha256']='f'*64
        elif damage=='runtime':changed['candidate']['runtime_sha256']='f'*64
        elif damage=='manual_flag':changed['forecast_qualified']=False
        else:changed['advisory_qualified']=True
        changed['report_sha256']=_digest({k:v for k,v in changed.items() if k!='report_sha256'})
        source=prepared(release_case,report=changed)
    monkeypatch.setattr(m,'_clock',lambda:at)
    value=m.build_installed_publication(path,source)
    assert value['status']=='unavailable' and value['forecast'] is None
    assert value['release']['forecastQualified'] is False


def test_missing_policy_allows_only_source_verified_shadow_bootstrap(tmp_path,release_case,monkeypatch):
    from thermal_model.installed_shade_calibrated_origin import write_calibrated_capture
    from thermal_model.installed_shade_qualification import qualify_calibrated_installed_shade_candidate
    _,_,capture,now=release_case;m=module();tmp_path.chmod(0o700);path=write_calibrated_capture(tmp_path,capture)
    report=qualify_calibrated_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=now)
    monkeypatch.setattr(m,'_clock',lambda:now)
    value=m.build_installed_publication(path,prepared(release_case,report=report))
    assert value['status']=='shadow' and value['confidence']['grade']=='low'
    assert value['release']['forecastQualified'] is False and value['forecast']==capture['output']


def test_publication_factory_reads_original_references_and_does_not_accept_cached_report(tmp_path,release_case,monkeypatch):
    artifact,report,_,now=release_case;m=module();tmp_path.chmod(0o700)
    refs=dict(schema='earthship-installed-shade-release-inputs/v1',registration_path='seal',candidate_path='model.installed-shade-candidate-v2.json',
        runtime_bundle_path='runtime',original_pairs_path=None)
    path=tmp_path/'refs.json';path.write_text(json.dumps(refs));path.chmod(0o600)
    monkeypatch.setattr(m,'_clock',lambda:now)
    monkeypatch.setattr(m,'read_runtime_bundle',lambda _:dict(runtime=artifact['runtime'],revision_paths=['thermal_intel.py','thermal_model/installed_shade_publication.py']))
    monkeypatch.setattr(m,'build_runtime_binding',lambda *args:artifact['runtime'])
    monkeypatch.setattr(m,'read_calibrated_candidate',lambda *args,**kwargs:dict(artifact=artifact,calibration=dict(summary=dict(complete=True)),fit_evidence=dict(fit_gates_passed=True)))
    monkeypatch.setattr(m,'qualify_published_installed_shade_candidate',lambda **kwargs:report)
    result=m.prepare_installed_qualification(path)
    assert isinstance(result,m.PreparedInstalledQualification) and result.source_ready is True
    path.write_text(json.dumps(report))
    assert m.prepare_installed_qualification(path).source_ready is False


def test_source_factory_refuses_current_code_that_differs_from_archived_runtime(tmp_path,release_case,monkeypatch):
    artifact,report,_,now=release_case;m=module();tmp_path.chmod(0o700)
    path=tmp_path/'refs.json';path.write_text(json.dumps(dict(schema='earthship-installed-shade-release-inputs/v1',
        registration_path='seal',candidate_path='model.installed-shade-candidate-v2.json',runtime_bundle_path='runtime',original_pairs_path=None)));path.chmod(0o600)
    monkeypatch.setattr(m,'_clock',lambda:now)
    monkeypatch.setattr(m,'read_runtime_bundle',lambda _:dict(runtime=artifact['runtime'],revision_paths=['thermal_intel.py','thermal_model/installed_shade_publication.py']))
    monkeypatch.setattr(m,'build_runtime_binding',lambda *args:{**artifact['runtime'],'code_revision':'8'*64},raising=False)
    monkeypatch.setattr(m,'read_calibrated_candidate',lambda *args,**kwargs:dict(artifact=artifact,calibration=dict(summary=dict(complete=True)),fit_evidence=dict(fit_gates_passed=True)))
    monkeypatch.setattr(m,'qualify_published_installed_shade_candidate',lambda **kwargs:report)
    assert m.prepare_installed_qualification(path).source_ready is False


def test_invalid_configured_registration_is_not_absent_policy_bootstrap(tmp_path,release_case,monkeypatch):
    from thermal_model.installed_shade_qualification import qualify_calibrated_installed_shade_candidate
    artifact,_,_,now=release_case;m=module();tmp_path.chmod(0o700)
    path=tmp_path/'refs.json';path.write_text(json.dumps(dict(schema=m.REFERENCE_SCHEMA,
        registration_path='invalid-seal',candidate_path='model.installed-shade-candidate-v2.json',runtime_bundle_path='runtime',original_pairs_path=None)));path.chmod(0o600)
    report=qualify_calibrated_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=now)
    monkeypatch.setattr(m,'_clock',lambda:now)
    monkeypatch.setattr(m,'read_runtime_bundle',lambda _:dict(runtime=artifact['runtime'],revision_paths=['thermal_intel.py','thermal_model/installed_shade_publication.py']))
    monkeypatch.setattr(m,'build_runtime_binding',lambda *args:artifact['runtime'],raising=False)
    monkeypatch.setattr(m,'read_calibrated_candidate',lambda *args,**kwargs:dict(artifact=artifact,calibration=dict(summary=dict(complete=True)),fit_evidence=dict(fit_gates_passed=True)))
    monkeypatch.setattr(m,'qualify_published_installed_shade_candidate',lambda **kwargs:report)
    assert m.prepare_installed_qualification(path).source_ready is False


def test_delivery_rechecks_current_runtime(tmp_path,release_case,monkeypatch):
    from thermal_model.installed_shade_calibrated_origin import write_calibrated_capture
    _,_,capture,now=release_case;m=module();tmp_path.chmod(0o700);path=write_calibrated_capture(tmp_path,capture)
    source=prepared(release_case);monkeypatch.setattr(m,'_clock',lambda:now)
    monkeypatch.setattr(m,'build_runtime_binding',lambda *args:{**capture['runtime'],'code_revision':'8'*64})
    assert m.build_installed_publication(path,source)['status']=='unavailable'


def test_absent_policy_without_explicit_bootstrap_is_unavailable(tmp_path,release_case,monkeypatch):
    from thermal_model.installed_shade_calibrated_origin import write_calibrated_capture
    from thermal_model.installed_shade_qualification import qualify_calibrated_installed_shade_candidate
    artifact,_,capture,now=release_case;m=module();tmp_path.chmod(0o700);path=write_calibrated_capture(tmp_path,capture)
    report=qualify_calibrated_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=now)
    source=m.PreparedInstalledQualification(_canonical(report),_canonical(artifact),True,False,('thermal_intel.py','thermal_model/installed_shade_publication.py'))
    monkeypatch.setattr(m,'_clock',lambda:now)
    assert m.build_installed_publication(path,source)['status']=='unavailable'


def test_literal_absent_registration_allows_prepared_bootstrap(tmp_path,release_case,monkeypatch):
    from thermal_model.installed_shade_qualification import qualify_calibrated_installed_shade_candidate
    artifact,_,_,now=release_case;m=module();tmp_path.chmod(0o700)
    path=tmp_path/'refs.json';path.write_text(json.dumps(dict(schema=m.REFERENCE_SCHEMA,
        registration_path=None,candidate_path='model.installed-shade-candidate-v2.json',runtime_bundle_path='runtime',original_pairs_path=None)));path.chmod(0o600)
    report=qualify_calibrated_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=now)
    monkeypatch.setattr(m,'_clock',lambda:now)
    monkeypatch.setattr(m,'read_runtime_bundle',lambda _:dict(runtime=artifact['runtime'],revision_paths=['thermal_intel.py','thermal_model/installed_shade_publication.py']))
    monkeypatch.setattr(m,'read_calibrated_candidate',lambda *args,**kwargs:dict(artifact=artifact,calibration=dict(summary=dict(complete=True)),fit_evidence=dict(fit_gates_passed=True)))
    monkeypatch.setattr(m,'qualify_published_installed_shade_candidate',lambda **kwargs:report)
    result=m.prepare_installed_qualification(path)
    assert result.source_ready is True and result.registration_absent is True
    changed=deepcopy(artifact['runtime']);del changed['source_manifest']['thermal_model/graduation_statistics.py']
    monkeypatch.setattr(m,'read_runtime_bundle',lambda _:dict(runtime=changed,revision_paths=['thermal_intel.py','thermal_model/installed_shade_publication.py']))
    assert m.prepare_installed_qualification(path).source_ready is False


@pytest.mark.parametrize('damage',['boolean_shade','removed_shade','regime','mode'])
def test_publication_refuses_changed_installed_domain(tmp_path,release_case,monkeypatch,damage):
    from thermal_model.installed_shade_calibrated_origin import write_calibrated_capture
    _,_,capture,now=release_case;m=module();tmp_path.chmod(0o700);path=write_calibrated_capture(tmp_path,capture)
    monkeypatch.setattr(m,'_clock',lambda:now)
    value=m.build_installed_publication(path,prepared(release_case))
    assert value['status']=='forecast_active'
    if damage=='boolean_shade':value['forecast']['origin_actions']['outdoor_shade_present']=True
    elif damage=='removed_shade':value['forecast']['origin_actions']['outdoor_shade_present']=0
    elif damage=='regime':value['forecast']['prediction_intervals'][0]['regime']='winter'
    else:value['forecast']['origin_actions']['mode']='invented'
    with pytest.raises(ValueError):m.validate_installed_publication(value)


@pytest.mark.parametrize('helper',['weather_temperature_evidence.py','weather_temperature_reader.py'])
def test_runtime_closure_requires_native_proof_helpers(tmp_path,release_case,monkeypatch,helper):
    artifact,report,_,now=release_case;m=module();tmp_path.chmod(0o700)
    path=tmp_path/'refs.json';path.write_text(json.dumps(dict(schema=m.REFERENCE_SCHEMA,
        registration_path='seal',candidate_path='model.installed-shade-candidate-v2.json',runtime_bundle_path='runtime',original_pairs_path=None)));path.chmod(0o600)
    changed=deepcopy(artifact['runtime']);changed['source_manifest'].pop(helper,None)
    monkeypatch.setattr(m,'_clock',lambda:now)
    monkeypatch.setattr(m,'read_runtime_bundle',lambda _:dict(runtime=changed,revision_paths=['thermal_intel.py','thermal_model/installed_shade_publication.py']))
    monkeypatch.setattr(m,'build_runtime_binding',lambda *args:changed)
    monkeypatch.setattr(m,'read_calibrated_candidate',lambda *args,**kwargs:dict(artifact=artifact,calibration=dict(summary=dict(complete=True)),fit_evidence=dict(fit_gates_passed=True)))
    monkeypatch.setattr(m,'qualify_published_installed_shade_candidate',lambda **kwargs:report)
    assert m.prepare_installed_qualification(path).source_ready is False


@pytest.mark.parametrize('helper',['weather_temperature_evidence.py','weather_temperature_reader.py'])
def test_actual_runtime_binding_detects_native_helper_byte_drift(tmp_path,helper,monkeypatch):
    from pathlib import Path
    from thermal_model.origin_capture import build_runtime_binding
    # Hash copied code only; never import/execute that tree or access live data.
    root=Path(__file__).resolve().parent;paths=tuple(sorted(module().RUNTIME_PATHS))
    for name in paths:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((root/name).read_bytes());target.chmod(0o600)
    # Hosted Python tool-cache ownership/modes need not satisfy the production
    # trust policy. Retain actual bytes in an owned non-writable test fixture;
    # never execute it or relax _source_bytes. This proves helper byte binding,
    # not trust in the host/runner's executing interpreter.
    import sys
    interpreter=tmp_path/'python-copy';interpreter.write_bytes(Path(sys.executable).resolve().read_bytes());interpreter.chmod(0o600)
    monkeypatch.setattr(sys,'executable',str(interpreter))
    before=build_runtime_binding(tmp_path,paths)
    changed=tmp_path/helper;changed.write_bytes(changed.read_bytes()+b'\n# synthetic drift, never executed\n')
    after=build_runtime_binding(tmp_path,paths)
    assert before['source_manifest'][helper]!=after['source_manifest'][helper]
    assert before['code_revision']!=after['code_revision']
    assert before['interpreter_sha256']==after['interpreter_sha256']
