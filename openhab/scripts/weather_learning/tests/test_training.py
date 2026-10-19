from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import importlib,unittest
from learning_fixtures import T,EPOCH,REVISION,pair

class TrainingTests(unittest.TestCase):
    def setUp(self):
        try:self.m=importlib.import_module('weather_learning.training')
        except ModuleNotFoundError:self.fail('Fresh WeatherNext training is not implemented')
        self.samples=[pair(day) for day in range(8)]
        self.cutoff=T+timedelta(days=9)
        self.target=pair(10).forecast

    def fit(self,samples=None,**kwargs):
        return self.m.fit_bias(self.samples if samples is None else samples,cutoff=self.cutoff,code_revision=REVISION,**kwargs)

    def predict(self,model,target=None):
        return self.m.predict(model,self.target if target is None else target,sensor_epoch=EPOCH)

    def test_empty_training_serves_raw_with_untrained_status(self):
        model=self.fit([])
        result=self.predict(model)
        self.assertEqual(result['status'],'UNTRAINED')
        self.assertAlmostEqual(result['value_c'],10)
        self.assertEqual(model['sample_count'],0)

    def test_bias_learns_google_error_and_preserves_bound(self):
        model=self.fit(max_correction_c=1.5)
        self.assertAlmostEqual(self.predict(model)['value_c'],11.5)
        self.assertEqual(model['target_dates'],8)
        self.assertEqual(model['provider'],'weathernext3')

    def test_weathernext_never_uses_openmeteo_bias_state(self):
        model=self.fit()
        for contaminated in (dict(model,provider='openmeteo'),dict(model,kalman={'hi':{'b':99}}),dict(model,parent_provider='openmeteo')):
            with self.subTest(contaminated=list(contaminated)),self.assertRaises(ValueError):self.predict(contaminated)

    def test_changed_coefficients_are_refused_by_model_identity(self):
        model=self.fit();model['intercept_c']=99
        with self.assertRaises(ValueError):self.predict(model)

    def test_future_labels_cannot_enter_training(self):
        with self.assertRaises(ValueError):self.fit(self.samples+[pair(10)])

    def test_mixed_sensor_epochs_or_sites_cannot_be_pooled(self):
        with self.assertRaises(ValueError):self.fit(self.samples+[pair(0,epoch='00000000-0000-4000-8000-000000000003')])
        sample=pair(0)
        changed=replace(sample,forecast=replace(sample.forecast,grid_digest='b'*64))
        with self.assertRaises(ValueError):self.fit(self.samples+[changed])

    def test_conflicting_snapshots_for_same_decision_target_are_refused(self):
        with self.assertRaises(ValueError):self.fit(self.samples+[pair(0,mean_c=11)])

    def test_duplicate_forecast_outcome_pair_is_idempotent(self):
        one=self.fit();duplicated=self.fit(self.samples+self.samples)
        self.assertEqual(one['artifact_sha256'],duplicated['artifact_sha256'])
        self.assertEqual(duplicated['sample_count'],8)

    def test_same_original_label_queried_again_is_not_conflicting_evidence(self):
        sample=self.samples[0]
        later=replace(sample,outcome=replace(sample.outcome,assessed_at=sample.outcome.assessed_at+timedelta(hours=1)))
        model=self.fit(self.samples+[later])
        self.assertEqual(model['sample_count'],8)

    def test_artifact_freezes_sources_preprocessing_code_and_window(self):
        model=self.fit()
        self.assertEqual(model['code_revision'],REVISION)
        self.assertEqual(len(model['training_manifest']),8)
        self.assertEqual(model['training_end'],self.samples[-1].outcome.target_at.isoformat())
        self.assertEqual(model['cutoff'],self.cutoff.isoformat())
        self.assertEqual(model['qualification'],'SHADOW_ONLY')
        for row in model['training_manifest']:
            self.assertEqual(set(row),{'pair_sha256','snapshot_sha256','issue_sha256','outcome_sha256','target_at','issued_at'})

    def test_inference_rejects_artifact_from_after_issue_or_wrong_epoch(self):
        model=self.fit()
        with self.assertRaises(ValueError):self.predict(model,self.samples[0].forecast)
        with self.assertRaises(ValueError):self.m.predict(model,self.target,sensor_epoch='00000000-0000-4000-8000-000000000003')

    def test_regularized_residual_learns_temperature_pattern(self):
        # Residual is linear in WeatherNext temperature, independent of local hour.
        samples=[pair(day,mean_c=day%5,actual_c=1.5*(day%5)+1) for day in range(20)]
        model=self.m.fit_residual(samples,cutoff=T+timedelta(days=21),code_revision=REVISION,ridge=0.01)
        target=pair(22,mean_c=3).forecast
        result=self.m.predict(model,target,sensor_epoch=EPOCH)
        self.assertAlmostEqual(result['value_c'],5.5,delta=.1)
        self.assertEqual(len(model['feature_names']),len(model['coefficients']))
        self.assertTrue(all(x>0 for x in model['feature_scales']))

    def test_residual_model_has_finite_output_with_constant_predictors(self):
        model=self.m.fit_residual(self.samples,cutoff=self.cutoff,code_revision=REVISION)
        self.assertAlmostEqual(self.predict(model)['value_c'],12,delta=.01)

    def test_prepared_predictor_freezes_original_model_bytes(self):
        model=self.fit()
        predictor=self.m.TemperaturePredictor(model)
        model['intercept_c']=99
        result=predictor.predict(self.target,sensor_epoch=EPOCH)
        self.assertAlmostEqual(result['value_c'],12)

    def test_rehashed_malformed_manifest_or_training_clocks_are_refused(self):
        from weather_learning.contracts import identity
        for change in ('revision','manifest','cutoff','epoch','ridge'):
            model=self.fit()
            if change=='revision':model['code_revision']='main'
            if change=='manifest':model['training_manifest'][0]['snapshot_sha256']='not-a-digest'
            if change=='cutoff':model['training_end']=(self.cutoff+timedelta(days=1)).isoformat()
            if change=='epoch':model['sensor_epoch']='legacy'
            if change=='ridge':model['ridge']=float('inf')
            # Infinity cannot be canonically hashed, so validate its numeric form directly.
            if change!='ridge':model['artifact_sha256']=identity({key:value for key,value in model.items() if key!='artifact_sha256'})
            with self.subTest(change=change),self.assertRaises(ValueError):self.predict(model)

    def test_invalid_revision_or_unbounded_correction_refused(self):
        with self.assertRaises(ValueError):self.m.fit_bias(self.samples,cutoff=self.cutoff,code_revision='main')
        for value in (0,float('inf'),True):
            with self.subTest(value=value),self.assertRaises(ValueError):self.fit(max_correction_c=value)

if __name__=='__main__':unittest.main()
