from datetime import datetime,timedelta,timezone
from copy import deepcopy
import unittest
from weather_learning.config import Site,COLLECTIONS
from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
T=datetime(2026,10,18,tzinfo=timezone.utc);S=Site(38.3739919,-105.7744609,'America/Denver')
def response():
 return dict(metadata=[{'system:index':'image1','start_time':T.isoformat(),'end_time':(T+timedelta(hours=1)).isoformat(),'forecast_hour':1,'ingestion_time_utc':1792281600000}],
  region=[['id','longitude','latitude','time','station_head_temperature_2m_mean'],['image1',-105.75,38.35,(T+timedelta(hours=1)).timestamp()*1000,273.15]])
class EEParsingTests(unittest.TestCase):
 def parse(self,raw=None,**kwargs):
  return parse_collection_response(response() if raw is None else raw,collection=COLLECTIONS['station'],bands=('station_head_temperature_2m_mean',),site=S,initialized_at=T,horizon=1,**kwargs)
 def test_native_point_units_provenance_and_source_metadata_retained(self):
  source,points=self.parse();self.assertEqual(points[0]['value'],0);self.assertEqual(source['payload']['metadata'][0]['forecast_hour'],1)
  self.assertEqual(points[0]['source_ref'],COLLECTIONS['station']+'/image1')
 def test_missing_value_not_zero(self):
  raw=response();raw['region'][1][-1]=None;_,points=self.parse(raw);self.assertIsNone(points[0]['value'])
 def test_missing_target_or_unknown_schema_refused(self):
  for change in ('missing_row','unknown_band','wrong_init','wrong_valid','wrong_cell'):
   raw=response()
   if change=='missing_row':raw['region']=raw['region'][:1]
   if change=='unknown_band':raw['region'][0][-1]='invented_mean'
   if change=='wrong_init':raw['metadata'][0]['start_time']=(T-timedelta(hours=1)).isoformat()
   if change=='wrong_valid':raw['region'][1][3]+=3600000
   if change=='wrong_cell':raw['region'][1][1]=0
   with self.subTest(change=change),self.assertRaises(ValueError):self.parse(raw)
 def test_source_initialization_clock_does_not_replace_forecast_target(self):
  raw=response();raw['metadata'][0]['system:time_start']=T.timestamp()*1000
  raw['region'][1][3]=T.timestamp()*1000
  source,points=self.parse(raw)
  self.assertEqual(points[0]['valid_at'],'2026-10-18T01:00:00+00:00')
  self.assertEqual(source['payload']['region'][1][3],1792281600000)
 def test_reported_source_clock_must_match_row_and_known_run_or_target(self):
  for clock,row_clock in ((T.timestamp()*1000,T.timestamp()*1000+1),(T.timestamp()*1000+1,T.timestamp()*1000+1),(float('nan'),T.timestamp()*1000)):
   raw=response();raw['metadata'][0]['system:time_start']=clock;raw['region'][1][3]=row_clock
   with self.subTest(clock=clock),self.assertRaises(ValueError):self.parse(raw)
 def test_gridded_rain_products_retain_separate_original_values(self):
  raw=response();bands=['total_precipitation_1hr_mean','imerg_tp_1hr_mean','experimental_tp_1hr_mean']
  raw['region']=[['id','longitude','latitude','time',*bands],['image1',-105.8,38.4,1792285200000,.001,.002,.003]]
  source,points=parse_collection_response(raw,collection=COLLECTIONS['gridded'],bands=bands,site=S,initialized_at=T,horizon=1)
  self.assertEqual([row['variable'] for row in points],['total_precipitation_1hr','imerg_tp_1hr','experimental_tp_1hr'])
  self.assertEqual([row['value'] for row in points],[1.,2.,3.])
  self.assertEqual(source['payload']['region'][1][-3:],[.001,.002,.003])
 def test_other_collection_or_global_download_refused(self):
  with self.assertRaises(ValueError):parse_collection_response(response(),collection='projects/other/assets/foo',bands=('station_head_temperature_2m_mean',),site=S,initialized_at=T,horizon=1)
 def test_source_availability_and_initialization_remain_separate(self):
  source,points=self.parse();snap=make_snapshot([(source,points)],site=S,initialized_at=T,first_seen_at=T+timedelta(minutes=20),completed_at=T+timedelta(minutes=21))
  self.assertNotEqual(snap['initialized_at'],snap['first_seen_at']);self.assertEqual(len(snap['source_originals']),1)
 def test_upstream_ingest_field_required_not_invented(self):
  raw=response();del raw['metadata'][0]['ingestion_time_utc']
  with self.assertRaises(ValueError):self.parse(raw)
