"""Scheduled profile scoring preserves originals and uses verified compact reports."""
from pathlib import Path
from datetime import timedelta
from hashlib import sha256
import importlib,gzip,os
from household.codec import canonical,loads
from household.control_contracts import instant
from test_household_profiled_outcomes import case,originals
import pytest


def staged(tmp_path,monkeypatch,originals):
    _,args=case(tmp_path,monkeypatch,originals)
    from household_cycle import _retain_original
    stage=tmp_path/'profile-stage';evidence=stage/'evidence';evidence.mkdir(parents=True,mode=0o700)
    for value,suffix,limit in ((args['plan_receipt'],'.household-model-plan-v6.json',2097152),(args['energy_receipt'],'.household-energy-forecast-v1.json',262144),(args['profiled_receipt'],'.household-profiled-energy-v1.json',262144)):
        path=_retain_original(evidence,value,suffix,limit);issued=instant(args['profiled_receipt']['output']['issued_at']);os.utime(path,(issued.timestamp(),issued.timestamp()))
    root=tmp_path/'profile-state';root.mkdir(mode=0o700);calls=[]
    def hour_reader(*,start,end):
        calls.append('hour');assert start==issued and end==issued+timedelta(hours=1);return args['hour_sources']['1']
    def endpoint_reader(*,target_at):calls.append('endpoint');assert target_at==issued+timedelta(hours=1);return args['endpoint_sources']['1']
    api=importlib.import_module('household_profiled_score')
    kwargs=dict(stage=stage,historical=[],guard=lambda:None,deadline=115.,clock=lambda:args['assessed_at'],monotonic=lambda:100.,state_root=root,hour_reader=hour_reader,endpoint_reader=endpoint_reader)
    return api,kwargs,calls,args


def test_regular_score_slot_retains_full_originals_and_refreshes_small_public_metrics(tmp_path,monkeypatch,originals):
    api,kwargs,calls,args=staged(tmp_path,monkeypatch,originals);before={p.name:p.read_bytes() for p in (kwargs['stage']/'evidence').iterdir()}
    result=api.run(**kwargs)
    assert result['status']=='profiled_energy_performance_refreshed' and result['count']==2 and calls==['hour','endpoint']
    report=loads((kwargs['state_root']/'profiled-energy-performance.json').read_bytes())
    assert report['by_horizon']['1']['load']['count']==1 and report['by_horizon']['1']['soc']['count']==1
    store=kwargs['state_root']/'profiled-energy-outcomes';raw=next(store.glob('*.profiled-energy-outcome-v1.json.gz'))
    complete=loads(gzip.decompress(raw.read_bytes()))
    assert complete['inputs']['hour_sources']==args['hour_sources'] and complete['reference_score']['inputs']['endpoint_sources']==args['endpoint_sources']
    assert {p.name:p.read_bytes() for p in (kwargs['stage']/'evidence').iterdir()}==before
    assert all(p.stat().st_mode&0o777==0o600 for p in store.iterdir())
    def forbidden(*a,**kw):pytest.fail('settled report re-parsed old electrical originals')
    monkeypatch.setattr(api,'_read_full_score',forbidden)
    again=api.run(**kwargs)
    assert again['count']==2 and calls==['hour','endpoint']


def test_changed_pinned_full_score_refuses_even_when_compact_sample_is_unchanged(tmp_path,monkeypatch,originals):
    api,kwargs,_,_=staged(tmp_path,monkeypatch,originals);api.run(**kwargs)
    path=next((kwargs['state_root']/'profiled-energy-outcomes').glob('*.profiled-energy-outcome-v1.json.gz'));path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError):api.run(**kwargs)


def test_source_failure_is_deferred_without_losing_other_domain_or_original_forecasts(tmp_path,monkeypatch,originals):
    api,kwargs,calls,args=staged(tmp_path,monkeypatch,originals)
    def failed(**kw):raise ValueError('private reader detail')
    kwargs['hour_reader']=failed;result=api.run(**kwargs)
    assert result['count']==1 and 'private reader detail' not in str(result)
    report=loads((kwargs['state_root']/'profiled-energy-performance.json').read_bytes())
    assert report['by_horizon']['1']['load']['count']==0 and report['by_horizon']['1']['soc']['count']==1
    index=loads((kwargs['state_root']/'profiled-energy-outcomes/samples.json').read_bytes())
    assert next(iter(index['samples'].values()))['retry_after'] is not None


