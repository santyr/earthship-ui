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
