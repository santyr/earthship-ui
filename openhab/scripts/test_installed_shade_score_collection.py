"""Mature source-packet collection; fixtures never prove household release."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
from pathlib import Path
import pytest
from test_installed_shade_published_origin import issued,release_case,candidate
from test_installed_shade_origin import outcome
from thermal_model.forcing_capture import _canonical
from thermal_model.installed_shade_artifact import _digest


def module():
    from thermal_model import installed_shade_score_collection
    return installed_shade_score_collection


class Backend:
    def __init__(self,record,damage=None):self.record=record;self.damage=damage;self.calls=[]
    def verify_unchanged(self):
        if self.damage=='configuration':raise ValueError('synthetic drift')
    def publication(self,receipt):
        self.calls.append(('publication',receipt['item']))
        actual=deepcopy(receipt)
        if self.damage=='publication':actual['time']+=1
        return actual
    def native(self,targets,*,assessed_at,sensor_epoch):
        self.calls.append(('native',targets,assessed_at,sensor_epoch))
        issue=datetime.fromisoformat(self.record['numeric_capture']['issued_at'])
        if targets[0]>=issue:
            receipt=outcome(targets[0],73.)
            if self.damage=='phase':receipt['sensorEpoch']='33333333-99ee-4b7a-b5fc-e6a96e7274d8'
            if self.damage=='late':receipt['storedAt']=(targets[0]+timedelta(seconds=1)).isoformat()
            return [[targets[0],None if self.damage=='outcome' else receipt]]
        return [[at,None if self.damage=='history' else outcome(at,74.)] for at in targets]


@pytest.fixture
def collection(issued,tmp_path,monkeypatch):
    from thermal_model.installed_shade_published_origin import write_publication_capture
    m=module();record=issued[0];root=tmp_path/'collect';root.mkdir(mode=0o700)
    path=write_publication_capture(root,record)
    # The real publisher retains this owned lock in its source archive.
    (root/'.installed-shade-live.lock').touch(mode=0o600)
    issue=datetime.fromisoformat(record['numeric_capture']['issued_at'])
    monkeypatch.setattr(m,'_clock',lambda:issue+timedelta(hours=24,minutes=10))
    return m,root,path,record,issue


@pytest.mark.parametrize('hours',[1,6,12,24])
def test_collected_sources_replay_exact_publication_and_native_baselines(collection,hours,monkeypatch):
    from thermal_model.installed_shade_qualification import _score_packets
    m,root,path,record,issue=collection;backend=Backend(record)
    monkeypatch.setattr(m,'ERRORS',())  # Surface failures in the positive math fixture.
    result=m.collect_published_score(origin_path=path,horizon_hours=hours,output_directory=root,backend=backend)
    assert result['status']=='scored' and result['release_authorized'] is False
    packets=json.loads(Path(result['packet_path']).read_text());score=json.loads(Path(result['score_path']).read_text())
    assert len(packets)==1 and packets[0]['publication']==record['publication']
    assert score['schema']=='earthship-installed-shade-source-scored-pair/v3'
    assert packets[0]['outcome']['receipt']['temperatureF']==73.
    assert score['scored_pair']['persistence_error_f']==pytest.approx(1.)
    assert score['scored_pair']['recent_cycle_error_f']==pytest.approx(1.)
    assert score['scored_pair']['model_error_f']==pytest.approx(record['numeric_capture']['output']['trajectory'][hours-1]['air_f']-73.)
    replay=_score_packets(packets,assessed_at=issue+timedelta(hours=24,minutes=10),version=3)
    assert replay['rows']==[score['scored_pair']]
    assert [row for row in backend.calls if row[0]=='publication']==[('publication','Thermal_OriginalForecast_JSON'),('publication','Thermal_Model_JSON')]
    historic=[row for row in backend.calls if row[0]=='native' and row[1][0]<issue]
    assert len(historic)==7 and all(row[2]==issue for row in historic)
    assert all(at<issue for row in historic for at in row[1])
    numeric=json.loads(Path(result['numeric_packet_path']).read_text())
    assert numeric[0]['publication']=={k:v for k,v in record['numeric_publication'].items() if k!='item'}
    assert numeric[0]['origin_path'].endswith('.installed-shade-origin-v2.json')
    for key in ('packet_path','score_path','numeric_packet_path'):
        member=Path(result[key]);assert member.stat().st_mode&0o777==0o600
        assert member.name.startswith(_digest(json.loads(member.read_text())))


@pytest.mark.parametrize('damage',['publication','outcome','phase','late','history','configuration'])
def test_unqualified_sources_never_become_retained_score_packets(collection,damage):
    m,root,path,record,_=collection;before=set(root.iterdir())
    result=m.collect_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=Backend(record,damage))
    assert result['status']=='withheld' and result['release_authorized'] is False
    assert set(root.iterdir())==before


def test_immature_target_performs_no_source_queries_or_retention(collection,monkeypatch):
    m,root,path,record,issue=collection;backend=Backend(record);before=set(root.iterdir())
    monkeypatch.setattr(m,'_clock',lambda:issue+timedelta(hours=1,minutes=4))
    result=m.collect_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='pending' and backend.calls==[] and set(root.iterdir())==before


def test_repeating_the_same_mature_collection_preserves_immutable_source_addresses(collection):
    m,root,path,record,_=collection;backend=Backend(record)
    first=m.collect_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    before={p.name:p.read_bytes() for p in root.iterdir()}
    again=m.collect_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=Backend(record))
    assert again==first and {p.name:p.read_bytes() for p in root.iterdir()}==before


def test_configuration_drift_after_outcome_read_retains_no_packet(collection):
    m,root,path,record,issue=collection;before=set(root.iterdir())
    class DriftBackend(Backend):
        changed=False
        def native(self,targets,**values):
            result=super().native(targets,**values)
            if targets[0]>=issue:self.changed=True
            return result
        def verify_unchanged(self):
            if self.changed:raise ValueError('synthetic late source drift')
    result=m.collect_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=DriftBackend(record))
    assert result['status']=='withheld' and set(root.iterdir())==before



def test_collector_does_not_compete_with_live_publisher_lock(collection):
    import fcntl,os
    m,root,path,record,_=collection;backend=Backend(record);before=set(root.iterdir())
    fd=os.open(root/'.installed-shade-live.lock',os.O_RDWR)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=m.collect_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
        assert result['status']=='busy' and backend.calls==[] and set(root.iterdir())==before
    finally:os.close(fd)


def test_uncalibrated_main_capture_retains_numeric_sources_for_explicit_calibration_api(collection,monkeypatch):
    from thermal_model import installed_shade_calibrated_origin as calibrated
    from thermal_model import installed_shade_origin as base
    from thermal_model import installed_shade_publication as publisher
    from thermal_model import installed_shade_published_origin as published
    from thermal_model import installed_shade_qualification as q
    m,root,_,record,issue=collection;numeric=calibrated._core_view(record['numeric_capture'])
    raw_path=base.write_issued_capture(root,numeric)
    report=q.qualify_installed_shade_candidate(registration_path=None,candidate_path=None,runtime_bundle_path=None,original_pairs=[],now=issue)
    ready=publisher.PreparedInstalledQualification(_canonical(report),_canonical(numeric['candidate']),True,True,
        ('thermal_intel.py','thermal_model/installed_shade_publication.py'))
    monkeypatch.setattr(publisher,'_clock',lambda:issue+timedelta(seconds=3))
    monkeypatch.setattr(publisher,'ERRORS',())
    # The embedded base runtime differs from the later calibrated runtime.
    # Bind only the synthetic executing-runtime port to that original base.
    monkeypatch.setattr(publisher,'build_runtime_binding',lambda *args:numeric['runtime'])
    output=publisher.build_installed_publication(raw_path,ready);assert output['status']=='shadow'
    actual=dict(item='Thermal_Model_JSON',time=int((issue+timedelta(seconds=3)).timestamp()*1000),state=_canonical(output).decode())
    original=dict(item='Thermal_OriginalForecast_JSON',time=int((issue+timedelta(seconds=2)).timestamp()*1000),state=_canonical(numeric['output']).decode())
    monkeypatch.setattr(published,'_clock',lambda:issue+timedelta(seconds=4))
    uncalibrated=published.build_publication_capture(raw_path,numeric_publication=original,publication=actual)
    path=published.write_publication_capture(root,uncalibrated)
    result=m.collect_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=Backend(uncalibrated))
    assert result['status']=='scored'
    packets=json.loads(Path(result['numeric_packet_path']).read_text())
    replay=q._score_packets(packets,assessed_at=issue+timedelta(hours=24,minutes=10),version=1)
    assert replay['calibrated_intervals'] is False and replay['rows'][0]['interval_width_f'] is None
    assert packets[0]['origin_path'].endswith('.installed-shade-origin-v1.json')


class RawBackend(Backend):
    """Transport fixture emits whole native packets, not fabricated receipts."""
    def __init__(self,record,root):
        super().__init__(record);self.root=root;self.native_source_paths=[];self.raw_rows={}
    def native(self,targets,*,assessed_at,sensor_epoch):
        from weather_temperature_evidence import TemperaturePolicy,MODELS
        from weather_temperature_receiver import TemperatureCollector
        from weather_temperature_sources import build_temperature_source,write_temperature_source,replay_temperature_source
        from thermal_model.temperature_history import POLICY
        issue=datetime.fromisoformat(self.record['numeric_capture']['issued_at'])
        policy=TemperaturePolicy('Fineoffset-WH32B',235,**POLICY);clock={'at':targets[0]-timedelta(seconds=30),'tick':1000}
        source=TemperatureCollector({'indoor':policy},sensor_epochs={'indoor':sensor_epoch},clock=lambda:clock['at'],monotonic=lambda:clock['tick'],process_id=lambda:1)
        raw=[]
        for i,at in enumerate(targets):
            clock.update(at=at-timedelta(seconds=30),tick=1000+i*86400)
            source.observe({'model':policy.model,'id':str(policy.sensor_id),MODELS[policy.model][1]:'73' if at>=issue else '74'})
            if at not in self.raw_rows:self.raw_rows[at]=(at-timedelta(seconds=20),json.dumps(source.snapshot()))
            raw.append(self.raw_rows[at])
        packet=build_temperature_source(rows=raw,targets=targets,assessed_at=assessed_at,stream='indoor',policy=policy,sensor_epoch=sensor_epoch)
        path=write_temperature_source(self.root,packet);self.native_source_paths.append(str(path))
        return replay_temperature_source(packet)


@pytest.mark.parametrize('hours',[1,24])
def test_collector_binds_raw_query_packets_to_exact_score_inputs(collection,hours,monkeypatch):
    m,root,path,record,issue=collection;backend=RawBackend(record,root)
    monkeypatch.setattr(m,'ERRORS',())
    result=m.collect_published_score(origin_path=path,horizon_hours=hours,output_directory=root,backend=backend)
    assert result['status']=='scored'
    assert 'raw_packet_path' in result,'collector did not retain typed raw source binding'
    from thermal_model.installed_shade_raw_score_sources import replay_native_score_binding
    raw=json.loads(Path(result['raw_packet_path']).read_text())
    assert raw['schema']=='earthship-installed-shade-score-sources/v2'
    assert raw['release_authority'] is False
    phase=record['numeric_capture']['source_epochs']['air']
    replay_native_score_binding(raw['native_binding'],raw['score_sources'],issue_at=issue,sensor_epoch=phase,assessed_at=issue+timedelta(hours=24,minutes=10))
    assert len(raw['native_binding']['query_sources'])==8


def test_raw_score_reader_recomputes_score_and_refuses_lost_raw_source(collection):
    m,root,path,record,issue=collection;backend=RawBackend(record,root)
    result=m.collect_published_score(origin_path=path,horizon_hours=1,output_directory=root,backend=backend)
    assert result['status']=='scored'
    from thermal_model import installed_shade_raw_score_sources as raw
    assert hasattr(raw,'read_raw_score_sources'),'missing independent raw score reader'
    replay=raw.read_raw_score_sources(Path(result['raw_packet_path']),assessed_at=issue+timedelta(hours=24,minutes=10))
    assert replay['score']==json.loads(Path(result['score_path']).read_text())
    Path(backend.native_source_paths[0]).unlink()
    with pytest.raises((ValueError,OSError)):
        raw.read_raw_score_sources(Path(result['raw_packet_path']),assessed_at=issue+timedelta(hours=24,minutes=10))
