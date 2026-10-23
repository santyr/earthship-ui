"""Optional near24 preparation/retention never changes the core publication."""
from datetime import timedelta
from pathlib import Path
import importlib.util,json
import pytest
from test_near_term_correction import context
from test_production_runtime import LocalOpenHAB
from learning_fixtures import SITE
from weather_learning.archive import Archive
from weather_learning.contracts import instant
from weather_learning.provider import load_publication_forecast
from weather_learning.production_runtime import ProductionTransport,run_publication
from openhab_runtime_io import ReadBudget


def runtime(context,tmp_path):
    assert importlib.util.find_spec('weather_learning.refresh_runtime'), 'Task6 prospective near24 runtime missing'
    from weather_learning.refresh_runtime import RefreshRuntime
    args,_,_=context
    return RefreshRuntime(state_root=tmp_path/'runtime-state',archive=args['archive'],site=SITE,sensor_epoch=args['sensor_epoch'],
        selection_path=args['selection_path'],origin_metadata=args['origin_metadata'],origin_acquired_at=args['origin_acquired_at'],clock=lambda:args['decision_at']+timedelta(seconds=60))


def publish(context,tmp_path,**kwargs):
    args,_,_=context;elapsed=[0.];server=LocalOpenHAB()
    def advance(seconds):elapsed[0]+=seconds
    transport=ProductionTransport(base='http://127.0.0.1:8080/rest',token_reader=lambda:'synthetic',
        budget=ReadBudget(85,clock=lambda:elapsed[0],sleeper=advance,max_requests=96),opener=server.open)
    evidence=tmp_path/'core';evidence.mkdir(mode=0o700)
    lock=tmp_path/'core.lock';lock.write_bytes(b'');lock.chmod(0o600)
    result=run_publication(archive=Archive.open_readonly(args['archive'].root),site=SITE,evidence_directory=evidence,
        shared_lock=lock,code_revision='a'*40,transport=transport,authorize=lambda p:True,guard=lambda:None,
        clock=lambda:args['decision_at']+timedelta(seconds=elapsed[0]),**kwargs)
    return result,server


def test_optional_near24_preserves_raw_core_states_and_retains_original_candidate(context,tmp_path):
    rt=runtime(context,tmp_path)
    result,server=publish(context,tmp_path,near_term_preparer=rt.prepare,refresh_retainer=rt.retain)
    assert result['status']=='PUBLISHED' and result['refresh_status']=='retained_candidate'
    core=json.loads(server.states['Forecast_10Day_JSON'])
    assert core['days'][0]['hours'][0]['tempF']==68  # native raw20C
    cache=json.loads((rt.root/'near-term-correction.json').read_bytes())
    assert cache['status']=='CORRECTED_READ_ONLY' and cache['hours'][0]['local_c']==pytest.approx(22)
    assert cache['source']['snapshot_sha256']==context[2]
    assert cache['issued'] is False and cache['local_coverage_qualified'] is False
    assert 'selected_originals' not in cache and 'origin_capture' not in cache
    assert len(list((rt.root/'refresh-issues').glob('*.json')))==1


def test_optional_preparer_failure_still_publishes_and_retains_core_original(context,tmp_path):
    rt=runtime(context,tmp_path)
    def broken(*args):raise RuntimeError('synthetic private dependency')
    result,_=publish(context,tmp_path,near_term_preparer=broken,refresh_retainer=rt.retain)
    assert result['status']=='PUBLISHED' and result['refresh_status']=='retained_raw_only'
    assert result['near_term_preparation_status']=='UNAVAILABLE'
    assert not (rt.root/'near-term-correction.json').exists()


def test_optional_retention_failure_does_not_withdraw_successful_core_publication(context,tmp_path):
    rt=runtime(context,tmp_path)
    def broken(*args):raise OSError('synthetic storage failure')
    result,server=publish(context,tmp_path,near_term_preparer=rt.prepare,refresh_retainer=broken)
    assert result['status']=='PUBLISHED' and result['refresh_status']=='UNAVAILABLE'
    assert json.loads(server.states['Forecast_10Day_JSON'])['providerStatus']=='AVAILABLE'


def test_late_history_registration_cannot_create_a_current_near24_cache(context,tmp_path):
    rt=runtime(context,tmp_path);args,_,_=context
    near=rt.prepare(args['decision_at'],load_publication_forecast(args['archive'],decision_at=args['decision_at'],site=SITE))
    result,_=publish(context,tmp_path)
    attempt=json.loads(Path(result['attempt_path']).read_bytes());completed=json.loads(Path(result['result_path']).read_bytes())
    rt.clock=lambda:args['decision_at']+timedelta(minutes=3)
    assert rt.retain(attempt,completed,near)=='retained_historical_only'
    assert not (rt.root/'near-term-correction.json').exists()


def test_incomplete_optional_callback_pair_is_refused_before_core_writes(context,tmp_path):
    rt=runtime(context,tmp_path)
    with pytest.raises(ValueError,match='paired'):
        publish(context,tmp_path,near_term_preparer=rt.prepare)
