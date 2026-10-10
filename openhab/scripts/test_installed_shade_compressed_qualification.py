"""Compressed complete release contracts; synthetic fixtures grant no authority."""
from datetime import datetime,timezone
from pathlib import Path
import pytest
from test_installed_shade_raw_origin import source_origin_case,raw_math_capture,candidate
from thermal_model.installed_shade_artifact import _digest


def test_missing_compressed_release_proofs_emit_closed_v7_and_matching_private_report(tmp_path):
    from thermal_model import installed_shade_qualification as q
    api=getattr(q,'qualify_compressed_installed_shade_candidate',None)
    assert callable(api),'missing complete compressed release qualification'
    report=api(registration_path=None,candidate_path=None,runtime_bundle_path=None,
        original_pairs=[],now=datetime(2026,10,10,tzinfo=timezone.utc))
    assert report['schema']=='earthship-installed-shade-qualification-report/v7'
    assert report['candidate_schema']=='earthship-installed-shade-candidate/v5'
    assert report['registration_source_bindings']==[]
    assert all(report['gates'][key] is False for key in ('raw_development_sources','raw_calibration_sources','raw_native_issue_sources','raw_native_score_sources'))
    assert report['recommended_stage']=='unavailable' and report['forecast_qualified'] is False
    assert report['advisory_qualified'] is False and report['automatic_actuation_authorized'] is False
    q.validate_compressed_installed_shade_qualification_report(report)
    with pytest.raises(ValueError):q.validate_complete_raw_installed_shade_qualification_report(report)
    paths=q.write_compressed_installed_shade_qualification_report(tmp_path,report)
    assert all(p.stat().st_mode&0o777==0o600 for p in paths)
    assert paths[0].name.endswith('.installed-shade-qualification-v7.json')
    assert 'raw_native_issue_sources: not passed' in paths[1].read_text()
    assert 'Recommended stage: unavailable' in paths[1].read_text()


def test_v7_release_adapter_replays_original_queries_and_refuses_legacy_profile(source_origin_case,tmp_path,monkeypatch):
    from test_installed_shade_raw_publication_capture import compressed_calibrated_archive_case
    from thermal_model import installed_shade_qualification as q
    _,_,args,now,backend,result=compressed_calibrated_archive_case(source_origin_case,tmp_path,monkeypatch)
    refs=[dict(raw_score_sources_path=result['raw_packet_path'])]
    scored=q._score_packets(refs,assessed_at=now,version=7)
    assert scored['raw_native_issue_sources'] is True and scored['raw_native_score_sources'] is True
    assert scored['calibrated_intervals'] is True
    assert scored['bindings'][0]['native_origin_binding_sha256']
    with pytest.raises(ValueError):q._score_packets(refs,assessed_at=now,version=5)
    frozen={key:scored['rows'][0][key] for key in ('artifact_sha256','runtime_sha256','sensor_epochs')}
    frozen['artifact_sha256']='f'*64
    with pytest.raises(ValueError,match='mixed frozen'):q._score_packets(refs,assessed_at=now,candidate=frozen,version=7)
    Path(args['native_source_paths']['air']).unlink()
    with pytest.raises((ValueError,OSError)):q._score_packets(refs,assessed_at=now,version=7)
    from thermal_model import policy_registration as registration
    monkeypatch.setattr(registration,'read_compressed_installed_shade_registered_policy',lambda _:pytest.fail('missing release inventory reached development/candidate replay'))
    with pytest.raises((ValueError,OSError)):q.qualify_compressed_installed_shade_candidate(registration_path='unused',candidate_path='unused',runtime_bundle_path='unused',original_pairs=refs,now=now)


def test_v7_cannot_promote_missing_issue_proof_by_rehashing():
    from thermal_model import installed_shade_qualification as q
    api=getattr(q,'qualify_compressed_installed_shade_candidate',None)
    assert callable(api),'missing complete compressed release qualification'
    report=api(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=datetime(2026,10,10,tzinfo=timezone.utc))
    report['gates']['raw_native_issue_sources']=True
    report['report_sha256']=_digest({k:v for k,v in report.items() if k!='report_sha256'})
    with pytest.raises(ValueError):q.validate_compressed_installed_shade_qualification_report(report)


from test_installed_shade_raw_candidate import compressed_candidate_values
from test_installed_shade_raw_calibration import retained_compressed_calibration_case,source_calibration_origin_case


