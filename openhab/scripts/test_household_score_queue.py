"""Missing measurements stay absent while later delivered jobs can be scored."""
from datetime import timedelta
from pathlib import Path
import importlib,json
import pytest
from test_provisional_thermal_live import fixture,module as live
from test_provisional_thermal_monitor import module as monitor
from test_installed_shade_origin import outcome


def api():return importlib.import_module('household_score_queue')


def native_packet(directory,target,assessed,phase,*,qualified=False,stream='indoor'):
    from thermal_model.temperature_history import POLICY
    from weather_temperature_evidence import TemperaturePolicy,MODELS
    from weather_temperature_receiver import TemperatureCollector
    from weather_temperature_sources import build_temperature_source,write_compressed_temperature_source
    policy=TemperaturePolicy('Fineoffset-WH32B',235,**POLICY);rows=[]
    if qualified:
        received=target-timedelta(seconds=30)
        collector=TemperatureCollector({'indoor':policy},sensor_epochs={'indoor':phase},clock=lambda:received,process_id=lambda:1,monotonic=lambda:1000.)
        collector.observe({'model':policy.model,'id':str(policy.sensor_id),MODELS[policy.model][1]:'70'})
        rows=[(target-timedelta(seconds=20),json.dumps(collector.snapshot()))]
    packet=build_temperature_source(rows=rows,targets=[target],assessed_at=assessed,stream=stream,policy=policy,sensor_epoch=phase)
    return write_compressed_temperature_source(directory,packet)


def setup_queue(tmp_path,monkeypatch):
    settings,backend,clock,candidate=fixture(tmp_path,monkeypatch)
    first=live().publish_cycle(settings,backend=backend,guard=lambda:None)
    first.update(json.loads(Path(first['delivery_path']).read_bytes()))
    clock[0]=monitor()._utc(first['issued_at'])+timedelta(minutes=5,seconds=-30)
    second=live().publish_cycle(settings,backend=backend,guard=lambda:None)
    second.update(json.loads(Path(second['delivery_path']).read_bytes()))
    clock[0]+=timedelta(hours=1,minutes=5)
    monkeypatch.setattr(monitor(),'_clock',lambda:clock[0])
    monkeypatch.setattr(monitor(),'_resource_preflight',lambda:None)
    monkeypatch.setattr(monitor(),'current_runtime',lambda:candidate['runtime'])
    monkeypatch.setattr(monitor(),'read_candidate',lambda *a,**kw:candidate)
    settings.update(native_db_config='synthetic',native_policy='synthetic',token_file='synthetic',openhab_base='http://127.0.0.1:8080/rest')
    target=monitor()._utc(first['issued_at'])+timedelta(hours=1)
    packets=tmp_path/'native-queries';packets.mkdir(mode=0o700)
    class Reader:
        native_source_paths=[]
        calls=[]
        def verify_unchanged(self):pass
        def publication(self,receipt):return receipt
        def native(self,targets,*,assessed_at,sensor_epoch):
            self.calls.extend(targets)
            if targets==[target]:
                self.native_source_paths=[str(native_packet(packets,target,assessed_at,sensor_epoch))]
            return [(at,None if at==target else outcome(at,75)) for at in targets]
    return settings,Reader(),clock,first,second,target


def test_gap_is_retained_without_score_and_next_invocation_scores_later_delivery(tmp_path,monkeypatch):
    settings,reader,clock,first,second,target=setup_queue(tmp_path,monkeypatch)
    result=api().score_jobs(settings,guard=lambda:None,reader=reader)
    assert result['status']=='monitoring_refreshed' and result['scored']==0
    assert result['pending_reason']=='mature_outcome_unavailable'
    assert len(reader.calls)==1 and reader.calls[0]==target
    gaps=list(Path(settings['evidence_directory']).glob('scores-*/*.provisional-gap-v1.json'))
    assert len(gaps)==1 and not list(Path(settings['evidence_directory']).glob('scores-*/*.provisional-completion-v1.json'))
    gap=json.loads(gaps[0].read_bytes());assert gap['target_at']==target.isoformat() and gap['automatic_actuation'] is False
    reader.calls=[]
    result=api().score_jobs(settings,guard=lambda:None,reader=reader)
    assert result['scored']==1 and target not in reader.calls
    pair=json.loads(next(Path(settings['evidence_directory']).glob('scores-*/*.provisional-pair-v1.json')).read_bytes())
    assert pair['capture_sha256']==second['capture_sha256']
    report=json.loads((Path(settings['evidence_directory'])/'latest-provisional-performance.json').read_bytes())
    assert report['by_horizon']['1']['model']['count']==1 and report['graduated'] is False


def test_gap_retry_uses_original_target_after_bounded_wait(tmp_path,monkeypatch):
    settings,reader,clock,_,_,target=setup_queue(tmp_path,monkeypatch)
    api().score_jobs(settings,guard=lambda:None,reader=reader)
    clock[0]+=timedelta(minutes=16);reader.calls=[]
    result=api().score_jobs(settings,guard=lambda:None,reader=reader)
    assert result['scored']==0 and reader.calls==[target]


def test_corrupt_gap_cannot_authorize_skipping_original_job(tmp_path,monkeypatch):
    settings,reader,_,_,_,_=setup_queue(tmp_path,monkeypatch)
    api().score_jobs(settings,guard=lambda:None,reader=reader)
    gap=next(Path(settings['evidence_directory']).glob('scores-*/*.provisional-gap-v1.json'));gap.write_text('{}');reader.calls=[]
    with pytest.raises((ValueError,KeyError)):api().score_jobs(settings,guard=lambda:None,reader=reader)
    assert reader.calls==[]


