"""Matched as-issued comparisons and explicit model/policy attribution."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from learning_fixtures import T,SITE,EPOCH,REVISION,full_snapshot,receipt
from weather_learning.archive import Archive
from weather_learning.contracts import identity
from weather_learning.publish import seal_payload
from weather_learning.shadow import ShadowStore,shadow_once
from weather_learning.monitoring import monitor_once


class PerformanceContractTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.archive=Archive(self.root/'archive');self.state=ShadowStore(self.root/'shadow')

    def issue(self,day,local_values,model):
        start=T+timedelta(days=day);self.archive.store_snapshot(full_snapshot(init=start,hours=80))
        at=start+timedelta(minutes=30)
        # Construct an original READY issue through the actual issuer/validator,
        # then retain precisely the declared two-hour diagnostic predictions.
        payload=shadow_once(self.archive,ShadowStore(self.root/('issuer-'+str(day))),now=at,site=SITE,
            sensor_epoch=EPOCH,code_revision=REVISION,horizon=2,clock=lambda:at+timedelta(seconds=1))
        body={k:deepcopy(v) for k,v in payload.items() if k!='generation'}
        body['model']=dict(status='SHADOW_ONLY',sha256=model,fittedAt=(at-timedelta(hours=1)).isoformat(),
            trainingEnd=(at-timedelta(hours=2)).isoformat(),sampleCount=24,targetDates=3,validation=None)
        body['hours']=body['hours'][:len(local_values)]
        for row,local in zip(body['hours'],local_values):row['localC']=local
        original=seal_payload(body);self.state.retain_issue(original,sensor_epoch=EPOCH,code_revision=REVISION)
        return original

    def monitor(self,now,observations):
        return monitor_once(self.archive,self.state,now=now,site=SITE,sensor_epoch=EPOCH,code_revision=REVISION,
            observation_policy_sha256='b'*64,read_temperature=lambda targets,at:{t:receipt(t,observations(t)) for t in targets},
            read_solar=lambda *args:None,read_rain=lambda *args:None)

    def test_horizon_uses_matched_raw_and_includes_difficult_raw_fallback(self):
        self.issue(0,[None,11.],'c'*64)
        report=self.monitor(T+timedelta(hours=3),lambda t:0. if t.hour==1 else 9.)
        horizon=report['temperature']['by_horizon']['0-24h']
        self.assertAlmostEqual(horizon['raw']['mae_c'],5.5)
        self.assertAlmostEqual(horizon['candidate']['mae_c'],2.)
        self.assertAlmostEqual(horizon['candidate_paired_raw']['mae_c'],1.)
        self.assertAlmostEqual(horizon['candidate_relative_mae_gain'],-1.)
        self.assertAlmostEqual(horizon['policy']['mae_c'],6.)
        self.assertEqual(horizon['coverage']['corrected'],1)
        self.assertEqual(horizon['coverage']['fallback'],1)

    def test_current_artifact_cannot_inherit_six_older_models_good_errors(self):
        for day in range(7):self.issue(day,[9.,9.] if day<6 else [13.,13.],identity({'model_day':day}))
        report=self.monitor(T+timedelta(days=6,hours=3),lambda t:9.)
        temperature=report['temperature']
        self.assertAlmostEqual(temperature['candidate']['mae_c'],4/7)
        cohorts=list(temperature['artifact_cohorts'].values())
        current=[r for r in cohorts if r['cohort']['model_sha256']==identity({'model_day':6})]
        self.assertEqual(len(current),1)
        self.assertAlmostEqual(current[0]['comparison']['candidate']['mae_c'],4.)
        self.assertAlmostEqual(current[0]['comparison']['candidate_paired_raw']['mae_c'],1.)
        self.assertEqual(current[0]['comparison']['candidate']['pairs'],2)
        self.assertEqual(temperature['evaluation_scope'],'versioned_sampled_forecasting_policy_and_separate_artifact_diagnostics')

    def scores(self):
        from weather_learning.features import temperature_targets,local_temperature_outcome
        from weather_learning.performance import score_temperature
        payload=self.issue(0,[None,11.],'c'*64)
        original=self.state.training_issues(T,T+timedelta(days=1),sensor_epoch=EPOCH)[0]
        targets={t.target_at:t for t in temperature_targets(self.archive.read(payload['source']['snapshotSha256']),issued_at=T+timedelta(minutes=30))}
        return [score_temperature(original=original,target=targets[T+timedelta(hours=i+1)],row=row,
            outcome=local_temperature_outcome(receipt(T+timedelta(hours=i+1),9.),target_at=T+timedelta(hours=i+1),
                assessed_at=T+timedelta(hours=3),sensor_epoch=EPOCH),observation_policy_sha256='b'*64)
            for i,row in enumerate(payload['hours'])]

    def test_empty_support_is_unavailable_and_has_no_qualification(self):
        from weather_learning.performance import summarize_temperature_scores
        report=summarize_temperature_scores([],withheld=3)
        for name in ('raw','candidate','candidate_paired_raw','policy'):self.assertIsNone(report[name])
        self.assertEqual(report['withheld'],3)
        self.assertFalse(report['release_authorized']);self.assertFalse(report['automatic_actuation'])

    def test_exact_repeated_scores_do_not_add_support_or_change_metrics(self):
        from weather_learning.performance import summarize_temperature_scores
        scores=self.scores()
        once=summarize_temperature_scores(scores)
        self.assertEqual(summarize_temperature_scores(scores*2),once)
        self.assertEqual(once['raw']['pairs'],2)
        self.assertEqual(once['raw']['unique_measured_targets'],2)
        self.assertEqual(once['candidate']['unique_measured_targets'],1)

    def test_score_contract_rejects_resealed_tampering_and_conflicting_identity(self):
        from weather_learning.performance import summarize_temperature_scores,validate_temperature_score
        scores=self.scores();damaged=deepcopy(scores[0]);damaged['policy_c']=0.
        damaged['score_sha256']=identity({k:v for k,v in damaged.items() if k!='score_sha256'})
        with self.assertRaisesRegex(ValueError,'fallback'):validate_temperature_score(damaged)
        damaged=deepcopy(scores[0]);damaged['observed_c']=8.
        damaged['score_sha256']=identity({k:v for k,v in damaged.items() if k!='score_sha256'})
        with self.assertRaisesRegex(ValueError,'conflicting'):summarize_temperature_scores(scores+[damaged])

    def test_policy_and_measurement_epoch_are_part_of_evaluation_identity(self):
        from weather_learning.performance import temperature_evaluation_key
        fields=dict(issue_sha256='a'*64,target_at=T.isoformat(),source_grid='b'*64,sensor_epoch=EPOCH,observation_policy_sha256='c'*64)
        key=temperature_evaluation_key(**fields)
        self.assertNotEqual(key,temperature_evaluation_key(**(fields|{'observation_policy_sha256':'d'*64})))
        self.assertNotEqual(key,temperature_evaluation_key(**(fields|{'sensor_epoch':'00000000-0000-4000-8000-000000000099'})))
        self.assertEqual(key,temperature_evaluation_key(**(fields|{'target_at':'2025-12-31T17:00:00-07:00'})))

    def test_seven_day_maximum_sparse_population_keeps_existing_report_byte_bound(self):
        from weather_learning.contracts import canonical
        from weather_learning.performance import summarize_temperature_scores,temperature_evaluation_key
        template=self.scores()[0];scores=[]
        # Bounded synthetic record-volume fixture, not historical skill data:
        # 39 actual-policy slots per daily original, seven distinct artifacts.
        for day in range(7):
            issue=T+timedelta(days=day,minutes=30)
            for offset in range(1,40):
                target=issue+timedelta(hours=offset)
                row=deepcopy(template);row.update(issued_at=issue.isoformat(),target_at=target.isoformat(),
                    issue_sha256=identity({'issue':day}),issue_generation=identity({'generation':day}),
                    outcome_available_at=target.isoformat(),outcome_sha256=identity({'measurement':target.isoformat()}),
                    model_sha256=identity({'model':day}))
                row['evaluation_key']=temperature_evaluation_key(issue_sha256=row['issue_sha256'],target_at=row['target_at'],
                    source_grid=row['grid_sha256'],sensor_epoch=row['sensor_epoch'],observation_policy_sha256=row['observation_policy_sha256'])
                row['score_sha256']=identity({k:v for k,v in row.items() if k!='score_sha256'});scores.append(row)
        report=summarize_temperature_scores(scores)
        self.assertEqual(report['raw']['pairs'],273)
        # Leave room within the existing512KiB top-level bound for rain/solar.
        self.assertLess(len(canonical(report)),350*1024)

    def test_score_rejects_target_beyond_original_maximum_and_late_outcome(self):
        from weather_learning.performance import validate_temperature_score,temperature_evaluation_key
        for late_target in (True,False):
            row=deepcopy(self.scores()[0])
            if late_target:row['target_at']=(T+timedelta(hours=400)).isoformat();row['outcome_available_at']=row['target_at']
            else:row['outcome_available_at']=(T+timedelta(days=20)).isoformat()
            row['evaluation_key']=temperature_evaluation_key(issue_sha256=row['issue_sha256'],target_at=row['target_at'],
                source_grid=row['grid_sha256'],sensor_epoch=row['sensor_epoch'],observation_policy_sha256=row['observation_policy_sha256'])
            row['score_sha256']=identity({k:v for k,v in row.items() if k!='score_sha256'})
            with self.subTest(late_target=late_target),self.assertRaisesRegex(ValueError,'clocks|arrival'):
                validate_temperature_score(row)
