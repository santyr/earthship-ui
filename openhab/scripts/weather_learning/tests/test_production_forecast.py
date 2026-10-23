"""The deployed product changes served points and preserves each actual source."""
from dataclasses import replace
from datetime import timedelta
import json
import pytest
from learning_fixtures import T,SITE,native_snapshot,full_snapshot
from test_probabilistic import POLICY,pairs
from test_probabilistic_issue import context
from test_production_model_admission import AUTH
from weather_learning.archive import Archive
from weather_learning.contracts import identity,instant
from weather_learning.provider import load_production_forecast,forecast_payloads
from weather_learning.probabilistic_retained import prepare_marginal_source
from weather_learning.probabilistic_issue import wind_context
from weather_learning.production_training import fit_production
from weather_learning.production_model_admission import prepare_admission

NOW=T+timedelta(days=15,hours=9,minutes=30)


def original(init=T+timedelta(days=15),hours=80,temperature=10):
 from weather_learning.weathernext_ee import make_snapshot
 n=native_snapshot(day=(init-T).days,mean_c=temperature,hours=hours)
 f=full_snapshot(init,hours=hours,temperature_k=temperature+273.15)
 return make_snapshot([(n['source_originals'][0],n['points']),(f['source_originals'][1],[p for p in f['points'] if p['variable']!='station_head_temperature_2m'])],site=SITE,initialized_at=init,first_seen_at=init+timedelta(minutes=20),completed_at=init+timedelta(minutes=21))


@pytest.fixture
def serving(tmp_path):
 from weather_learning.probabilistic_issue import temperature_context
 from learning_fixtures import receipt,EPOCH
 archive=Archive(tmp_path/'archive');pin=archive.store_snapshot(original())
 provider=load_production_forecast(archive,decision_at=NOW,required_horizon=timedelta(hours=48),site=SITE)
 contexts={'temperature':temperature_context(receipt(NOW),sampled_at=NOW,acquired_at=NOW,sensor_epoch=EPOCH),'wind':wind_context(decision=NOW)}
 source=prepare_marginal_source(archive.read(pin),assessed_at=NOW);models=[]
 for kind,family in [('temperature','temperature_normal'),('wind','nonnegative')]:
  quality=contexts[kind].quality_at(NOW);frame=source.forecast(kind,target=NOW.replace(minute=0)+timedelta(hours=2),quality=quality,origin=NOW)
  ctx=dict(kind=kind,measurement_quality=quality,grid_sha256=frame.grid_sha256,availability_basis='recorded_ingestion_availability',lead_scope_hours=[0,24],timezone=SITE.timezone)
  rows=[replace(p,forecast=replace(p.forecast,grid_sha256=frame.grid_sha256,cohort_sha256=frame.cohort_sha256)) for p in pairs(kind)]
  bundle=fit_production(rows,family=family,training_context=ctx,cutoff=T+timedelta(days=15),completed_at=T+timedelta(days=15,minutes=1),policy=POLICY,population_sha256='a'*64,authorization=AUTH,authorization_sha256=identity(AUTH)).bundle
  admission=prepare_admission(bundle,family=family,expected_model_sha256=bundle.to_dict()['models'][family]['model_sha256'],policy=POLICY,authorization=AUTH,authorization_sha256=identity(AUTH),admitted_at=T+timedelta(days=15,minutes=2))
  models.append((bundle,admission))
 return dict(provider=provider,read_source=archive.read,contexts=contexts,models=models,policy=POLICY,authorize=lambda r:True)


def prepare(serving,**overrides):
 from weather_learning.production_forecast import prepare_production_forecast
 return prepare_production_forecast(**(serving|overrides))


def test_actual_prepared_product_changes_temperature_but_not_native_physical_wind_or_radiation(serving):
 from weather_learning.production_forecast import production_payloads
 before=serving['provider'].to_dict();product=prepare(serving);hourly,daily,detail=production_payloads(product,provider=serving['provider'],now=NOW)
 first=detail['days'][0]['hours'][0];second=detail['days'][0]['hours'][1]
 assert detail['version']==3 and first['tempF']==pytest.approx(53.6,abs=.9)
 assert first['windMph']==pytest.approx(2.2369362921) and first.get('windMeanMph') is None
 assert second['windMeanMph'] is not None and second['windMph']==first['windMph']
 assert first['radiationWm2']==100 and first['precipIn']==pytest.approx(1/25.4)
 assert hourly[0]['t']==round(first['tempF']) and hourly[0]['r']==100
 assert serving['provider'].to_dict()==before
 assert product.to_dict()['issued'] is False and detail['productionModel']['localCoverageQualified'] is False
 rows=product.to_dict()['rows'];assert any(r['prediction'] is not None and r['prediction']['issued'] is False for r in rows)
 assert detail['productionModel']['issueSha256']==product.to_dict()['issue_sha256']


def test_remaining_day_extrema_use_future_points_not_backdated_predictions(serving):
 from weather_learning.production_forecast import production_payloads
 product=prepare(serving);_,daily,detail=production_payloads(product,provider=serving['provider'],now=NOW)
 today=next(d for d in detail['days'] if d['date']=='2026-01-16')
 assert today['summary']['temperatureScope']=='remaining'
 assert today['summary']['temperatureStatistic']=='extrema_of_hourly_point_forecasts'
 assert today['summary']['highF']==max(h['tempF'] for h in today['hours'])
 assert today['summary']['lowF']==min(h['tempF'] for h in today['hours'])
 assert daily[0]['hi']==round(today['summary']['highF'])
 assert all(instant(r['at'])>NOW for r in product.to_dict()['rows'])


