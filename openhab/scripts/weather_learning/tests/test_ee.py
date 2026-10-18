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
