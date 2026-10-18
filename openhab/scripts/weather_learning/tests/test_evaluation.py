from dataclasses import replace
from datetime import timedelta
import importlib,unittest
from learning_fixtures import T,EPOCH,REVISION,pair

class EvaluationTests(unittest.TestCase):
    def setUp(self):
        try:self.e=importlib.import_module('weather_learning.evaluation')
        except ModuleNotFoundError:self.fail('Chronological WeatherNext evaluation is not implemented')
        from weather_learning.training import fit_bias
        self.train=[pair(day) for day in range(8)]
        self.holdout=[pair(day) for day in range(10,14)]
        self.model=fit_bias(self.train,cutoff=T+timedelta(days=8),code_revision=REVISION)
        self.policy=self.e.EvaluationPolicy(declared_at=T+timedelta(days=8),train_end=T+timedelta(days=8),holdout_start=T+timedelta(days=10),holdout_end=T+timedelta(days=14),embargo_hours=48)

    def test_chronological_split_sorts_and_embargoes_instead_of_random_rows(self):
        split=self.e.chronological_split(list(reversed(self.train+[pair(8),pair(9)]+self.holdout)),self.policy)
        self.assertEqual(len(split.train),8)
        self.assertEqual(len(split.holdout),4)
        self.assertEqual(split.excluded,2)
        self.assertEqual(split.train[0].outcome.target_at,T+timedelta(hours=2))

    def test_overlap_with_holdout_target_is_excluded_from_training(self):
        overlap=pair(7,hour=72)
        split=self.e.chronological_split(self.train+[overlap]+self.holdout,self.policy)
        self.assertEqual(len(split.train),8)
        self.assertEqual(split.excluded,1)

    def test_holdout_policy_must_precede_holdout_and_enforce_embargo(self):
        for policy in (replace(self.policy,declared_at=T+timedelta(days=11)),replace(self.policy,holdout_start=T+timedelta(days=9))):
            with self.subTest(policy=policy),self.assertRaises(ValueError):self.e.chronological_split(self.holdout,policy)

    def test_raw_and_corrected_scores_use_day_weighted_metrics(self):
        report=self.e.evaluate(self.model,self.holdout,self.policy)
        self.assertAlmostEqual(report['scores']['raw']['mae_c'],2)
        self.assertAlmostEqual(report['scores']['candidate']['mae_c'],0)
        self.assertEqual(report['scores']['candidate']['target_dates'],4)
        self.assertEqual(report['qualification'],'SHADOW_ONLY')
        self.assertIn('prospective_acquisition',report['missing_release_evidence'])
        self.assertEqual(report['model_sha256'],self.model['artifact_sha256'])

    def test_empty_holdout_reports_unavailable_metrics_without_nan(self):
        report=self.e.evaluate(self.model,[],self.policy)
        self.assertIsNone(report['scores']['candidate'])
        self.assertIsNone(report['paired_incumbent_comparison']['relative_mae_gain'])
        self.assertEqual(report['holdout_pairs'],0)

    def test_only_incumbent_issues_available_at_the_same_decision_are_compared(self):
        first=self.holdout[0].forecast
        original=self.e.IncumbentForecast(issued_at=first.issued_at,available_at=first.issued_at,target_at=first.target_at,value_c=13,source_digest='b'*64)
        late=replace(original,issued_at=first.issued_at+timedelta(minutes=1),available_at=first.issued_at+timedelta(minutes=1),value_c=0)
        report=self.e.evaluate(self.model,self.holdout,self.policy,incumbent=[original,late])
        comparison=report['paired_incumbent_comparison']
        self.assertEqual(comparison['pairs'],1)
        self.assertAlmostEqual(comparison['incumbent']['mae_c'],1)
        self.assertAlmostEqual(comparison['relative_mae_gain'],1)

    def test_persistence_uses_only_prior_qualified_local_observations(self):
        report=self.e.evaluate(self.model,self.holdout,self.policy,prior_outcomes=[pair(9,actual_c=11).outcome])
        self.assertEqual(report['scores']['persistence']['pairs'],4)
        self.assertAlmostEqual(report['scores']['persistence']['mae_c'],.25)

    def test_future_persistence_value_cannot_change_an_earlier_forecast(self):
        report=self.e.evaluate(self.model,self.holdout[:1],self.policy,prior_outcomes=[pair(11,actual_c=40).outcome])
        self.assertIsNone(report['scores']['persistence'])

    def test_horizon_and_regime_gaps_are_explicit(self):
        report=self.e.evaluate(self.model,self.holdout+[pair(10,hour=48)],self.policy,regimes_by_day={'2026-01-10':('cloudy',)})
        self.assertEqual(set(report['by_horizon']),{'0-24h','24-72h'})
        self.assertIn('cloudy',report['by_regime'])
        self.assertIn('unclassified',report['by_regime'])
        self.assertIn('cold_front',report['missing_regimes'])

    def test_training_or_out_of_window_rows_cannot_be_scored_as_holdout(self):
        for sample in (self.train[0],pair(14)):
            with self.subTest(sample=sample.forecast.target_at),self.assertRaises(ValueError):self.e.evaluate(self.model,[sample],self.policy)

    def test_repeated_pairs_do_not_inflate_metrics_or_report_identity(self):
        once=self.e.evaluate(self.model,self.holdout,self.policy)
        repeated=self.e.evaluate(self.model,self.holdout+self.holdout,self.policy)
        self.assertEqual(once['report_sha256'],repeated['report_sha256'])
        self.assertEqual(repeated['holdout_pairs'],4)

if __name__=='__main__':unittest.main()