def test_backlogged_origin_saves_bounded_progress_in_each_opportunity(tmp_path,monkeypatch,originals):
    api,kwargs,calls,args=staged(tmp_path,monkeypatch,originals)
    issue=instant(args['profiled_receipt']['output']['issued_at']);elapsed=[100.]
    kwargs.update(clock=lambda:issue+timedelta(hours=25),monotonic=lambda:elapsed[0])
    def hour_reader(*,start,end):
        calls.append(('hour',end));elapsed[0]+=2
        return args['hour_sources']['1'] if end==issue+timedelta(hours=1) else None
    def endpoint_reader(*,target_at):
        calls.append(('endpoint',target_at));elapsed[0]+=2
        return args['endpoint_sources']['1'] if target_at==issue+timedelta(hours=1) else None
    kwargs.update(hour_reader=hour_reader,endpoint_reader=endpoint_reader)
    result=api.run(**kwargs)
    assert result['count']==2 and len(calls)==2
    index=loads((kwargs['state_root']/'profiled-energy-outcomes/samples.json').read_bytes())
    assert next(iter(index['samples'].values()))['sample_sha256'] is not None
    kwargs['deadline']=elapsed[0]+15
    again=api.run(**kwargs)
    assert again['count']==2 and len(calls)==4
    assert all(target!=issue+timedelta(hours=1) for _,target in calls[2:])


@pytest.mark.parametrize('already_indexed',[False,True])
def test_new_unavailable_forecast_keeps_previous_valid_origin_scoring(tmp_path,monkeypatch,originals,already_indexed):
    api,kwargs,calls,args=staged(tmp_path,monkeypatch,originals)
    # Retain a valid origin before its first target has matured.
    issue=instant(args['profiled_receipt']['output']['issued_at'])
    kwargs['clock']=lambda:issue+timedelta(minutes=30)
    if already_indexed:api.run(**kwargs)
    assert calls==[]
    from household_profiled_forecast import seal_profiled_forecast,profiled_runtime_manifest
    from household_energy_forecast import forecast_runtime_manifest
    from household_cycle import _retain_original
    unavailable=seal_profiled_forecast(energy_receipt=args['energy_receipt'],plan_receipt=args['plan_receipt'],load_source=None,now=instant(args['energy_receipt']['inputs']['assessed_at']),
        runtime_manifest=profiled_runtime_manifest(),energy_runtime_manifest=forecast_runtime_manifest(),load_runtime_manifest={})
    path=_retain_original(kwargs['stage']/'evidence',unavailable,api.SUFFIX,262144)
    at=(issue+timedelta(minutes=1)).timestamp();os.utime(path,(at,at))
    kwargs['clock']=lambda:args['assessed_at']
    result=api.run(**kwargs)
    assert result['status']=='profiled_energy_performance_refreshed' and result['count']==2
    assert calls==['hour','endpoint']


@pytest.mark.parametrize('already_indexed',[False,True])
def test_changed_underlying_energy_runtime_keeps_old_profile_originals_out_of_current_scoring(tmp_path,monkeypatch,originals,already_indexed):
    api,kwargs,calls,args=staged(tmp_path,monkeypatch,originals)
    if already_indexed:api.run(**kwargs)
    calls.clear()
    previous=kwargs['stage'];current=tmp_path/'new-stage';(current/'evidence').mkdir(parents=True,mode=0o700)
    kwargs.update(stage=current,historical=[dict(stage=str(previous))])
    originals_before={p.name:p.read_bytes() for p in (previous/'evidence').iterdir()}
    old_runtime=api.forecast_runtime_manifest()
    monkeypatch.setattr(api,'forecast_runtime_manifest',lambda:{**old_runtime,'new-energy-source.py':'a'*64})
    result=api.run(**kwargs)
    assert result['status']=='waiting' and result['reason']=='current_load_profile_unavailable'
    assert calls==[]
    assert {p.name:p.read_bytes() for p in (previous/'evidence').iterdir()}==originals_before
