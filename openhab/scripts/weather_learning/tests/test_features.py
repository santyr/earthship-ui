from copy import deepcopy
from datetime import timedelta
import importlib,unittest
from learning_fixtures import T,EPOCH,native_snapshot,receipt,pair

class FeatureTests(unittest.TestCase):
    def setUp(self):
        try:self.f=importlib.import_module('weather_learning.features')
        except ModuleNotFoundError:self.fail('WeatherNext/local feature boundary is not implemented')

    def test_google_target_preserves_original_issue_cell_and_spread(self):
        raw=native_snapshot()
        targets=self.f.temperature_targets(raw,issued_at=T+timedelta(minutes=30))
        self.assertEqual(len(targets),2)
        self.assertAlmostEqual(targets[-1].mean_c,10)
        self.assertAlmostEqual(targets[-1].spread_c,4)
        self.assertEqual(targets[-1].target_at,T+timedelta(hours=2))
        self.assertNotEqual(targets[-1].snapshot_digest,targets[-1].issue_digest)

    def test_late_backfilled_or_wrong_provider_forecasts_cannot_be_features(self):
        for change in ('historical','provider','late'):
            raw=native_snapshot()
            if change=='late':raw['ingestion_completed_at']=(T+timedelta(minutes=31)).isoformat()
            else:raw[change]=True if change=='historical' else 'openmeteo'
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.f.temperature_targets(raw,issued_at=T+timedelta(minutes=30))

    def test_modified_normalized_value_cannot_train_against_unchanged_original(self):
        raw=native_snapshot();raw['points'][0]['value']=80
        with self.assertRaises(ValueError):self.f.temperature_targets(raw,issued_at=T+timedelta(minutes=30))

    def test_original_snapshot_digest_is_checked(self):
        raw=native_snapshot();raw['snapshot_sha256']='b'*64
        with self.assertRaises(ValueError):self.f.temperature_targets(raw,issued_at=T+timedelta(minutes=30))

    def test_unqualified_stale_or_foreign_sensor_metadata_is_not_a_label(self):
        target=T+timedelta(hours=2)
        for change in ('missing','expired','foreign','future'):
            raw=receipt(target)
            if change=='missing':del raw['snapshotSha256']
            if change=='expired':raw['validUntil']=target
            if change=='foreign':raw['sensorEpoch']='00000000-0000-4000-8000-000000000003'
            if change=='future':raw['storedAt']=target+timedelta(seconds=1)
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.f.local_temperature_outcome(raw,target_at=target,assessed_at=target+timedelta(minutes=1),sensor_epoch=EPOCH)

    def test_local_observation_conversion_and_original_availability(self):
        target=T+timedelta(hours=2)
        outcome=self.f.local_temperature_outcome(receipt(target,0),target_at=target,assessed_at=target+timedelta(days=1),sensor_epoch=EPOCH)
        self.assertEqual(outcome.value_c,0)
        self.assertEqual(outcome.available_at,target)
        self.assertEqual(outcome.sensor_epoch,EPOCH)

    def test_recent_innovations_exclude_future_outcomes_and_other_epochs(self):
        early=pair(0,10,12);future=pair(2,10,40)
        other=pair(0,10,40,epoch='00000000-0000-4000-8000-000000000003')
        result=self.f.recent_innovation([early,future,other],issued_at=T+timedelta(days=1),cohort=early.cohort)
        self.assertAlmostEqual(result,2)

    def test_same_outcome_reissued_many_times_does_not_inflate_recent_error(self):
        sample=pair()
        self.assertAlmostEqual(self.f.recent_innovation([sample]*10,issued_at=T+timedelta(days=1),cohort=sample.cohort),2)

    def test_missing_quantile_withholds_residual_features_without_filling_zero(self):
        raw=native_snapshot();raw['points']=[p for p in raw['points'] if p['statistic']!='p10']
        # Original capsule must agree too; this is a genuinely absent product.
        original=raw['source_originals'][0]
        index=original['payload']['region'][0].index('station_head_temperature_2m_p10')
        for row in original['payload']['region']:row.pop(index)
        from weather_learning.contracts import identity
        for p in raw['points']:p['source_digest']=identity(original)
        target=self.f.temperature_targets(raw,issued_at=T+timedelta(minutes=30))[-1]
        self.assertIsNone(target.spread_c)
        with self.assertRaises(ValueError):self.f.feature_vector(target)

if __name__=='__main__':unittest.main()
