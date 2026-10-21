"""Actual publication decisions stay separate from retrospective daily issues."""
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import pytest
from learning_fixtures import T,SITE,full_snapshot
from weather_learning.archive import Archive
from weather_learning.contracts import canonical,identity


def api():
    assert importlib.util.find_spec('weather_learning.refresh_evaluation'), 'Task6 original publication evaluator missing'
    from weather_learning import refresh_evaluation
    return refresh_evaluation


@pytest.fixture
def sources(tmp_path):
    archive=Archive(tmp_path/'archive')
    full=archive.store_snapshot(full_snapshot(hours=360))
    short=full_snapshot(T+timedelta(hours=2),hours=48,temperature_k=293.15)
    short.update(first_seen_at=(T+timedelta(hours=9,minutes=30)).isoformat(),
                 ingestion_completed_at=(T+timedelta(hours=10)).isoformat())
    interim=archive.store_snapshot(short)
    return archive,full,interim,T+timedelta(hours=10,minutes=30)


def publication(tmp_path,sources):
    from test_production_runtime import LocalOpenHAB
    from openhab_runtime_io import ReadBudget
    from weather_learning.production_runtime import ProductionTransport,run_publication
    archive,_,_,now=sources
    elapsed=[0.]
    def advance(seconds):elapsed[0]+=seconds
    server=LocalOpenHAB()
    transport=ProductionTransport(base='http://127.0.0.1:8080/rest',token_reader=lambda:'synthetic',
        budget=ReadBudget(85,clock=lambda:elapsed[0],sleeper=advance,max_requests=96),opener=server.open)
    root=tmp_path/'publications';root.mkdir(mode=0o700)
    lock=tmp_path/'lock';lock.write_bytes(b'');lock.chmod(0o600)
    result=run_publication(archive=Archive.open_readonly(archive.root),site=SITE,evidence_directory=root,
        shared_lock=lock,code_revision='a'*40,transport=transport,authorize=lambda provider:True,
        guard=lambda:None,clock=lambda:now+timedelta(seconds=elapsed[0]))
    return json.loads(Path(result['attempt_path']).read_bytes()),json.loads(Path(result['result_path']).read_bytes())


def reseal(value,key):
    value[key]=identity({k:v for k,v in value.items() if k!=key})
    return value


def test_delayed_interim_remaining_coverage_and_full_range_are_independent(sources):
    archive,full,short,now=sources
    value=api().refresh_profiles(archive,decision_at=now,site=SITE).to_dict()
    near=value['profiles']['latest_48h_collection']
    assert near['source']['snapshot_sha256']==short
    assert near['source']['availability_lag_hours']==8
    assert near['source']['initialization_age_hours']==8.5
    assert near['source']['remaining_native_hours']==39.5
    assert near['served_hours']==25  # ceil requested endpoint, not 48h beyond arrival
    assert value['profiles']['latest_360h_collection']['source']['snapshot_sha256']==full
    assert near['hours'][0]['raw_c']==20
    assert value['profiles']['latest_360h_collection']['hours'][0]['raw_c']==10
    assert value['probability_claim'] is False


def test_later_fetch_cannot_rewrite_past_refresh_selection(sources):
    archive,_,short,now=sources
    newer=full_snapshot(T+timedelta(hours=4),hours=48,temperature_k=303.15)
    newer.update(first_seen_at=(now+timedelta(seconds=1)).isoformat(),
                 ingestion_completed_at=(now+timedelta(seconds=2)).isoformat())
    archive.store_snapshot(newer)
    value=api().refresh_profiles(archive,decision_at=now,site=SITE).to_dict()
    assert value['profiles']['latest_48h_collection']['source']['snapshot_sha256']==short


def test_missing_internal_hour_does_not_pass_complete_near_profile(sources):
    archive,_,_,now=sources
    original=full_snapshot(T+timedelta(hours=4),hours=48,temperature_k=303.15)
    # A missing mean can be represented honestly in the original provider capsule.
    source=original['source_originals'][0]
    source['payload']['region'][20][4]=None
    from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
    from weather_learning.contracts import instant
    parts=[]
    for item in original['source_originals']:
        raw=item['payload']
        parts.append(parse_collection_response(raw,collection=item['collection'],bands=raw['region'][0][4:],site=SITE,initialized_at=instant(original['initialized_at']),horizon=48))
    archive.store_snapshot(make_snapshot(parts,site=SITE,initialized_at=instant(original['initialized_at']),
        first_seen_at=instant(original['first_seen_at']),completed_at=instant(original['ingestion_completed_at'])))
    value=api().refresh_profiles(archive,decision_at=now,site=SITE).to_dict()
    assert value['profiles']['latest_48h_collection']['source']['snapshot_sha256']==sources[2]


