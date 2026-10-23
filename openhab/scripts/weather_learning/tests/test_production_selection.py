"""A reviewed profile, not a permissive callback, owns selected production models."""
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import pytest
from test_production_forecast import serving,NOW
from test_probabilistic import POLICY,pairs
from learning_fixtures import T,SITE,EPOCH,receipt
from daily_temperature_runtime import SOURCE_POLICY
from weather_learning.contracts import canonical,identity
from weather_learning.production_training import fit_production,retain_production
from weather_learning.production_model_admission import prepare_admission
from weather_learning.shadow import ShadowStore


def private(path,value):
 path.write_bytes(canonical(value));path.chmod(0o600);return path


@pytest.fixture
def selected(serving,tmp_path):
 from weather_learning.production_worker import runtime_manifest
 state=ShadowStore(tmp_path/'selected');(state.root/'production-admissions').mkdir(mode=0o700)
 auth=json.loads(Path('docs/operations/weathernext3-capabilities/deployment-policy.json').read_bytes());registered=[]
 for old,_ in serving['models']:
  body=old.to_dict();ctx=body['training_context'];kind=body['kind'];family='temperature_normal' if kind=='temperature' else 'nonnegative'
  rows=[replace(p,forecast=replace(p.forecast,grid_sha256=ctx['grid_sha256'],cohort_sha256=body['training_cohort_sha256'])) for p in pairs(kind)]
  fitted=fit_production(rows,family=family,training_context=ctx,cutoff=T+timedelta(days=15),completed_at=T+timedelta(days=15,minutes=1),policy=POLICY,population_sha256='a'*64,authorization=auth,authorization_sha256=identity(auth))
  ref=retain_production(state,fitted,policy=POLICY);body=fitted.bundle.to_dict();model=body['models'][family]
  admission=prepare_admission(fitted.bundle,family=family,expected_model_sha256=model['model_sha256'],policy=POLICY,authorization=auth,authorization_sha256=identity(auth),admitted_at=T+timedelta(days=15,minutes=2))
  private(state.root/'production-admissions'/(admission['admission_sha256']+'.json'),admission)
  registered.append(dict(bundle_sha256=body['bundle_sha256'],artifact_sha256=ref['artifact_sha256'],model_sha256=model['model_sha256'],admission_sha256=admission['admission_sha256']))
 policy=private(tmp_path/'temperature-policy.json',dict(version=2,streams={'outdoor':dict(SOURCE_POLICY,sensor_epoch=EPOCH)}))
 db=private(tmp_path/'db.json',dict(host='127.0.0.1',port=5432,dbname='openhab',user='weather_temperature_reader',password='synthetic-only'))
 profile=dict(schema='earthship-selected-weather-production-profile/v1',archive=str(serving['read_source'].__self__.root),state=str(state.root),site=SITE.__dict__,models=registered,
  temperature_policy=str(policy),temperature_db_config=str(db),runtime_sha256=identity(runtime_manifest()),authorization_policy_sha256=identity(auth),parallel_shadow_required=False,automatic_actuation=False)
 path=private(tmp_path/'selected-profile.json',profile)
 return path,profile,state


def load(serving,selected,**kwargs):
 from weather_learning.production_selection import from_profile
 from hashlib import sha256
 path,profile,state=selected
 return from_profile(path,expected_sha256=sha256(path.read_bytes()).hexdigest(),archive=serving['read_source'].__self__,site=SITE,clock=lambda:NOW,guard=lambda:None,**kwargs)


def test_reviewed_profile_preflight_is_readonly_and_serves_only_its_registered_models(serving,selected):
 runtime=load(serving,selected);path,profile,state=selected
 before={p:p.read_bytes() for p in state.root.rglob('*') if p.is_file()}
 runtime.capture_contexts(temperature_reader=lambda at,policy,epoch:receipt(at,epoch=epoch))
 product=runtime.prepare(NOW,serving['provider'])
 assert runtime.verify(product) is True
 assert len(runtime.models)==2 and sum(r['prediction'] is not None for r in product.to_dict()['rows'])>40
 assert all(p.read_bytes()==raw for p,raw in before.items())
 assert not (state.root/'production-current.json').exists() and not (state.root/'production-issues').exists()


def test_changed_profile_or_model_capsule_is_refused_before_transport(serving,selected):
 runtime=load(serving,selected);path,profile,state=selected
 runtime.capture_contexts(temperature_reader=lambda at,policy,epoch:receipt(at,epoch=epoch));product=runtime.prepare(NOW,serving['provider'])
 old=path.read_bytes();path.write_bytes(old+b'\n')
 with pytest.raises(ValueError,match='selection|profile'):runtime.verify(product)
 path.write_bytes(old)
 artifact=next((state.root/'production-models').glob('*.json'));artifact.write_bytes(artifact.read_bytes()+b'\n')
 with pytest.raises(ValueError,match='artifact|model'):runtime.verify(product)


def test_unavailable_current_temperature_metadata_keeps_valid_wind_and_names_raw_temperature(serving,selected):
 runtime=load(serving,selected);runtime.capture_contexts(temperature_reader=lambda *args:None)
 product=runtime.prepare(NOW,serving['provider']);body=product.to_dict()
 assert runtime.verify(product) is True
 assert any(r['kind']=='wind' and r['prediction'] is not None for r in body['rows'])
 assert all(r['prediction'] is None and r['reason']=='origin_measurement_context_unavailable' for r in body['rows'] if r['kind']=='temperature')


def test_unreviewed_profile_wrong_archive_and_shadow_mode_are_refused(serving,selected):
 from weather_learning.production_selection import from_profile
 from hashlib import sha256
 path,profile,state=selected
 with pytest.raises(ValueError):from_profile(path,expected_sha256='f'*64,archive=serving['read_source'].__self__,site=SITE,clock=lambda:NOW,guard=lambda:None)
 for change in [dict(parallel_shadow_required=True),dict(archive=str(state.root)),dict(authorization_policy_sha256='f'*64)]:
  private(path,profile|change)
  with pytest.raises(ValueError):load(serving,selected)


def test_expired_models_keep_original_clocks_and_use_named_raw_fallback(serving,selected):
 from weather_learning.production_selection import from_profile
 from weather_learning.provider import load_production_forecast
 from test_production_forecast import original
 from hashlib import sha256
 path,profile,state=selected;future=T+timedelta(days=31,hours=9,minutes=30);archive=serving['read_source'].__self__
 archive.store_snapshot(original(init=T+timedelta(days=31)))
 before={p:p.read_bytes() for p in (state.root/'production-models').glob('*.json')}
 runtime=from_profile(path,expected_sha256=sha256(path.read_bytes()).hexdigest(),archive=archive,site=SITE,clock=lambda:future,guard=lambda:None)
 runtime.capture_contexts(temperature_reader=lambda at,policy,epoch:receipt(at,epoch=epoch))
 provider=load_production_forecast(archive,decision_at=future,required_horizon=timedelta(hours=48),site=SITE)
 product=runtime.prepare(future,provider)
 assert product.to_dict()['rows'] and all(r['prediction'] is None for r in product.to_dict()['rows'])
 assert any(r['reason']=='registered_model_invalid_expired_or_missing_statistics' for r in product.to_dict()['rows'])
 assert runtime.verify(product) is True and all(p.read_bytes()==raw for p,raw in before.items())
