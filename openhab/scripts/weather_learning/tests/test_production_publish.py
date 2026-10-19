"""Publication mechanics use injected local stores, never a live transport."""
from datetime import timedelta
import importlib,json,pathlib,tempfile,unittest
from learning_fixtures import T,SITE
from test_provider import full_snapshot
from weather_learning.archive import Archive
from weather_learning.provider import load_production_forecast


class ProductionPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        archive=Archive(pathlib.Path(self.tmp.name));archive.store_snapshot(full_snapshot())
        self.now=T+timedelta(minutes=30)
        self.provider=load_production_forecast(archive,decision_at=self.now,required_horizon=timedelta(hours=48),site=SITE)
        self.empty=load_production_forecast(Archive(pathlib.Path(self.tmp.name)/'empty'),decision_at=self.now,required_horizon=timedelta(hours=48),site=SITE)
        self.api=importlib.import_module('weather_learning.production_publish')
        self.store={};self.writes=[]
    def put(self,item,value):self.writes.append((item,value));self.store[item]=value
    def read(self,item):return self.store[item]
    def publish(self,provider=None,**kwargs):
        return self.api.publish_cycle(self.provider if provider is None else provider,now=self.now,put_state=kwargs.get('put_state',self.put),read_state=kwargs.get('read_state',self.read),authorize=kwargs.get('authorize',lambda provider:True))

    def test_authorization_is_required_before_any_state_write(self):
        for authorization in (None,lambda provider:False,lambda provider:1):
            with self.subTest(authorization=authorization),self.assertRaises(ValueError):self.publish(authorize=authorization)
        self.assertEqual(self.writes,[])

    def test_numeric_values_have_item_units_and_no_fake_partial_day_or_old_learning(self):
        states=self.api.production_states(self.provider,now=self.now)
        self.assertEqual(states['Forecast_Temp'],'50.0 °F')
        self.assertEqual(states['Forecast_Cloudiness'],'50.0 %')
        self.assertEqual(states['Forecast_Radiation'],'100.0 W/m²')
        self.assertEqual(states['Forecast_Daily_High'],'UNDEF')
        self.assertEqual(states['Forecast_Daily_Low'],'UNDEF')
        self.assertEqual(states['Forecast_Daily_PrecipSum'],'UNDEF')
        self.assertEqual(float(states['Forecast_Tomorrow_High']),50)
        self.assertEqual(float(states['Forecast_Tomorrow_Low']),50)
        self.assertEqual(len(states),11)
        self.assertFalse(any('Correction' in item or 'Error' in item or item.startswith('Predicted_') for item in states))

    def test_detail_is_withdrawn_first_and_committed_last_after_all_readbacks(self):
        reads=[]
        def read(item):reads.append(item);return self.read(item)
        result=self.publish(read_state=read)
        self.assertEqual(result['status'],'PUBLISHED')
        self.assertEqual(self.writes[0][0],self.api.DETAIL)
        self.assertEqual(json.loads(self.writes[0][1])['providerReason'],'PUBLICATION_PENDING')
        self.assertEqual(self.writes[-1][0],self.api.DETAIL)
        self.assertEqual(json.loads(self.writes[-1][1])['providerStatus'],'AVAILABLE')
        self.assertEqual(set(reads),set(self.api.production_states(self.provider,now=self.now)))
        self.assertFalse(result['release_authorized']);self.assertFalse(result['automatic_actuation'])

    def test_missing_source_withdraws_all_owned_numeric_and_json_states(self):
        self.store.update(self.api.production_states(self.provider,now=self.now))
        result=self.publish(self.empty)
        self.assertEqual(result['status'],'WITHDRAWN')
        self.assertEqual(json.loads(self.store[self.api.DETAIL])['providerStatus'],'UNAVAILABLE')
        self.assertEqual(json.loads(self.store['Forecast_Daily_JSON']),[])
        self.assertTrue(all(self.store[item]=='UNDEF' for item in self.api.NUMERIC_ITEMS))

    def test_midcycle_failure_withdraws_every_owned_output_and_never_commits_ready(self):
        failed=[]
        def put(item,value):
            if item=='Forecast_Radiation' and not failed:failed.append(True);raise OSError('simulated failure')
            self.put(item,value)
        result=self.publish(put_state=put)
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(result['unconfirmed_withdrawals'],[])
        self.assertEqual(set(result['withdrawal_attempts']),set(self.api.production_states(self.provider,now=self.now)))
        self.assertEqual(json.loads(self.store[self.api.DETAIL])['providerReason'],'PUBLICATION_FAILED')
        self.assertTrue(all(self.store[item]=='UNDEF' for item in self.api.NUMERIC_ITEMS))
        self.assertFalse(any(json.loads(raw)['providerStatus']=='AVAILABLE' for item,raw in self.writes if item==self.api.DETAIL))

    def test_readback_failure_and_persistent_clear_failure_are_reported_without_stopping_other_clears(self):
        def put(item,value):
            if item=='Forecast_Radiation':raise OSError('private transport detail must not escape')
            self.put(item,value)
        result=self.publish(put_state=put)
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(result['unconfirmed_withdrawals'],['Forecast_Radiation'])
        self.assertEqual(len(result['withdrawal_attempts']),11)
        self.assertNotIn('private transport',json.dumps(result))

    def test_numerical_readback_accepts_native_temperature_unit_conversion(self):
        def read(item):return '10 °C' if item=='Forecast_Temp' else self.read(item)
        self.assertEqual(self.publish(read_state=read)['status'],'PUBLISHED')

    def test_dimensionless_percentage_readback_accepts_only_equivalent_quantities(self):
        self.assertTrue(self.api._same_state('Forecast_Cloudiness','25 %','0.25 one'))
        self.assertTrue(self.api._same_state('Forecast_Cloudiness','25 %','0.25 1'))
        self.assertFalse(self.api._same_state('Forecast_Cloudiness','25 %','25 one'))
        self.assertFalse(self.api._same_state('Forecast_Cloudiness','25 %','0.25'))

    def test_wrong_readback_withdraws_rather_than_claiming_publication(self):
        def read(item):return '999 °F' if item=='Forecast_Temp' else self.read(item)
        result=self.publish(read_state=read)
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(result['unconfirmed_withdrawals'],['Forecast_Temp'])
        self.assertEqual(json.loads(self.store[self.api.DETAIL])['providerStatus'],'UNAVAILABLE')

    def test_every_single_write_or_read_failure_attempts_the_complete_withdrawal(self):
        for operation in ('write','read'):
            for fail_at in range(1,13):
                with self.subTest(operation=operation,fail_at=fail_at):
                    self.store={};self.writes=[];counts={'write':0,'read':0}
                    def put(item,value):
                        counts['write']+=1
                        if operation=='write' and counts['write']==fail_at:raise OSError('simulated write failure')
                        self.put(item,value)
                    def read(item):
                        counts['read']+=1
                        if operation=='read' and counts['read']==fail_at:raise OSError('simulated read failure')
                        return self.read(item)
                    result=self.publish(put_state=put,read_state=read)
                    self.assertEqual(result['status'],'FAILED')
                    self.assertEqual(len(result['withdrawal_attempts']),11)
                    self.assertEqual(result['unconfirmed_withdrawals'],[])
                    self.assertEqual(json.loads(self.store[self.api.DETAIL])['providerStatus'],'UNAVAILABLE')
                    self.assertTrue(all(self.store[item]=='UNDEF' for item in self.api.NUMERIC_ITEMS))

    def test_daily_numeric_extrema_preserve_distinct_high_and_low(self):
        from copy import deepcopy
        from weather_learning.config import COLLECTIONS
        from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
        source=full_snapshot();parts=[]
        for original in source['source_originals']:
            raw=deepcopy(original['payload']);bands=raw['region'][0][4:]
            if original['collection']==COLLECTIONS['station']:
                for hour,row in enumerate(raw['region'][1:],1):row[4]=273.15+hour%24
            parts.append(parse_collection_response(raw,collection=original['collection'],bands=bands,site=SITE,initialized_at=T,horizon=80))
        source=make_snapshot(parts,site=SITE,initialized_at=T,first_seen_at=T+timedelta(minutes=20),completed_at=T+timedelta(minutes=21))
        archive=Archive(pathlib.Path(self.tmp.name)/'varied');archive.store_snapshot(source)
        now=T+timedelta(hours=20)
        provider=load_production_forecast(archive,decision_at=now,required_horizon=timedelta(hours=48),site=SITE)
        states=self.api.production_states(provider,now=now)
        self.assertAlmostEqual(float(states['Forecast_Daily_High'].split()[0]),73.4)
        self.assertAlmostEqual(float(states['Forecast_Daily_Low'].split()[0]),32)
        self.assertAlmostEqual(float(states['Forecast_Tomorrow_High']),73.4)
        self.assertAlmostEqual(float(states['Forecast_Tomorrow_Low']),32)
        self.assertAlmostEqual(float(states['Forecast_Daily_PrecipSum'].split()[0]),24)
