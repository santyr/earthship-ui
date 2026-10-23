"""Optional groups share one bounded collector and never replace core inputs."""
from datetime import timedelta
import json,os
import pytest
from capability_fixtures import reader,raw_response
from learning_fixtures import T,SITE,full_snapshot
from weather_learning.archive import Archive
from weather_learning.capabilities import profile,profile_coverage
from weather_learning.capability_publish import build_capability_report
from weather_learning.contracts import canonical
from weather_learning.worker import collect_once

PROFILES=('uncertainty-v1','atmosphere-v1','rain-uncertainty-v1')
def collect(r,a,now,**kwargs):
    return collect_once(r,a,probe=False,horizon=360,include_interim=True,clock=lambda:now[0],free_bytes=10**9,
        optional_profiles=PROFILES,**kwargs)

def test_all_enabled_bands_use_native_sdk_queries_and_independent_full_interim_originals(tmp_path):
    r,now=reader();a=Archive(tmp_path/'archive');value=collect(r,a,now)
    assert value['schema']=='earthship-weathernext-ingest-result/v2'
    assert len(value['capabilities'])==5
    assert all(g['status']=='collected' and g['normalized'] and not g['consumed'] for g in value['capabilities'])
    assert len(list(a.objects.glob('*.json')))==7
    requests={(q['grid'],b,q['horizon']) for q in r.ee.queries for b in q['bands']}
    for name in PROFILES:
        p=profile(name)
        for horizon in p.horizons:
            for grid,band in p.bands:assert (grid,band,horizon) in requests
    assert not any(q['horizon']==48 and q['bands'][0].startswith('total_precipitation') for q in r.ee.queries)
    cells={}
    for path in a.objects.glob('*.json'):
        snapshot=a.read(path.stem)
        for point in snapshot['points']:cells.setdefault('station' if point['variable'].startswith('station') else 'gridded',set()).add((point['latitude'],point['longitude']))
    assert cells=={'station':{(38.35,-105.75)},'gridded':{(38.4,-105.8)}}
    assert value['acquisition_budget']['requests_used']<=32
    assert value['acquisition_budget']['response_bytes_used']<=8*1024**2
    assert value['archive_capacity']['objects']==7
    assert value['archive_capacity']['eecu_remaining'] is None
    assert value['archive_capacity']['maximum_new_objects_per_cycle']==7
    assert value['archive_capacity']['maximum_archive_growth_bytes_per_cycle']==56*1024**2
    assert value['archive_capacity']['conservative_complete_cycles_remaining']==292
    full={g['profile']:a.read(g['snapshot_sha256']) for g in value['capabilities'] if g['horizon']==360}
    def point(name,variable,stat):return next(p for p in full[name]['points'] if p['variable']==variable and p['statistic']==stat)
    assert point('uncertainty-v1','station_head_temperature_2m','p25')['value']==9
    assert point('uncertainty-v1','station_head_temperature_2m','p50')['value']==10
    solar=point('uncertainty-v1','surface_solar_radiation_downwards_1hr','p10')
    assert solar['value']==60 and solar['raw_value']==216000 and solar['period_seconds']==3600
    assert point('uncertainty-v1','wind_speed_10m','p10')['value']==0
    assert point('atmosphere-v1','u_component_of_wind_10m','mean')['value']==-1
    assert point('atmosphere-v1','high_cloud_cover','mean')['value']==40
    for variable in ('total_precipitation_1hr','imerg_tp_1hr','experimental_tp_1hr'):
        rain=point('rain-uncertainty-v1',variable,'p50')
        assert rain['raw_value']==.0005 and rain['value']==.5 and rain['unit']=='mm'

def test_warm_cache_never_redownloads_or_renews_availability_and_replays_to_public(tmp_path):
    r,now=reader();a=Archive(tmp_path/'archive');first=collect(r,a,now)
    before={p.name:p.read_bytes() for p in a.objects.glob('*.json')}
    public=build_capability_report(a,decision=now[0],site=SITE,horizons=(24,336))
    assert public['groups']['temperature']['hours'][0]['p50_c'] is None
    r.ee.queries.clear();now[0]+=timedelta(minutes=5)
    second=collect(r,a,now)
    assert r.ee.queries==[] and all(g['status']=='cached' for g in second['capabilities'])
    assert {p.name:p.read_bytes() for p in a.objects.glob('*.json')}==before
    replay=build_capability_report(a,decision=now[0],site=SITE,horizons=(24,336))
    assert replay['sources']==public['sources']
    assert second['archive_capacity']['objects']==first['archive_capacity']['objects']

