"""Future issues retain known procedure identity without inventing legacy history."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile,unittest
from learning_fixtures import T,SITE,EPOCH,REVISION,native_snapshot,pair,receipt
from weather_learning.archive import Archive
from weather_learning.contracts import identity
from weather_learning.shadow import ShadowStore,shadow_once,train_once
from weather_learning.training import fit_bias

class IssueProvenanceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.state=ShadowStore(self.root/'shadow');self.archive=Archive(self.root/'archive')
        self.archive.store_snapshot(native_snapshot(hours=4));self.now=T+timedelta(minutes=30)
    def issue(self,**kw):
        return shadow_once(self.archive,self.state,now=self.now,site=SITE,sensor_epoch=EPOCH,
            code_revision=REVISION,horizon=1,clock=lambda:self.now+timedelta(seconds=1),**kw)
    def original(self):
        return self.state.training_issues(T-timedelta(days=3),self.now+timedelta(hours=1),sensor_epoch=EPOCH)[-1]
    def test_new_raw_issue_has_closed_complete_provenance_and_unchanged_public_payload(self):
        payload=self.issue();original=self.original()
        self.assertEqual(original['schema'],'earthship-weather-shadow-issue/v3')
        p=original['provenance'];self.assertEqual(p['status'],'complete')
        self.assertEqual(p['method_policy']['family'],'original_raw')
        self.assertEqual(p['training_policy']['family'],'not_applicable')
        for name in ('method_policy','training_policy','selection_policy'):
            self.assertEqual(p[name+'_sha256'],identity(p[name]))
        self.assertEqual(payload['version'],2);self.assertNotIn('provenance',payload)
    def test_legacy_model_receipt_records_known_recipe_but_never_guesses_training_window(self):
        model=fit_bias([pair(-2)],cutoff=T-timedelta(days=1),code_revision=REVISION)
        self.state.install_model(model,fitted_at=T-timedelta(hours=23))
        self.assertEqual(self.state.current_model()['schema'],'earthship-weather-shadow-model-receipt/v1')
        self.issue();original=self.original()
        self.assertEqual(original['schema'],'earthship-weather-shadow-issue/v3')
        p=original['provenance'];self.assertEqual(p['status'],'training_policy_unretained')
        self.assertIsNone(p['training_policy']);self.assertIsNone(p['training_policy_sha256'])
        self.assertEqual(p['method_policy']['algorithm'],'bounded_bias')
        self.assertIn(p['method_policy_sha256'],p['method'])
    def test_actual_training_request_is_retained_and_future_issue_is_complete(self):
        self.issue();cutoff=T+timedelta(days=1)
        result=train_once(self.archive,self.state,reader=lambda targets,at:{t:receipt(t) for t in targets},
            site=SITE,sensor_epoch=EPOCH,cutoff=cutoff,code_revision=REVISION,days=30,apply=True,clock=lambda:cutoff+timedelta(seconds=1))
        self.assertEqual(result['status'],'CANDIDATE_FITTED')
        current=self.state.current_model()
        self.assertEqual(current['schema'],'earthship-weather-shadow-model-receipt/v2')
        self.assertEqual(current['training_policy']['history_days'],30)
        self.assertIn('numerical_sources',current['training_policy'])
        self.assertEqual(current['training_policy_sha256'],identity(current['training_policy']))
        self.archive.store_snapshot(native_snapshot(day=1,hours=4));self.now+=timedelta(days=1)
        self.issue();p=self.original()['provenance']
        self.assertEqual(p['status'],'complete')
        self.assertEqual(p['training_policy'],current['training_policy'])
    def test_direct_legacy_retention_remains_strict_v2(self):
        payload=self.issue();legacy=ShadowStore(self.root/'legacy')
        name=legacy.retain_issue(payload,sensor_epoch=EPOCH,code_revision=REVISION)
        original=legacy.read_issue(name)
        self.assertEqual(set(original),{'schema','sensor_epoch','code_revision','payload'})
        self.assertEqual(original['schema'],'earthship-weather-shadow-issue/v2')
    def test_changed_training_request_cannot_reuse_an_unrecorded_or_different_history_policy(self):
        self.issue();cutoff=T+timedelta(days=1)
        def train(days):
            return train_once(self.archive,self.state,reader=lambda targets,at:{t:receipt(t) for t in targets},
                site=SITE,sensor_epoch=EPOCH,cutoff=cutoff,code_revision=REVISION,days=days,apply=True,clock=lambda:cutoff+timedelta(seconds=1))
        train(30);first=self.state.current_model()['training_policy_sha256']
        self.assertEqual(train(90)['status'],'CANDIDATE_FITTED')
        self.assertNotEqual(self.state.current_model()['training_policy_sha256'],first)
        self.assertEqual(self.state.current_model()['training_policy']['history_days'],90)
    def test_recipe_identity_changes_for_hyperparameters_but_not_daily_artifact_or_pointer(self):
        from weather_learning.provenance import issue_provenance,native_training_policy
        from weather_learning.shadow import TRAIN_OFFSETS
        first=fit_bias([pair(-2)],cutoff=T-timedelta(days=1),code_revision=REVISION)
        second=fit_bias([pair(-2,actual_c=13)],cutoff=T-timedelta(days=1),code_revision=REVISION)
        policy=native_training_policy(first,days=90,offsets=TRAIN_OFFSETS)
        a=issue_provenance(first,training_policy=policy,selection_original_sha256='a'*64)
        b=issue_provenance(second,training_policy=policy,selection_original_sha256='b'*64)
        self.assertNotEqual(first['artifact_sha256'],second['artifact_sha256'])
        for key in ('method','training_policy_sha256','selection_policy_sha256'):self.assertEqual(a[key],b[key])
        third=fit_bias([pair(-2)],cutoff=T-timedelta(days=1),code_revision=REVISION,max_correction_c=5)
        self.assertNotEqual(issue_provenance(third)['method'],a['method'])
    def test_closed_hashed_provenance_rejects_tampering_and_recipe_training_mismatch(self):
        from weather_learning.provenance import issue_provenance,native_training_policy,validate_provenance
        from weather_learning.shadow import TRAIN_OFFSETS
        model=fit_bias([pair(-2)],cutoff=T-timedelta(days=1),code_revision=REVISION)
        p=issue_provenance(model,training_policy=native_training_policy(model,days=90,offsets=TRAIN_OFFSETS))
        for key in ('method_policy','selection_policy'):
            bad=deepcopy(p);bad[key]['extra']=True
            with self.assertRaises(ValueError):validate_provenance(bad)
        bad=deepcopy(p);bad['training_policy']['ridge']=2
        bad['training_policy_sha256']=identity(bad['training_policy'])
        with self.assertRaises(ValueError):validate_provenance(bad)
    def test_original_public_raw_cannot_claim_a_corrected_method(self):
        from weather_learning.provenance import issue_provenance
        payload=self.issue();model=fit_bias([pair(-2)],cutoff=T-timedelta(days=1),code_revision=REVISION)
        with self.assertRaises(ValueError):self.state.retain_issue(payload,sensor_epoch=EPOCH,code_revision=REVISION,provenance=issue_provenance(model))
