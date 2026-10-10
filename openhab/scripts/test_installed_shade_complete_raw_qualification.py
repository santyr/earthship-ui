"""Qualification v5 binds all raw evidence phases; fixtures are not release proof."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from test_installed_shade_raw_publication_capture import candidate,raw_math_capture,raw_delivered,RawBackend
from thermal_model.installed_shade_artifact import _digest


def test_missing_complete_raw_proofs_emit_closed_v5_report(tmp_path):
    from thermal_model import installed_shade_qualification as qualification
    report=qualification.qualify_complete_raw_installed_shade_candidate(registration_path=None,
        candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=datetime(2026,10,9,tzinfo=timezone.utc))
    assert report['schema']=='earthship-installed-shade-qualification-report/v5'
    assert report['candidate_schema']=='earthship-installed-shade-candidate/v3'
    assert report['registration_source_bindings']==[]
    for gate in ('raw_development_sources','raw_calibration_sources','raw_native_score_sources'):
        assert report['gates'][gate] is False
    assert report['forecast_qualified'] is False and report['recommended_stage']=='unavailable'
    qualification.validate_complete_raw_installed_shade_qualification_report(report)
    with pytest.raises(ValueError):qualification.validate_raw_published_installed_shade_qualification_report(report)
    tmp_path.chmod(0o700)
    paths=qualification.write_complete_raw_installed_shade_qualification_report(tmp_path,report)
    assert all(path.stat().st_mode&0o777==0o600 for path in paths)
    assert paths[0].name.endswith('.installed-shade-qualification-v5.json')
    text=paths[1].read_text()
    assert 'raw_calibration_sources: not passed' in text
    assert 'Recommended stage: unavailable' in text


def test_v5_release_adapter_replays_v3_queries_and_refuses_older_profile(raw_delivered,monkeypatch):
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_score_collection as collector
    from thermal_model import installed_shade_qualification as qualification
    root,record,_,issue=raw_delivered;path=published.write_raw_publication_capture(root,record)
    backend=RawBackend(record,root)
    monkeypatch.setattr(collector,'_clock',lambda:issue+timedelta(hours=24,minutes=10))
    result=collector.collect_raw_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='scored'
    refs=[dict(raw_score_sources_path=result['raw_packet_path'])]
    assessed=issue+timedelta(hours=24,minutes=10)
    actual=qualification._score_packets(refs,assessed_at=assessed,version=5)
    assert actual['raw_native_score_sources'] is True and actual['calibrated_intervals'] is True
    assert len(actual['rows'])==1 and actual['support']['1']['independent_days']==1
    assert actual['bindings'][0]['native_binding_sha256']
    with pytest.raises(ValueError):qualification._score_packets(refs,assessed_at=assessed,version=4)
    Path(backend.native_source_paths[-1]).unlink()
    with pytest.raises((ValueError,OSError)):qualification._score_packets(refs,assessed_at=assessed,version=5)



from test_installed_shade_raw_candidate import raw_candidate_values,raw_routing_case,prepared,original,source_case


def policy_for(artifact):
    from test_thermal_graduation_policy import inputs
    from thermal_model.graduation_policy import derive_policy
    values=inputs();created=datetime.fromisoformat(artifact['created_at'])
    values['candidate']=dict(artifact_sha256=artifact['artifact_sha256'],runtime_sha256=artifact['runtime_revision'],
        trained_through=artifact['trained_through'],created_at=artifact['created_at'],
        active_parameter_count=10,sensor_epochs=artifact['sensor_epochs'])
    values['declared_at']=created+timedelta(minutes=10)
    values['intervals'].update(holdout_start=(created+timedelta(days=1)).isoformat(),
        holdout_end=(created+timedelta(days=90)).isoformat(),
        prospective_start=(created+timedelta(days=1)).isoformat(),prospective_end=None)
    return derive_policy(**values)


def registration_for(policy):
    # Loader orchestration seam only; this is not a sealed raw development cohort.
    return dict(schema='earthship-installed-shade-policy-registration/v3',
        candidate_schema='earthship-installed-shade-candidate/v3',source_contract='earthship-installed-shade-score-sources/v2',
        policy=policy,registration_sha256='1'*64,
        development_source_bindings=[dict(native_binding_sha256=_digest(dict(native_index=index)),
            raw_score_sources_sha256=_digest(dict(raw_index=index))) for index in range(len(policy['development']))])


@pytest.fixture
def complete_raw_case(raw_candidate_values,monkeypatch):
    from thermal_model import installed_shade_qualification as qualification
    from thermal_model import installed_shade_calibrated_artifact as artifact
    values=raw_candidate_values;aggregate=artifact.build_raw_calibrated_candidate(**values)
    policy=policy_for(aggregate);registration=registration_for(policy)
    loaded=dict(artifact=aggregate,calibration=values['calibration'],fit_evidence=values['base_bundle']['fit_evidence'])
    monkeypatch.setattr(qualification,'read_raw_calibrated_installed_shade_registered_policy',lambda _:deepcopy(registration))
    monkeypatch.setattr(qualification,'read_raw_calibrated_candidate',lambda *args,**kwargs:deepcopy(loaded))
    monkeypatch.setattr(qualification,'read_runtime_bundle',lambda _:dict(runtime=values['runtime']))
    now=datetime.fromisoformat(policy['declared_at'])
    options=dict(registration_path='synthetic-seal',candidate_path='synthetic-candidate',runtime_bundle_path='synthetic-runtime',
        original_pairs=[],now=now)
    return qualification,options,registration,loaded


def test_v5_requires_release_evidence_even_with_raw_phase_components(complete_raw_case):
    qualification,options,_,_=complete_raw_case
    report=qualification.qualify_complete_raw_installed_shade_candidate(**options)
    assert report['gates']['raw_development_sources'] is True
    assert report['gates']['raw_calibration_sources'] is True
    assert report['gates']['raw_native_score_sources'] is False
    assert report['forecast_qualified'] is False and report['recommended_stage']=='unavailable'
    assert report['statistics'] is None


@pytest.mark.parametrize('damage',['development','calibration'])
def test_v5_old_phase_contracts_close_source_gates(complete_raw_case,monkeypatch,damage):
    qualification,options,registration,loaded=complete_raw_case
    if damage=='development':
        registration['schema']='earthship-installed-shade-policy-registration/v2'
        monkeypatch.setattr(qualification,'read_raw_calibrated_installed_shade_registered_policy',lambda _:registration)
    else:
        loaded['calibration']['schema']='earthship-installed-shade-calibration/v1'
        monkeypatch.setattr(qualification,'read_raw_calibrated_candidate',lambda *args,**kwargs:loaded)
    report=qualification.qualify_complete_raw_installed_shade_candidate(**options)
    assert report['gates']['raw_'+damage+'_sources'] is False
    assert report['forecast_qualified'] is False and report['recommended_stage']=='unavailable'


@pytest.mark.parametrize('damage',['calibration_metadata','development_binding','phase_gate'])
def test_rehashed_v5_report_cannot_relabel_weaker_phase_proof(complete_raw_case,damage):
    qualification,options,_,_=complete_raw_case
    report=qualification.qualify_complete_raw_installed_shade_candidate(**options)
    if damage=='calibration_metadata':report['candidate_bundle']['calibration']['source_contract']='earthship-installed-shade-score-sources/v1'
    elif damage=='development_binding':report['registration_source_bindings'][0].pop('native_binding_sha256')
    else:report['gates']['raw_calibration_sources']=False
    report['report_sha256']=_digest({key:value for key,value in report.items() if key!='report_sha256'})
    with pytest.raises(ValueError):qualification.validate_complete_raw_installed_shade_qualification_report(report)



from test_installed_shade_raw_calibration import retained_raw_case,collection,issued,release_case
from test_installed_shade_calibrated import runtime


def test_v5_fresh_candidate_read_closes_gate_after_calibration_query_is_deleted(retained_raw_case,candidate,monkeypatch):
    from thermal_model import installed_shade_calibrated_artifact as artifact
    from thermal_model import installed_shade_qualification as qualification
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    calibration,source_values,backend,root,_=retained_raw_case
    new=runtime(candidate)
    for name in RAW_RUNTIME_PATHS-new['source_manifest'].keys():new['source_manifest'][name]='7'*64
    record=calibration.build_raw_calibration(**source_values)
    values=dict(base_bundle=candidate[0],inputs=candidate[1],calibration=record,
        original_pairs=source_values['original_pairs'],base_runtime=candidate[2],runtime=new,created_at=source_values['created_at'])
    aggregate=artifact.build_raw_calibrated_candidate(**values)
    archive=root/'candidate';archive.mkdir(mode=0o700)
    parameters={key:values[key] for key in ('base_bundle','inputs','calibration','original_pairs')}
    path=artifact.write_raw_calibrated_candidate(archive,aggregate,**parameters,
        expected_runtime_revision=_digest(new),assessed_at=values['created_at'])
    policy=policy_for(aggregate);registration=registration_for(policy)
    # Registration/runtime lookup seams only. Candidate proof and original
    # training/calibration query reads are real and must be fresh on both calls.
    monkeypatch.setattr(qualification,'read_raw_calibrated_installed_shade_registered_policy',lambda _:registration)
    monkeypatch.setattr(qualification,'read_runtime_bundle',lambda _:dict(runtime=new))
    options=dict(registration_path='synthetic-seal',candidate_path=path,runtime_bundle_path='synthetic-runtime',
        original_pairs=[],now=datetime.fromisoformat(policy['declared_at']))
    before=qualification.qualify_complete_raw_installed_shade_candidate(**options)
    assert before['gates']['raw_calibration_sources'] is True and before['forecast_qualified'] is False
    Path(backend.native_source_paths[-1]).unlink()
    after=qualification.qualify_complete_raw_installed_shade_candidate(**options)
    assert after['gates']['raw_calibration_sources'] is False and after['gates']['frozen_candidate'] is False
    assert after['forecast_qualified'] is False and after['recommended_stage']=='unavailable'
    assert 'frozen_candidate' in after['source_errors']



def test_v5_incomplete_development_bindings_cannot_pass_source_gate(complete_raw_case,monkeypatch):
    qualification,options,registration,_=complete_raw_case
    registration['development_source_bindings']=registration['development_source_bindings']*2
    monkeypatch.setattr(qualification,'read_raw_calibrated_installed_shade_registered_policy',lambda _:registration)
    report=qualification.qualify_complete_raw_installed_shade_candidate(**options)
    assert report['gates']['raw_development_sources'] is False
    assert report['forecast_qualified'] is False
