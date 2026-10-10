"""Registered queue resolution is scheduling metadata, never release permission."""
import json
from pathlib import Path
import pytest
from test_installed_publication_registration import registration_case

@pytest.mark.parametrize('hours',[1,6,12,24])
def test_resolver_selects_explicit_horizon_and_rechecks_registry(registration_case,hours):
    from thermal_model.installed_shade_score_registration import resolve_registered_score_queue
    reg,*_=registration_case
    path,verify=resolve_registered_score_queue(registration_path=reg,horizon_hours=hours,guard=lambda:None)
    assert str(path)==json.loads(reg.read_text())['queues'][str(hours)]
    verify();reg.write_text('{}')
    with pytest.raises(ValueError):verify()


def test_resolver_rejects_wrong_horizon_jobs(registration_case):
    from thermal_model.installed_shade_score_registration import resolve_registered_score_queue
    reg,origin,*_=registration_case
    path=Path(json.loads(reg.read_text())['queues']['1'])
    path.write_text(json.dumps(dict(schema='earthship-installed-score-jobs/v4',jobs=[dict(origin_path=str(origin),horizon_hours=6)])))
    with pytest.raises(ValueError):resolve_registered_score_queue(registration_path=reg,horizon_hours=1,guard=lambda:None)

@pytest.mark.parametrize('index',[False,True])
def test_registered_scorer_routes_under_actual_lock_without_changing_old_defaults(registration_case,monkeypatch,capsys,index):
    import thermal_installed_score as cli,thermal_installed_intel as intel
    from thermal_model import installed_shade_score_inputs as inputs,installed_shade_score_jobs as jobs,installed_shade_release_index as release,capture_guard
    reg,*_=registration_case;root=reg.parent;lock=root/'lock';lock.touch(mode=0o600)
    monkeypatch.setattr(intel,'_resource_preflight',lambda:None)
    monkeypatch.setattr(capture_guard,'verify_host_headroom',lambda:None)
    monkeypatch.setattr(inputs,'load_compressed_source_score_settings',lambda _:dict(output_directory=root))
    class Backend:
        def __init__(self,settings,*,shared_lock_guard):self.guard=shared_lock_guard;self.guard()
        def verify_unchanged(self):self.guard()
    monkeypatch.setattr(inputs,'ScoreReader',Backend)
    def operation(**kw):
        if index:kw['guard']()
        else:kw['backend'].verify_unchanged()
        assert str(kw['queue_path'])==json.loads(reg.read_text())['queues']['24']
        return dict(status='index_pending' if index else 'queue_complete',release_authorized=False)
    monkeypatch.setattr(jobs,'collect_compressed_queued_score',operation)
    monkeypatch.setattr(release,'append_compressed_completed_queue',operation)
    args=['--update-release-index','--release-reference',str(root/'refs')] if index else ['--batch']
    assert cli.main(['--config',str(root/'config'),'--contract-version','4','--shared-lock',str(lock),'--score-registration',str(reg),'--horizon','24',*args])==0
    assert json.loads(capsys.readouterr().out)['release_authorized'] is False


def test_registry_change_before_collection_refuses_without_running_source_backend(registration_case,monkeypatch,capsys):
    import thermal_installed_score as cli,thermal_installed_intel as intel
    from thermal_model import installed_shade_score_inputs as inputs,installed_shade_score_jobs as jobs
    reg,*_=registration_case;root=reg.parent;lock=root/'lock';lock.touch(mode=0o600)
    monkeypatch.setattr(intel,'_resource_preflight',lambda:None)
    monkeypatch.setattr(inputs,'load_compressed_source_score_settings',lambda _:dict(output_directory=root))
    class Backend:
        def __init__(self,settings,*,shared_lock_guard):reg.write_text('{}');shared_lock_guard()
    monkeypatch.setattr(inputs,'ScoreReader',Backend)
    monkeypatch.setattr(jobs,'collect_compressed_queued_score',lambda **kw:pytest.fail('changed registry reached source collection'))
    assert cli.main(['--config',str(root/'config'),'--contract-version','4','--shared-lock',str(lock),'--score-registration',str(reg),'--horizon','1','--batch'])==1
    assert json.loads(capsys.readouterr().out)['status']=='withheld'


from test_installed_shade_raw_origin import source_origin_case,raw_math_capture,candidate


