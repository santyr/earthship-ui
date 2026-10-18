"""Google native forcing retains original capsules, never legacy SQL receipts."""
from copy import deepcopy
from datetime import timedelta
import importlib,pathlib,tempfile,unittest
from unittest.mock import patch
from learning_fixtures import T,SITE
from test_provider import full_snapshot
from weather_learning.archive import Archive

class NativeForecastTests(unittest.TestCase):
    def setUp(self):
        self.api=importlib.import_module('weather_learning.native_forecast')
        self.origin=T+timedelta(hours=8,minutes=15)
        self.known=self.origin-timedelta(seconds=30)
        self.snapshot=full_snapshot()
    def make(self,**kwargs):
        return self.api.make_native_forecast(self.snapshot,origin=self.origin,available_by=self.known,horizon_hours=24,site=kwargs.get('site',SITE))
    def test_capsule_has_left_bracket_and_google_identity_without_fake_weather_codes(self):
        value=self.make()
        self.assertEqual(value['source'],'weathernext3')
        self.assertEqual(len(value['rows']),26)
        self.assertEqual(value['rows'][0]['at'],(T+timedelta(hours=8)).isoformat())
        self.assertEqual(value['rows'][-1]['at'],(T+timedelta(hours=33)).isoformat())
        self.assertEqual(value['rows'][0]['tempF'],50)
        self.assertEqual(value['rows'][0]['radiationWm2'],100)
        self.assertAlmostEqual(value['rows'][0]['windMph'],3600/1609.344)
        self.assertTrue(all(row['weatherCode'] is None for row in value['rows']))
        self.assertNotIn('metric_receipts',value)
        self.assertEqual(value['issued_at'],T.isoformat())
        self.assertEqual(value['available_by'],self.known.isoformat())
        self.assertEqual(self.api.validate_native_forecast(value),value)
    def test_replay_reads_no_files_database_or_external_api(self):
        value=self.make()
        with patch('builtins.open',side_effect=AssertionError('file access')),patch('sqlite3.connect',side_effect=AssertionError('database access')),patch('requests.Session.request',side_effect=AssertionError('network access')),patch('urllib.request.urlopen',side_effect=AssertionError('network access')):
            self.assertEqual(self.api.validate_native_forecast(value),value)
    def test_rows_clocks_and_original_capsule_cannot_be_resealed_as_different_weather(self):
        from weather_learning.contracts import identity
        for damage in ('row','available','origin','original','site'):
            with self.subTest(damage=damage):
                value=deepcopy(self.make())
                if damage=='row':value['rows'][0]['tempF']+=5;value['rows_sha256']=identity(value['rows'])
                if damage=='available':value['available_by']=(self.origin+timedelta(seconds=1)).isoformat()
                if damage=='origin':value['origin']=(self.origin+timedelta(hours=1)).isoformat()
                if damage=='original':value['source_original']['uncompressed_sha256']='f'*64
                if damage=='site':value['site']['latitude']=0
                value['forecast_sha256']=identity({k:v for k,v in value.items() if k!='forecast_sha256'})
                with self.assertRaises(ValueError):self.api.validate_native_forecast(value)
    def test_future_historical_or_old_source_is_refused(self):
        for damage in ('future','historical','stale'):
            with self.subTest(damage=damage):
                original=deepcopy(self.snapshot)
                if damage=='future':self.snapshot['ingestion_completed_at']=(self.known+timedelta(seconds=1)).isoformat()
                if damage=='historical':self.snapshot['historical']=True
                if damage=='stale':self.origin=T+timedelta(hours=25);self.known=self.origin-timedelta(seconds=30)
                with self.assertRaises(ValueError):self.make()
                self.snapshot=original
    def test_missing_left_bracket_refuses_instead_of_extrapolating(self):
        self.origin=T+timedelta(minutes=30);self.known=self.origin-timedelta(seconds=1)
        with self.assertRaises(ValueError):self.make()
    def test_missing_required_value_is_not_zeroed(self):
        self.snapshot=full_snapshot()
        from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
        parts=[]
        for original in self.snapshot['source_originals']:
            raw=deepcopy(original['payload']);bands=raw['region'][0][4:]
            if bands[0].startswith('surface_'):raw['region'][8][4]=None
            parts.append(parse_collection_response(raw,collection=original['collection'],bands=bands,site=SITE,initialized_at=T,horizon=80))
        self.snapshot=make_snapshot(parts,site=SITE,initialized_at=T,first_seen_at=T+timedelta(minutes=20),completed_at=T+timedelta(minutes=21))
        with self.assertRaises(ValueError):self.make()
    def test_archive_loader_never_uses_an_external_or_incumbent_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            archive=Archive(pathlib.Path(directory));archive.store_snapshot(self.snapshot)
            actual=self.api.load_native_forecast(archive,origin=self.origin,available_by=self.known,horizon_hours=24,site=SITE)
            self.assertEqual(actual,self.make())
            with patch.object(archive,'eligible_snapshot',return_value=None),patch('urllib.request.urlopen',side_effect=AssertionError('provider fallback')):
                self.assertIsNone(self.api.load_native_forecast(archive,origin=self.origin,available_by=self.known,horizon_hours=24,site=SITE))
    def test_capsule_decompression_is_bounded_and_trailing_data_is_refused(self):
        from weather_learning.contracts import identity
        value=self.make();value['source_original']['uncompressed_bytes']=1000000000
        value['forecast_sha256']=identity({k:v for k,v in value.items() if k!='forecast_sha256'})
        with self.assertRaises(ValueError):self.api.validate_native_forecast(value)
        import base64
        value=self.make();packed=base64.b64decode(value['source_original']['data'])
        value['source_original']['data']=base64.b64encode(packed+b'trailing').decode()
        value['forecast_sha256']=identity({k:v for k,v in value.items() if k!='forecast_sha256'})
        with self.assertRaises(ValueError):self.api.validate_native_forecast(value)