def test_missing_current_measurement_epoch_is_target_specific_raw_fallback(serving):
 from weather_learning.production_forecast import production_payloads
 product=prepare(serving,contexts={'wind':serving['contexts']['wind']});_,_,detail=production_payloads(product,provider=serving['provider'],now=NOW)
 assert detail['days'][0]['hours'][0]['tempF']==50
 assert detail['days'][0]['hours'][1]['windMeanMph'] is not None
 rows=[r for r in product.to_dict()['rows'] if r['kind']=='temperature']
 assert all(r['prediction'] is None and r['reason']=='origin_measurement_context_unavailable' for r in rows)


def test_owner_refusal_and_ambiguous_model_selection_cannot_silently_publish(serving):
 with pytest.raises(ValueError,match='owner'):prepare(serving,authorize=None)
 with pytest.raises(ValueError,match='owner'):prepare(serving,authorize=lambda r:False)
 with pytest.raises(ValueError,match='unique|ambiguous'):prepare(serving,models=[*serving['models'],serving['models'][0]])


def test_product_cannot_be_reused_at_another_decision_or_with_another_source(serving):
 from weather_learning.production_forecast import production_payloads
 product=prepare(serving)
 with pytest.raises(ValueError,match='decision|original'):production_payloads(product,provider=serving['provider'],now=NOW+timedelta(seconds=1))
 with pytest.raises(ValueError):production_payloads(product.to_dict(),provider=serving['provider'],now=NOW)


def test_prepared_states_and_publication_use_the_same_corrected_values(serving):
 from weather_learning.production_publish import production_states,publish_cycle
 product=prepare(serving);states=production_states(serving['provider'],now=NOW,production=product);store={}
 assert float(states['Forecast_Temp'].split()[0])==pytest.approx(53.6,abs=.9)
 result=publish_cycle(serving['provider'],now=NOW,production=product,put_state=lambda item,value:store.__setitem__(item,value),read_state=store.__getitem__,authorize=lambda p:True)
 assert result['status']=='PUBLISHED' and store==states
 assert result['production_issue_sha256']==product.to_dict()['issue_sha256']
 assert len(store['Forecast_10Day_JSON'].encode())<65536


def test_independent_near_source_changes_hours_but_extended_source_still_owns_daily_extrema(serving,tmp_path):
 from weather_learning.provider import load_publication_forecast
 from weather_learning.production_forecast import production_payloads
 archive=Archive(tmp_path/'profiles');extended=archive.store_snapshot(original(hours=360))
 near=original(hours=40,temperature=3);near['first_seen_at']=(T+timedelta(days=15,minutes=22)).isoformat();near['ingestion_completed_at']=(T+timedelta(days=15,minutes=23)).isoformat();near=archive.store_snapshot(near)
 provider=load_publication_forecast(archive,decision_at=NOW,site=SITE)
 product=prepare(serving,provider=provider,read_source=archive.read);_,_,detail=production_payloads(product,provider=provider,now=NOW)
 first=detail['days'][0]['hours'][0]
 assert first['forecastProfile']=='nearTerm' and first['tempF']==pytest.approx(41,abs=1)
 assert detail['days'][0]['summary']['highF']==pytest.approx(53.6,abs=1)
 assert detail['days'][0]['summary']['forecastProfile']=='extended'
 rows=product.to_dict()['rows']
 assert next(r for r in rows if r['profile']=='nearTerm')['source_sha256']==near
 assert next(r for r in rows if r['profile']=='extended')['source_sha256']==extended
 assert len(json.dumps(detail).encode())<65536


@pytest.mark.parametrize('init,day,hours',[
 ('2026-03-07T00:00:00+00:00','2026-03-08',23),
 ('2026-10-31T00:00:00+00:00','2026-11-01',25),
])
def test_complete_future_day_respects_dst_without_synthetic_24_hour_extrema(serving,tmp_path,init,day,hours):
 from weather_learning.production_forecast import production_payloads
 init=instant(init);now=init+timedelta(hours=20);archive=Archive(tmp_path/'dst');archive.store_snapshot(original(init=init))
 provider=load_production_forecast(archive,decision_at=now,required_horizon=timedelta(hours=48),site=SITE)
 product=prepare(serving,provider=provider,read_source=archive.read,contexts={},models=[])
 _,_,detail=production_payloads(product,provider=provider,now=now);full=next(d for d in detail['days'] if d['date']==day)
 assert len(full['hours'])==hours and full['summary']['highF']==full['summary']['lowF']==50
 assert full['summary']['temperatureScope']=='full_day'
 assert detail['productionModel']['status']=='RAW_FALLBACK'



def test_owner_refusal_during_prediction_is_fatal_instead_of_becoming_raw_fallback(serving):
 calls=[]
 def owner(receipt):
  calls.append(receipt['model_sha256'])
  return len(calls)!=4
 with pytest.raises((ValueError,PermissionError),match='owner'):prepare(serving,authorize=owner)
