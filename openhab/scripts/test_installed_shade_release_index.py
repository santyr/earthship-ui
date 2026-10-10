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
    paths={k:save(k+'.json',{}) for k in ('registration_path','candidate_path','runtime_bundle_path')}
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


def test_scorer_explicit_index_update_uses_shared_lock_and_grants_no_release(monkeypatch,tmp_path,capsys):
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
        kw['guard']();calls.append((kw['reference_path'],kw['additional_pairs_path']))
        return dict(status='index_updated',release_authorized=False)
    monkeypatch.setattr(index,'append_compressed_release_sources',append)
    args=['--config',str(tmp_path/'config'),'--contract-version','4','--update-release-index',
        '--release-reference',str(tmp_path/'reference'),'--additional-pairs',str(tmp_path/'new'),'--shared-lock',str(tmp_path/'lock')]
    assert cli.main(args)==0
    assert calls==['preflight','headroom',(tmp_path/'reference',tmp_path/'new')]
    assert json.loads(capsys.readouterr().out)==dict(status='index_updated',release_authorized=False)

@pytest.mark.parametrize('lose_source',[False,True])
def test_index_retention_replays_actual_compressed_issue_and_outcome_originals(index_case,source_origin_case,tmp_path,monkeypatch,lose_source):
    from thermal_model import installed_shade_qualification as q,installed_shade_release_index as m
    from test_installed_shade_raw_publication_capture import compressed_calibrated_archive_case
    _,_,args,now,_,result=compressed_calibrated_archive_case(source_origin_case,tmp_path,monkeypatch)
    ref,extra,index,_,_,_=index_case
    refs=[dict(raw_score_sources_path=result['raw_packet_path'])]
    extra.write_text(json.dumps(refs));index.write_text('[]')
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
        with pytest.raises((ValueError,OSError)):m.append_compressed_release_sources(reference_path=ref,additional_pairs_path=extra,guard=lambda:None)
        assert ref.read_bytes()==before
    else:
        assert m.append_compressed_release_sources(reference_path=ref,additional_pairs_path=extra,guard=lambda:None)['status']=='index_updated'
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
