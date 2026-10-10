"""Complete-raw publisher contracts; mathematical fixtures are not release proof."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
from pathlib import Path
import pytest
from test_installed_shade_raw_origin import candidate,raw_math_capture
from test_installed_shade_publication import release_case
from thermal_model.forcing_capture import _canonical
from thermal_model.installed_shade_artifact import _digest


@pytest.fixture
def raw_bootstrap(raw_math_capture,tmp_path,monkeypatch):
    from thermal_model import installed_shade_publication as publisher
    from thermal_model import installed_shade_calibrated_origin as origin
    from thermal_model import installed_shade_qualification as qualification
    root=tmp_path/'publisher';root.mkdir(mode=0o700)
    record=raw_math_capture;issue=datetime.fromisoformat(record['issued_at'])
    path=origin.write_raw_calibrated_capture(root,record)
    report=qualification.qualify_complete_raw_installed_shade_candidate(registration_path=None,
        candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=issue)
    monkeypatch.setattr(publisher,'_clock',lambda:issue+timedelta(seconds=3))
    monkeypatch.setattr(publisher,'build_runtime_binding',lambda *args:record['runtime'])
    prepared=publisher.PreparedRawInstalledQualification(_canonical(report),_canonical(record['candidate']),
        True,True,('thermal_intel.py','thermal_model/installed_shade_publication.py'))
    return publisher,path,record,prepared,report


def test_raw_bootstrap_preserves_new_numeric_contract_without_activation(raw_bootstrap):
    publisher,path,record,prepared,_=raw_bootstrap
    output=publisher.build_raw_installed_publication(path,prepared)
    assert output['schema']=='earthship-installed-shade-publication/v2' and output['version']==5
    assert output['status']=='shadow' and output['forecast']==record['output']
    assert output['release']['schema']=='earthship-installed-shade-release/v2'
    assert output['release']['forecastQualified'] is False and output['release']['automaticActuation'] is False
    assert output['confidence']['actionLabels']=='withheld'
    with pytest.raises(ValueError):publisher.validate_installed_publication(output)


@pytest.mark.parametrize('damage',['old_prepared','cached_report','raw_flag','runtime','stale_sensor','manual_active'])
def test_raw_publisher_refuses_weaker_or_invalid_preparation(raw_bootstrap,monkeypatch,damage):
    publisher,path,record,prepared,report=raw_bootstrap
    if damage=='old_prepared':prepared=publisher.PreparedInstalledQualification(prepared.report_json,prepared.candidate_json,True,True,prepared.runtime_paths,True)
    elif damage=='cached_report':prepared=report
    elif damage=='raw_flag':prepared=publisher.PreparedRawInstalledQualification(prepared.report_json,prepared.candidate_json,True,True,prepared.runtime_paths,False)
    elif damage=='runtime':monkeypatch.setattr(publisher,'build_runtime_binding',lambda *args:dict(record['runtime'],code_revision='a'*64))
    elif damage=='stale_sensor':monkeypatch.setattr(publisher,'_clock',lambda:datetime.fromisoformat(record['issued_at'])+timedelta(minutes=3))
    else:
        report=deepcopy(report);report['forecast_qualified']=True;report['recommended_stage']='forecast_active'
        report['report_sha256']=_digest({key:value for key,value in report.items() if key!='report_sha256'})
        prepared=publisher.PreparedRawInstalledQualification(_canonical(report),prepared.candidate_json,True,True,prepared.runtime_paths)
    output=publisher.build_raw_installed_publication(path,prepared)
    assert output['status']=='unavailable' and output['forecast'] is None
    assert output['version']==5 and output['release']['forecastQualified'] is False


def test_raw_reference_factory_refuses_old_profiles_and_cached_reports(raw_bootstrap):
    publisher,path,_,_,report=raw_bootstrap
    for schema in ('earthship-installed-shade-release-inputs/v1','earthship-installed-shade-release-inputs/v2'):
        refs=dict(schema=schema,registration_path=None,candidate_path='candidate',runtime_bundle_path='runtime',original_pairs_path=None)
        target=path.parent/'refs.json';target.write_bytes(_canonical(refs));target.chmod(0o600)
        assert publisher.prepare_raw_installed_qualification(target).source_ready is False
    target.write_bytes(_canonical(report))
    assert publisher.prepare_raw_installed_qualification(target).source_ready is False



@pytest.fixture(scope='module')
def raw_release_math(release_case):
    # Full report/trajectory math only. No original calibration or release query
    # archives exist for this fixture, so it is never household release evidence.
    from thermal_model import installed_shade_calibration as calibration
    from thermal_model import installed_shade_calibrated_origin as origin
    from thermal_model import installed_shade_qualification as qualification
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    from thermal_model.graduation_policy import derive_policy
    from thermal_model.graduation_statistics import assess_current_predictive_skill
    from test_installed_shade_calibration import rows
    artifact,report,numeric,now=deepcopy(release_case)
    residuals=rows()
    for row in residuals:row['model_error_f']=1.
    metadata=artifact['calibration']
    learned=dict(schema=calibration.RAW_SCHEMA,source_contract=calibration.RAW_SOURCE_CONTRACT,
        base_candidate_sha256=artifact['base_candidate']['artifact_sha256'],runtime_sha256=_digest(artifact['base_runtime']),
        sensor_epochs=artifact['sensor_epochs'],calibration_start=metadata['calibration_start'],
        calibration_end=metadata['calibration_end'],created_at=metadata['created_at'],regimes=['warm'],
        method=calibration._method(),summary=calibration._summarize(residuals,regimes=['warm']),
        source_packets_sha256='4'*64,source_pair_bindings=[dict(native_binding_sha256=_digest(dict(native_index=index)),
        raw_score_sources_sha256=_digest(dict(source_index=index))) for index in range(len(residuals))],
        coverage_guaranteed=False,release_authorized=False)
    learned['calibration_sha256']=_digest(learned)
    artifact['schema']='earthship-installed-shade-candidate/v3'
    artifact['calibration'].update(schema=learned['schema'],source_contract=learned['source_contract'],
        calibration_sha256=learned['calibration_sha256'])
    for name in RAW_RUNTIME_PATHS-artifact['runtime']['source_manifest'].keys():artifact['runtime']['source_manifest'][name]='7'*64
    artifact['runtime_revision']=_digest(artifact['runtime'])
    artifact['artifact_sha256']=_digest({key:value for key,value in artifact.items() if key!='artifact_sha256'})
    issue=datetime.fromisoformat(numeric['issued_at'])
    prepared=origin.PreparedRawCalibratedCandidate(_canonical(artifact),issue)
    numeric=origin.build_raw_calibrated_capture(prepared,issued_at=issue,inputs_available_at=numeric['inputs_available_at'],
        published_at=numeric['published_at'],runtime=artifact['runtime'],forecast=numeric['forecast'],
        current=numeric['current'],origin_temperatures=numeric['origin_temperatures'],action_snapshot=numeric['action_snapshot'])
    old=report['policy'];candidate_metadata=dict(old['candidate'],artifact_sha256=artifact['artifact_sha256'],runtime_sha256=artifact['runtime_revision'])
    policy=derive_policy(old['development'],declared_at=old['declared_at'],intervals=old['intervals'],candidate=candidate_metadata,regimes=old['regimes'])
    scored=report['scored_pairs']
    for row in scored:row.update(artifact_sha256=artifact['artifact_sha256'],runtime_sha256=artifact['runtime_revision'])
    report.update(schema=qualification.COMPLETE_RAW_SCHEMA,candidate_schema=artifact['schema'],candidate=candidate_metadata,
        candidate_bundle=dict(artifact=artifact,calibration=learned,fit_evidence=report['candidate_bundle']['fit_evidence']),policy=policy,
        runtime=dict(runtime=artifact['runtime']),gates={gate:True for gate in qualification.COMPLETE_RAW_FORECAST_GATES},
        statistics=assess_current_predictive_skill(policy,scored,now=report['assessed_at']),
        registration_source_bindings=[dict(native_binding_sha256=_digest(dict(development_native=index)),
            raw_score_sources_sha256=_digest(dict(development_source=index))) for index in range(len(policy['development']))],
        original_pair_bindings=[dict(native_binding_sha256=_digest(dict(release_native=index)),
            raw_score_sources_sha256=_digest(dict(release_source=index))) for index in range(len(scored))])
    report['report_sha256']=_digest({key:value for key,value in report.items() if key!='report_sha256'})
    qualification.validate_complete_raw_installed_shade_qualification_report(report)
    return artifact,report,numeric,now


@pytest.fixture
def raw_active(raw_release_math,tmp_path,monkeypatch):
    from thermal_model import installed_shade_publication as publisher
    from thermal_model import installed_shade_calibrated_origin as origin
    artifact,report,numeric,now=raw_release_math;tmp_path.chmod(0o700)
    path=origin.write_raw_calibrated_capture(tmp_path,numeric)
    monkeypatch.setattr(publisher,'_clock',lambda:now)
    monkeypatch.setattr(publisher,'build_runtime_binding',lambda *args:artifact['runtime'])
    prepared=publisher.PreparedRawInstalledQualification(_canonical(report),_canonical(artifact),True,False,
        ('thermal_intel.py','thermal_model/installed_shade_publication.py'))
    return publisher,path,prepared,report,numeric,now


def test_complete_raw_forecast_activation_matches_report_and_withholds_advice(raw_active):
    publisher,path,prepared,report,numeric,_=raw_active
    output=publisher.build_raw_installed_publication(path,prepared)
    assert report['recommended_stage']=='forecast_active' and output['status']==report['recommended_stage']
    assert output['version']==5 and output['forecast']==numeric['output']
    assert output['release']['reportSha256']==report['report_sha256']
    assert output['release']['forecastQualified'] is True and output['release']['advisoryQualified'] is False
    assert output['release']['automaticActuation'] is False


def test_raw_factory_replays_only_complete_profile_references(raw_active,monkeypatch):
    publisher,path,_,report,numeric,_=raw_active;artifact=numeric['candidate']
    refs=dict(schema='earthship-installed-shade-release-inputs/v3',registration_path='seal',
        candidate_path='model.installed-shade-candidate-v3.json',runtime_bundle_path='runtime',original_pairs_path=None)
    target=path.parent/'refs.json';target.write_bytes(_canonical(refs));target.chmod(0o600)
    # Loader orchestration seams only; actual source replay is tested separately.
    monkeypatch.setattr(publisher,'read_runtime_bundle',lambda _:dict(runtime=artifact['runtime'],
        revision_paths=['thermal_intel.py','thermal_model/installed_shade_publication.py']))
    monkeypatch.setattr(publisher,'read_raw_calibrated_candidate',lambda *args,**kwargs:report['candidate_bundle'])
    monkeypatch.setattr(publisher,'qualify_complete_raw_installed_shade_candidate',lambda **kwargs:report)
    prepared=publisher.prepare_raw_installed_qualification(target)
    assert isinstance(prepared,publisher.PreparedRawInstalledQualification) and prepared.source_ready is True
    assert publisher.build_raw_installed_publication(path,prepared)['status']=='forecast_active'
    assert publisher.prepare_installed_qualification(target).source_ready is False


@pytest.mark.parametrize('damage',['expired','raw_calibration_gate','old_report'])
def test_complete_raw_publisher_refuses_expired_or_weaker_release(raw_active,monkeypatch,damage):
    publisher,path,prepared,report,_,_=raw_active
    if damage=='expired':monkeypatch.setattr(publisher,'_clock',lambda:datetime.fromisoformat(report['qualification_expires_at']))
    else:
        report=deepcopy(report)
        if damage=='raw_calibration_gate':report['gates']['raw_calibration_sources']=False
        else:report['schema']='earthship-installed-shade-qualification-report/v4'
        report['report_sha256']=_digest({key:value for key,value in report.items() if key!='report_sha256'})
        prepared=publisher.PreparedRawInstalledQualification(_canonical(report),prepared.candidate_json,True,False,prepared.runtime_paths)
    assert publisher.build_raw_installed_publication(path,prepared)['status']=='unavailable'



from test_installed_shade_raw_calibration import retained_raw_case,collection,issued
from test_installed_shade_calibrated import runtime


def test_raw_factory_fresh_read_refuses_deleted_calibration_query(retained_raw_case,candidate,monkeypatch):
    from thermal_model import installed_shade_publication as publisher
    from thermal_model import installed_shade_calibrated_artifact as artifact
    calibration,source_values,backend,root,_=retained_raw_case
    new=runtime(candidate)
    for name in publisher.RAW_RUNTIME_PATHS-new['source_manifest'].keys():new['source_manifest'][name]='7'*64
    learned=calibration.build_raw_calibration(**source_values)
    values=dict(base_bundle=candidate[0],inputs=candidate[1],calibration=learned,original_pairs=source_values['original_pairs'],
        base_runtime=candidate[2],runtime=new,created_at=source_values['created_at'])
    aggregate=artifact.build_raw_calibrated_candidate(**values)
    archive=root/'candidate';archive.mkdir(mode=0o700)
    parameters={key:values[key] for key in ('base_bundle','inputs','calibration','original_pairs')}
    path=artifact.write_raw_calibrated_candidate(archive,aggregate,**parameters,
        expected_runtime_revision=_digest(new),assessed_at=values['created_at'])
    refs=dict(schema='earthship-installed-shade-release-inputs/v3',registration_path=None,
        candidate_path=str(path),runtime_bundle_path='runtime',original_pairs_path=None)
    target=archive/'refs.json';target.write_bytes(_canonical(refs));target.chmod(0o600)
    # Runtime lookup/executing ports only; candidate/input/raw calibration reads
    # and complete-raw qualification dispatch remain real.
    monkeypatch.setattr(publisher,'_clock',lambda:values['created_at'])
    monkeypatch.setattr(publisher,'read_runtime_bundle',lambda _:dict(runtime=new,
        revision_paths=['thermal_intel.py','thermal_model/installed_shade_publication.py']))
    monkeypatch.setattr(publisher,'build_runtime_binding',lambda *args:new)
    # The acquisition fixture surfaces construction errors with ERRORS=().
    # Restore production handling before checking the fail-safe factory path.
    monkeypatch.setattr(publisher,'ERRORS',(OSError,RuntimeError,ValueError,TypeError,KeyError,AttributeError,OverflowError))
    before=publisher.prepare_raw_installed_qualification(target)
    assert before.candidate_json is not None
    assert before.source_ready is False  # Genuine fixture support remains short.
    Path(backend.native_source_paths[-1]).unlink()
    after=publisher.prepare_raw_installed_qualification(target)
    assert after.source_ready is False and after.candidate_json is None



def test_configured_bad_raw_registration_cannot_bootstrap(raw_active,monkeypatch):
    publisher,path,_,report,numeric,now=raw_active
    from thermal_model import installed_shade_qualification as qualification
    artifact=numeric['candidate'];target=path.parent/'refs.json'
    target.write_bytes(_canonical(dict(schema='earthship-installed-shade-release-inputs/v3',
        registration_path='invalid-seal',candidate_path='model.installed-shade-candidate-v3.json',
        runtime_bundle_path='runtime',original_pairs_path=None)));target.chmod(0o600)
    monkeypatch.setattr(publisher,'read_runtime_bundle',lambda _:dict(runtime=artifact['runtime'],
        revision_paths=['thermal_intel.py','thermal_model/installed_shade_publication.py']))
    monkeypatch.setattr(publisher,'read_raw_calibrated_candidate',lambda *args,**kwargs:report['candidate_bundle'])
    failed=qualification.qualify_complete_raw_installed_shade_candidate(registration_path=None,candidate_path=None,
        runtime_bundle_path=None,original_pairs=[],now=now)
    monkeypatch.setattr(publisher,'qualify_complete_raw_installed_shade_candidate',lambda **kwargs:failed)
    prepared=publisher.prepare_raw_installed_qualification(target)
    assert prepared.source_ready is False and prepared.candidate_json is None
    assert publisher.build_raw_installed_publication(path,prepared)['status']=='unavailable'