def test_real_publication_adapter_replays_served_composite_not_daily_population(tmp_path,sources):
    attempt,result=publication(tmp_path,sources)
    value=api().publication_decision(attempt,result,archive=sources[0],site=SITE).to_dict()
    assert value['population']=='actual_publication_decisions_v1'
    assert value['attempt_sha256']==attempt['attempt_sha256']
    assert value['result_sha256']==result['result_sha256']
    assert value['profiles']['near_term']['source']['snapshot_sha256']==sources[2]
    assert value['profiles']['extended']['source']['snapshot_sha256']==sources[1]
    assert value['hours'][0]['raw_c']==20
    assert value['hours'][25]['raw_c']==10
    assert value['hours'][0]['profile']=='near_term'
    assert value['hours'][25]['profile']=='extended'
    assert value['prospective_score'] is True
    assert value['automatic_actuation'] is False


def test_rehashed_published_temperature_must_match_original_forecast(tmp_path,sources):
    attempt,result=publication(tmp_path,sources)
    profile=attempt['provider']['near_term']
    profile['hours'][0]['temp_f']+=9
    reseal(profile,'provider_snapshot_sha256');reseal(attempt['provider'],'provider_snapshot_sha256')
    # Consistent fresh public state hashes still do not replace original Google data.
    from weather_learning.provider import _freeze
    from weather_learning.production_publish import production_states
    body=dict(attempt['provider']);body.pop('provider_snapshot_sha256')
    attempt['states']=production_states(_freeze(body),now=sources[3])
    attempt['states_sha256']=identity(attempt['states']);reseal(attempt,'attempt_sha256')
    result['attempt_sha256']=attempt['attempt_sha256']
    result['publication']['provider_snapshot_sha256']=attempt['provider']['provider_snapshot_sha256']
    result['publication']['states_sha256']=attempt['states_sha256']
    reseal(result['publication'],'result_sha256');reseal(result,'result_sha256')
    with pytest.raises(ValueError,match='original'):
        api().publication_decision(attempt,result,archive=sources[0],site=SITE)


def test_failed_or_unconfirmed_publication_is_not_scored_as_served(tmp_path,sources):
    attempt,result=publication(tmp_path,sources)
    result['status']='FAILED';reseal(result,'result_sha256')
    with pytest.raises(ValueError,match='published'):
        api().publication_decision(attempt,result,archive=sources[0],site=SITE)


def test_publication_originals_and_returned_evidence_are_immutable(tmp_path,sources):
    attempt,result=publication(tmp_path,sources);before=canonical([attempt,result])
    record=api().publication_decision(attempt,result,archive=sources[0],site=SITE)
    value=record.to_dict();value['hours'][0]['raw_c']=999
    assert record.to_dict()['hours'][0]['raw_c']==20
    assert canonical([attempt,result])==before
    with pytest.raises(AttributeError):record.hours=[]


def test_wrong_site_or_index_availability_cannot_enter_refresh_population(sources):
    archive,_,_,now=sources
    with archive._connect() as db:
        db.execute('UPDATE snapshots SET completed=? WHERE digest=?',((now-timedelta(seconds=1)).isoformat(),sources[2]))
    with pytest.raises(ValueError,match='index'):
        api().refresh_profiles(archive,decision_at=now,site=SITE)


def test_later_archive_object_cannot_change_recorded_published_selection(tmp_path,sources):
    attempt,result=publication(tmp_path,sources)
    record=api().publication_decision(attempt,result,archive=sources[0],site=SITE).to_dict()
    newer=full_snapshot(T+timedelta(hours=4),hours=48,temperature_k=303.15)
    newer.update(first_seen_at=(sources[3]+timedelta(seconds=1)).isoformat(),
                 ingestion_completed_at=(sources[3]+timedelta(seconds=2)).isoformat())
    sources[0].store_snapshot(newer)
    assert api().publication_decision(attempt,result,archive=sources[0],site=SITE).to_dict()==record


def test_published_record_requires_every_confirmed_item_readback(tmp_path,sources):
    attempt,result=publication(tmp_path,sources)
    result['publication']['verified_items'].pop()
    reseal(result['publication'],'result_sha256');reseal(result,'result_sha256')
    with pytest.raises(ValueError,match='readbacks'):
        api().publication_decision(attempt,result,archive=sources[0],site=SITE)
