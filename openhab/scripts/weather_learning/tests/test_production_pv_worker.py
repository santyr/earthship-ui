"""Real daily compiler/cache boundaries with isolated synthetic source adapters."""
from datetime import timedelta
from pathlib import Path
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest
from test_production_pv import fit,CONTEXT,MEASUREMENT,ORIGIN,geometry,forecast
from test_production_pv_runtime import write,AUTH
from native_solar_fixtures import SITE,ARRAY,HORIZON
from weather_learning.contracts import canonical,identity

@pytest.fixture
def daily(tmp_path,monkeypatch):
 import daily_pv_worker as worker
 import household_cycle_pressure,household_native_geometry_prepare,astro_geometry_worker
 import weather_learning.openhab as openhab
 import weather_learning.provider as provider
 import weather_learning.native_solar_forecast as native
 from weather_learning.archive import Archive
 from weather_learning.production_pv_runtime import runtime_manifest
 actual=Path(worker.__file__).resolve().parents[2];repo=tmp_path/'repo';(repo/'openhab/scripts').mkdir(parents=True)
 system=json.loads((actual/'openhab/household-pv-system.json').read_bytes());system['array']=ARRAY;system['recorded_at']=(ORIGIN-timedelta(days=1)).isoformat();system['orientation_source']['inclinometer_reading_degrees']=90-ARRAY['surface_tilt_degrees']
 horizon=json.loads((actual/'openhab/household-solar-horizon.json').read_bytes());horizon.update(profile=HORIZON,timezone=SITE.timezone,site_sha256=identity({k:SITE.__dict__[k] for k in ('latitude','longitude')}),recorded_at=system['recorded_at'])
 horizon['source']['retrieved_at']=system['recorded_at']
 import test_weather_energy_history as history
 import test_household_pv_window as power_fixture
 start=(ORIGIN+timedelta(hours=1)).replace(minute=0,second=0,microsecond=0)
 policy=json.dumps(dict(json.loads(power_fixture.POLICY),cutover=(start-timedelta(days=1)).isoformat()))
 monkeypatch.setattr(history,'START',start);monkeypatch.setattr(history,'END',start+timedelta(hours=1));monkeypatch.setattr(history,'POLICY',policy)
 measured=history.source()
 measurement=identity({k:measured[k] for k in ('policy_raw','bank_start','items')})
 power=policy.encode()
 system_path=write(repo/'openhab/household-pv-system.json',system,0o644);horizon_path=write(repo/'openhab/household-solar-horizon.json',horizon,0o644);power_path=write(tmp_path/'power.json',power,0o644)
 context=dict(CONTEXT,measurement_cohort_sha256=measurement,system_sha256=sha256(system_path.read_bytes()).hexdigest(),horizon_sha256=sha256(horizon_path.read_bytes()).hexdigest(),power_policy_sha256=sha256(power).hexdigest())
 from test_production_pv import rows
 population=rows()
 for row in population:
  row['cohort_sha256']=identity(dict(measurement=measurement,solar_grid=CONTEXT['solar_grid_sha256']))
  row['pair_sha256']=identity({k:v for k,v in row.items() if k!='pair_sha256'})
 model,_=fit(population,context=context,authorization=AUTH,authorization_sha256=identity(AUTH));model_path=write(tmp_path/'model.json',model.to_dict())
 profile=dict(schema='earthship-component-pv-production-profile/v1',model_path=str(model_path),model_file_sha256=sha256(model_path.read_bytes()).hexdigest(),calibration_sha256=model.to_dict()['calibration_sha256'],
  measurement_cohort_sha256=measurement,system_path=str(system_path),horizon_path=str(horizon_path),power_policy_path=str(power_path),runtime_sha256=identity(runtime_manifest()),authorization_policy_sha256=identity(AUTH),
  parallel_shadow_required=False,automatic_actuation=False)
 path=write(tmp_path/'profile.json',profile);libraries=write(tmp_path/'libraries.json',{})
 monkeypatch.setattr(worker,'__file__',str(repo/'openhab/scripts/daily_pv_worker.py'))
 monkeypatch.setattr(household_cycle_pressure,'PublicationHeadroom',lambda:SimpleNamespace(check=lambda:None))
 monkeypatch.setattr(household_native_geometry_prepare,'_library_paths',lambda raw:{})
 monkeypatch.setattr(astro_geometry_worker,'runtime_identity',lambda *a,**k:{'fixture':'native_runtime'})
 monkeypatch.setattr(Archive,'open_readonly',staticmethod(lambda p:object()))
 monkeypatch.setattr(worker,'day_geometry',lambda *a,**k:SimpleNamespace(sha256='f'*64,to_dict=lambda:{'caches':[{'positions':geometry(count=144)}]}))
 def oh_get(url):
  if url=='/services/org.openhab.i18n/config':return {'location':'40,-105','timezone':'UTC'}
  if url=='/things/astro:sun:local':return {'configuration':{'geolocation':'40,-105'},'statusInfo':{'status':'ONLINE'}}
  if url=='/addons/binding-astro':return {'installed':True,'version':'fixture_binding'}
  pytest.fail('unexpected source request '+url)
 monkeypatch.setattr(openhab,'oh_get',oh_get)
 monkeypatch.setattr(provider.Site,'from_openhab_config',classmethod(lambda cls,c:SITE))
 p=SimpleNamespace(to_dict=lambda:{'status':'AVAILABLE','provider_snapshot_sha256':'a'*64})
 monkeypatch.setattr(provider,'load_publication_forecast',lambda *a,**k:p)
 monkeypatch.setattr(provider,'forecast_payloads',lambda *a,**k:([],[],{'days':[{'date':'2026-06-21'}]}))
 monkeypatch.setattr(provider,'_presentation',lambda *a,**k:({'hours':[]},{}))
 monkeypatch.setattr(native,'load_component_forecast',lambda *a,**k:forecast(hours=12))
 args=dict(archive_path=tmp_path/'archive',state_path=tmp_path/'state',output_path=tmp_path/'published.json',libraries_path=libraries,
  component_profile_path=path,component_profile_sha256=sha256(path.read_bytes()).hexdigest(),clock=lambda:ORIGIN)
 return worker,args,path

