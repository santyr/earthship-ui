"""Durable selection of real issued horizons, independent of report lookback."""
from datetime import timedelta
from pathlib import Path
import tempfile,unittest
from unittest.mock import Mock
from learning_fixtures import T,SITE,EPOCH,REVISION,full_snapshot,receipt
from weather_learning.archive import Archive
from weather_learning.shadow import ShadowStore,shadow_once
from weather_learning.contracts import identity,instant

POLICY='a'*64
from weather_learning.performance import EVALUATION_CONTRACT_SHA256
CONTRACT=EVALUATION_CONTRACT_SHA256
VERSION='earthship-weather-evaluation/v2'

class PendingScoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.archive=Archive(root/'archive');self.state=ShadowStore(root/'shadow')
        self.archive.store_snapshot(full_snapshot(hours=360));self.issued=T+timedelta(minutes=30)
        self.payload=shadow_once(self.archive,self.state,now=self.issued,site=SITE,sensor_epoch=EPOCH,
            code_revision=REVISION,horizon=336,clock=lambda:self.issued+timedelta(seconds=1))
        self.assertEqual(self.payload['status'],'READY')
    def queue(self,**kw):
        from weather_learning.pending_scores import PendingScores
        return PendingScores(self.state,sensor_epoch=EPOCH,observation_policy_sha256=kw.get('policy',POLICY),
            evaluation_version=VERSION,evaluation_contract_sha256=kw.get('contract',CONTRACT),**({'db_path':kw['db_path']} if 'db_path' in kw else {}))
    def test_monitor_scores_actual_240_and_336_hour_rows_after_issue_is_older_than_seven_days(self):
        from weather_learning.monitoring import monitor_once
        seen=[]
        def temperatures(targets,assessed_at):
            seen.extend(targets);return {t:receipt(t) for t in targets}
        monitor_once(self.archive,self.state,now=T+timedelta(hours=337),site=SITE,sensor_epoch=EPOCH,
            code_revision=REVISION,observation_policy_sha256=POLICY,read_temperature=temperatures,
            read_solar=lambda *a:None,read_rain=lambda *a:None)
        self.assertIn(T+timedelta(hours=240),seen)
        self.assertIn(T+timedelta(hours=336),seen)
    def bootstrap(self,q,now=None,limit=16):
        return q.bootstrap(self.archive,site=SITE,now=now or self.issued+timedelta(seconds=2),limit=limit)
    def test_restart_keeps_unmatured_actual_horizons_and_selects_only_sparse_issued_rows(self):
        q=self.queue();self.bootstrap(q)
        self.assertEqual(q.due(self.issued),[])
        q=self.queue();due=q.due(T+timedelta(hours=337))
        hours={(instant(w['target_at'])-T).total_seconds()/3600 for w in due}
        self.assertIn(240,hours);self.assertIn(336,hours)
        self.assertNotIn(335,hours);self.assertNotIn(360,hours)
        self.assertEqual(len(hours),len(due));self.assertLessEqual(len(due),40)
        for w in due:
            original,target,row=q.load(w,self.archive,site=SITE)
            self.assertEqual(row['at'],w['target_at']);self.assertEqual(target.target_at,instant(w['target_at']))
            self.assertEqual(original['payload']['generation'],self.payload['generation'])
    def test_outcome_commit_is_atomic_idempotent_and_rejects_conflicting_reassessment(self):
        q=self.queue();self.bootstrap(q);now=T+timedelta(hours=3)
        work=q.due(now)[0]
        score={'evaluation_key':work['work_key'],'schema':'synthetic-score','target_at':work['target_at'],'value':12}
        validate=lambda v: v if v.get('schema')=='synthetic-score' else (_ for _ in ()).throw(ValueError('invalid score'))
        with self.assertRaises(ValueError):q.commit(work,dict(score,schema='bad'),validator=validate)
        self.assertIn(work,q.due(now))
        q.commit(work,score,validator=validate)
        self.assertNotIn(work,self.queue().due(now))
        q.commit(work,score,validator=validate)
        with self.assertRaises(ValueError):q.commit(work,dict(score,value=13),validator=validate)
        self.assertEqual(list(q.iter_scores(T,T+timedelta(days=1))),[score])
    def test_retry_and_expiry_are_target_relative_and_never_synthetic_scores(self):
        q=self.queue();self.bootstrap(q)
        now=T+timedelta(hours=3);work=q.due(now)[0]
        q.defer(work,reason='quality_withheld',now=now)
        self.assertNotIn(work,q.due(now));self.assertIn(work,q.due(now+timedelta(hours=1)))
        late=instant(work['target_at'])+timedelta(days=7,minutes=1)
        q.defer(work,reason='observation_missing',now=late)
        self.assertNotIn(work,q.due(late+timedelta(days=1)))
        self.assertEqual(list(q.iter_scores(T,late)),[])
        self.assertEqual(q.counts()['expired'],1)
    def test_policy_and_contract_changes_have_independent_work_and_score_namespaces(self):
        q=self.queue();self.bootstrap(q);now=T+timedelta(hours=3)
        first=q.due(now)[0]['work_key']
        for changed in (self.queue(policy='c'*64),self.queue(contract='d'*64)):
            self.bootstrap(changed)
            self.assertNotEqual(changed.due(now)[0]['work_key'],first)
    def test_bounded_bootstrap_cursor_sees_late_inserted_old_issue_and_ignores_later_same_day(self):
        # Later same-day issue is never allowed to substitute the first original.
        shadow_once(self.archive,self.state,now=self.issued+timedelta(minutes=2),site=SITE,
            sensor_epoch=EPOCH,code_revision=REVISION,horizon=48,clock=lambda:self.issued+timedelta(minutes=3))
        q=self.queue();r=self.bootstrap(q,limit=1)
        self.assertEqual(r['indexed'],1);self.assertEqual(q.counts()['issues'],1)
        self.assertEqual(self.bootstrap(q,limit=1)['indexed'],1)
        self.assertEqual(q.counts()['issues'],1)
        # Append an older local-date original after the cursor has advanced.
        old=T-timedelta(days=1);self.archive.store_snapshot(full_snapshot(init=old,hours=48))
        shadow_once(self.archive,self.state,now=old+timedelta(minutes=30),site=SITE,sensor_epoch=EPOCH,
            code_revision=REVISION,horizon=24,clock=lambda:old+timedelta(minutes=31))
        self.assertEqual(self.bootstrap(q,limit=1)['indexed'],1)
        self.assertEqual(q.counts()['issues'],2)
    def test_missing_original_does_not_stall_discovery_or_cursor_and_can_recover(self):
        path=next((self.state.root/'issues').glob('*.json'));raw=path.read_bytes();path.unlink()
        q=self.queue();r=self.bootstrap(q)
        self.assertEqual(r['dependencies'],1);self.assertEqual(q.due(T+timedelta(hours=3)),[])
        self.assertEqual(q.counts()['missing_original'],1)
        path.write_bytes(raw);path.chmod(0o600)
        self.bootstrap(q,now=self.issued+timedelta(hours=1,minutes=1))
        self.assertGreater(len(q.due(T+timedelta(hours=3))),0)
    def test_deleted_source_index_anchor_restarts_bounded_discovery_without_duplicate_targets(self):
        q=self.queue();self.bootstrap(q)
        before=q.due(T+timedelta(hours=337))
        with self.state._connect() as db:
            row=db.execute('SELECT * FROM issues').fetchone();db.execute('DELETE FROM issues')
            db.execute('INSERT INTO issues(rowid,digest,issued,completed,local_day,epoch) VALUES(100,?,?,?,?,?)',row)
        self.assertEqual(self.bootstrap(q)['indexed'],1)
        self.assertEqual(q.due(T+timedelta(hours=337)),before)
    def test_corrupt_original_and_unindexed_file_are_reported_without_reconstruction(self):
        path=next((self.state.root/'issues').glob('*.json'));path.write_bytes(b'{}')
        q=self.queue();self.bootstrap(q)
        self.assertEqual(q.counts()['invalid_original'],1)
        self.assertEqual(q.due(T+timedelta(hours=337)),[])
        orphan=self.state.root/'issues'/('f'*64+'.json');orphan.write_text('{}');orphan.chmod(0o600)
        self.assertEqual(q.source_dependencies()['unindexed_issue_files'],'not_reconciled')
    def test_hard_batch_limits_and_read_issue_identity_validation(self):
        q=self.queue()
        for limit in (0,17):
            with self.assertRaises(ValueError):self.bootstrap(q,limit=limit)
        for limit in (0,65):
            with self.assertRaises(ValueError):q.due(T,limit=limit)
        name=next((self.state.root/'issues').glob('*.json')).stem
        self.assertEqual(identity(self.state.read_issue(name)),name)
        with self.assertRaises(ValueError):self.state.read_issue('../bad')
    def test_real_score_key_matches_queue_and_completed_target_never_requeries(self):
        from weather_learning.features import local_temperature_outcome
        from weather_learning.performance import score_temperature,validate_temperature_score
        q=self.queue();self.bootstrap(q);now=T+timedelta(hours=3)
        work=q.due(now)[0];original,target,row=q.load(work,self.archive,site=SITE)
        outcome=local_temperature_outcome(receipt(target.target_at),target_at=target.target_at,assessed_at=now,sensor_epoch=EPOCH)
        score=score_temperature(original=original,target=target,row=row,outcome=outcome,observation_policy_sha256=POLICY)
        self.assertEqual(score['evaluation_key'],work['work_key'])
        q.commit(work,score,validator=validate_temperature_score)
        self.assertEqual(list(self.queue().iter_scores(T,now)),[score])
        self.assertNotIn(work,self.queue().due(now+timedelta(days=3)))
    def test_batches_are_bounded_across_days_and_second_batch_survives_restart(self):
        for day in (1,2):
            start=T+timedelta(days=day);self.archive.store_snapshot(full_snapshot(init=start,hours=360))
            shadow_once(self.archive,self.state,now=start+timedelta(minutes=30),site=SITE,sensor_epoch=EPOCH,
                code_revision=REVISION,horizon=336,clock=lambda:start+timedelta(minutes=31))
        q=self.queue();self.bootstrap(q,now=T+timedelta(days=16))
        now=T+timedelta(days=16);batch=q.due(now)
        self.assertEqual(len(batch),64)
        for work in batch:q.defer(work,reason='observation_missing',now=now)
        second=self.queue().due(now)
        self.assertGreater(len(second),0);self.assertLessEqual(len(second),64)
        self.assertFalse({w['work_key'] for w in second}&{w['work_key'] for w in batch})
    def test_snapshot_absence_is_retriable_and_cannot_use_newer_run(self):
        original=self.state.read_issue(next((self.state.root/'issues').glob('*.json')).stem)
        name=original['payload']['source']['snapshotSha256']
        path=self.archive.objects/(name+'.json');raw=path.read_bytes();path.unlink()
        q=self.queue();self.bootstrap(q)
        self.assertEqual(q.counts()['missing_original'],1)
        self.assertEqual(q.due(T+timedelta(hours=337)),[])
        path.write_bytes(raw);path.chmod(0o600)
        self.bootstrap(q,now=T+timedelta(hours=2))
        self.assertGreater(len(q.due(T+timedelta(hours=337))),0)
    def test_preview_database_is_confined_private_and_does_not_advance_persistent_cursor(self):
        with tempfile.TemporaryDirectory(dir=self.state.root) as temp:
            preview=self.queue(db_path=Path(temp)/'preview.sqlite3')
            self.bootstrap(preview)
            self.assertGreater(len(preview.due(T+timedelta(hours=3))),0)
        self.assertFalse((self.state.root/'pending-scores.sqlite3').exists())
        self.assertEqual(self.bootstrap(self.queue())['indexed'],1)
        with self.assertRaises(ValueError):self.queue(db_path=Path(self.temp.name)/'outside.sqlite3')
    def test_failed_enqueue_transaction_retries_after_cursor_advance_without_partial_work(self):
        import sqlite3
        q=self.queue()
        with q._connect() as db:
            db.execute("CREATE TRIGGER interrupted_enqueue BEFORE INSERT ON work WHEN (SELECT COUNT(*) FROM work)>0 BEGIN SELECT RAISE(ABORT,'interrupted'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.bootstrap(q)
        self.assertEqual(q.counts().get('pending',0),0)
        with q._connect() as db:db.execute('DROP TRIGGER interrupted_enqueue')
        result=self.bootstrap(self.queue())
        self.assertEqual(result['indexed'],0);self.assertEqual(result['resolved'],1)
        self.assertGreater(len(q.due(T+timedelta(hours=337))),0)
    def test_read_issue_refuses_original_index_clock_disagreement(self):
        name=next((self.state.root/'issues').glob('*.json')).stem
        with self.state._connect() as db:db.execute('UPDATE issues SET completed=? WHERE digest=?',(T.isoformat(),name))
        with self.assertRaisesRegex(ValueError,'index differs'):self.state.read_issue(name)
        q=self.queue();self.bootstrap(q)
        self.assertEqual(q.counts()['invalid_original'],1)
    def test_preview_refuses_public_directory_and_symlink_database(self):
        public=self.state.root/'public';public.mkdir(mode=0o755)
        with self.assertRaises(ValueError):self.queue(db_path=public/'preview.sqlite3')
        link=self.state.root/'linked.sqlite3';link.symlink_to(self.state.db)
        with self.assertRaises(OSError):self.queue(db_path=link)
    def test_daily_name_selection_remains_available_when_original_is_missing(self):
        self.assertTrue(hasattr(self.state,'training_issue_names'))
        name=next((self.state.root/'issues').glob('*.json')).stem
        (self.state.root/'issues'/(name+'.json')).unlink()
        self.assertEqual(self.state.training_issue_names(T,T+timedelta(days=1),sensor_epoch=EPOCH),[name])
        with self.assertRaises(FileNotFoundError):self.state.training_issues(T,T+timedelta(days=1),sensor_epoch=EPOCH)
    def test_late_inserted_earlier_same_day_original_supersedes_report_support_but_keeps_score(self):
        from weather_learning.features import local_temperature_outcome
        from weather_learning.performance import score_temperature,validate_temperature_score
        q=self.queue();self.bootstrap(q);now=T+timedelta(hours=3)
        old=q.due(now)[0];original,target,row=q.load(old,self.archive,site=SITE)
        score=score_temperature(original=original,target=target,row=row,
            outcome=local_temperature_outcome(receipt(target.target_at),target_at=target.target_at,assessed_at=now,sensor_epoch=EPOCH),
            observation_policy_sha256=POLICY)
        q.commit(old,score,validator=validate_temperature_score)
        self.assertEqual(self.coverage(q,now)['scored'],1)
        earlier=self.issued-timedelta(minutes=5)
        new_payload=shadow_once(self.archive,self.state,now=earlier,site=SITE,sensor_epoch=EPOCH,
            code_revision=REVISION,horizon=336,clock=lambda:earlier+timedelta(seconds=1))
        self.assertEqual(new_payload['status'],'READY')
        # An index insert changes the canonical population even before bootstrap
        # reaches that row. A completed superseded original must not be shown.
        self.assertEqual(list(q.iter_scores(T,now)),[])
        self.assertEqual(self.coverage(q,now)['scored'],0)
        self.bootstrap(q,now=now)
        self.assertEqual(q.counts()['superseded_completed'],1)
        self.assertEqual(q.read_score(old['work_key']),score)
        changes=q.source_dependencies()['selection_changes']
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]['previous_issue_sha256'],identity(original))
        self.assertNotEqual(changes[0]['current_issue_sha256'],identity(original))
        self.assertTrue(q.due(now))
        self.assertTrue(all(w['issue_sha256']!=identity(original) for w in q.due(now)))
    def test_incomplete_future_issue_cannot_starve_other_originals_at_small_bootstrap_limit(self):
        from weather_learning.publish import seal_payload
        self.state=ShadowStore(Path(self.temp.name)/'future-shadow')
        body={k:v for k,v in self.payload.items() if k!='generation'}
        body['generatedAt']=(T+timedelta(days=10)).isoformat()
        self.state.retain_issue(seal_payload(body),sensor_epoch=EPOCH,code_revision=REVISION)
        start=T+timedelta(days=1);self.archive.store_snapshot(full_snapshot(init=start,hours=360))
        shadow_once(self.archive,self.state,now=start+timedelta(minutes=30),site=SITE,sensor_epoch=EPOCH,
            code_revision=REVISION,horizon=336,clock=lambda:start+timedelta(minutes=31))
        q=self.queue();now=T+timedelta(days=2)
        self.assertEqual(self.bootstrap(q,now=now,limit=1)['resolved'],0)
        self.assertEqual(self.bootstrap(q,now=now,limit=1)['resolved'],1)
        self.assertGreater(len(q.due(now)),0)
    def test_original_disappearing_after_selection_is_an_explicit_work_dependency(self):
        q=self.queue();self.bootstrap(q);now=T+timedelta(hours=3);work=q.due(now)[0]
        (self.state.root/'issues'/(work['issue_sha256']+'.json')).unlink()
        with self.assertRaises(FileNotFoundError):q.load(work,self.archive,site=SITE)
        q.defer(work,reason='missing_original',now=now)
        self.assertIn('work_dependency_reasons',q.counts())
        self.assertEqual(q.counts()['work_dependency_reasons']['missing_original'],1)
        self.assertIsNone(q.read_score(work['work_key']))
    def coverage(self,q,now):
        self.assertTrue(hasattr(q,'window_counts'))
        return q.window_counts(T,T+timedelta(hours=7),now=now)
    def test_window_coverage_names_known_sampled_future_and_maturity_boundaries(self):
        q=self.queue();self.bootstrap(q)
        before=self.coverage(q,T+timedelta(hours=1,minutes=1))
        self.assertEqual(before['sampled_issued'],6);self.assertEqual(before['eligible'],6)
        self.assertEqual(before['matured'],0);self.assertEqual(before['not_yet_mature'],6)
        self.assertEqual(before['pending'],6);self.assertEqual(before['scored'],0)
        after=self.coverage(q,T+timedelta(hours=1,minutes=2))
        self.assertEqual(after['matured'],1);self.assertEqual(after['due'],1)
        self.assertEqual(after['not_yet_mature'],5)
        self.assertIsNone(after['complete_population_totals'])
        self.assertTrue(after['discovery']['indexed_cursor_caught_up'])
        self.assertIsNone(after['discovery']['source_discovery_complete'])
    def test_window_coverage_reports_score_quality_missing_and_expiry_as_separate_dimensions(self):
        from weather_learning.features import local_temperature_outcome
        from weather_learning.performance import score_temperature,validate_temperature_score
        q=self.queue();self.bootstrap(q);now=T+timedelta(hours=7)
        works=[w for w in q.due(now) if instant(w['target_at'])<now]
        self.assertEqual(len(works),6)
        work=works[0];original,target,row=q.load(work,self.archive,site=SITE)
        score=score_temperature(original=original,target=target,row=row,
            outcome=local_temperature_outcome(receipt(target.target_at),target_at=target.target_at,assessed_at=now,sensor_epoch=EPOCH),
            observation_policy_sha256=POLICY)
        q.commit(work,score,validator=validate_temperature_score)
        for work,reason in zip(works[1:5],('quality_withheld','observation_missing','missing_original','invalid_original')):
            q.defer(work,reason=reason,now=now)
        late=T+timedelta(days=8);q.defer(works[5],reason='observation_missing',now=late)
        c=self.coverage(q,late)
        self.assertEqual(c['sampled_issued'],6);self.assertEqual(c['unique_target_times'],6)
        self.assertEqual(c['matured'],6);self.assertEqual(c['scored'],1)
        self.assertEqual(c['pending'],4);self.assertEqual(c['expired'],1)
        self.assertEqual(c['quality_withheld'],1);self.assertEqual(c['observation_missing'],2)
        self.assertEqual(c['missing_source_evidence'],2);self.assertEqual(c['due'],4)
    def test_window_coverage_cannot_invent_target_totals_from_unscanned_or_missing_issues(self):
        q=self.queue();initial=self.coverage(q,T+timedelta(hours=7))
        self.assertEqual(initial['sampled_issued'],0)
        self.assertEqual(initial['global_backlog']['unscanned_index_rows'],1)
        self.assertFalse(initial['discovery']['indexed_cursor_caught_up'])
        path=next((self.state.root/'issues').glob('*.json'));path.unlink()
        self.bootstrap(q)
        missing=self.coverage(q,T+timedelta(hours=7))
        self.assertEqual(missing['sampled_issued'],0)
        self.assertEqual(missing['global_backlog']['intake_states']['missing_original'],1)
        self.assertEqual(missing['missing_source_evidence'],0) # no target rows can truthfully be invented
        self.assertIsNone(missing['complete_population_totals'])
    def test_window_coverage_excludes_late_superseded_daily_original_before_and_after_bootstrap(self):
        q=self.queue();self.bootstrap(q);now=T+timedelta(hours=7)
        self.assertEqual(self.coverage(q,now)['sampled_issued'],6)
        earlier=self.issued-timedelta(minutes=5)
        shadow_once(self.archive,self.state,now=earlier,site=SITE,sensor_epoch=EPOCH,
            code_revision=REVISION,horizon=336,clock=lambda:earlier+timedelta(seconds=1))
        before=self.coverage(q,now)
        self.assertEqual(before['sampled_issued'],0)
        self.assertEqual(before['global_backlog']['unscanned_index_rows'],1)
        self.bootstrap(q,now=now)
        after=self.coverage(q,now)
        self.assertEqual(after['sampled_issued'],6);self.assertEqual(after['pending'],6)
        self.assertEqual(after['global_backlog']['unscanned_index_rows'],0)
    def test_window_coverage_counts_forecast_instances_separately_from_shared_target_times(self):
        start=T+timedelta(days=1);self.archive.store_snapshot(full_snapshot(init=start,hours=360))
        shadow_once(self.archive,self.state,now=start+timedelta(minutes=30),site=SITE,sensor_epoch=EPOCH,
            code_revision=REVISION,horizon=336,clock=lambda:start+timedelta(minutes=31))
        q=self.queue();self.bootstrap(q,now=T+timedelta(hours=49))
        c=q.window_counts(T+timedelta(hours=24),T+timedelta(hours=48),now=T+timedelta(hours=49))
        self.assertEqual(c['sampled_issued'],25);self.assertEqual(c['unique_target_times'],24)
        self.assertEqual(c['matured'],25)
    def test_window_coverage_bounds_and_cursor_reset_do_not_claim_complete_discovery(self):
        q=self.queue();self.bootstrap(q)
        for start,end in ((T,T),(T,T+timedelta(days=367))):
            with self.assertRaises(ValueError):q.window_counts(start,end,now=T)
        with self.state._connect() as db:
            row=db.execute('SELECT * FROM issues').fetchone();db.execute('DELETE FROM issues')
            db.execute('INSERT INTO issues(rowid,digest,issued,completed,local_day,epoch) VALUES(100,?,?,?,?,?)',row)
        before=self.coverage(q,T+timedelta(hours=7))
        self.assertEqual(before['discovery']['cursor_status'],'requires_bounded_rebootstrap')
        self.assertFalse(before['discovery']['indexed_cursor_caught_up'])
        self.assertEqual(before['global_backlog']['unscanned_index_rows'],1)
        self.bootstrap(q)
        self.assertTrue(self.coverage(q,T+timedelta(hours=7))['discovery']['indexed_cursor_caught_up'])
    def test_window_coverage_source_attachment_enforces_read_only_database(self):
        import sqlite3
        from contextlib import contextmanager
        q=self.queue();self.bootstrap(q);connect=q._connect
        original=self.state.db.read_bytes()
        @contextmanager
        def checked():
            with connect() as db:
                yield db
                with self.assertRaisesRegex(sqlite3.OperationalError,'readonly'):
                    db.execute('DELETE FROM originals.issues')
        q._connect=checked
        self.coverage(q,T+timedelta(hours=7))
        self.assertEqual(self.state.db.read_bytes(),original)
