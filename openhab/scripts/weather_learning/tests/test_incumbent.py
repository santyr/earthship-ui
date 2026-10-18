from datetime import timedelta
import importlib,json,unittest
from learning_fixtures import T,SITE

class IncumbentTests(unittest.TestCase):
    def setUp(self):
        try:self.m=importlib.import_module('weather_learning.incumbent')
        except ModuleNotFoundError:self.fail('Isolated as-issued incumbent capture is not implemented')
        self.raw=dict(version=2,generatedAt=T.isoformat(),timezone=SITE.timezone,temperatureAdjustment={},days=[dict(date='2026-01-01',hours=[dict(at=(T+timedelta(hours=1)).isoformat(),tempF=68)])])

    def capture(self,raw=None):
        return self.m.capture_incumbent(json.dumps(self.raw if raw is None else raw),observed_at=T+timedelta(minutes=25),site=SITE)

    def test_control_preserves_actual_observation_clock_and_original_state(self):
        metadata,values,original=self.capture()
        self.assertEqual(values[T+timedelta(hours=1)],20)
        self.assertEqual(metadata['observedAt'],(T+timedelta(minutes=25)).isoformat())
        self.assertEqual(json.loads(original['state']),self.raw)

    def test_future_stale_unknown_or_unbounded_control_is_refused(self):
        for change in ('future','stale','version','size'):
            raw=dict(self.raw)
            if change=='future':raw['generatedAt']=(T+timedelta(hours=1)).isoformat()
            if change=='stale':raw['generatedAt']=(T-timedelta(days=2)).isoformat()
            if change=='version':raw['version']=99
            if change=='size':raw['extra']='x'*65536
            with self.subTest(change=change),self.assertRaises(ValueError):self.capture(raw)

    def test_duplicate_target_or_nonfinite_temperature_is_refused(self):
        self.raw['days'][0]['hours']*=2
        with self.assertRaises(ValueError):self.capture()
        self.raw['days'][0]['hours']=self.raw['days'][0]['hours'][:1]
        self.raw['days'][0]['hours'][0]['tempF']=float('nan')
        with self.assertRaises(ValueError):self.capture()

if __name__=='__main__':unittest.main()