def test_component_mode_defaults_to_preparation_without_public_cache(daily):
 worker,args,_=daily;value=worker.run(**args)
 assert value['status']=='component_pv_prepared' and value['production_states_written'] is False
 assert value['view']['schema']=='earthship-daily-pv-potential/v4' and value['available_days']==1
 assert not args['output_path'].exists() and not list(args['state_path'].glob('*.emission.json'))

def test_explicit_cache_publication_retains_originals_and_confirmed_bytes(daily):
 worker,args,_=daily;value=worker.run(**args,component_publish=True)
 assert value['status']=='component_daily_pv_published' and value['production_retention_status']=='CONFIRMED'
 emission=json.loads((args['state_path']/(value['emission_sha256']+'.emission.json')).read_bytes())
 receipt=json.loads((args['state_path']/(value['receipt_sha256']+'.receipt.json')).read_bytes())
 assert emission['issued'] is True and receipt['issued'] is False
 assert emission['view_bytes_sha256']==sha256(args['output_path'].read_bytes()).hexdigest()
 assert emission['receipt_sha256']==receipt['receipt_sha256']

def test_failed_retention_after_real_cache_replacement_preserves_published_truth_and_cli_nonzero(daily,monkeypatch,capsys):
 worker,args,_=daily;save=worker.save
 def fail_emission(path,value):
  if value.get('schema')=='earthship-confirmed-component-daily-emission/v1':raise OSError('synthetic original-retention failure')
  return save(path,value)
 monkeypatch.setattr(worker,'save',fail_emission);run=worker.run
 monkeypatch.setattr(worker,'run',lambda **kw:run(**dict(kw,clock=lambda:ORIGIN)))
 argv=['--archive',str(args['archive_path']),'--state',str(args['state_path']),'--output',str(args['output_path']),'--libraries',str(args['libraries_path']),
  '--component-profile',str(args['component_profile_path']),'--component-profile-sha256',args['component_profile_sha256'],'--component-publish']
 assert worker.main(argv)==1
 value=json.loads(capsys.readouterr().out.splitlines()[-1])
 assert value['status']=='PUBLISHED' and value['production_states_written'] is True and value['production_retention_status']=='FAILED_AFTER_PUBLICATION'
 assert json.loads(args['output_path'].read_bytes())['schema']=='earthship-daily-pv-potential/v4'

def test_concurrent_profile_change_refuses_before_any_public_cache(daily,monkeypatch):
 worker,args,path=daily;save=worker.save;changed=[]
 def change_after_original(path2,value):
  result=save(path2,value)
  if value.get('schema')=='earthship-daily-pv-potential-receipt/v2':
   path.write_bytes(path.read_bytes()+b'\n');changed.append(True)
  return result
 monkeypatch.setattr(worker,'save',change_after_original)
 with pytest.raises(ValueError):worker.run(**args,component_publish=True)
 assert changed==[True] and not args['output_path'].exists()

def test_cache_write_failure_never_claims_the_original_cache_was_preserved(daily,monkeypatch):
 worker,args,_=daily;save=worker.save
 def fail_cache(path,value):
  if path==args['output_path']:raise OSError('synthetic cache transport failure')
  return save(path,value)
 monkeypatch.setattr(worker,'save',fail_cache)
 value=worker.run(**args,component_publish=True)
 assert value['status']=='PUBLICATION_UNCERTAIN' and value['production_states_written'] is None

def test_full_original_store_refuses_before_public_cache_or_new_receipt(daily):
 worker,args,_=daily
 args['state_path'].mkdir(mode=0o700)
 occupied=args['state_path']/'retained-original.json'
 with occupied.open('wb') as stream:stream.truncate(2*1024**3-1)
 occupied.chmod(0o600)
 with pytest.raises(ValueError,match='capacity'):worker.run(**args,component_publish=True)
 assert not args['output_path'].exists() and not list(args['state_path'].glob('*.receipt.json'))
