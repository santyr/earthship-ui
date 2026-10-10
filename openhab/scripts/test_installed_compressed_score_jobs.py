"""Compressed queue/operator contracts; synthetic ports grant no release."""
import json
from pathlib import Path
import pytest
from test_installed_raw_score_cli import settings


@pytest.mark.parametrize('batch',[False,True])
def test_compressed_score_cli_routes_under_shared_lock(settings,monkeypatch,capsys,batch):
    import thermal_installed_score as cli,thermal_installed_intel as publisher
    from thermal_model import installed_shade_score_inputs as inputs,installed_shade_score_jobs as jobs
    path,value,lock=settings;value=dict(value,schema='earthship-installed-shade-score-config/v4');path.write_text(json.dumps(value))
    monkeypatch.setattr(publisher,'_resource_preflight',lambda:None)
    class Reader:
        def __init__(self,settings,*,shared_lock_guard):self.guard=shared_lock_guard;self.guard()
        def verify_unchanged(self):self.guard()
    monkeypatch.setattr(inputs,'ScoreReader',Reader)
    def collect(**kw):
        kw['backend'].verify_unchanged();assert kw['output_directory']==value['output_directory']
        return dict(status='pending',release_authorized=False)
    monkeypatch.setattr(jobs,'collect_compressed_queued_score',collect,raising=False)
    monkeypatch.setattr(jobs,'collect_compressed_original_score',collect,raising=False)
    args=['--batch','--queue',str(path.parent/'queue')] if batch else ['--collect','--origin',str(path.parent/'origin'),'--horizon','1']
    assert cli.main(['--contract-version','4','--config',str(path),'--shared-lock',str(lock),*args])==0
    assert json.loads(capsys.readouterr().out)['release_authorized'] is False


def test_compressed_queue_empty_closed_profile_has_no_release_authority(tmp_path):
    from thermal_model import installed_shade_score_jobs as jobs
    api=getattr(jobs,'collect_compressed_queued_score',None)
    assert callable(api),'missing compressed original-source queue'
    tmp_path.chmod(0o700);path=tmp_path/'jobs';path.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v4',jobs=[])));path.chmod(0o600)
    class Backend:
        def verify_unchanged(self):pass
    assert api(queue_path=path,output_directory=tmp_path,backend=Backend())==dict(status='queue_complete',release_authorized=False)
    assert jobs.collect_source_queued_score(queue_path=path,output_directory=tmp_path,backend=Backend())['status']=='withheld'


from datetime import timedelta
from test_installed_shade_raw_origin import candidate,raw_math_capture,source_origin_case


@pytest.fixture(params=['base','calibrated'])
def retained_queue(source_origin_case,tmp_path,monkeypatch,request):
    from test_installed_shade_raw_publication_capture import deliver_source,CompressedRawBackend
    from thermal_model import installed_shade_published_origin as captures,installed_shade_score_jobs as jobs,installed_shade_score_collection as collector
    kind=request.param
    root,record,_,issue,_,args=deliver_source((source_origin_case,tmp_path,monkeypatch,kind),compressed=True)
    writer=captures.write_compressed_source_publication_capture if kind=='base' else captures.write_compressed_calibrated_publication_capture
    origin=writer(root,record);job=dict(origin_path=str(origin),horizon_hours=1)
    path=root/'jobs';path.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v4',jobs=[job])));path.chmod(0o600)
    now=issue+timedelta(hours=24,minutes=10)
    monkeypatch.setattr(jobs,'_clock',lambda:now);monkeypatch.setattr(collector,'_clock',lambda:now)
    return jobs,path,root,job,CompressedRawBackend(record,root),args,kind,monkeypatch


def test_compressed_queue_retains_distinct_completion_replays_originals_and_never_recollects_loss(retained_queue):
    jobs,path,root,job,backend,args,kind,_=retained_queue
    result=jobs.collect_compressed_queued_score(queue_path=path,output_directory=root,backend=backend)
    assert result['status']=='scored'
    packet=json.loads(Path(result['raw_packet_path']).read_text())
    assert packet['schema']=='earthship-installed-shade-score-sources/v'+('6' if kind=='base' else '7')
    markers=list(root.glob('*.score-job-v4.json'));assert len(markers)==1
    saved=json.loads(markers[0].read_text());assert saved['schema']=='earthship-installed-score-job-completion/v4'
    assert saved['job']==job and saved['release_authority'] is False
    assert jobs.collect_compressed_queued_score(queue_path=path,output_directory=root,backend=backend)['status']=='completion_verified'
    before=list(backend.calls);Path(args['native_source_paths']['air']).unlink()
    assert jobs.collect_compressed_queued_score(queue_path=path,output_directory=root,backend=backend)['status']=='withheld'
    assert backend.calls==before


