from copy import deepcopy
from datetime import datetime,timedelta
import importlib,pathlib,tempfile,unittest
from unittest.mock import patch
from learning_fixtures import T,SITE,EPOCH,REVISION,native_snapshot,receipt,pair
from weather_learning.archive import Archive
from weather_learning.training import fit_bias
from weather_learning.worker import collector_lock

class ShadowTests(unittest.TestCase):
    def setUp(self):
        try:
            self.m=importlib.import_module('weather_learning.shadow')
            self.p=importlib.import_module('weather_learning.publish')
        except ModuleNotFoundError:self.fail('Prospective shadow runtime is not implemented')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
        self.archive=Archive(self.root/'archive');self.state=self.m.ShadowStore(self.root/'shadow')
        self.now=T+timedelta(minutes=30)
        self.archive.store_snapshot(native_snapshot(hours=4))

    def run_shadow(self,**kwargs):
        return self.m.shadow_once(self.archive,self.state,now=self.now,site=SITE,sensor_epoch=EPOCH,code_revision=REVISION,horizon=1,clock=lambda:self.now+timedelta(seconds=1),**kwargs)

    def test_default_shadow_retains_original_issue_without_publishing(self):
        report=self.run_shadow()
        self.assertEqual(report['status'],'READY')
        self.assertEqual(report['model']['status'],'UNTRAINED')
        self.assertTrue(all(row['localC'] is None for row in report['hours']))
        self.assertFalse(report['automaticActuation'])
        issues=self.state.training_issues(T-timedelta(days=1),T+timedelta(days=1),sensor_epoch=EPOCH)
        self.assertEqual(len(issues),1)
        self.assertEqual(issues[0]['payload']['generation'],report['generation'])

    def shifted_issue(self,report,offset):
        value=deepcopy(report)
        for name in ('generatedAt','decisionAt'):
            value[name]=(datetime.fromisoformat(value[name])+offset).isoformat()
        for name in ('initializedAt','firstSeenAt','ingestedAt'):
            value['source'][name]=(datetime.fromisoformat(value['source'][name])+offset).isoformat()
        for row in value['hours']:
            row['at']=(datetime.fromisoformat(row['at'])+offset).isoformat()
        value.pop('generation')
        value=self.p.seal_payload(value)
        self.state.retain_issue(value,sensor_epoch=EPOCH,code_revision=REVISION)
        return value

    def test_partial_oldest_day_cannot_substitute_a_later_daily_issue(self):
        report=self.run_shadow()
        self.shifted_issue(report,timedelta(hours=1))
        issues=self.state.training_issues(self.now+timedelta(minutes=30),self.now+timedelta(days=1),sensor_epoch=EPOCH)
        self.assertEqual(issues,[])

    def test_maximum_rolling_window_selects_latest_366_original_dates(self):
        report=self.run_shadow()
        self.shifted_issue(report,timedelta(hours=3))
        for day in range(1,367):
            self.shifted_issue(report,timedelta(days=day,hours=1))
        end=self.now+timedelta(days=366,hours=2)
        issues=self.state.training_issues(end-timedelta(days=366),end,sensor_epoch=EPOCH)
        self.assertEqual(len(issues),366)
        self.assertEqual(issues[0]['payload']['decisionAt'],(self.now+timedelta(days=1,hours=1)).isoformat())
        self.assertEqual(issues[-1]['payload']['decisionAt'],(self.now+timedelta(days=366,hours=1)).isoformat())

    def test_inference_uses_pinned_model_without_running_fitting(self):
        model=fit_bias([pair(-2)],cutoff=T-timedelta(days=1),code_revision=REVISION)
        self.state.install_model(model,fitted_at=T-timedelta(hours=23))
        report=self.run_shadow()
        self.assertAlmostEqual(report['hours'][0]['localC'],12)
        self.assertEqual(report['model']['sha256'],model['artifact_sha256'])

    def test_stale_source_reports_unavailable_and_preserves_model(self):
        model=fit_bias([],cutoff=T,code_revision=REVISION);self.state.install_model(model,fitted_at=T)
        self.now=T+timedelta(days=2)
        report=self.run_shadow()
        self.assertEqual(report['status'],'UNAVAILABLE')
        self.assertEqual(report['hours'],[])
        self.assertEqual(self.state.current_model()['model']['artifact_sha256'],model['artifact_sha256'])

    def test_concurrent_inference_refuses_before_any_issue_or_publication(self):
        with collector_lock(self.state.root/'shadow.lock'):
            with self.assertRaises(BlockingIOError):self.run_shadow()
        self.assertEqual(self.state.training_issues(T,T+timedelta(days=1),sensor_epoch=EPOCH),[])

    def test_interrupted_model_pointer_write_preserves_previous_candidate(self):
        old=fit_bias([],cutoff=T,code_revision=REVISION);self.state.install_model(old,fitted_at=T)
        newer=fit_bias([pair()],cutoff=T+timedelta(days=1),code_revision=REVISION)
        with patch('weather_learning.shadow.os.replace',side_effect=OSError('synthetic interrupted write')):
            with self.assertRaises(OSError):self.state.install_model(newer,fitted_at=T+timedelta(days=1))
        self.assertEqual(self.state.current_model()['model']['artifact_sha256'],old['artifact_sha256'])

    def test_training_uses_earliest_daily_issue_and_google_only(self):
        self.run_shadow()
        later=native_snapshot(mean_c=20,hours=4)
        later['first_seen_at']=(T+timedelta(hours=1,minutes=20)).isoformat()
        later['ingestion_completed_at']=(T+timedelta(hours=1,minutes=21)).isoformat()
        self.archive.store_snapshot(later);self.now=T+timedelta(hours=1,minutes=30);self.run_shadow()
        def read(targets,assessed_at):return {at:receipt(at,12) for at in targets}
        result=self.m.train_once(self.archive,self.state,reader=read,site=SITE,sensor_epoch=EPOCH,cutoff=T+timedelta(days=1),code_revision=REVISION,apply=True)
        self.assertEqual(result['selected_issues'],1)
        self.assertEqual(result['pairs'],2)
        self.assertAlmostEqual(self.state.current_model()['model']['intercept_c'],2)

    def test_missing_local_labels_cannot_replace_previous_model(self):
        self.run_shadow()
        old=fit_bias([],cutoff=T,code_revision=REVISION);self.state.install_model(old,fitted_at=T)
        result=self.m.train_once(self.archive,self.state,reader=lambda targets,assessed_at:{},site=SITE,sensor_epoch=EPOCH,cutoff=T+timedelta(days=1),code_revision=REVISION,apply=True)
        self.assertEqual(result['status'],'NO_ELIGIBLE_PAIRS')
        self.assertEqual(self.state.current_model()['model']['artifact_sha256'],old['artifact_sha256'])

    def test_training_cli_reads_native_labels_in_isolated_runtime_without_applying(self):
        import io,json
        from contextlib import redirect_stdout
        from weather_learning.cli import main_train
        from weather_temperature_evidence import TemperaturePolicy
        from daily_temperature_runtime import SOURCE_POLICY
        self.run_shadow()
        policy=TemperaturePolicy(**SOURCE_POLICY)
        def fetch(connection_factory,**kwargs):
            self.assertEqual(kwargs['stream'],'outdoor')
            self.assertEqual(kwargs['sensor_epoch'],EPOCH)
            return [(at,receipt(at,12)) for at in kwargs['targets']]
        output=io.StringIO()
        args=['--archive',str(self.archive.root),'--state',str(self.state.root),'--temperature-policy','/unused',
              '--temperature-db-config','/unused','--code-revision',REVISION,'--days','366']
        with patch('weather_learning.cli._context',return_value=(self.archive,self.state,SITE,policy,EPOCH)),patch('hourly_temperature_runtime.read_db_config',return_value={}),patch('weather_temperature_history.fetch_temperature_grid_v2',side_effect=fetch),redirect_stdout(output):
            status=main_train(args)
        self.assertEqual(status,0,output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['pairs'],2)
        self.assertFalse(json.loads(output.getvalue())['applied'])
        self.assertIsNone(self.state.current_model())

    def test_foreign_epoch_and_site_cannot_initialize_candidate(self):
        self.run_shadow()
        issues=self.state.training_issues(T,T+timedelta(days=1),sensor_epoch='00000000-0000-4000-8000-000000000003')
        self.assertEqual(issues,[])
        raw=native_snapshot();raw['site']['latitude']=0
        # Google/source validation refuses a relabeled site even if a capsule was retained.
        with self.assertRaises(ValueError):self.m.reconstruct_targets(raw,self.now,SITE)

    def test_state_capacity_refusal_precedes_any_publication(self):
        with patch('weather_learning.shadow.shutil.disk_usage',return_value=type('Disk',(),{'free':0})()):
            with self.assertRaises(ValueError):self.run_shadow()

    def test_shadow_publisher_rejects_production_and_actuator_items(self):
        report=self.run_shadow();sent=[]
        for name in ('Forecast_10Day_JSON','SouthOutlet_Outlet1_Switch','Forecast_Provider_Status_JSON/../../commands'):
            with self.subTest(name=name),self.assertRaises(ValueError):self.p.publish_item(name,report,lambda *args:sent.append(args))
        self.assertEqual(sent,[])

    def test_publisher_commits_status_last_and_stops_on_failed_write(self):
        report=self.run_shadow();sent=[]
        def put(name,value):
            sent.append(name)
            if len(sent)==2:raise OSError('synthetic network loss')
        with self.assertRaises(OSError):self.p.publish_bundle(report,put)
        self.assertEqual(sent,['Forecast_Local_Shadow_JSON','Forecast_Comparison_JSON'])

    def test_invalid_payload_is_refused_before_writing_any_item(self):
        report=self.run_shadow();sent=[]
        for mutate in ('version','number','authority'):
            invalid=deepcopy(report)
            if mutate=='version':invalid['version']=3
            if mutate=='number':invalid['hours'][0]['rawC']=float('nan')
            if mutate=='authority':invalid['automaticActuation']=True
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):self.p.publish_bundle(invalid,lambda *args:sent.append(args))
        self.assertEqual(sent,[])

    def test_google_only_contract_and_retained_issue_have_no_incumbent_source(self):
        report=self.run_shadow()
        self.assertEqual(report['version'],2)
        self.assertEqual(report['schema'],'earthship-weather-provider-shadow/v2')
        self.assertNotIn('incumbent',report)
        self.assertTrue(all(set(row)=={'at','rawC','localC'} for row in report['hours']))
        issues=self.state.training_issues(T-timedelta(days=1),T+timedelta(days=1),sensor_epoch=EPOCH)
        self.assertEqual(issues[0]['schema'],'earthship-weather-shadow-issue/v2')
        self.assertEqual(set(issues[0]),{'schema','sensor_epoch','code_revision','payload'})

    def test_previous_shadow_contract_cannot_publish_into_fresh_google_cohort(self):
        value=self.run_shadow()
        value.pop('generation')
        value.update(version=1,schema='earthship-weather-provider-shadow/v1')
        with self.assertRaises(ValueError):self.p.seal_payload(value)

if __name__=='__main__':unittest.main()