def test_missing_optional_group_does_not_suppress_other_groups_or_core(tmp_path):
    r,now=reader();r.ee.fail_band='station_head_temperature_2m_p25';a=Archive(tmp_path/'archive')
    value=collect(r,a,now)
    assert value['status']=='ARCHIVED'
    failed=[g for g in value['capabilities'] if g['profile']=='uncertainty-v1']
    assert len(failed)==2 and all(g['status']=='unavailable' and g['normalized'] for g in failed)
    assert all(g['status']=='collected' for g in value['capabilities'] if g['profile']!='uncertainty-v1')
    assert build_capability_report(a,decision=now[0],site=SITE,horizons=(24,))['status']=='available'

def test_partial_null_delivery_is_retained_but_cannot_satisfy_profile_cache(tmp_path):
    r,now=reader();r.ee.null_band='station_head_temperature_2m_p50';a=Archive(tmp_path/'archive')
    value=collect(r,a,now)
    for group in value['capabilities']:
        if group['profile']!='uncertainty-v1':continue
        assert group['status']=='unavailable' and group['reason']=='partial_delivery'
        original=a.read(group['snapshot_sha256'])
        assert profile_coverage(original,profile('uncertainty-v1'),decision=now[0],horizon=group['horizon'])['status']=='missing_fields'

def test_old_mean_only_cache_cannot_be_relabelled_as_expanded_quantiles(tmp_path):
    r,now=reader();a=Archive(tmp_path/'archive');a.store_snapshot(full_snapshot(hours=360))
    value=collect(r,a,now)
    assert all(g['status']=='collected' for g in value['capabilities'])
    assert any('station_head_temperature_2m_p50' in q['bands'] for q in r.ee.queries)

def test_bounded_backoff_survives_restart_and_stops_after_two_attempts(tmp_path):
    r,now=reader();r.ee.fail_band='station_head_temperature_2m_p25';a=Archive(tmp_path/'archive')
    first=collect(r,a,now);requests=len(r.ee.queries)
    second=collect(r,Archive(a.root),now)
    assert len(r.ee.queries)==requests
    assert all(g['reason']=='retry_backoff' for g in second['capabilities'] if g['profile']=='uncertainty-v1')
    now[0]+=timedelta(hours=1);third=collect(r,a,now)
    assert len(r.ee.queries)==requests+4  # two grids in each of two bounded retries; valid grid originals retained
    requests=len(r.ee.queries);now[0]+=timedelta(hours=2);last=collect(r,a,now)
    assert len(r.ee.queries)==requests
    assert all(g['reason']=='attempt_limit' for g in last['capabilities'] if g['profile']=='uncertainty-v1')

def test_cumulative_capacity_defers_optional_groups_before_query_and_preserves_originals(tmp_path):
    r,now=reader();a=Archive(tmp_path/'archive');filler=a.objects/('f'*64+'.json')
    fd=os.open(filler,os.O_CREAT|os.O_WRONLY,0o600)
    try:os.ftruncate(fd,8*1024**2-1)
    finally:os.close(fd)
    value=collect(r,a,now,max_archive_bytes=16*1024**2)
    assert value['status']=='ARCHIVED' and filler.stat().st_size==8*1024**2-1
    assert all(g['status']=='deferred' and g['reason']=='archive_capacity' for g in value['capabilities'])
    assert sum(p.stat().st_size for p in a.objects.glob('*.json'))<=16*1024**2

