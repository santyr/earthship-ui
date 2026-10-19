"""Production short/extended forecasts retain independent original provenance."""
from datetime import timedelta
import json,pathlib,tempfile,unittest
from learning_fixtures import T,SITE,full_snapshot
from weather_learning.archive import Archive
from weather_learning import provider as p
from weather_learning.production_publish import production_states

class DualHorizonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.archive=Archive(pathlib.Path(self.tmp.name))
        self.long=self.archive.store_snapshot(full_snapshot(hours=360))
        self.short=self.archive.store_snapshot(full_snapshot(T+timedelta(hours=2),hours=48,temperature_k=293.15))
        self.now=T+timedelta(hours=10,minutes=30)
    def load(self):
        self.assertTrue(hasattr(p,'load_publication_forecast'),'publisher needs independent near-term and extended selection')
        return p.load_publication_forecast(self.archive,decision_at=self.now,site=SITE)
    def test_hourly_uses_newer_interim_and_daily_retains_extended_original(self):
        value=self.load();raw=value.to_dict();states=production_states(value,now=self.now)
        detail=json.loads(states['Forecast_10Day_JSON'])
        self.assertEqual(raw['source']['snapshot_sha256'],self.long)
        self.assertEqual(raw['near_term']['source']['snapshot_sha256'],self.short)
        self.assertEqual(detail['profiles']['nearTerm']['source']['snapshot_sha256'],self.short)
        self.assertEqual(detail['profiles']['extended']['source']['snapshot_sha256'],self.long)
        hours=[h for d in detail['days'] for h in d['hours']]
        self.assertTrue(all(h.get('forecastProfile')=='nearTerm' for h in hours[:24]))
        self.assertTrue(all(h.get('forecastProfile','extended')=='extended' for h in hours[25:]))
        self.assertEqual(hours[0]['tempF'],68)
        self.assertEqual(hours[25]['tempF'],50)
        self.assertEqual(detail['days'][1]['summary']['forecastProfile'],'extended')
        self.assertEqual(detail['profiles']['nearTerm']['requiredHorizonSeconds'],86400)
        today=detail['days'][0]['summary']
        self.assertEqual(today['precipitationScope'],'remaining')
        self.assertAlmostEqual(today['precipSumIn'],20/25.4)
        self.assertIn('T04:00:00',today['precipitationFromAt'])
        self.assertIn('T00:00:00',today['precipitationThroughAt'])
        self.assertAlmostEqual(json.loads(states['Forecast_Daily_JSON'])[0]['a'],24/25.4)
        self.assertAlmostEqual(float(states['Forecast_Daily_PrecipSum'].split()[0]),24)
        self.assertLess(len(states['Forecast_10Day_JSON'].encode()),65536)
        self.assertEqual(len(p.publication_sources(value)),2)
    def test_no_extended_original_still_serves_near_term_without_invented_long_range(self):
        with tempfile.TemporaryDirectory() as directory:
            self.archive=Archive(pathlib.Path(directory));self.archive.store_snapshot(full_snapshot(T+timedelta(hours=2),hours=48,temperature_k=293.15))
            detail=json.loads(production_states(self.load(),now=self.now)['Forecast_10Day_JSON'])
        self.assertEqual(detail['providerStatus'],'AVAILABLE')
        self.assertEqual(detail['profiles']['extended']['status'],'UNAVAILABLE')
        self.assertEqual(detail['profiles']['nearTerm']['status'],'AVAILABLE')
        self.assertLessEqual(sum(len(d['hours']) for d in detail['days']),25)
        self.assertIsNone(detail['source'])
    def test_one_retained_full_run_can_supply_both_profiles_without_duplicate_source_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            self.archive=Archive(pathlib.Path(directory));self.archive.store_snapshot(full_snapshot(hours=360))
            value=self.load();detail=json.loads(production_states(value,now=self.now)['Forecast_10Day_JSON'])
        self.assertEqual(detail['profiles']['nearTerm']['source'],detail['profiles']['extended']['source'])
        self.assertEqual(len(p.publication_sources(value)),1)
    def test_expired_profiles_withdraw_all_predictions(self):
        self.now=T+timedelta(hours=27)
        states=production_states(self.load(),now=self.now);detail=json.loads(states['Forecast_10Day_JSON'])
        self.assertEqual(detail['providerStatus'],'UNAVAILABLE');self.assertEqual(detail['days'],[])
        self.assertEqual(states['Forecast_Temp'],'UNDEF');self.assertEqual(states['Forecast_Hourly_JSON'],'[]')

if __name__=='__main__':unittest.main()
