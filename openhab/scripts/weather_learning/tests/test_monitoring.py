"""Scheduled weather scores retain original issues and never invent observations or refit."""
from datetime import timedelta
from pathlib import Path
import tempfile,unittest
from unittest.mock import Mock,patch
from learning_fixtures import T,SITE,EPOCH,REVISION,full_snapshot,receipt
from weather_learning.archive import Archive
from weather_learning.shadow import ShadowStore,shadow_once

class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.archive=Archive(root/'archive');self.state=ShadowStore(root/'shadow')
        self.archive.store_snapshot(full_snapshot(hours=80));self.issue=T+timedelta(minutes=30)
        self.payload=shadow_once(self.archive,self.state,now=self.issue,site=SITE,sensor_epoch=EPOCH,code_revision=REVISION,horizon=48,clock=lambda:self.issue+timedelta(seconds=1))
        self.temperature=Mock(side_effect=lambda targets,assessed_at:{t:receipt(t,12) for t in targets})
        self.solar=Mock(return_value=None);self.rain=Mock(return_value=None)
    def run_monitor(self,now=None,**kwargs):
        from weather_learning.monitoring import monitor_once
        return monitor_once(self.archive,self.state,now=now or T+timedelta(hours=3),site=SITE,sensor_epoch=EPOCH,
            code_revision=REVISION,observation_policy_sha256='a'*64,read_temperature=self.temperature,
            read_solar=self.solar,read_rain=self.rain,**kwargs)
    def test_completed_raw_temperature_targets_score_without_fitting_a_candidate(self):
        with patch('weather_learning.training.fit_bias',side_effect=AssertionError('fitting refused')):
            report=self.run_monitor()
        self.assertEqual(report['temperature']['raw']['pairs'],2)
        self.assertAlmostEqual(report['temperature']['raw']['mae_c'],2)
        self.assertIsNone(report['temperature']['candidate'])
        self.assertFalse(report['automatic_actuation']);self.assertFalse(report['calibration_qualified'])
    def test_immature_solar_and_rain_windows_are_pending_and_not_queried(self):
        report=self.run_monitor()
        self.solar.assert_not_called();self.rain.assert_not_called()
        self.assertGreater(report['pending']['solar'],0);self.assertGreater(report['pending']['rain'],0)
    def test_qualified_source_absence_is_not_scored_as_zero(self):
        self.temperature.side_effect=lambda targets,assessed_at:{}
        report=self.run_monitor(now=T+timedelta(days=2))
        self.assertIsNone(report['temperature']['raw'])
        self.assertGreater(report['temperature']['withheld'],0)
        self.solar.assert_called();self.rain.assert_called()
        self.assertEqual(report['solar']['pairs'],[]);self.assertEqual(report['rain']['pairs'],[])
    def test_future_local_receipt_is_withheld(self):
        now=T+timedelta(hours=3)
        def future(targets,assessed_at):
            rows={t:receipt(t,12) for t in targets}
            for row in rows.values():row['storedAt']=now+timedelta(hours=1)
            return rows
        self.temperature.side_effect=future
        report=self.run_monitor(now=now)
        self.assertIsNone(report['temperature']['raw']);self.assertEqual(report['temperature']['withheld'],2)
    def test_only_explicit_apply_publishes_report_and_original_pairs(self):
        self.run_monitor();self.assertFalse((self.state.root/'weather-performance.json').exists())
        report=self.run_monitor(apply=True)
        import json
        self.assertEqual(json.loads((self.state.root/'weather-performance.json').read_text()),report)
        self.assertEqual(len(report['temperature']['pair_manifest']),2)
    def test_missing_original_is_a_named_dependency_not_whole_monitor_failure(self):
        path=next((self.state.root/'issues').glob('*.json'));path.unlink()
        report=self.run_monitor(apply=True)
        self.assertIsNone(report['temperature']['raw'])
        self.assertEqual(report['temperature']['work']['states']['missing_original'],1)
        self.assertTrue(any(row['kind']=='original_issue' for row in report['source_withheld']))
    def test_durable_completed_scores_survive_restart_without_reading_or_reposting(self):
        first=self.run_monitor(apply=True)
        self.temperature.reset_mock()
        second=self.run_monitor(apply=True)
        self.temperature.assert_not_called()
        self.assertEqual(second['temperature']['pair_manifest'],first['temperature']['pair_manifest'])
        self.assertEqual(second['temperature']['work']['states']['completed'],2)
    def test_preview_never_creates_or_advances_persistent_scoring_index(self):
        self.run_monitor()
        self.assertFalse((self.state.root/'pending-scores.sqlite3').exists())
        self.assertEqual(list(self.state.root.glob('monitor-preview-*')),[])
    def test_temperature_reader_outage_is_scoped_and_defers_instead_of_zero(self):
        self.temperature.side_effect=ConnectionError('fixture dependency outage')
        report=self.run_monitor(apply=True)
        self.assertIsNone(report['temperature']['raw'])
        self.assertTrue(any(row['kind']=='temperature' for row in report['source_withheld']))
        self.assertEqual(report['temperature']['work']['states']['work_dependency_reasons']['observation_missing'],2)
    def test_malformed_optional_solar_source_does_not_suppress_valid_temperature(self):
        self.solar.return_value={'invalid':'source'}
        report=self.run_monitor(now=T+timedelta(days=2))
        self.assertIsNotNone(report['temperature']['raw'])
        self.assertTrue(any(row['kind']=='solar' for row in report['source_withheld']))

    def test_correction_pipeline_shares_deadline_budget_and_optional_failure_is_scoped(self):
        corrections=Mock(return_value={'schema':'fixture-corrections','observations_attempted':0})
        report=self.run_monitor(read_corrections=corrections)
        self.assertEqual(report['corrections']['schema'],'fixture-corrections')
        args=corrections.call_args.kwargs
        self.assertLessEqual(args['limit'],32)
        self.assertLessEqual(report['temperature']['work']['batch_limit'],32)
        self.assertEqual(args['apply'],False)
        corrections.side_effect=ConnectionError('optional diagnostic unavailable')
        report=self.run_monitor(read_corrections=corrections)
        self.assertIsNotNone(report['temperature']['raw'])
        self.assertEqual(report['corrections']['status'],'unavailable')
        self.assertFalse(report['automatic_actuation'])