if __name__=='__main__':unittest.main()

import importlib.util
from unittest.mock import Mock,patch
from weather_learning.config import AccessPolicy
from weather_learning.transport import BoundedTransport
from weather_learning.weathernext_ee import EarthEngineReader
from test_transport import Session,Response
import json
@unittest.skipUnless(importlib.util.find_spec('ee'),'requires isolated pinned Earth Engine environment')
class SDKInitializationTests(unittest.TestCase):
 def test_sdk_bootstrap_does_not_set_deadline_before_sdk_initializes(self):
  reader=EarthEngineReader(policy=AccessPolicy(backend='earthengine',noncommercial_verified=True),site=S,credential_path='/unused')
  reader.transport=BoundedTransport(reader.policy,session=Session(Response(json.dumps({'registrationState':'REGISTERED_NOT_COMMERCIALLY'}).encode())))
  credential=Mock();credential.token='synthetic-'+str(id(self))
  with patch('weather_learning.weathernext_ee.load_credentials',return_value=credential),patch('ee.Initialize') as initialize:
   reader.initialize();initialize.assert_called_once();self.assertTrue(reader.ready)

@unittest.skipUnless(importlib.util.find_spec('ee'),'requires isolated pinned Earth Engine environment')
class NativeProjectionTests(unittest.TestCase):
 def test_query_preserves_native_projection_without_wkt_as_affine_transform(self):
  import ee,inspect
  from types import SimpleNamespace
  projection=SimpleNamespace(transform=lambda:'GEOGCS[WKT is a string]')
  signature=inspect.signature(ee.ImageCollection.getRegion)
  class Image:
   def select(self,*args):return self
   def projection(self):return projection
  class Collection:
   def filter(self,*args):return self
   def sort(self,*args):return self
   def limit(self,*args):return self
   def first(self):return Image()
   def select(self,*args):return self
   def toList(self,*args):return SimpleNamespace(map=lambda f:response()['metadata'])
   def getRegion(self,*args,**kwargs):
    bound=signature.bind(self,*args,**kwargs);bound.apply_defaults()
    if bound.arguments['crs'] is not projection or bound.arguments['crsTransform'] is not None:
     raise ValueError('native projection must retain its existing affine transform')
    return response()['region']
  reader=EarthEngineReader(policy=AccessPolicy(backend='earthengine',noncommercial_verified=True),site=S,credential_path='/unused',clock=lambda:T+timedelta(minutes=20))
  reader.ready=True
  reader.ee=SimpleNamespace(ImageCollection=lambda _:Collection(),Image=lambda x:x,
   Geometry=SimpleNamespace(Point=lambda x:tuple(x)),Filter=SimpleNamespace(eq=lambda *a:None,gte=lambda *a:None,lte=lambda *a:None),
   Dictionary=lambda d:SimpleNamespace(getInfo=lambda:d))
  result=reader.fetch_points(run={'start_time':T.isoformat()},bands_by_grid={'station':('station_head_temperature_2m_mean',)},horizon=1)
  self.assertEqual(result['points'][0]['value'],0)

@unittest.skipUnless(importlib.util.find_spec('ee'),'requires isolated pinned Earth Engine environment')
class WorkerCredentialScopesTests(unittest.TestCase):
 def test_signed_worker_request_can_read_external_raster_storage(self):
  import base64,tempfile
  from pathlib import Path
  from urllib.parse import parse_qs
  from cryptography.hazmat.primitives.asymmetric import rsa
  from cryptography.hazmat.primitives import serialization
  from weather_learning.config import PROJECT,READER
  from weather_learning.weathernext_ee import load_credentials
  # Generate disposable key material in memory; no real credential fixture.
  key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
  encoded=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'worker.json'
   path.write_text(json.dumps(dict(type='service_account',project_id=PROJECT,client_email=READER,token_uri='https://oauth2.googleapis.com/token',private_key=encoded)))
   path.chmod(0o600)
   credentials=load_credentials(path)
   def exchange(url,method,body,headers,**kwargs):
    assertion=parse_qs(body.decode())['assertion'][0]
    payload=assertion.split('.')[1];claims=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
    self.assertEqual(set(claims['scope'].split()),{'https://www.googleapis.com/auth/earthengine','https://www.googleapis.com/auth/devstorage.read_only'})
    self.assertEqual(claims['iss'],READER)
    from types import SimpleNamespace
    return SimpleNamespace(status=200,data=json.dumps({'access_token':str(id(self)),'expires_in':3600,'token_type':'Bearer'}).encode())
   credentials.refresh(exchange)
   self.assertIsNone(credentials.quota_project_id)
