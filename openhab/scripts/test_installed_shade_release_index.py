"""Index routing seams do not prove genuine household release qualification."""
import json
from pathlib import Path
from datetime import datetime,timezone
import pytest
from test_installed_shade_raw_origin import source_origin_case,raw_math_capture,candidate

@pytest.fixture
def index_case(tmp_path,monkeypatch):
    from thermal_model import installed_shade_qualification as q
    root=tmp_path/'private';root.mkdir(mode=0o700)
    def save(name,value):
        p=root/name;p.write_text(json.dumps(value));p.chmod(0o600);return p
    old=dict(raw_score_sources_path=str(root/'old.json'))
    new=dict(raw_score_sources_path=str(root/'new.json'))
    index=save('old-index.json',[old]);extra=save('new-index.json',[new])
    paths={k:save(k+'.json',{}) for k in ('registration_path','candidate_path')}
    from thermal_model.runtime_bundle import capture_runtime_bundle
    runtime_sources=root/'runtime-sources';runtime_sources.mkdir(mode=0o700)
    (runtime_sources/'thermal_model').mkdir(mode=0o700)
    (runtime_sources/'thermal_intel.py').write_text('# routing fixture only\n')
    (runtime_sources/'thermal_model/origin_capture.py').write_text('# routing observer fixture only\n')
    for source in (runtime_sources/'thermal_intel.py',runtime_sources/'thermal_model/origin_capture.py'):source.chmod(0o600)
    archives=root/'runtime-archives';archives.mkdir(mode=0o700)
    paths['runtime_bundle_path']=capture_runtime_bundle(archives,runtime_sources,['thermal_intel.py'])
    ref=save('release.json',dict(schema='earthship-installed-shade-release-inputs/v4',original_pairs_path=str(index),**{k:str(v) for k,v in paths.items()}))
    state={'gates':dict.fromkeys(('preregistered_policy','frozen_candidate','frozen_runtime','qualified_training_sources','measured_fit','raw_development_sources','raw_calibration_sources','original_source_pairs','raw_native_issue_sources','raw_native_score_sources','calibrated_intervals'),True),'calls':[],'changed':False}
    def qualify(**kw):
        state['calls'].append(kw['original_pairs'])
        return dict(gates=state['gates'],candidate={k:None for k in ('artifact_sha256','runtime_sha256','sensor_epochs')},original_pair_bindings=['routing-binding'],forecast_qualified=False)
    monkeypatch.setattr(q,'qualify_compressed_installed_shade_candidate',qualify)
    monkeypatch.setattr(q,'validate_compressed_installed_shade_qualification_report',lambda _:None)
    monkeypatch.setattr(q,'score_compressed_source_calibrated_packets',lambda *a,**kw:dict(bindings=['routing-binding']))
    return ref,extra,index,old,new,state

def test_append_keeps_old_entries_and_accepts_failed_skill_without_release_authority(index_case):
    from thermal_model.installed_shade_release_index import append_compressed_release_sources
    ref,extra,index,old,new,state=index_case
    result=append_compressed_release_sources(reference_path=ref,additional_pairs_path=extra,guard=lambda:None)
    assert result['status']=='index_updated' and result['release_authorized'] is False
    target=Path(json.loads(ref.read_text())['original_pairs_path'])
    assert json.loads(target.read_text())==[old,new] and json.loads(index.read_text())==[old]
    assert target.stat().st_mode&0o777==0o600
    assert state['calls']==[[old,new]]
    assert append_compressed_release_sources(reference_path=ref,additional_pairs_path=extra,guard=lambda:None)['status']=='index_unchanged'

@pytest.mark.parametrize('gate',['frozen_candidate','frozen_runtime','raw_native_issue_sources','original_source_pairs'])
def test_invalid_originals_leave_pointer_unchanged(index_case,gate):
    from thermal_model.installed_shade_release_index import append_compressed_release_sources
    ref,extra,_,_,_,state=index_case;before=ref.read_bytes();state['gates'][gate]=False
    with pytest.raises(ValueError):append_compressed_release_sources(reference_path=ref,additional_pairs_path=extra,guard=lambda:None)
    assert ref.read_bytes()==before

def test_guard_failure_during_actual_temporary_write_cannot_replace_pointer(index_case,monkeypatch):
    from thermal_model import installed_shade_release_index as m
    ref,extra,_,_,_,_=index_case;before=ref.read_bytes();real=m._write_private
    state={'fail':False}
    def write(path,raw):
        real(path,raw)
        if path.name.startswith('.release-index-pointer-'):state['fail']=True
    monkeypatch.setattr(m,'_write_private',write)
    def guard():
        if state['fail']:raise ValueError('lost shared lock')
    with pytest.raises(ValueError):m.append_compressed_release_sources(reference_path=ref,additional_pairs_path=extra,guard=guard)
    assert ref.read_bytes()==before