def test_global_owner_stop_is_not_swallowed_as_optional_profile_failure(tmp_path):
    r,now=reader();a=Archive(tmp_path/'archive')
    fetch=r.fetch_points
    def stopped(**kw):
        if 'station_head_temperature_2m_p25' in kw['bands_by_grid'].get('station',()):raise TimeoutError('owner deadline')
        return fetch(**kw)
    r.fetch_points=stopped
    with pytest.raises(TimeoutError):collect(r,a,now)
    assert len(list(a.objects.glob('*.json')))==2

def test_profiles_are_explicit_collect_only_and_priority_ordered(tmp_path):
    r,now=reader();a=Archive(tmp_path/'archive')
    with pytest.raises(ValueError):collect_once(r,a,probe=True,optional_profiles=PROFILES)
    with pytest.raises(ValueError):collect_once(r,a,probe=False,optional_profiles=('temperature-display-v1',))
    with pytest.raises(ValueError):collect_once(r,a,probe=False,optional_profiles=('uncertainty-v1','uncertainty-v1'))
    value=collect_once(r,a,probe=False,horizon=360,include_interim=True,clock=lambda:now[0],optional_profiles=tuple(reversed(PROFILES)))
    names=[g['profile'] for g in value['capabilities']]
    assert names.index('uncertainty-v1')<names.index('atmosphere-v1')<names.index('rain-uncertainty-v1')

def test_request_budget_is_shared_with_initialization_and_core_acquisition(tmp_path):
    from test_transport import Response
    from weather_learning.config import PROJECT
    r,now=reader();a=Archive(tmp_path/'archive')
    def initialize():
        r.transport.session.response=Response(json.dumps({'registrationState':'REGISTERED_NOT_COMMERCIALLY'}).encode())
        for _ in range(25):r.transport.request('https://earthengine.googleapis.com/v1/projects/'+PROJECT+'/config')
    r.initialize=initialize
    value=collect(r,a,now)
    assert value['status']=='ARCHIVED' and value['acquisition_budget']['requests_used']==32
    assert len(r.transport.session.calls)==32
    assert all(g['status']=='deferred' for g in value['capabilities'])
    assert len(list(a.objects.glob('*.json')))==3
    partial=a.read(value['capabilities'][0]['snapshot_sha256'])
    assert {p['variable'] for p in partial['points']}=={'station_head_temperature_2m'}

def test_total_transfer_ceiling_is_not_reset_for_each_optional_profile(tmp_path):
    from dataclasses import replace
    from test_transport import Session
    from weather_learning.transport import BoundedTransport
    measured,now=reader();baseline=Archive(tmp_path/'baseline')
    collect_once(measured,baseline,probe=False,horizon=360,include_interim=True,clock=lambda:now[0])
    bound=measured.transport.bytes_received+1024
    r,now=reader();r.policy=replace(r.policy,max_bytes=bound);r.transport=BoundedTransport(r.policy,session=Session());r.transport.noncommercial_verified=True
    a=Archive(tmp_path/'archive');value=collect(r,a,now)
    assert value['status']=='ARCHIVED'
    assert value['acquisition_budget']['response_bytes_used']==bound+1  # one sentinel byte detects oversize
    assert all(g['status']=='deferred' for g in value['capabilities'])
    assert len(list(a.objects.glob('*.json')))==2

def test_quota_refusal_defers_lower_priority_profiles_and_persists_cooldown(tmp_path):
    r,now=reader();r.ee.quota_band='station_head_temperature_2m_p25';a=Archive(tmp_path/'archive')
    value=collect(r,a,now)
    assert value['status']=='ARCHIVED' and all(g['status']=='deferred' for g in value['capabilities'])
    assert sum(t['status']==429 for t in r.transport.trace)==1
    r.ee.queries.clear();second=collect(r,Archive(a.root),now)
    assert r.ee.queries==[]
    assert all(g['reason']=='quota_backoff' for g in second['capabilities'])
    now[0]+=timedelta(hours=1);third=collect(r,a,now)
    first=third['capabilities'][0]
    assert first['retry_at']==(now[0]+timedelta(hours=6)).isoformat()
    assert sum(t['status']==429 for t in r.transport.trace)==2
    assert third['acquisition_budget']['paid_access_allowed'] is False

