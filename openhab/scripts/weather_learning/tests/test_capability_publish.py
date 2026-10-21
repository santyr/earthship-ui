"""Retained raw quantiles reach a separate product without legacy reinterpretation."""
from copy import deepcopy
from datetime import timedelta
import importlib,json
import pytest
from learning_fixtures import T,SITE,native_snapshot,full_snapshot
from weather_learning.archive import Archive
from weather_learning.contracts import canonical,identity

def api():return importlib.import_module('weather_learning.capability_publish')

def archived(tmp_path,snapshot):
    path=tmp_path/'archive';a=Archive(path);a.store_snapshot(snapshot);return a

def report(a):return api().build_capability_report(a,decision=T+timedelta(minutes=30),site=SITE,horizons=(3,))

def test_retained_temperature_statistics_preserve_mean_range_source_and_no_median(tmp_path):
    snapshot=native_snapshot(mean_c=0,hours=6);before=deepcopy(snapshot)
    value=report(archived(tmp_path,snapshot));temperature=value['groups']['temperature']
    assert value['schema']=='earthship-weathernext-capabilities/v1'
    assert temperature['local_coverage_qualified'] is False
    assert temperature['label']=='WeatherNext p10–p90; local coverage not yet verified'
    first=temperature['hours'][0]
    assert first['mean_c']==0 and first['p10_c']==-2 and first['p90_c']==2
    assert first['p50_c'] is None and first['range_status']=='available'
    source=value['sources'][0]
    assert source['available_at']==snapshot['ingestion_completed_at']
    assert source['initialized_at']==T.isoformat()
    assert value['automatic_actuation'] is False and value['release_authorized'] is False
    assert snapshot==before
    assert not any(s in json.dumps(value) for s in ['latitude','longitude','source_originals','/home/','credential'])
    assert api().validate_capability_report(value)==value

def test_mean_only_source_keeps_deterministic_information_when_range_missing(tmp_path):
    value=report(archived(tmp_path,full_snapshot(hours=6)))
    first=value['groups']['temperature']['hours'][0]
    assert first['mean_c']==10 and first['p10_c'] is None
    assert first['range_status']=='missing_quantiles'
    assert value['status']=='available'

def test_crossing_quantiles_withhold_only_range_and_retain_original_mean(tmp_path):
    snapshot=native_snapshot(hours=6)
    original=snapshot['source_originals'][0];index=original['payload']['region'][0].index('station_head_temperature_2m_p10')
    for row in original['payload']['region'][1:]:row[index]=300
    from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
    collections=[parse_collection_response(original['payload'],collection=original['collection'],bands=original['payload']['region'][0][4:],site=SITE,initialized_at=T,horizon=6)]
    snapshot=make_snapshot(collections,site=SITE,initialized_at=T,first_seen_at=T+timedelta(minutes=20),completed_at=T+timedelta(minutes=21))
    value=report(archived(tmp_path,snapshot));first=value['groups']['temperature']['hours'][0]
    assert first['mean_c']==10 and first['range_status']=='crossing_quantiles'
    assert first['p10_c'] is None and first['p90_c'] is None
    assert snapshot['source_originals'][0]['payload']['region'][1][index]==300

def test_unavailable_source_never_runs_a_fetch_or_reuses_expired_range(tmp_path):
    a=archived(tmp_path,native_snapshot(hours=48))
    unavailable=api().build_capability_report(a,decision=T+timedelta(hours=25),site=SITE,horizons=(3,))
    assert unavailable['status']=='unavailable' and unavailable['groups']['temperature']['hours']==[]
    current=report(a)
    with pytest.raises(ValueError):api().validate_capability_report(current,now=T+timedelta(hours=3))

def test_supplemental_publication_retains_original_issued_values_for_later_scoring(tmp_path):
    a=archived(tmp_path,native_snapshot(hours=6));cache=tmp_path/'cache';cache.mkdir(mode=0o700)
    value=report(a);api().retain_capability_report(cache,value)
    name=value['report_sha256'];original=(cache/'capability-issues'/(name+'.json')).read_bytes()
    changed=deepcopy(value);changed['groups']['temperature']['hours'][0]['mean_c']=99
    with pytest.raises(ValueError):api().retain_capability_report(cache,changed)
    assert (cache/'capability-issues'/(name+'.json')).read_bytes()==original
    assert json.loads((cache/'weather-capabilities.json').read_bytes())==value

