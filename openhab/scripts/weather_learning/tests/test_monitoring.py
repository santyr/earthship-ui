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

    def test_legacy_window_reads_also_consume_the_job_observation_budget(self):
        for day in (1,2,3):
            origin=T+timedelta(days=day)
            self.archive.store_snapshot(full_snapshot(init=origin,hours=360))
            shadow_once(self.archive,self.state,now=origin+timedelta(minutes=30),site=SITE,
                sensor_epoch=EPOCH,code_revision=REVISION,horizon=336,clock=lambda:origin+timedelta(minutes=31))
        report=self.run_monitor(now=T+timedelta(days=5),apply=True)
        legacy=self.solar.call_count+self.rain.call_count
        scored=report['temperature']['work']['states'].get('completed',0)
        self.assertGreater(legacy,0)
        self.assertLessEqual(scored+legacy,64)

    def test_solar_derivation_failure_leaves_temperature_and_corrections_publishable(self):
        with patch('weather_learning.monitoring.solar_window_forecast',side_effect=ValueError('private fixture detail')):
            report=self.run_monitor(apply=True,read_corrections=lambda **kw:dict(status='fixture_correction_completed'))
        self.assertEqual(report['temperature']['raw']['pairs'],2)
        self.assertEqual(report['corrections']['status'],'fixture_correction_completed')
        self.assertEqual(report['solar']['pairs'],[])
        self.assertEqual(report['pending']['solar'],0)
        self.assertTrue(any(r['kind']=='solar_derivation' and r['reason']=='ValueError' for r in report['source_withheld']))
        self.assertNotIn('private fixture detail',str(report))

    def test_rain_derivation_failure_leaves_temperature_and_solar_work_publishable(self):
        with patch('weather_learning.monitoring.rain_day_forecast',side_effect=ValueError('fixture grid unavailable')):
            report=self.run_monitor(apply=True)
        self.assertEqual(report['temperature']['raw']['pairs'],2)
        self.assertGreater(report['pending']['solar'],0)
        self.assertEqual(report['pending']['rain'],0)
        self.assertTrue(any(r['kind']=='rain_derivation' for r in report['source_withheld']))

    def test_bad_solar_issue_does_not_discard_a_later_valid_issue(self):
        from weather_learning.monitoring import solar_window_forecast
        origin=T+timedelta(days=1)
        self.archive.store_snapshot(full_snapshot(init=origin,hours=80))
        shadow_once(self.archive,self.state,now=origin+timedelta(minutes=30),site=SITE,sensor_epoch=EPOCH,
            code_revision=REVISION,horizon=48,clock=lambda:origin+timedelta(minutes=31))
        def solar(snapshot,**kw):
            if kw['issued_at']==self.issue:raise ValueError('fixture original grid')
            return solar_window_forecast(snapshot,**kw)
        with patch('weather_learning.monitoring.solar_window_forecast',side_effect=solar):
            report=self.run_monitor(now=T+timedelta(days=2),apply=True)
        self.assertEqual(len(report['solar']['decisions']),1)
        self.assertGreater(report['temperature']['raw']['pairs'],2)
        self.assertEqual(len([r for r in report['source_withheld'] if r['kind']=='solar_derivation']),1)

    def test_optional_local_outcome_failures_are_not_pending_or_zero_observations(self):
        self.solar.side_effect=ConnectionError('local source unavailable')
        self.rain.side_effect=ConnectionError('local source unavailable')
        report=self.run_monitor(now=T+timedelta(days=2),apply=True)
        self.assertIsNotNone(report['temperature']['raw'])
        self.assertEqual({r['kind'] for r in report['source_withheld']},{'solar','rain'})
        self.assertEqual(report['pending'],dict(solar=0,rain=0))
        self.assertEqual(report['solar']['pairs'],[]);self.assertEqual(report['rain']['pairs'],[])

    def test_aggregation_failure_preserves_committed_scores_across_restart(self):
        for domain in ('solar','rain'):
            with self.subTest(domain=domain):
                with patch('weather_learning.monitoring.'+('compare_solar_windows' if domain=='solar' else 'compare_rain_products'),
                           side_effect=ValueError('fixture conflicting originals')):
                    first=self.run_monitor(apply=True)
                self.assertEqual(first['temperature']['raw']['pairs'],2)
                self.assertEqual(first[domain]['pairs'],[])
                self.assertTrue(any(r['kind']==domain+'_aggregation' for r in first['source_withheld']))
                self.temperature.reset_mock()
                second=self.run_monitor(apply=True)
                self.assertEqual(first['temperature']['pair_manifest'],second['temperature']['pair_manifest'])
                self.assertEqual(second['temperature']['work']['states']['completed'],2)
                self.temperature.assert_not_called()

    def test_global_deadline_and_admission_failures_are_never_optional_domain_failures(self):
        from household_job_budget import AdmissionDeferred
        for boundary in ('solar_window_forecast','rain_day_forecast','compare_solar_windows','compare_rain_products'):
            for error in (TimeoutError('global deadline'),AdmissionDeferred('global resource stop'),MemoryError('global allocation stop')):
                with self.subTest(boundary=boundary,error=type(error).__name__):
                    with patch('weather_learning.monitoring.'+boundary,side_effect=error):
                        with self.assertRaises(type(error)):self.run_monitor(apply=True)
        for reader in ('solar','rain'):
            source=getattr(self,reader)
            source.side_effect=AdmissionDeferred('global resource stop')
            with self.assertRaises(AdmissionDeferred):self.run_monitor(now=T+timedelta(days=2),apply=True)
            source.side_effect=None

    def test_global_guard_expiry_in_an_optional_boundary_stops_publication(self):
        expired=[False]
        def fail(*a,**kw):expired[0]=True;raise ValueError('optional failure during deadline')
        def guard():
            if expired[0]:raise TimeoutError('global monitor deadline')
        with patch('weather_learning.monitoring.solar_window_forecast',side_effect=fail):
            with self.assertRaises(TimeoutError):self.run_monitor(apply=True,guard=guard)
        self.assertFalse((self.state.root/'weather-performance.json').exists())

    def test_report_exposes_remaining_known_backlog_after_durable_commit(self):
        report=self.run_monitor(apply=True)
        work=report['temperature']['work']['backlog']
        self.assertEqual(work['state_counts'],dict(completed=2,pending=24))
        self.assertEqual(work['due'],0)
        self.assertIsNone(work['oldest_due_wait_seconds'])
        self.assertEqual(work['population'],'known_enqueued_work_only')

    def test_interrupted_report_replace_preserves_previous_report_and_newly_committed_scores(self):
        import os
        first=self.run_monitor(apply=True)
        target=self.state.root/'weather-performance.json';before=target.read_bytes();replace=os.replace
        def interrupted(source,destination):
            if Path(destination)==target:raise OSError('disposable report publication interruption')
            return replace(source,destination)
        with patch('weather_learning.shadow.os.replace',side_effect=interrupted):
            with self.assertRaises(OSError):self.run_monitor(now=T+timedelta(hours=4),apply=True)
        self.assertEqual(target.read_bytes(),before)
        self.assertEqual(list(self.state.root.glob('.pending-*')),[])
        self.temperature.reset_mock()
        recovered=self.run_monitor(now=T+timedelta(hours=4),apply=True)
        self.assertEqual(recovered['temperature']['raw']['pairs'],3)
        self.assertTrue({r['score_sha256'] for r in first['temperature']['pair_manifest']}<=
                        {r['score_sha256'] for r in recovered['temperature']['pair_manifest']})
        self.temperature.assert_not_called()