def test_malformed_retry_state_is_optional_and_never_leaks_private_fields(tmp_path):
    r,now=reader();a=Archive(tmp_path/'archive')
    path=a.root/'.capability-backoff.json';path.write_text('{"operator-private":"secret"}');path.chmod(0o600)
    value=collect(r,a,now)
    assert value['status']=='ARCHIVED'
    assert all(g['reason']=='backoff_state_invalid' for g in value['capabilities'])
    assert 'operator-private' not in json.dumps(value) and 'secret' not in json.dumps(value)

def test_ingest_cli_requires_explicit_profile_optin_before_local_or_cloud_access(tmp_path,monkeypatch,capsys):
    import importlib.util
    from pathlib import Path
    from weather_learning import openhab
    spec=importlib.util.spec_from_file_location('capability_ingest_cli',Path(__file__).parents[2]/'weathernext_ingest.py')
    script=importlib.util.module_from_spec(spec);spec.loader.exec_module(script)
    reads=[]
    monkeypatch.setattr(openhab,'oh_get',lambda path:reads.append(path) or {'location':f'{SITE.latitude},{SITE.longitude}','timezone':SITE.timezone})
    r,now=reader();monkeypatch.setattr(script,'EarthEngineReader',lambda **kw:r)
    actual=script.collect_once
    monkeypatch.setattr(script,'collect_once',lambda *a,**kw:actual(*a,**kw,clock=lambda:now[0]))
    with pytest.raises(SystemExit):script.main(['--probe','--archive',str(tmp_path/'refused'),'--capability-profile','atmosphere-v1'])
    assert reads==[] and not (tmp_path/'refused').exists()
    result=script.main(['--collect','--archive',str(tmp_path/'archive'),'--capability-profile','atmosphere-v1'])
    assert result==0
    value=json.loads(capsys.readouterr().out)
    assert {g['profile'] for g in value['capabilities']}=={'atmosphere-v1'}

def test_profile_cache_cannot_rebind_a_retained_original_to_another_run(tmp_path):
    r,now=reader();a=Archive(tmp_path/'archive');value=collect(r,a,now)
    original=next(g for g in value['capabilities'] if g['profile']=='uncertainty-v1' and g['horizon']==360)
    different=(T+timedelta(hours=6)).isoformat()
    with a._connect() as db:db.execute('UPDATE snapshots SET initialized=? WHERE digest=?',(different,original['snapshot_sha256']))
    assert a.completed_profile(different,capability=profile('uncertainty-v1'),horizon=360,as_of=now[0]+timedelta(hours=6),site=SITE) is None

def test_profile_cache_does_not_reuse_another_authoritative_site(tmp_path):
    from weather_learning.config import Site
    r,now=reader();a=Archive(tmp_path/'archive');collect(r,a,now)
    assert a.completed_profile(T.isoformat(),capability=profile('uncertainty-v1'),horizon=360,as_of=now[0],site=Site(0,0,'UTC')) is None

def test_expired_shared_wall_clock_defers_even_warm_optional_cache_work(tmp_path):
    first,now=reader();a=Archive(tmp_path/'archive');collect(first,a,now)
    r,_=reader(clock=lambda:now[0]);discover=r.discover_run;calls=[]
    def spent(**kw):
        result=discover(**kw);calls.append(kw)
        if len(calls)==2:r.transport.started=r.transport.clock()-76
        return result
    r.discover_run=spent
    result=collect(r,a,now)
    assert result['status']=='ARCHIVED'
    assert all(g['status']=='deferred' and g['reason']=='deadline_budget' for g in result['capabilities'])
    assert r.ee.queries==[]

def test_profile_cache_global_cancellation_after_validation_is_not_optional_missing(tmp_path):
    r,now=reader();a=Archive(tmp_path/'archive');value=collect(r,a,now)
    group=next(g for g in value['capabilities'] if g['profile']=='uncertainty-v1' and g['horizon']==360)
    snapshot=a.read(group['snapshot_sha256']);snapshot.pop('snapshot_sha256')
    single=Archive(tmp_path/'single');single.store_snapshot(snapshot);checks=[]
    def stop():
        checks.append(True)
        if len(checks)==2:raise TimeoutError('global deadline')
    with pytest.raises(TimeoutError):
        single.completed_profile(T.isoformat(),capability=profile('uncertainty-v1'),horizon=360,as_of=now[0],site=SITE,guard=stop)

