"""Raw queue dispatch and completion hints; synthetic ports are not release proof."""
import json
from pathlib import Path
import pytest
from test_installed_score_jobs import setup,Backend,NOW


def raw_setup(tmp_path,monkeypatch):
    m,queue,out,jobs,calls=setup(tmp_path,monkeypatch)
    queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v2',jobs=jobs)))
    monkeypatch.setattr(m,'read_raw_publication_capture',m.read_publication_capture,raising=False)
    monkeypatch.setattr(m,'collect_raw_published_score',m.collect_published_score,raising=False)
    monkeypatch.setattr(m,'read_calibrated_raw_score_sources',m.read_raw_score_sources,raising=False)
    monkeypatch.setattr(m,'read_publication_capture',lambda *_:pytest.fail('legacy capture reader selected'))
    monkeypatch.setattr(m,'collect_published_score',lambda **kw:pytest.fail('legacy collection selected'))
    monkeypatch.setattr(m,'read_raw_score_sources',lambda *a,**kw:pytest.fail('weak raw reader selected'))
    return m,queue,out,jobs,calls


def test_raw_queue_retains_distinct_completion_and_replays_strong_originals(tmp_path,monkeypatch):
    m,queue,out,jobs,calls=raw_setup(tmp_path,monkeypatch)
    result=m.collect_raw_queued_score(queue_path=queue,output_directory=out,backend=Backend())
    assert result['status']=='scored' and result['release_authorized'] is False
    markers=list(out.glob('*.score-job-v2.json'));assert len(markers)==1
    saved=json.loads(markers[0].read_text())
    assert saved['schema']=='earthship-installed-score-job-completion/v2' and saved['job']==jobs[1]
    assert not list(out.glob('*.score-job-v1.json'))
    assert m.collect_raw_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='completion_verified'
    assert len(calls)==1


def test_raw_queue_missing_original_completion_is_withheld_not_recollected(tmp_path,monkeypatch):
    m,queue,out,_,calls=raw_setup(tmp_path,monkeypatch)
    assert m.collect_raw_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='scored'
    def missing(*a,**kw):raise ValueError('original query missing')
    monkeypatch.setattr(m,'read_calibrated_raw_score_sources',missing)
    assert m.collect_raw_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='withheld'
    assert len(calls)==1


def test_legacy_queue_refuses_v2_before_source_reads(tmp_path,monkeypatch):
    m,queue,out,_,calls=raw_setup(tmp_path,monkeypatch)
    assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='withheld'
    assert calls==[] and list(out.iterdir())==[]


def test_raw_queue_refuses_v1_without_promoting_old_completion(tmp_path,monkeypatch):
    m,queue,out,jobs,calls=raw_setup(tmp_path,monkeypatch)
    queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v1',jobs=jobs)))
    assert m.collect_raw_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='withheld'
    assert calls==[] and list(out.iterdir())==[]


def test_raw_queue_bad_original_rotates_before_following_tick(tmp_path,monkeypatch):
    m,queue,out,jobs,calls=raw_setup(tmp_path,monkeypatch)
    bad=Path(jobs[0]['origin_path']);queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v2',jobs=[jobs[0],jobs[1]])))
    def read(path):
        if path==bad:raise ValueError('invalid original')
        return dict(numeric_capture=dict(issued_at=NOW.replace(hour=21).isoformat()))
    monkeypatch.setattr(m,'read_raw_publication_capture',read)
    assert m.collect_raw_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='withheld'
    assert m.collect_raw_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='scored'
    assert len(calls)==1 and calls[0]['origin_path']==Path(jobs[1]['origin_path'])

from test_installed_shade_raw_publication_capture import raw_delivered,raw_math_capture,candidate


def test_raw_queue_replays_retained_query_files_and_refuses_deleted_source(raw_delivered,monkeypatch):
    from datetime import timedelta
    from thermal_model import installed_shade_score_jobs as queueing,installed_shade_score_collection as collector
    from thermal_model.installed_shade_published_origin import write_raw_publication_capture
    from test_installed_shade_score_collection import RawBackend
    root,record,_,issue=raw_delivered;path=write_raw_publication_capture(root,record)
    queue=root/'jobs.json';queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v2',jobs=[dict(origin_path=str(path),horizon_hours=1)])));queue.chmod(0o600)
    now=issue+timedelta(hours=24,minutes=10);backend=RawBackend(record,root)
    monkeypatch.setattr(queueing,'_clock',lambda:now);monkeypatch.setattr(collector,'_clock',lambda:now)
    result=queueing.collect_raw_queued_score(queue_path=queue,output_directory=root,backend=backend)
    assert result['status']=='scored' and result['release_authorized'] is False
    assert json.loads(Path(result['raw_packet_path']).read_text())['schema']=='earthship-installed-shade-score-sources/v3'
    assert queueing.collect_raw_queued_score(queue_path=queue,output_directory=root,backend=backend)['status']=='completion_verified'
    before=list(backend.calls);missing=Path(backend.native_source_paths[-1]);missing.unlink()
    assert queueing.collect_raw_queued_score(queue_path=queue,output_directory=root,backend=backend)['status']=='withheld'
    assert backend.calls==before and not missing.exists()
