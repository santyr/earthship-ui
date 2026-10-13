"""Native monitor queue uses retained query sources; delivery lookup is synthetic."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
from pathlib import Path
import pytest
from thermal_model.forcing_capture import _canonical
from test_native_thermal_score_sources import queried,originals
from astro_geometry_series import replay_series
from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM


def setup(tmp_path,monkeypatch,originals,*,delivered=True,history='available'):
    import native_thermal_live as live
    import native_thermal_artifact as artifact
    import native_thermal_forecast as forecast
    args=queried(tmp_path,monkeypatch,originals,history=history)
    old=json.loads(Path(args['capture_path']).read_bytes());runtime=deepcopy(args['runtime'])
    runtime['native_source_manifest'][live.SOURCE]='d'*64;runtime['native_code_revision']=artifact.digest(runtime['native_source_manifest'])
    candidate=artifact.build_native_candidate(originals={role:Path(ref['path']) for role,ref in old['candidate']['originals'].items()},runtime=runtime,created_at=old['candidate']['created_at'])
    candidate_path=tmp_path/(candidate['artifact_sha256']+'.native-provisional-candidate-v2.json');candidate_path.write_bytes(_canonical(candidate));candidate_path.chmod(0o600)
    geometry=replay_series(_canonical(old['geometry']),request=old['geometry']['request'],expected_series_sha256=old['geometry_series_sha256'],expected_native_runtime=old['geometry']['native_runtime'])
    capture=forecast.build_capture(candidate,old['inputs'],geometry=geometry,runtime=runtime,expected_artifact_sha256=candidate['artifact_sha256'],expected_geometry_sha256=geometry.sha256,
        issue=old['issued_at'],available=old['inputs_available_at'],published=old['published_at'])
    root=tmp_path/'archive';root.mkdir(mode=0o700);issue=datetime.fromisoformat(capture['issued_at'])
    origins=root/('origins-'+issue.strftime('%Y%m%d'));origins.mkdir(mode=0o700)
    origin=forecast.persist(origins,capture)
    receipts=deepcopy(args['receipts'])
    receipts[NUMERIC_ITEM]['state']=_canonical(capture['output']).decode();receipts[PUBLICATION_ITEM]['state']=_canonical(forecast.publication(capture)).decode()
    d=dict(schema='earthship-provisional-thermal-delivery/v2',issued_at=capture['issued_at'],capture_path=str(origin),capture_sha256=capture['capture_sha256'],
        artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'],geometry_series_sha256=geometry.sha256,receipts=receipts)
    d['delivery_sha256']=forecast.digest(d,'delivery_sha256')
    if delivered:
        from thermal_model.provisional_forecast import persist
        persist(origins,d,field='delivery_sha256',suffix='.native-provisional-delivery-v2.json',maximum=65536)
    clock=[args['assessed_at']]
    monkeypatch.setattr(live,'_clock',lambda:clock[0]);monkeypatch.setattr(live,'current_runtime',lambda **kw:deepcopy(runtime));monkeypatch.setattr(live,'_resource_preflight',lambda:None)
    s=dict(schema=live.LIVE_SCHEMA,evidence_directory=str(root),candidate_path=str(candidate_path),artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'],native_cutover=(issue-timedelta(days=40)).isoformat())
    from weather_temperature_sources import read_compressed_temperature_source,replay_temperature_source
    packets={}
    for name in args['source_paths']:
        path=Path(name);packet=read_compressed_temperature_source(path.parent,path)
        key=(tuple(packet['targets']),packet['assessed_at']);packets[key]=(str(path),replay_temperature_source(packet))
    class Reader:
        def __init__(self):self.native_source_paths=[];self.publications=[];self.queries=[]
        def verify_unchanged(self):pass
        def publication(self,receipt):self.publications.append(deepcopy(receipt));return deepcopy(receipt)
        def native(self,targets,*,assessed_at,sensor_epoch):
            assert sensor_epoch==candidate['fit']['sensor_epochs']['air']
            key=(tuple(at.isoformat() for at in targets),assessed_at.isoformat());name,rows=packets[key]
            self.queries.append(key)
            if name not in self.native_source_paths:self.native_source_paths.append(name)
            return deepcopy(rows)
    return live,s,Reader(),clock,capture,d


def test_native_monitor_empty_archive_reports_no_qualified_errors(tmp_path,monkeypatch,originals):
    live,s,reader,clock,capture,d=setup(tmp_path,monkeypatch,originals,delivered=False)
    result=live.score_jobs(s,guard=lambda:None,reader=reader)
    assert result['status']=='waiting' and result['scored']==0
    report=json.loads((Path(s['evidence_directory'])/'latest-native-provisional-performance.json').read_bytes())
    assert set(report['by_horizon'])=={'1','6','12','24'} and report['graduated'] is False
    assert all(stat['count']==0 and stat['mae_f'] is None for row in report['by_horizon'].values() for stat in row.values())
    assert reader.publications==[] and reader.queries==[]


def test_native_monitor_scores_one_actual_source_packet_and_reconciles_completion(tmp_path,monkeypatch,originals):
    live,s,reader,clock,capture,d=setup(tmp_path,monkeypatch,originals)
    result=live.score_jobs(s,guard=lambda:None,reader=reader)
    assert result['status']=='scored' and result['scored']==1
    assert len(reader.publications)==2 and len(reader.queries)==8
    root=Path(s['evidence_directory']);scores=list(root.glob('scores-*/*.native-thermal-score-sources-v1.json'));completed=list(root.glob('scores-*/*.native-thermal-completion-v1.json'))
    assert len(scores)==len(completed)==1
    record=json.loads(scores[0].read_bytes());done=json.loads(completed[0].read_bytes());report=json.loads((root/'latest-native-provisional-performance.json').read_bytes())
    assert record['pair']['capture_sha256']==capture['capture_sha256'] and done['source_score_sha256']==record['source_score_sha256']
    assert report['by_horizon']['1']['model']['count']==1 and report['by_horizon']['1']['persistence']['mae_f']==1
    assert report['graduated'] is False and result['automatic_actuation'] is False


def test_native_missing_outcome_retains_absence_and_retries_after_fifteen_minutes(tmp_path,monkeypatch,originals):
    live,s,reader,clock,capture,d=setup(tmp_path,monkeypatch,originals)
    from test_household_score_queue import native_packet
    target=datetime.fromisoformat(capture['issued_at'])+timedelta(hours=1)
    packets=tmp_path/'missing';packets.mkdir(mode=0o700)
    path=native_packet(packets,target,clock[0],capture['candidate']['fit']['sensor_epochs']['air'])
    calls=[]
    def absent(targets,*,assessed_at,sensor_epoch):
        assert targets==[target];calls.append(assessed_at)
        reader.native_source_paths=[str(path)];return [(target,None)]
    reader.native=absent
    result=live.score_jobs(s,guard=lambda:None,reader=reader)
    assert result['status']=='monitoring_refreshed' and result['scored']==0
    assert result['pending_reason']=='mature_outcome_unavailable'
    gaps=list(Path(s['evidence_directory']).glob('scores-*/*.native-thermal-gap-v1.json'))
    assert len(gaps)==1 and not list(Path(s['evidence_directory']).glob('scores-*/*.native-thermal-completion-v1.json'))
    clock[0]+=timedelta(minutes=1)
    live.score_jobs(s,guard=lambda:None,reader=reader)
    assert len(calls)==1
    path.unlink()
    with pytest.raises((ValueError,OSError)):live.score_jobs(s,guard=lambda:None,reader=reader)


def test_native_queue_rechecks_both_real_publications_before_any_outcome_query(tmp_path,monkeypatch,originals):
    live,s,reader,clock,capture,d=setup(tmp_path,monkeypatch,originals)
    reader.publication=lambda receipt:dict(receipt,state='{}')
    with pytest.raises(ValueError,match='actual original native publication missing'):live.score_jobs(s,guard=lambda:None,reader=reader)
    assert reader.queries==[] and not list(Path(s['evidence_directory']).glob('scores-*/*.native-thermal-completion-v1.json'))


def test_native_completion_source_loss_refuses_report_instead_of_counting_cached_errors(tmp_path,monkeypatch,originals):
    live,s,reader,clock,capture,d=setup(tmp_path,monkeypatch,originals)
    live.score_jobs(s,guard=lambda:None,reader=reader)
    path=next(Path(s['evidence_directory']).glob('scores-*/*.native-thermal-score-sources-v1.json'));path.unlink()
    with pytest.raises((ValueError,OSError)):live.score_jobs(s,guard=lambda:None,reader=reader)
    assert not (Path(s['evidence_directory'])/'latest-native-provisional-performance.json').exists()


def test_native_full_thirty_one_cycle_absence_does_not_fabricate_recent_baseline(tmp_path,monkeypatch,originals):
    live,s,reader,clock,capture,d=setup(tmp_path,monkeypatch,originals,history='missing')
    result=live.score_jobs(s,guard=lambda:None,reader=reader)
    assert result['scored']==1 and len(reader.queries)==32
    report=json.loads((Path(s['evidence_directory'])/'latest-native-provisional-performance.json').read_bytes())
    assert report['by_horizon']['1']['recent_cycle']=={'count':0,'mae_f':None,'bias_f':None}
    assert report['by_horizon']['1']['model']['count']==1 and report['graduated'] is False


def test_native_active_model_precedes_an_earlier_other_revision(tmp_path,monkeypatch,originals):
    import native_thermal_artifact as artifacts
    import native_thermal_forecast as forecast
    from test_native_thermal_forecast import future
    from test_installed_shade_origin import native,weather,actions
    from thermal_model.provisional_forecast import persist
    live,s,reader,clock,capture,d=setup(tmp_path,monkeypatch,originals)
    other=artifacts.build_native_candidate(originals={role:Path(ref['path']) for role,ref in capture['candidate']['originals'].items()},
        runtime=capture['candidate']['runtime'],created_at=datetime.fromisoformat(capture['candidate']['created_at'])+timedelta(seconds=1))
    issue=datetime.fromisoformat(capture['issued_at'])-timedelta(minutes=5);current,proof=native(issue);geometry=future(issue)
    inputs=dict(forecast=weather(issue),current=current,origin_temperatures=proof,action_snapshot=actions(issue),native_source_paths={'mathematical':'source'})
    older=forecast.build_capture(other,inputs,geometry=geometry,runtime=other['runtime'],expected_artifact_sha256=other['artifact_sha256'],
        expected_geometry_sha256=geometry.sha256,issue=issue,available=issue,published=issue+timedelta(seconds=2))
    folder=Path(d['capture_path']).parent;origin=forecast.persist(folder,older)
    receipts={name:dict(item=name,time=int((issue+timedelta(seconds=3+i)).timestamp()*1000),state=_canonical(value).decode())
        for i,(name,value) in enumerate(((NUMERIC_ITEM,older['output']),(PUBLICATION_ITEM,forecast.publication(older))))}
    delivery=dict(schema='earthship-provisional-thermal-delivery/v2',issued_at=issue.isoformat(),capture_path=str(origin),capture_sha256=older['capture_sha256'],
        artifact_sha256=other['artifact_sha256'],runtime_sha256=other['runtime_sha256'],geometry_series_sha256=geometry.sha256,receipts=receipts)
    delivery['delivery_sha256']=forecast.digest(delivery,'delivery_sha256');persist(folder,delivery,field='delivery_sha256',suffix='.native-provisional-delivery-v2.json',maximum=65536)
    result=live.score_jobs(s,guard=lambda:None,reader=reader)
    assert result['scored']==1
    records=list(Path(s['evidence_directory']).glob('scores-*/*.native-thermal-score-sources-v1.json'))
    assert len(records)==1 and json.loads(records[0].read_bytes())['artifact_sha256']==s['artifact_sha256']


def test_native_absence_is_requeried_at_retry_time_without_completing_a_score(tmp_path,monkeypatch,originals):
    from test_household_score_queue import native_packet
    live,s,reader,clock,capture,d=setup(tmp_path,monkeypatch,originals)
    target=datetime.fromisoformat(capture['issued_at'])+timedelta(hours=1);folder=tmp_path/'retry';folder.mkdir(mode=0o700);queries=[]
    def missing(targets,*,assessed_at,sensor_epoch):
        assert targets==[target];queries.append(assessed_at)
        path=native_packet(folder,target,assessed_at,sensor_epoch)
        reader.native_source_paths=[str(path)];return [(target,None)]
    reader.native=missing
    live.score_jobs(s,guard=lambda:None,reader=reader);clock[0]+=timedelta(minutes=15)
    result=live.score_jobs(s,guard=lambda:None,reader=reader)
    assert len(queries)==2 and result['scored']==0 and result['status']=='monitoring_refreshed'
    assert len(list(Path(s['evidence_directory']).glob('scores-*/*.native-thermal-gap-v1.json')))==2
    assert not list(Path(s['evidence_directory']).glob('scores-*/*.native-thermal-completion-v1.json'))


def test_native_gap_cache_accepts_more_than_eight_hours_within_recent_queue_window(tmp_path,monkeypatch,originals):
    from test_household_score_queue import native_packet
    from thermal_model.provisional_live import _phase_directory
    from native_thermal_artifact import digest
    live,s,reader,clock,capture,d=setup(tmp_path,monkeypatch,originals)
    target=datetime.fromisoformat(capture['issued_at'])+timedelta(hours=1);packets=tmp_path/'long-gap';packets.mkdir(mode=0o700)
    job=digest({'capture_sha256':capture['capture_sha256'],'horizon_hours':1});delivery_path=Path(d['capture_path']).parent/(d['delivery_sha256']+'.native-provisional-delivery-v2.json')
    root=Path(s['evidence_directory']);base=clock[0]
    for i in range(48):
        assessed=base+timedelta(minutes=15*i);packet=native_packet(packets,target,assessed,capture['candidate']['fit']['sensor_epochs']['air'])
        folder=_phase_directory(root,'scores',assessed)
        live._retain_native_gap(folder,job,d,delivery_path,capture,horizon=1,target=target,now=assessed,paths=[str(packet)],guard=lambda:None)
    now=base+timedelta(minutes=15*47+1)
    assert live._native_gap_pending(root,now,job,d,delivery_path,capture,lambda:None) is True