def test_current_ui_payload_parser_remains_a_separate_legacy_contract(tmp_path):
    from weather_learning.provider import load_production_forecast,forecast_payloads
    a=archived(tmp_path,full_snapshot(hours=8))
    before=forecast_payloads(load_production_forecast(a,decision_at=T+timedelta(minutes=30),required_horizon=timedelta(hours=3),site=SITE),now=T+timedelta(minutes=30))
    report(a)
    after=forecast_payloads(load_production_forecast(a,decision_at=T+timedelta(minutes=30),required_horizon=timedelta(hours=3),site=SITE),now=T+timedelta(minutes=30))
    assert canonical(before)==canonical(after)

def test_report_refresh_cannot_extend_the_original_source_lifetime(tmp_path):
    value=report(archived(tmp_path,native_snapshot(hours=6)))
    source=value['sources'][0];old=T-timedelta(hours=23)
    source.update(initialized_at=old.isoformat(),run_id='ee:'+old.isoformat(),
        first_seen_at=(old+timedelta(minutes=20)).isoformat(),available_at=(old+timedelta(minutes=21)).isoformat())
    value['report_sha256']=identity({k:v for k,v in value.items() if k!='report_sha256'})
    with pytest.raises(ValueError):api().validate_capability_report(value)

def test_global_deadline_is_not_downgraded_to_optional_missing_source():
    class ExpiredArchive:
        def eligible_snapshot(self,*a,**kw):raise TimeoutError('shared deadline')
    with pytest.raises(TimeoutError):report(ExpiredArchive())

def test_staging_worker_prepares_without_creating_state_and_only_explicit_apply_retains(tmp_path):
    a=archived(tmp_path,native_snapshot(hours=30));path=tmp_path/'separate-shadow'
    worker=importlib.import_module('weather_learning.capability_worker')
    prepared=worker.publish_capabilities(a.root,path,decision=T+timedelta(minutes=30),site=SITE,horizons=(3,),apply=False)
    assert prepared['retained'] is False and not path.exists()
    applied=worker.publish_capabilities(a.root,path,decision=T+timedelta(minutes=30),site=SITE,horizons=(3,),apply=True)
    assert applied['retained'] is True
    assert applied['report_sha256']==prepared['report_sha256']
    assert (path/'capability-scores.sqlite3').exists()
    assert json.loads((path/'weather-capabilities.json').read_text())['status']=='available'

def test_capability_originals_consume_the_existing_shared_shadow_byte_cap(tmp_path):
    from weather_learning.shadow import ShadowStore
    state=ShadowStore(tmp_path/'shadow');directory=state.root/'capability-issues';directory.mkdir(mode=0o700)
    # Sparse retained file exercises cumulative metadata accounting without
    # allocating two GiB or changing the production cap.
    with (directory/'retained.json').open('wb') as stream:stream.truncate(2*1024**3)
    with pytest.raises(ValueError,match='capacity'):
        state._write(state.root/'weather-capabilities.json',dict(status='available'))
    assert not (state.root/'weather-capabilities.json').exists()

@pytest.mark.parametrize('run',['private:/operator-secret','ee:2025-12-31T18:00:00+00:00'])
def test_public_run_reference_must_match_a_known_native_run_and_initialization(tmp_path,run):
    value=report(archived(tmp_path,native_snapshot(hours=6)))
    value['sources'][0]['run_id']=run
    value['report_sha256']=identity({k:v for k,v in value.items() if k!='report_sha256'})
    with pytest.raises(ValueError):api().validate_capability_report(value)

def test_actual_retained_median_is_preserved_independently_of_the_mean(tmp_path):
    from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
    snapshot=native_snapshot(hours=6);original=deepcopy(snapshot['source_originals'][0]);raw=original['payload']
    raw['region'][0].append('station_head_temperature_2m_p50')
    for row in raw['region'][1:]:row.append(282.15)
    parsed=parse_collection_response(raw,collection=original['collection'],bands=raw['region'][0][4:],site=SITE,initialized_at=T,horizon=6)
    snapshot=make_snapshot([parsed],site=SITE,initialized_at=T,first_seen_at=T+timedelta(minutes=20),completed_at=T+timedelta(minutes=21))
    value=report(archived(tmp_path,snapshot));hour=value['groups']['temperature']['hours'][0]
    assert hour['p50_c']==9 and hour['mean_c']==10

def test_extended_optional_failure_leaves_the_available_near_source_publishable(tmp_path):
    a=archived(tmp_path,native_snapshot(hours=30))
    class PartialArchive:
        def eligible_snapshot(self,decision,end,**kwargs):
            if end>decision+timedelta(hours=48):raise ValueError('extended optional segment')
            return a.eligible_snapshot(decision,end,**kwargs)
    value=api().build_capability_report(PartialArchive(),decision=T+timedelta(minutes=30),site=SITE)
    assert value['status']=='available' and len(value['sources'])==1
    assert len(value['groups']['temperature']['hours'])==25
