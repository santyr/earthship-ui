"""Registration routing seams grant no household evidence or release authority."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import pytest

@pytest.fixture
def registration_case(tmp_path,monkeypatch):
    from thermal_model import installed_shade_published_origin as captures
    tmp_path.chmod(0o700)
    now=datetime(2026,11,1,18,tzinfo=timezone.utc)
    def save(name,value):
        p=tmp_path/name;p.write_text(json.dumps(value));p.chmod(0o600);return p
    record=dict(numeric_capture=dict(issued_at=now.isoformat(),candidate=dict(artifact_sha256='a'*64),runtime=dict(test='routing'),source_epochs=dict(air='routing-air',mass='routing-mass',outdoor='routing-outdoor')))
    origin=save('first.installed-shade-origin-v13.json',record);records={str(origin):record}
    queues={str(h):str(save(str(h)+'.jobs.json',dict(schema='earthship-installed-score-jobs/v4',jobs=[]))) for h in (1,6,12,24)}
    registration=save('registration.json',dict(schema='earthship-installed-score-registration/v1',candidate=None,queues=queues))
    monkeypatch.setattr(captures,'read_compressed_calibrated_publication_capture',lambda p:records[str(p)])
    return registration,origin,record,records,save


def test_verified_original_registration_atomically_updates_all_horizons_and_is_idempotent(registration_case):
    from thermal_model.installed_shade_score_registration import register_compressed_publication_jobs
    reg,origin,_,_,_=registration_case;old=json.loads(reg.read_text())
    assert register_compressed_publication_jobs(registration_path=reg,origin_path=origin,guard=lambda:None)==dict(status='jobs_registered',release_authorized=False)
    updated=json.loads(reg.read_text());assert updated['candidate']['artifact_sha256']=='a'*64
    for h,path in updated['queues'].items():
        assert json.loads(Path(path).read_text())['jobs']==[dict(origin_path=str(origin),horizon_hours=int(h))]
        assert json.loads(Path(old['queues'][h]).read_text())['jobs']==[]
    assert register_compressed_publication_jobs(registration_path=reg,origin_path=origin,guard=lambda:None)['status']=='jobs_unchanged'

@pytest.mark.parametrize('hours,status',[(6,'origin_not_selected'),(24,'jobs_registered')])
def test_dense_issues_do_not_replace_independent_daily_window(registration_case,hours,status):
    from thermal_model.installed_shade_score_registration import register_compressed_publication_jobs
    reg,origin,record,records,save=registration_case
    register_compressed_publication_jobs(registration_path=reg,origin_path=origin,guard=lambda:None)
    other=json.loads(json.dumps(record));other['numeric_capture']['issued_at']=(datetime.fromisoformat(record['numeric_capture']['issued_at'])+timedelta(hours=hours)).isoformat()
    new=save('second.installed-shade-origin-v13.json',other);records[str(new)]=other
    assert register_compressed_publication_jobs(registration_path=reg,origin_path=new,guard=lambda:None)['status']==status
    for path in json.loads(reg.read_text())['queues'].values():assert len(json.loads(Path(path).read_text())['jobs'])==(2 if hours==24 else 1)


def test_different_frozen_candidate_refuses_without_dropping_jobs(registration_case):
    from thermal_model.installed_shade_score_registration import register_compressed_publication_jobs
    reg,origin,record,records,save=registration_case
    register_compressed_publication_jobs(registration_path=reg,origin_path=origin,guard=lambda:None);before=reg.read_bytes()
    other=json.loads(json.dumps(record));other['numeric_capture']['candidate']['artifact_sha256']='b'*64
    new=save('other.installed-shade-origin-v13.json',other);records[str(new)]=other
    with pytest.raises(ValueError):register_compressed_publication_jobs(registration_path=reg,origin_path=new,guard=lambda:None)
    assert reg.read_bytes()==before


def test_shared_guard_loss_after_actual_pointer_write_leaves_all_old_queues_selected(registration_case,monkeypatch):
    from thermal_model import installed_shade_score_registration as m
    reg,origin,_,_,_=registration_case;before=reg.read_bytes();write=m._write_private;state={'lost':False}
    def retain(path,raw):
        write(path,raw)
        if path.name.startswith('.score-registration-pointer-'):state['lost']=True
    monkeypatch.setattr(m,'_write_private',retain)
    def guard():
        if state['lost']:raise ValueError('lost shared lock')
    with pytest.raises(ValueError):m.register_compressed_publication_jobs(registration_path=reg,origin_path=origin,guard=guard)
    assert reg.read_bytes()==before

@pytest.mark.parametrize('delivered',[True,False])
def test_compressed_operator_registers_only_verified_publication_receipts(monkeypatch,tmp_path,capsys,delivered):
    import thermal_installed_intel as cli
    from thermal_model import installed_shade_live_inputs as inputs,installed_shade_live as live,installed_shade_score_registration as registration
    tmp_path.chmod(0o700);lock=tmp_path/'lock';lock.touch(mode=0o600);calls=[]
    settings=dict(release_inputs_path=tmp_path/'refs',evidence_directory=tmp_path)
    monkeypatch.setattr(cli,'_resource_preflight',lambda:None)
    monkeypatch.setattr(inputs,'load_compressed_live_settings',lambda _:settings)
    monkeypatch.setattr(inputs,'CompressedSourceLiveBackend',lambda *a,**kw:object())
    receipt=dict(status='published' if delivered else 'withdrawn',delivery_verified=True,capture_path=str(tmp_path/'actual.installed-shade-origin-v13.json'))
    def run(**kw):calls.append('verified_receipt');return dict(receipt)
    monkeypatch.setattr(live,'run_compressed_live_cycle',run)
    def register(**kw):
        kw['guard']();calls.append('registered')
        assert kw['origin_path']==Path(receipt['capture_path']) and kw['registration_path']==tmp_path/'registry'
        return dict(status='jobs_registered',release_authorized=False)
    monkeypatch.setattr(registration,'register_compressed_publication_jobs',register)
    assert cli.main(['--config',str(tmp_path/'config'),'--contract-version','3','--publish','--shared-lock',str(lock),'--score-registration',str(tmp_path/'registry')])==0
    assert calls==(['verified_receipt','registered'] if delivered else ['verified_receipt'])
    result=json.loads(capsys.readouterr().out)
    if delivered:assert result['scoring_registration']=='jobs_registered'


def test_registration_failure_preserves_publication_receipt_but_returns_failure(monkeypatch,tmp_path,capsys):
    import thermal_installed_intel as cli
    from thermal_model import installed_shade_live_inputs as inputs,installed_shade_live as live,installed_shade_score_registration as registration
    tmp_path.chmod(0o700);lock=tmp_path/'lock';lock.touch(mode=0o600)
    monkeypatch.setattr(cli,'_resource_preflight',lambda:None)
    monkeypatch.setattr(inputs,'load_compressed_live_settings',lambda _:dict(release_inputs_path=tmp_path/'refs',evidence_directory=tmp_path))
    monkeypatch.setattr(inputs,'CompressedSourceLiveBackend',lambda *a,**kw:object())
    monkeypatch.setattr(live,'run_compressed_live_cycle',lambda **kw:dict(status='published',delivery_verified=True,capture_path=str(tmp_path/'actual.installed-shade-origin-v13.json')))
    def refuse(**kw):raise ValueError('private registration diagnostic')
    monkeypatch.setattr(registration,'register_compressed_publication_jobs',refuse)
    assert cli.main(['--config',str(tmp_path/'config'),'--contract-version','3','--publish','--shared-lock',str(lock),'--score-registration',str(tmp_path/'registry')])==1
    result=capsys.readouterr();value=json.loads(result.out)
    assert value['status']=='published' and value['delivery_verified'] is True and value['scoring_registration']=='withheld'
    assert 'private registration diagnostic' not in result.out+result.err

from test_installed_shade_raw_origin import source_origin_case,raw_math_capture,candidate

@pytest.mark.parametrize('lose_original',[False,True])
def test_registration_replays_actual_main13_original_queries_after_pointer_temp_write(registration_case,source_origin_case,tmp_path,monkeypatch,lose_original):
    from thermal_model import installed_shade_published_origin as captures,installed_shade_score_registration as m
    from test_installed_shade_raw_publication_capture import compressed_calibrated_delivery
    root,record,_,_,_,args=compressed_calibrated_delivery(source_origin_case,tmp_path,monkeypatch)
    origin=captures.write_compressed_calibrated_publication_capture(root,record)
    monkeypatch.setattr(captures,'read_compressed_calibrated_publication_capture',lambda path:captures._read_publication_capture(path,_version=13))
    reg=registration_case[0];before=reg.read_bytes();write=m._write_private
    def changed(path,raw):
        write(path,raw)
        if lose_original and path.name.startswith('.score-registration-pointer-'):Path(args['native_source_paths']['air']).unlink()
    monkeypatch.setattr(m,'_write_private',changed)
    if lose_original:
        with pytest.raises((ValueError,OSError)):m.register_compressed_publication_jobs(registration_path=reg,origin_path=origin,guard=lambda:None)
        assert reg.read_bytes()==before
    else:
        assert m.register_compressed_publication_jobs(registration_path=reg,origin_path=origin,guard=lambda:None)['status']=='jobs_registered'
        for h,path in json.loads(reg.read_text())['queues'].items():assert json.loads(Path(path).read_text())['jobs']==[dict(origin_path=str(origin),horizon_hours=int(h))]


def test_full_horizon_queue_refuses_without_removing_any_existing_job(registration_case):
    from thermal_model.installed_shade_score_registration import register_compressed_publication_jobs
    reg,origin,record,records,_=registration_case
    register_compressed_publication_jobs(registration_path=reg,origin_path=origin,guard=lambda:None)
    value=json.loads(reg.read_text());paths=[str(reg.parent/(str(n)+'.installed-shade-origin-v13.json')) for n in range(256)]
    last=json.loads(json.dumps(record));last['numeric_capture']['issued_at']=(datetime.fromisoformat(record['numeric_capture']['issued_at'])-timedelta(days=1)).isoformat()
    Path(paths[-1]).write_text(json.dumps(last));Path(paths[-1]).chmod(0o600);records[paths[-1]]=last
    for h,path in value['queues'].items():Path(path).write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v4',jobs=[dict(origin_path=p,horizon_hours=int(h)) for p in paths])))
    before=reg.read_bytes()
    with pytest.raises(ValueError,match='capacity'):register_compressed_publication_jobs(registration_path=reg,origin_path=origin,guard=lambda:None)
    assert reg.read_bytes()==before

@pytest.mark.parametrize('version,intent',[(2,'--publish'),(3,'--bootstrap-shadow'),(3,'--check-only')])
def test_score_registration_refuses_wrong_operator_phase_before_reading_settings(version,intent,tmp_path):
    import thermal_installed_intel as cli
    with pytest.raises(SystemExit) as refused:
        cli.main(['--config',str(tmp_path/'config'),'--contract-version',str(version),intent,'--score-registration',str(tmp_path/'registry')])
    assert refused.value.code==2
