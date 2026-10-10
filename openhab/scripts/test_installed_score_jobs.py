"""Queued scheduling is not qualification evidence; raw packets remain required."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import pytest

NOW=datetime(2026,10,9,23,tzinfo=timezone.utc)


def module():
    import importlib.util
    assert importlib.util.find_spec('thermal_model.installed_shade_score_jobs'),'missing bounded queued score collection'
    from thermal_model import installed_shade_score_jobs
    return installed_shade_score_jobs


class Backend:
    def verify_unchanged(self):pass


def setup(tmp_path,monkeypatch,status='scored'):
    m=module();tmp_path.chmod(0o700);out=tmp_path/'out';out.mkdir(mode=0o700)
    old=tmp_path/'old.json';old.touch(mode=0o600);future=tmp_path/'future.json';future.touch(mode=0o600)
    jobs=[dict(origin_path=str(future),horizon_hours=24),dict(origin_path=str(old),horizon_hours=1)]
    queue=tmp_path/'jobs.json';queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v1',jobs=jobs)));queue.chmod(0o600)
    monkeypatch.setattr(m,'_clock',lambda:NOW)
    monkeypatch.setattr(m,'read_publication_capture',lambda p:dict(numeric_capture=dict(issued_at=(NOW-timedelta(hours=2) if p==old else NOW).isoformat())))
    calls=[]
    def collect(**kwargs):
        calls.append(kwargs)
        raw=out/'raw.json';raw.write_text('{}');raw.chmod(0o600)
        return dict(status=status,raw_packet_path=str(raw),release_authorized=False)
    monkeypatch.setattr(m,'collect_published_score',collect)
    monkeypatch.setattr(m,'read_raw_score_sources',lambda *args,**kwargs:dict(score_packet=dict(origin_path=str(old),horizon_hours=1),raw_score_sources_sha256='a'*64))
    return m,queue,out,jobs,calls


def test_queue_skips_immature_job_and_collects_only_one_raw_bound_job(tmp_path,monkeypatch):
    m,queue,out,jobs,calls=setup(tmp_path,monkeypatch)
    result=m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())
    assert result['status']=='scored' and len(calls)==1
    assert calls[0]['origin_path']==Path(jobs[1]['origin_path']) and calls[0]['horizon_hours']==1
    assert len(list(out.glob('*.score-job-v1.json')))==1
    assert result['release_authorized'] is False


def test_completed_job_requires_original_raw_sources_and_is_not_recollected(tmp_path,monkeypatch):
    m,queue,out,_,calls=setup(tmp_path,monkeypatch)
    assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='scored'
    def missing(*args,**kwargs):raise ValueError('missing original raw sources')
    monkeypatch.setattr(m,'read_raw_score_sources',missing)
    result=m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())
    assert result['status']=='withheld' and len(calls)==1


def test_withheld_attempt_does_not_create_completed_job(tmp_path,monkeypatch):
    m,queue,out,_,calls=setup(tmp_path,monkeypatch,'withheld')
    assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='withheld'
    assert len(calls)==1 and not list(out.glob('*.score-job-v1.json'))


def test_duplicate_queue_jobs_refused_before_collection(tmp_path,monkeypatch):
    m,queue,out,jobs,calls=setup(tmp_path,monkeypatch)
    queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v1',jobs=[jobs[1],jobs[1]])))
    assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='withheld'
    assert calls==[]


def test_completion_replay_uses_actual_clock_after_collection(tmp_path,monkeypatch):
    m,queue,out,_,calls=setup(tmp_path,monkeypatch);clock=[NOW]
    monkeypatch.setattr(m,'_clock',lambda:clock[0])
    original=m.collect_published_score
    def collect(**kwargs):
        clock[0]+=timedelta(seconds=10);return original(**kwargs)
    def replay(*args,assessed_at,**kwargs):
        if assessed_at<clock[0]:raise ValueError('fresh outcome assessed after stale scheduling clock')
        return dict(score_packet=dict(origin_path=str(tmp_path/'old.json'),horizon_hours=1),raw_score_sources_sha256='a'*64)
    monkeypatch.setattr(m,'collect_published_score',collect);monkeypatch.setattr(m,'read_raw_score_sources',replay)
    assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='scored'
    assert len(calls)==1


def test_queue_decodes_the_same_original_bytes_it_pins(tmp_path,monkeypatch):
    m,queue,out,jobs,calls=setup(tmp_path,monkeypatch);read=m._owned_bytes;count=[0]
    def transient(path,maximum):
        raw=read(path,maximum)
        if path==queue:
            count[0]+=1
            if count[0]==2:
                changed=[jobs[0],dict(origin_path=jobs[1]['origin_path'],horizon_hours=6)]
                return json.dumps(dict(schema='earthship-installed-score-jobs/v1',jobs=changed)).encode()
        return raw
    monkeypatch.setattr(m,'_owned_bytes',transient)
    result=m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())
    # A second read may refuse a change, but must never select its transient data.
    assert result['status']=='withheld' or result['status']=='scored' and calls[0]['horizon_hours']==1
    assert not calls or calls[0]['horizon_hours']==1


def test_queue_cli_routes_one_guarded_invocation_without_explicit_origin(tmp_path,monkeypatch,capsys):
    import thermal_installed_score as cli
    import thermal_installed_intel as publication_cli
    from thermal_model import installed_shade_score_inputs as inputs
    m,queue,out,_,_=setup(tmp_path,monkeypatch);lock=tmp_path/'global-lock';lock.touch(mode=0o600)
    monkeypatch.setattr(publication_cli,'_resource_preflight',lambda:None)
    monkeypatch.setattr(inputs,'load_score_settings',lambda _:dict(output_directory=str(out)))
    class Reader:
        def __init__(self,settings,*,shared_lock_guard):self.guard=shared_lock_guard;self.guard()
        def verify_unchanged(self):self.guard()
    monkeypatch.setattr(inputs,'ScoreReader',Reader)
    assert cli.main(['--contract-version','1','--config',str(tmp_path/'config'),'--batch','--queue',str(queue),'--shared-lock',str(lock)])==0
    assert json.loads(capsys.readouterr().out)['status']=='scored'


@pytest.mark.parametrize('extra',[
    ['--batch'],['--batch','--queue','/private/queue','--shared-lock','/private/lock','--horizon','1'],
    ['--collect','--batch'],['--queue','/private/queue']])
def test_invalid_queue_cli_intent_refused_before_preflight(monkeypatch,extra):
    import thermal_installed_score as cli
    import thermal_installed_intel as publication_cli
    monkeypatch.setattr(publication_cli,'_resource_preflight',lambda:pytest.fail('invalid intent reached resources'))
    with pytest.raises(SystemExit) as error:cli.main(['--config','/private/config',*extra])
    assert error.value.code==2


@pytest.mark.parametrize('damage',['oversized','boolean_horizon','extra_field','relative_origin'])
def test_invalid_queue_refused_before_any_collection(tmp_path,monkeypatch,damage):
    m,queue,out,jobs,calls=setup(tmp_path,monkeypatch)
    altered=[dict(jobs[1])]
    if damage=='oversized':altered*=257
    elif damage=='boolean_horizon':altered[0]['horizon_hours']=True
    elif damage=='extra_field':altered[0]['active']=True
    else:altered[0]['origin_path']='relative.json'
    queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v1',jobs=altered)))
    assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='withheld'
    assert calls==[]


def test_raw_packet_for_different_horizon_never_marks_completion(tmp_path,monkeypatch):
    m,queue,out,_,calls=setup(tmp_path,monkeypatch)
    monkeypatch.setattr(m,'read_raw_score_sources',lambda *args,**kwargs:dict(
        score_packet=dict(origin_path=str(tmp_path/'old.json'),horizon_hours=6),raw_score_sources_sha256='a'*64))
    assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='withheld'
    assert len(calls)==1 and not list(out.glob('*.score-job-v1.json'))


def test_queue_change_during_collection_never_marks_completion(tmp_path,monkeypatch):
    m,queue,out,_,calls=setup(tmp_path,monkeypatch);original=m.collect_published_score
    def collect(**kwargs):
        result=original(**kwargs);queue.write_text('{}');return result
    monkeypatch.setattr(m,'collect_published_score',collect)
    assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='withheld'
    assert len(calls)==1 and not list(out.glob('*.score-job-v1.json'))


def test_withheld_first_job_does_not_starve_next_mature_job(tmp_path,monkeypatch):
    m,queue,out,jobs,calls=setup(tmp_path,monkeypatch,'withheld');second=tmp_path/'second.json';second.touch(mode=0o600)
    queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v1',jobs=[jobs[1],dict(origin_path=str(second),horizon_hours=1)])))
    monkeypatch.setattr(m,'read_publication_capture',lambda _:dict(numeric_capture=dict(issued_at=(NOW-timedelta(hours=2)).isoformat())))
    for _ in range(2):assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='withheld'
    assert [call['origin_path'] for call in calls]==[Path(jobs[1]['origin_path']),second]


def test_completed_prefix_replay_cannot_prevent_new_mature_job(tmp_path,monkeypatch):
    m,queue,out,jobs,calls=setup(tmp_path,monkeypatch)
    assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='scored'
    second=tmp_path/'second.json';second.touch(mode=0o600)
    queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v1',jobs=[jobs[1],dict(origin_path=str(second),horizon_hours=1)])))
    monkeypatch.setattr(m,'read_publication_capture',lambda _:dict(numeric_capture=dict(issued_at=(NOW-timedelta(hours=2)).isoformat())))
    def collect(**kwargs):
        calls.append(kwargs);raw=out/'second-raw.json';raw.write_text('{}');raw.chmod(0o600)
        return dict(status='scored',raw_packet_path=str(raw),release_authorized=False)
    replayed=[]
    def replay(path,**kwargs):
        replayed.append(path)
        if path.name=='raw.json':raise ValueError('completed-prefix replay budget exhausted')
        return dict(score_packet=dict(origin_path=str(second),horizon_hours=1),raw_score_sources_sha256='b'*64)
    monkeypatch.setattr(m,'collect_published_score',collect);monkeypatch.setattr(m,'read_raw_score_sources',replay)
    assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='scored'
    assert calls[-1]['origin_path']==second and replayed==[out/'second-raw.json']


def test_bad_original_is_rotated_before_next_tick(tmp_path,monkeypatch):
    m,queue,out,jobs,calls=setup(tmp_path,monkeypatch,'withheld');second=tmp_path/'second.json';second.touch(mode=0o600)
    queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v1',jobs=[jobs[1],dict(origin_path=str(second),horizon_hours=1)])))
    def original(path):
        if path.name=='old.json':raise ValueError('invalid original source')
        return dict(numeric_capture=dict(issued_at=(NOW-timedelta(hours=2)).isoformat()))
    monkeypatch.setattr(m,'read_publication_capture',original)
    for _ in range(2):assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='withheld'
    assert len(calls)==1 and calls[0]['origin_path']==second


def test_bounded_immature_scan_resumes_past_first_eight_jobs(tmp_path,monkeypatch):
    m,queue,out,jobs,calls=setup(tmp_path,monkeypatch,'withheld');pending=[]
    for index in range(8):
        path=tmp_path/f'future-{index}.json';path.touch(mode=0o600)
        pending.append(dict(origin_path=str(path),horizon_hours=24))
    queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v1',jobs=[*pending,jobs[1]])))
    assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='pending'
    assert calls==[]
    assert m.collect_queued_score(queue_path=queue,output_directory=out,backend=Backend())['status']=='withheld'
    assert len(calls)==1 and calls[0]['origin_path']==Path(jobs[1]['origin_path'])