def test_archive_rejects_oversized_normalized_original_before_any_write(tmp_path):
    from weather_learning.contracts import identity
    a=Archive(tmp_path/'archive');snapshot=full_snapshot(hours=1)
    source=snapshot['source_originals'][0];old=identity(source)
    source['payload']['retained_padding']='x'*(8*1024**2)
    new=identity(source)
    for point in snapshot['points']:
        if point['source_digest']==old:point['source_digest']=new
    with pytest.raises(ValueError,match='size cap'):
        a.store_snapshot(snapshot)
    assert list(a.objects.glob('*.json'))==[]

def test_full_run_only_profile_has_an_explicit_deferred_disposition_in_interim_job(tmp_path):
    r,now=reader();a=Archive(tmp_path/'archive')
    result=collect_once(r,a,probe=False,horizon=48,clock=lambda:now[0],optional_profiles=('rain-uncertainty-v1',))
    assert result['capabilities']==[dict(profile='rain-uncertainty-v1',profile_sha256=profile('rain-uncertainty-v1').signature,
        horizon=48,status='deferred',reason='full_run_only',normalized=False,consumed=False,snapshot_sha256=None,
        declared_consumer='rain_diagnostics',retry_at=None)]
    assert len(r.ee.queries)==2 and len(list(a.objects.glob('*.json')))==1

def test_structured_quota_code_defers_profiles_without_exposing_error_text(tmp_path):
    r,now=reader();r.ee.quota_band='station_head_temperature_2m_p25';r.ee.quota_http_status=403
    a=Archive(tmp_path/'archive');result=collect(r,a,now)
    assert all(g['status']=='deferred' for g in result['capabilities'])
    assert result['capabilities'][0]['reason']=='quota_restriction'
    assert sum(t.get('error_status')=='RESOURCE_EXHAUSTED' for t in r.transport.trace)==1

def test_successful_native_grid_original_survives_failure_of_another_grid(tmp_path):
    r,now=reader();r.ee.fail_band='station_head_temperature_2m_p25';a=Archive(tmp_path/'archive')
    result=collect(r,a,now)
    for group in result['capabilities']:
        if group['profile']!='uncertainty-v1':continue
        assert group['status']=='unavailable' and group['normalized'] is True
        snapshot=a.read(group['snapshot_sha256'])
        assert len(snapshot['source_originals'])==1
        assert {p['variable'] for p in snapshot['points']}=={'surface_solar_radiation_downwards_1hr','wind_speed_10m'}
        assert profile_coverage(snapshot,profile('uncertainty-v1'),decision=now[0],horizon=group['horizon'])['status']=='missing_fields'

def test_later_grid_quota_preserves_the_successful_grid_and_defers_further_remote_queries(tmp_path):
    r,now=reader();r.ee.quota_band='surface_solar_radiation_downwards_1hr_p10';a=Archive(tmp_path/'archive')
    result=collect(r,a,now);first=result['capabilities'][0]
    assert first['status']=='deferred' and first['reason']=='quota_restriction' and first['normalized']
    snapshot=a.read(first['snapshot_sha256'])
    assert {p['variable'] for p in snapshot['points']}=={'station_head_temperature_2m'}
    assert all(g['status']=='deferred' for g in result['capabilities'][1:])
    assert sum(t['status']==429 for t in r.transport.trace)==1

def test_rejected_optional_sources_remain_named_and_do_not_touch_core_originals(tmp_path):
    r,now=reader();r.ee.fail_bands={'station_head_temperature_2m_p25','surface_solar_radiation_downwards_1hr_p10',
        'high_cloud_cover_mean','total_precipitation_1hr_p10'}
    a=Archive(tmp_path/'archive');result=collect(r,a,now)
    assert result['status']=='ARCHIVED'
    assert all(g['status']=='rejected' and g['reason']=='invalid_optional_source' and not g['normalized'] for g in result['capabilities'])
    assert len(list(a.objects.glob('*.json')))==2