def test_registered_actual_source_collection_and_completion_discovery_retain_originals(registration_case,source_origin_case,tmp_path,monkeypatch):
    from thermal_model import installed_shade_published_origin as captures,installed_shade_score_inputs as registration
    from thermal_model import installed_shade_score_jobs as jobs,installed_shade_qualification as q,installed_shade_release_index as release
    from test_installed_shade_raw_publication_capture import compressed_calibrated_archive_case,CompressedRawBackend
    monkeypatch.setattr(captures,'read_compressed_calibrated_publication_capture',lambda path:captures._read_publication_capture(path,_version=13))
    from thermal_model import installed_shade_score_collection as collector
    monkeypatch.setattr(collector,'read_compressed_calibrated_publication_capture',lambda path:captures._read_publication_capture(path,_version=13))
    root,main,_,now,backend,result=compressed_calibrated_archive_case(source_origin_case,tmp_path,monkeypatch)
    raw=json.loads(Path(result['raw_packet_path']).read_text());origin=Path(raw['score_sources']['origin_path']);reg=registration_case[0]
    assert registration.register_compressed_publication_jobs(registration_path=reg,origin_path=origin,guard=lambda:None)['status']=='jobs_registered'
    queue,verify=registration.resolve_registered_score_queue(registration_path=reg,horizon_hours=1,guard=lambda:None)
    monkeypatch.setattr(jobs,'_clock',lambda:now)
    backend=CompressedRawBackend(main,root);backend.verify_unchanged=verify
    collected=jobs.collect_compressed_queued_score(queue_path=queue,output_directory=root,backend=backend)
    verify();assert collected['status']=='scored'
    checked=q._score_packets([dict(raw_score_sources_path=collected['raw_packet_path'])],assessed_at=now,version=7)
    identity={key:checked['rows'][0][key] for key in ('artifact_sha256','runtime_sha256','sensor_epochs')}
    # Registration/candidate qualification loaders remain mathematical seams;
    # issue, comparator, outcome and completion-source reads are actual originals.
    monkeypatch.setattr(q,'qualify_compressed_installed_shade_candidate',lambda **kw:dict(gates=dict.fromkeys(release.SOURCE_GATES,True),candidate=identity,original_pair_bindings=checked['bindings']))
    monkeypatch.setattr(q,'validate_compressed_installed_shade_qualification_report',lambda _:None)
    monkeypatch.setattr(q,'score_compressed_source_calibrated_packets',lambda packets,**kw:q._score_source_packets(packets,assessed_at=now,candidate=kw['candidate'],source_version=7))
    def save(name,value):
        p=reg.parent/name;p.write_text(json.dumps(value));p.chmod(0o600);return p
    refs={key:str(save(key+'.json',{})) for key in ('candidate_path','registration_path')}
    from thermal_model.runtime_bundle import capture_runtime_bundle
    runtime_sources=reg.parent/'runtime-sources';runtime_sources.mkdir(mode=0o700)
    (runtime_sources/'thermal_model').mkdir(mode=0o700)
    for name in ('thermal_intel.py','thermal_model/origin_capture.py'):
        path=runtime_sources/name;path.write_text('# routing fixture only\n');path.chmod(0o600)
    archives=reg.parent/'runtime-archives';archives.mkdir(mode=0o700)
    refs['runtime_bundle_path']=str(capture_runtime_bundle(archives,runtime_sources,['thermal_intel.py']))
    pointer=save('release-inputs.json',dict(schema='earthship-installed-shade-release-inputs/v4',original_pairs_path=None,**refs))
    assert release.append_compressed_completed_queue(reference_path=pointer,queue_path=queue,output_directory=root,guard=verify)['status']=='index_updated'
    admitted=json.loads(Path(json.loads(pointer.read_text())['original_pairs_path']).read_text())
    assert admitted==[dict(raw_score_sources_path=collected['raw_packet_path'])]
    reg.write_text('{}')
    with pytest.raises(ValueError):verify()


def test_registry_guard_can_run_inside_parent_budget_callback_without_recursion(registration_case):
    from thermal_model.installed_shade_score_registration import resolve_registered_score_queue
    from thermal_model.replay_budget import shared_replay_budget,check_shared_budget
    reg,*_=registration_case
    _,verify=resolve_registered_score_queue(registration_path=reg,horizon_hours=24,guard=lambda:None)
    def remaining():verify();return 20
    with shared_replay_budget(remaining):check_shared_budget()


def test_resolver_preserves_expired_parent_refusal_before_metadata_read(registration_case):
    from thermal_model.installed_shade_score_registration import resolve_registered_score_queue
    from thermal_model.replay_budget import shared_replay_budget
    reg,*_=registration_case;remaining={'seconds':20}
    with shared_replay_budget(lambda:remaining['seconds']):
        remaining['seconds']=0
        with pytest.raises(ValueError):resolve_registered_score_queue(registration_path=reg,horizon_hours=1,guard=lambda:None)