@pytest.mark.parametrize('damage',['legacy_reference','changed_index','expired_parent'])
def test_changed_or_incompatible_inputs_refuse_before_pointer_update(index_case,damage):
    from thermal_model import installed_shade_release_index as m
    from thermal_model.replay_budget import shared_replay_budget
    ref,extra,index,_,_,_=index_case
    if damage=='legacy_reference':
        value=json.loads(ref.read_text());value['schema']='earthship-installed-shade-release-inputs/v3';ref.write_text(json.dumps(value))
    before=ref.read_bytes();state={'calls':0}
    def guard():
        state['calls']+=1
        if damage=='changed_index' and state['calls']==12:index.write_text('[]')
    remaining={'seconds':60}
    with shared_replay_budget(lambda:remaining['seconds']):
        if damage=='expired_parent':remaining['seconds']=0
        with pytest.raises(ValueError):m.append_compressed_release_sources(reference_path=ref,additional_pairs_path=extra,guard=guard)
    assert ref.read_bytes()==before


@pytest.mark.parametrize('queued',[False,True])
def test_scorer_explicit_index_update_uses_shared_lock_and_grants_no_release(monkeypatch,tmp_path,capsys,queued):
    import thermal_installed_score as cli
    import thermal_installed_intel as intel
    from thermal_model import installed_shade_score_inputs as inputs,installed_shade_release_index as index
    from thermal_model import capture_guard
    from thermal_model.capture_guard import SharedScoreLock
    tmp_path.chmod(0o700);(tmp_path/'lock').touch(mode=0o600)
    calls=[]
    monkeypatch.setattr(intel,'_resource_preflight',lambda:calls.append('preflight'))
    monkeypatch.setattr(capture_guard,'verify_host_headroom',lambda:calls.append('headroom'))
    monkeypatch.setattr(inputs,'load_compressed_source_score_settings',lambda _:dict(output_directory=tmp_path))
    monkeypatch.setattr(inputs,'ScoreReader',lambda *a,**k:pytest.fail('index update constructs acquisition backend'))
    def append(**kw):
        kw['guard']();calls.append((kw['reference_path'],kw.get('additional_pairs_path',kw.get('queue_path'))))
        return dict(status='index_updated',release_authorized=False)
    monkeypatch.setattr(index,'append_compressed_release_sources',append)
    monkeypatch.setattr(index,'append_compressed_completed_queue',append)
    args=['--config',str(tmp_path/'config'),'--contract-version','4','--update-release-index',
        '--release-reference',str(tmp_path/'reference'),'--queue' if queued else '--additional-pairs',str(tmp_path/'new'),'--shared-lock',str(tmp_path/'lock')]
    assert cli.main(args)==0
    assert calls==['preflight','headroom',(tmp_path/'reference',tmp_path/'new')]
    assert json.loads(capsys.readouterr().out)==dict(status='index_updated',release_authorized=False)

@pytest.mark.parametrize('lose_source',[False,True])
def test_index_retention_replays_actual_compressed_issue_and_outcome_originals(index_case,source_origin_case,tmp_path,monkeypatch,lose_source):
    from thermal_model import installed_shade_qualification as q,installed_shade_release_index as m
    from test_installed_shade_raw_publication_capture import compressed_calibrated_archive_case
    archive_root,_,args,now,_,result=compressed_calibrated_archive_case(source_origin_case,tmp_path,monkeypatch)
    ref,extra,index,_,_,_=index_case
    refs=[dict(raw_score_sources_path=result['raw_packet_path'])]
    extra.write_text(json.dumps(refs));index.write_text('[]')
    from thermal_model.installed_shade_artifact import _digest
    header=json.loads(Path(result['raw_packet_path']).read_text())
    job={key:header['score_sources'][key] for key in ('origin_path','horizon_hours')}
    queue=archive_root/'release-jobs.json';queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v4',jobs=[job])));queue.chmod(0o600)
    marker=archive_root/(_digest(job)+'.score-job-v4.json')
    marker.write_text(json.dumps(dict(schema='earthship-installed-score-job-completion/v4',job=job,raw_packet_path=result['raw_packet_path'],raw_score_sources_sha256=_digest(header),release_authority=False)));marker.chmod(0o600)
    def append():return m.append_compressed_completed_queue(reference_path=ref,queue_path=queue,output_directory=archive_root,guard=lambda:None)
    # Mathematical registration/candidate loader seam remains explicit; actual
    # score7 query/capture/archive replay is restored for every source guard.
    def qualify(**kw):
        checked=q._score_packets(kw['original_pairs'],assessed_at=now,version=7)
        identity={key:checked['rows'][0][key] for key in ('artifact_sha256','runtime_sha256','sensor_epochs')}
        return dict(gates=dict.fromkeys(m.SOURCE_GATES,True),candidate=identity,original_pair_bindings=checked['bindings'])
    monkeypatch.setattr(q,'qualify_compressed_installed_shade_candidate',qualify)
    monkeypatch.setattr(q,'score_compressed_source_calibrated_packets',lambda packets,**kw:q._score_source_packets(packets,assessed_at=now,candidate=kw['candidate'],source_version=7))
    before=ref.read_bytes();write=m._write_private
    def retain(path,raw):
        write(path,raw)
        if lose_source and path.name.startswith('.release-index-pointer-'):Path(args['native_source_paths']['air']).unlink()
    monkeypatch.setattr(m,'_write_private',retain)
    if lose_source:
        with pytest.raises((ValueError,OSError)):append()
        assert ref.read_bytes()==before
    else:
        assert append()['status']=='index_updated'
        assert json.loads(Path(json.loads(ref.read_text())['original_pairs_path']).read_text())==refs