def test_compressed_completion_source_loss_after_actual_temp_write_refuses_marker(retained_queue):
    jobs,path,root,_,backend,args,_,monkeypatch=retained_queue
    from thermal_model import runtime_bundle
    writer=runtime_bundle._write_private
    def lost(target,raw):
        writer(target,raw)
        if 'earthship-installed-score-job-completion/v4' in raw.decode():Path(args['native_source_paths']['air']).unlink()
    monkeypatch.setattr(runtime_bundle,'_write_private',lost)
    assert jobs.collect_compressed_queued_score(queue_path=path,output_directory=root,backend=backend)['status']=='withheld'
    assert not list(root.glob('*.score-job-v4.json'))


def test_compressed_queue_inherits_parent_deadline_without_source_read(tmp_path,monkeypatch):
    from thermal_model import installed_shade_score_jobs as jobs
    from thermal_model.replay_budget import shared_replay_budget
    tmp_path.chmod(0o700);path=tmp_path/'jobs';path.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v4',jobs=[])));path.chmod(0o600)
    class Backend:
        def verify_unchanged(self):pass
    clock={'remaining':60}
    with shared_replay_budget(lambda:clock['remaining']):
        clock['remaining']=0
        assert jobs.collect_compressed_queued_score(queue_path=path,output_directory=tmp_path,backend=Backend())['status']=='withheld'


def test_compressed_queue_parent_expiry_after_capture_stops_before_collection(retained_queue):
    from thermal_model.replay_budget import shared_replay_budget
    jobs,path,root,_,backend,_,_,monkeypatch=retained_queue;reader=jobs._read_compressed_origin;clock={'remaining':60}
    def expire(origin):
        result=reader(origin);clock['remaining']=0;return result
    monkeypatch.setattr(jobs,'_read_compressed_origin',expire)
    with shared_replay_budget(lambda:clock['remaining']):
        assert jobs.collect_compressed_queued_score(queue_path=path,output_directory=root,backend=backend)['status']=='withheld'
    assert backend.calls==[] and not list(root.glob('*.score-job-v4.json'))


@pytest.mark.parametrize('damage',['duplicate','unknown_origin','old_schema'])
def test_compressed_queue_refuses_bad_profile_before_collection(tmp_path,monkeypatch,damage):
    from thermal_model import installed_shade_score_jobs as jobs
    tmp_path.chmod(0o700);path=tmp_path/'jobs';job=dict(origin_path=str(tmp_path/'unknown.json'),horizon_hours=1)
    if damage=='unknown_origin':
        origin=Path(job['origin_path']);origin.write_text('{}');origin.chmod(0o600)
    payload=dict(schema='earthship-installed-score-jobs/v4',jobs=[job,job] if damage=='duplicate' else [job])
    if damage=='old_schema':payload['schema']='earthship-installed-score-jobs/v3'
    path.write_text(json.dumps(payload));path.chmod(0o600)
    monkeypatch.setattr(jobs,'collect_compressed_original_score',lambda **kw:pytest.fail('invalid queue reached source collection'))
    class Backend:
        def verify_unchanged(self):pass
    assert jobs.collect_compressed_queued_score(queue_path=path,output_directory=tmp_path,backend=Backend())['status']=='withheld'


def test_compressed_score_config_check_does_not_construct_source_reader(settings,monkeypatch,capsys):
    import thermal_installed_score as cli
    from thermal_model import installed_shade_score_inputs as inputs
    path,value,_=settings;path.write_text(json.dumps(dict(value,schema='earthship-installed-shade-score-config/v4')))
    monkeypatch.setattr(inputs,'ScoreReader',lambda *a,**kw:pytest.fail('configuration check reached source reader'))
    assert cli.main(['--config',str(path),'--contract-version','4'])==0
    assert json.loads(capsys.readouterr().out)['collection_executed'] is False