def test_v7_binds_actual_calibration_metadata_and_closes_weaker_phase_proofs(compressed_candidate_values,monkeypatch):
    from copy import deepcopy
    from test_installed_shade_complete_raw_qualification import policy_for
    from thermal_model import installed_shade_qualification as q,policy_registration as registration
    from thermal_model import installed_shade_calibrated_artifact as artifact
    values,_,_,_=compressed_candidate_values
    aggregate=artifact.build_compressed_source_calibrated_candidate(**values)
    policy=policy_for(aggregate)
    # Explicit loader-routing seam only. Calibration/frozen candidate construction
    # above replay actual retained synthetic fit and query sources. This fabricated
    # registration is not a genuine sealed development cohort.
    seal=dict(schema='earthship-installed-shade-policy-registration/v4',candidate_schema=aggregate['schema'],
        source_contract='earthship-installed-shade-score-sources/v6',policy=policy,registration_sha256='1'*64,
        development_source_bindings=[dict(native_binding_sha256='2'*64,raw_score_sources_sha256='3'*64,native_origin_binding_sha256='4'*64) for _ in policy['development']])
    loaded=dict(artifact=aggregate,calibration=values['calibration'],fit_evidence=values['base_bundle']['fit_evidence'])
    current={'seal':seal,'loaded':loaded}
    monkeypatch.setattr(registration,'read_compressed_installed_shade_registered_policy',lambda _:deepcopy(current['seal']))
    monkeypatch.setattr(artifact,'read_compressed_source_calibrated_candidate',lambda *a,**kw:deepcopy(current['loaded']))
    monkeypatch.setattr(q,'read_runtime_bundle',lambda _:dict(runtime=values['runtime']))
    options=dict(registration_path='synthetic-routing-seal',candidate_path='synthetic-routing-candidate',runtime_bundle_path='synthetic-routing-runtime',original_pairs=[],now=policy['declared_at'])
    report=q.qualify_compressed_installed_shade_candidate(**options)
    assert report['gates']['raw_development_sources'] is True and report['gates']['raw_calibration_sources'] is True
    assert report['gates']['raw_native_issue_sources'] is False and report['forecast_qualified'] is False
    text=q.render_compressed_installed_shade_qualification_report(report)
    assert 'raw_calibration_bindings' in text and 'raw_development_bindings' in text
    for damage in ('development_issue','calibration_issue','calibration_schema','calibration_metadata'):
        current['seal']=deepcopy(seal);current['loaded']=deepcopy(loaded)
        if damage=='development_issue':current['seal']['development_source_bindings'][0].pop('native_origin_binding_sha256')
        elif damage=='calibration_issue':
            c=current['loaded']['calibration'];c['source_pair_bindings'][0].pop('native_origin_binding_sha256');c['calibration_sha256']=_digest({k:v for k,v in c.items() if k!='calibration_sha256'})
        elif damage=='calibration_schema':current['loaded']['calibration']['schema']='earthship-installed-shade-calibration/v3'
        else:current['loaded']['artifact']['calibration']['source_contract']='earthship-installed-shade-score-sources/v4'
        actual=q.qualify_compressed_installed_shade_candidate(**options)
        assert actual['gates']['raw_development_sources' if damage=='development_issue' else 'raw_calibration_sources'] is False
        assert actual['forecast_qualified'] is False
    changed=deepcopy(report);changed['registration_source_bindings'][0].pop('native_origin_binding_sha256')
    changed['report_sha256']=_digest({k:v for k,v in changed.items() if k!='report_sha256'})
    with pytest.raises(ValueError):q.validate_compressed_installed_shade_qualification_report(changed)


def test_compressed_qualification_inherits_expired_parent_before_any_loader(monkeypatch):
    from thermal_model import installed_shade_qualification as q,policy_registration as registration
    from thermal_model.replay_budget import shared_replay_budget
    monkeypatch.setattr(registration,'read_compressed_installed_shade_registered_policy',lambda _:pytest.fail('expired parent reached source reader'))
    clock={'remaining':60}
    with shared_replay_budget(lambda:clock['remaining']):
        clock['remaining']=0
        with pytest.raises(ValueError):q.qualify_compressed_installed_shade_candidate(registration_path='unused',candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=datetime(2026,10,10,tzinfo=timezone.utc))


@pytest.mark.parametrize('field',['statistics','qualification_expires_at'])
def test_rehashed_v7_missing_sources_cannot_claim_metrics_or_freshness(field):
    from thermal_model import installed_shade_qualification as q
    report=q.qualify_compressed_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=datetime(2026,10,10,tzinfo=timezone.utc))
    report[field]={'synthetic_claim':'passed'} if field=='statistics' else '2026-11-01T00:00:00+00:00'
    report['report_sha256']=_digest({k:v for k,v in report.items() if k!='report_sha256'})
    with pytest.raises(ValueError):q.validate_compressed_installed_shade_qualification_report(report)