def test_index_update_headroom_refusal_precedes_settings_and_qualification(monkeypatch,tmp_path,capsys):
    import thermal_installed_score as cli
    import thermal_installed_intel as intel
    from thermal_model import capture_guard,installed_shade_score_inputs as inputs
    monkeypatch.setattr(intel,'_resource_preflight',lambda:None)
    def refuse():raise ValueError('insufficient household headroom')
    monkeypatch.setattr(capture_guard,'verify_host_headroom',refuse)
    monkeypatch.setattr(inputs,'load_compressed_source_score_settings',lambda _:pytest.fail('headroom refusal reached settings'))
    assert cli.main(['--config',str(tmp_path/'config'),'--contract-version','4','--update-release-index',
        '--release-reference',str(tmp_path/'reference'),'--additional-pairs',str(tmp_path/'new'),'--shared-lock',str(tmp_path/'lock')])==1
    assert json.loads(capsys.readouterr().out)['status']=='withheld'

@pytest.fixture
def completed_queue(index_case):
    from thermal_model.installed_shade_artifact import _digest
    ref,extra,_,_,_,_=index_case;root=ref.parent
    job=dict(origin_path=str(root/('1'*64+'.installed-shade-origin-v13.json')),horizon_hours=24)
    queue=root/'jobs.json';queue.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v4',jobs=[job])));queue.chmod(0o600)
    marker=root/(_digest(job)+'.score-job-v4.json')
    header=dict(schema='earthship-installed-shade-score-sources/v7',score_sources=job)
    source_digest=_digest(header);packet=root/(source_digest+'.installed-shade-score-sources-v7.json')
    packet.write_text(json.dumps(header));packet.chmod(0o600)
    marker.write_text(json.dumps(dict(schema='earthship-installed-score-job-completion/v4',job=job,
        raw_packet_path=str(packet),raw_score_sources_sha256=source_digest,release_authority=False)));marker.chmod(0o600)
    return ref,queue,root,marker,packet


def test_queue_discovery_passes_original_references_to_full_qualification(index_case,completed_queue):
    from thermal_model.installed_shade_release_index import append_compressed_completed_queue
    ref,queue,root,_,packet=completed_queue
    result=append_compressed_completed_queue(reference_path=ref,queue_path=queue,output_directory=root,guard=lambda:None)
    assert result==dict(status='index_updated',release_authorized=False)
    assert index_case[-1]['calls'][0]==[index_case[3],dict(raw_score_sources_path=str(packet))]

@pytest.mark.parametrize('damage',['authority','digest','foreign_archive','wrong_job','legacy_queue','base_origin'])
def test_discovery_invalid_completion_or_queue_never_changes_pointer(completed_queue,damage):
    from thermal_model.installed_shade_release_index import append_compressed_completed_queue
    ref,queue,root,marker,_=completed_queue;before=ref.read_bytes();saved=json.loads(marker.read_text())
    if damage=='authority':saved['release_authority']=True
    elif damage=='digest':saved['raw_score_sources_sha256']='b'*64
    elif damage=='foreign_archive':saved['raw_packet_path']=str(root.parent/Path(saved['raw_packet_path']).name)
    elif damage=='wrong_job':saved['job']['horizon_hours']=6
    else:
        value=json.loads(queue.read_text())
        if damage=='legacy_queue':value['schema']='earthship-installed-score-jobs/v3'
        else:value['jobs'][0]['origin_path']=value['jobs'][0]['origin_path'].replace('v13','v11')
        queue.write_text(json.dumps(value))
    marker.write_text(json.dumps(saved))
    with pytest.raises(ValueError):append_compressed_completed_queue(reference_path=ref,queue_path=queue,output_directory=root,guard=lambda:None)
    assert ref.read_bytes()==before