def test_missing_gap_original_cannot_authorize_skipping(tmp_path,monkeypatch):
    settings,reader,_,first,_,_=setup_queue(tmp_path,monkeypatch)
    api().score_jobs(settings,guard=lambda:None,reader=reader)
    Path(first['origin_path']).unlink();reader.calls=[]
    with pytest.raises((OSError,ValueError)):api().score_jobs(settings,guard=lambda:None,reader=reader)
    assert reader.calls==[]


def test_malformed_native_result_refuses_without_gap_record(tmp_path,monkeypatch):
    settings,reader,_,_,_,_=setup_queue(tmp_path,monkeypatch)
    reader.native=lambda *a,**kw:[]
    with pytest.raises(ValueError):api().score_jobs(settings,guard=lambda:None,reader=reader)
    assert not list(Path(settings['evidence_directory']).glob('scores-*/*.provisional-gap-v1.json'))


def test_publication_receipt_failure_remains_a_refusal(tmp_path,monkeypatch):
    settings,reader,_,_,_,_=setup_queue(tmp_path,monkeypatch)
    reader.publication=lambda *a,**kw:None
    with pytest.raises(ValueError):api().score_jobs(settings,guard=lambda:None,reader=reader)
    assert not list(Path(settings['evidence_directory']).glob('scores-*/*.provisional-gap-v1.json'))


def test_rehashed_gap_without_original_fingerprints_still_refuses(tmp_path,monkeypatch):
    settings,reader,_,_,_,_=setup_queue(tmp_path,monkeypatch)
    api().score_jobs(settings,guard=lambda:None,reader=reader)
    path=next(Path(settings['evidence_directory']).glob('scores-*/*.provisional-gap-v1.json'))
    value=json.loads(path.read_bytes());value['original_fingerprints']={}
    value['gap_sha256']=monitor().digest(value,'gap_sha256')
    replacement=path.parent/(value['job_id']+'-'+value['gap_sha256']+'.provisional-gap-v1.json')
    path.rename(replacement);replacement.write_text(json.dumps(value));reader.calls=[]
    with pytest.raises(ValueError):api().score_jobs(settings,guard=lambda:None,reader=reader)
    assert reader.calls==[]


def test_supported_outcome_pair_is_identical_to_original_scorer(tmp_path,monkeypatch):
    settings,reader,_,_,_,_=setup_queue(tmp_path,monkeypatch)
    reader.native=lambda targets,**kw:[(at,outcome(at,75)) for at in targets]
    monitor().score_jobs(settings,guard=lambda:None,reader=reader)
    root=Path(settings['evidence_directory']);path=next(root.glob('scores-*/*.provisional-pair-v1.json'))
    expected=path.read_bytes()
    path.unlink();next(root.glob('scores-*/*.provisional-completion-v1.json')).unlink()
    result=api().score_jobs(settings,guard=lambda:None,reader=reader)
    assert result['scored']==1 and next(root.glob('scores-*/*.provisional-pair-v1.json')).read_bytes()==expected


def test_score_coordinator_can_advance_gap_queue(tmp_path,monkeypatch):
    settings,reader,_,_,_,_=setup_queue(tmp_path,monkeypatch)
    from household_forecast_score import score_with_report
    monkeypatch.setattr(monitor(),'ScoreReader',lambda *a,**kw:reader)
    first=score_with_report(settings,guard=lambda:None,clock=monitor()._clock,queue=True)
    second=score_with_report(settings,guard=lambda:None,clock=monitor()._clock,queue=True)
    assert first['scored']==0 and second['scored']==1


@pytest.mark.parametrize('damage',['removed','qualified','target','assessment','epoch','stream'])
def test_rehashed_gap_requires_exact_absent_native_query(damage,tmp_path,monkeypatch):
    settings,reader,clock,first,_,target=setup_queue(tmp_path,monkeypatch)
    api().score_jobs(settings,guard=lambda:None,reader=reader)
    path=next(Path(settings['evidence_directory']).glob('scores-*/*.provisional-gap-v1.json'))
    value=json.loads(path.read_bytes());packet=Path(value['native_source_paths'][0])
    value['original_fingerprints'].pop(str(packet));value['native_source_paths']=[]
    if damage!='removed':
        capture=json.loads(Path(first['origin_path']).read_bytes());phase=capture['candidate']['fit']['sensor_epochs']['air']
        if damage=='epoch':phase=capture['candidate']['fit']['sensor_epochs']['mass']
        substitute=native_packet(packet.parent,target+timedelta(seconds=1) if damage=='target' else target,
            clock[0]+timedelta(seconds=1) if damage=='assessment' else clock[0],phase,
            qualified=damage=='qualified',stream='outdoor' if damage=='stream' else 'indoor')
        value['native_source_paths']=[str(substitute)];value['original_fingerprints'][str(substitute)]=monitor()._fingerprint(substitute)
    value['gap_sha256']=monitor().digest(value,'gap_sha256')
    replacement=path.parent/(value['job_id']+'-'+value['gap_sha256']+'.provisional-gap-v1.json')
    path.rename(replacement);replacement.write_text(json.dumps(value));reader.calls=[]
    with pytest.raises(ValueError):api().score_jobs(settings,guard=lambda:None,reader=reader)
    assert reader.calls==[]
