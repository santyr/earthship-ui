"""Public ranges describe only original, confirmed production output."""
from datetime import timedelta
from hashlib import sha256
import json
import pytest
from test_production_forecast import serving,NOW,prepare
from test_production_emissions import published
from weather_learning.contracts import canonical,identity
from weather_learning.shadow import ShadowStore
from weather_learning.production_emissions import retain_prepared,confirm_publication


def confirmed(serving,tmp_path):
 product,attempt,result=published(serving);state=ShadowStore(tmp_path/'public-owner')
 retain_prepared(state,product,provider=serving['provider'],now=NOW)
 emission=confirm_publication(state,product,provider=serving['provider'],attempt=attempt,result=result)
 return state,product,emission


def test_public_ranges_bind_confirmed_original_points_without_private_sources_or_clock_renewal(serving,tmp_path):
 from weather_learning.production_public import retain_public_view
 state,product,emission=confirmed(serving,tmp_path)
 view=retain_public_view(state,emission['emission_sha256'])
 assert view['issued'] is True and product.to_dict()['issued'] is False
 assert view['issue_sha256']==emission['issue_sha256'] and view['generated_at']==NOW.isoformat()
 assert view['published_at']==emission['published_at'] and len(view['rows'])==len(emission['published_rows'])
 local=[r for r in view['rows'] if r['local'] is not None]
 assert local and all(r['local']['model_sha256'] in view['models'] for r in local)
 row=next(r for r in view['rows'] if r['kind']=='temperature' and r['local'] is not None)
 original=next(r for r in product.to_dict()['rows'] if (r['profile'],r['kind'],r['at'])==(row['profile'],row['kind'],row['target_end']))
 assert row['local']['point_estimate']==original['prediction']['point_estimate']
 assert row['local']['quantiles']==original['prediction']['local_quantiles']
 assert row['raw']['mean']==original['forecast']['baseline']
 assert row['raw']['statistic']=='native_point' and view['local_coverage_qualified'] is False
 raw=canonical(view);assert len(raw)<512*1024 and b'source_originals' not in raw and str(state.root).encode() not in raw
 receipt_path=state.root/'production-views'/('view-'+view['report_sha256']+'.json');receipt=json.loads(receipt_path.read_bytes())
 assert receipt['cache_bytes_sha256']==sha256(raw).hexdigest() and receipt['production_emission_sha256']==emission['emission_sha256']
 before={p:p.read_bytes() for p in state.root.rglob('*.json')}
 assert retain_public_view(state,emission['emission_sha256'])==view
 assert all(p.read_bytes()==v for p,v in before.items())


def test_unconfirmed_preparation_cannot_create_a_public_production_cache(serving,tmp_path):
 from weather_learning.production_public import retain_public_view
 state=ShadowStore(tmp_path/'not-published');product=prepare(serving)
 retain_prepared(state,product,provider=serving['provider'],now=NOW)
 with pytest.raises((ValueError,FileNotFoundError)):retain_public_view(state,product.to_dict()['issue_sha256'])
 assert not (state.root/'production-forecast.json').exists()


def test_raw_fallback_preserves_native_wind_quantity_and_missing_temperature_context(serving,tmp_path):
 from weather_learning.production_public import retain_public_view
 from weather_learning.production_publish import production_states,publish_cycle
 args=dict(serving,contexts={});product=prepare(args);provider=serving['provider'];states=production_states(provider,now=NOW,production=product);store={}
 publication=publish_cycle(provider,now=NOW,production=product,put_state=lambda k,v:store.__setitem__(k,v),read_state=store.__getitem__,authorize=lambda p:True)
 attempt=dict(started_at=NOW.isoformat(),provider=provider.to_dict(),states=states,states_sha256=identity(states));attempt['attempt_sha256']=identity(attempt)
 result=dict(attempt_sha256=attempt['attempt_sha256'],status='PUBLISHED',completed_at=(NOW+timedelta(seconds=5)).isoformat(),publication=publication);result['result_sha256']=identity(result)
 state=ShadowStore(tmp_path/'fallback');retain_prepared(state,product,provider=provider,now=NOW)
 emission=confirm_publication(state,product,provider=provider,attempt=attempt,result=result)
 view=retain_public_view(state,emission['emission_sha256'])
 # Instantaneous wind is not part of the confirmed hourly-mean population.
 assert all(r['kind']=='temperature' and r['local'] is None and r['reason']=='origin_measurement_context_unavailable' for r in view['rows'])
 assert view['models']=={} and all(r['raw']['mean']==10 for r in view['rows'])


def test_public_projection_receipts_count_toward_the_existing_shared_state_cap(tmp_path,monkeypatch):
 from pathlib import Path
 from types import SimpleNamespace
 state=ShadowStore(tmp_path/'capacity');directory=state.root/'production-views';directory.mkdir(mode=0o700)
 retained=directory/'old.json';retained.write_bytes(b'{}');retained.chmod(0o600);original_stat=Path.stat
 def stat(path,*args,**kwargs):
  if path==retained:return SimpleNamespace(st_size=2*1024**3)
  return original_stat(path,*args,**kwargs)
 monkeypatch.setattr(Path,'stat',stat)
 with pytest.raises(ValueError,match='capacity'):state._write(state.root/'production-forecast.json',{'would':'overrun retained views'})
 assert not (state.root/'production-forecast.json').exists()