def test_discovery_missing_completion_is_pending_without_qualification(index_case,completed_queue):
    from thermal_model.installed_shade_release_index import append_compressed_completed_queue
    ref,queue,root,marker,_=completed_queue;before=ref.read_bytes();marker.unlink()
    assert append_compressed_completed_queue(reference_path=ref,queue_path=queue,output_directory=root,guard=lambda:None)==dict(status='index_pending',release_authorized=False)
    assert index_case[-1]['calls']==[] and ref.read_bytes()==before

@pytest.mark.parametrize('target',['queue','completion'])
def test_discovery_original_change_after_pointer_temporary_write_refuses(completed_queue,monkeypatch,target):
    from thermal_model import installed_shade_release_index as m
    ref,queue,root,marker,_=completed_queue;before=ref.read_bytes();write=m._write_private
    def changed(path,raw):
        write(path,raw)
        if path.name.startswith('.release-index-pointer-'):(queue if target=='queue' else marker).write_text('{}')
    monkeypatch.setattr(m,'_write_private',changed)
    with pytest.raises(ValueError):m.append_compressed_completed_queue(reference_path=ref,queue_path=queue,output_directory=root,guard=lambda:None)
    assert ref.read_bytes()==before


def test_discovery_different_original_job_cannot_be_selected_by_completion_hint(index_case,completed_queue):
    from thermal_model.installed_shade_release_index import append_compressed_completed_queue
    from thermal_model.installed_shade_artifact import _digest
    ref,queue,root,marker,packet=completed_queue;before=ref.read_bytes()
    header=json.loads(packet.read_text());header['score_sources']['horizon_hours']=6
    digest=_digest(header);other=root/(digest+'.installed-shade-score-sources-v7.json');other.write_text(json.dumps(header));other.chmod(0o600)
    saved=json.loads(marker.read_text());saved.update(raw_packet_path=str(other),raw_score_sources_sha256=digest);marker.write_text(json.dumps(saved))
    with pytest.raises(ValueError):append_compressed_completed_queue(reference_path=ref,queue_path=queue,output_directory=root,guard=lambda:None)
    assert index_case[-1]['calls']==[] and ref.read_bytes()==before


def test_scheduled_index_template_is_bounded_and_has_no_acquisition_or_actuation():
    root=Path(__file__).resolve().parents[2]/'openhab/systemd/user'
    unit=(root/'thermal-installed-release-index.service').read_text()
    timer=(root/'thermal-installed-release-index.timer').read_text()
    for line in ('Type=oneshot','CPUQuota=20%','MemoryMax=256M','MemorySwapMax=0','TasksMax=24','Nice=15','IOWeight=10','UMask=0077'):
        assert line in unit.splitlines()
    command=next(line for line in unit.splitlines() if line.startswith('ExecStart='))
    assert '--contract-version 4' in command and '--update-release-index' in command and '--queue @VERIFIED_SCORE_QUEUE@' in command
    assert '--shared-lock @VERIFIED_SHARED_LOCK@' in command and '--release-reference @VERIFIED_RELEASE_REFERENCE@' in command
    assert 'timeout 60s' in command and '--collect' not in command and '--batch' not in command
    assert 'Persistent=false' in timer and 'Unit=thermal-installed-release-index.service' in timer

    collection=(root/'thermal-installed-compressed-score-queue.service').read_text()
    assert '--contract-version 4' in collection and '--batch' in collection and '--shared-lock @VERIFIED_SHARED_LOCK@' in collection
    for line in ('CPUQuota=20%','MemoryMax=256M','MemorySwapMax=0','TasksMax=24','Nice=15','IOWeight=10','UMask=0077'):
        assert line in collection.splitlines()
    collection_timer=(root/'thermal-installed-compressed-score-queue.timer').read_text()
    assert 'Persistent=false' in collection_timer and 'Unit=thermal-installed-compressed-score-queue.service' in collection_timer


@pytest.mark.parametrize('member',['manifest.json','interpreter.bin','sources/thermal_intel.py'])
def test_original_runtime_member_loss_at_pointer_write_prevents_incorporation(index_case,monkeypatch,member):
    from thermal_model import installed_shade_release_index as m
    ref,extra,_,_,_,_=index_case;before=ref.read_bytes()
    bundle=Path(json.loads(before)['runtime_bundle_path']);original=m._write_private;fired=[]
    def write(path,raw):
        original(path,raw)
        if path.name.startswith('.release-index-pointer-'):
            fired.append(True);(bundle/member).unlink()
    monkeypatch.setattr(m,'_write_private',write)
    with pytest.raises(ValueError):m.append_compressed_release_sources(reference_path=ref,additional_pairs_path=extra,guard=lambda:None)
    assert ref.read_bytes()==before
    assert fired, 'runtime loss must occur after the actual pointer temporary write'
