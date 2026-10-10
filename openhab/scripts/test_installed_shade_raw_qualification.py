"""Release qualification v4 requires original raw-source score archives."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from test_installed_shade_score_collection import collection,RawBackend,issued,release_case,candidate
from thermal_model.installed_shade_artifact import _digest


def module():
    from thermal_model import installed_shade_qualification as q
    assert hasattr(q,'qualify_raw_published_installed_shade_candidate'),'missing raw-source qualification v4'
    return q


def blocked():
    return module().qualify_raw_published_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=datetime(2026,10,9,tzinfo=timezone.utc))


def test_missing_raw_qualification_stays_unavailable_and_old_readers_refuse():
    q=module();report=blocked()
    assert report['schema']=='earthship-installed-shade-qualification-report/v4'
    assert report['forecast_qualified'] is False and report['recommended_stage']=='unavailable'
    assert report['gates']['raw_native_score_sources'] is False
    assert q.validate_raw_published_installed_shade_qualification_report(report)==report
    for reader in (q.validate_installed_shade_qualification_report,q.validate_calibrated_installed_shade_qualification_report,q.validate_published_installed_shade_qualification_report):
        with pytest.raises(ValueError):reader(report)


def test_raw_gate_cannot_pass_without_original_pair_bindings():
    q=module();report=blocked();report['gates']['raw_native_score_sources']=True
    report['report_sha256']=_digest({k:v for k,v in report.items() if k!='report_sha256'})
    with pytest.raises(ValueError):q.validate_raw_published_installed_shade_qualification_report(report)


def test_raw_report_archive_and_text_preserve_unavailable_decision(tmp_path):
    q=module();tmp_path.chmod(0o700);report=blocked()
    paths=q.write_raw_published_installed_shade_qualification_report(tmp_path,report)
    assert 'Recommended stage: unavailable' in q.render_raw_published_installed_shade_qualification_report(report)
    assert any(p.name.endswith('.installed-shade-qualification-v4.json') for p in paths)


def test_v4_pair_reader_requires_raw_archive_and_replays_it(collection):
    q=module();m,root,path,record,issue=collection
    result=m.collect_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=RawBackend(record,root))
    assert result['status']=='scored'
    reference={'raw_score_sources_path':result['raw_packet_path']};at=issue+timedelta(hours=24,minutes=10)
    scored=q._score_packets([reference],assessed_at=at,version=4)
    assert len(scored['rows'])==1 and scored['raw_native_score_sources'] is True
    assert len(scored['bindings'][0]['raw_score_sources_sha256'])==64
    assert len(scored['bindings'][0]['native_binding_sha256'])==64
    with pytest.raises(ValueError):q._score_packets([{'origin_path':str(path)}],assessed_at=at,version=4)
    with pytest.raises(ValueError):q._score_packets([reference,reference],assessed_at=at,version=4)


def test_v4_aggregate_raw_bound_refuses_before_numerical_replay(tmp_path,monkeypatch):
    import os
    from test_installed_shade_raw_score_sources import inputs
    from thermal_model.installed_shade_raw_score_sources import build_native_score_binding
    from thermal_model.installed_shade_calibration import _persist
    import thermal_model.installed_shade_raw_score_sources as raw
    q=module();args=inputs(tmp_path,monkeypatch);binding=build_native_score_binding(**args)
    origin=tmp_path/'fixture.installed-shade-origin-v3.json';origin.write_text('{}');origin.chmod(0o600)
    args['score_packet']['origin_path']=str(origin)
    paths=[]
    for index in range(17):
        p=tmp_path/(f'{index:064x}'+'.native-temperature-sources-v1.json')
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.ftruncate(fd,8*1024*1024);os.close(fd);paths.append(str(p))
    binding['query_sources']=paths
    packet=dict(schema='earthship-installed-shade-score-sources/v2',score_sources=args['score_packet'],native_binding=binding,release_authority=False)
    p=_persist(tmp_path,packet,_digest(packet),'.installed-shade-score-sources-v2.json')
    monkeypatch.setattr(raw,'read_raw_score_sources',lambda *a,**k:pytest.fail('oversized aggregate reached numerical replay'))
    with pytest.raises(ValueError,match='aggregate raw'):
        q._score_packets([{'raw_score_sources_path':str(p)}],assessed_at=args['assessed_at'],version=4)


def test_v4_elapsed_budget_refuses_before_source_replay(monkeypatch):
    q=module();assert hasattr(q,'_replay_time'),'missing qualification elapsed budget'
    ticks=iter([0.,61.]);monkeypatch.setattr(q,'_replay_time',lambda:next(ticks))
    with pytest.raises(ValueError,match='time budget'):
        q._score_packets([{'raw_score_sources_path':'/never/open'}],assessed_at=datetime(2026,10,9,tzinfo=timezone.utc),version=4)
