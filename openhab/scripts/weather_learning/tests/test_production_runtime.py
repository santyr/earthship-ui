"""Bounded Google publication uses real lock/file/REST adapters with local HTTP."""
from datetime import timedelta
import fcntl,importlib.util,io,json,os,pathlib,subprocess,sys,tempfile,unittest,uuid
from unittest.mock import patch
from urllib.parse import urlsplit
from learning_fixtures import T,SITE,full_snapshot
from weather_learning.archive import Archive
from weather_learning.contracts import identity
from openhab_runtime_io import ReadBudget

TYPES={
 'Forecast_Hourly_JSON':'String','Forecast_Daily_JSON':'String','Forecast_10Day_JSON':'String',
 'Forecast_Temp':'Number:Temperature','Forecast_Cloudiness':'Number:Dimensionless',
 'Forecast_Radiation':'Number:Intensity','Forecast_Daily_High':'Number:Temperature',
 'Forecast_Daily_Low':'Number:Temperature','Forecast_Daily_PrecipSum':'Number:Length',
 'Forecast_Tomorrow_High':'Number','Forecast_Tomorrow_Low':'Number',
}


class Response(io.BytesIO):
    def __init__(self,url,raw):super().__init__(raw);self.url=url
    def geturl(self):return self.url


class LocalOpenHAB:
    def __init__(self):
        self.types=dict(TYPES);self.links=[];self.states={};self.requests=[]
        self.before_put=None;self.fail_once=None
    def open(self,request,timeout):
        method=request.get_method();path=urlsplit(request.full_url).path.removeprefix('/rest')
        self.requests.append((method,path));assert 0<timeout<=5
        assert request.get_header('Authorization').startswith('Bearer ')
        if method=='GET' and path=='/links':data=self.links
        elif path.startswith('/items/'):
            parts=path.split('/');item=parts[2];assert item in TYPES
            if method=='PUT':
                assert parts[3:] == ['state']
                raw=request.data.decode()
                if self.before_put is not None:self.before_put(item,raw)
                if item==self.fail_once:
                    self.fail_once=None;raise OSError('synthetic unavailable state endpoint')
                self.states[item]=raw
                return Response(request.full_url,b'')
            if parts[3:]==['state']:return Response(request.full_url,self.states.get(item,'UNDEF').encode())
            data={'name':item,'type':self.types[item],'editable':False}
        else:raise AssertionError('unexpected endpoint: '+path)
        return Response(request.full_url,json.dumps(data).encode())


class PublicationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('weather_learning.production_runtime'),
            'planned qualified publication runtime is absent')
        self.api=importlib.import_module('weather_learning.production_runtime')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name);self.root.chmod(0o700)
        archive=Archive(self.root/'archive');self.snapshot=archive.store_snapshot(full_snapshot())
        self.archive=Archive.open_readonly(archive.root)
        self.evidence=self.root/'attempts';self.evidence.mkdir(mode=0o700)
        self.lock=self.root/'lock';self.lock.write_bytes(b'');self.lock.chmod(0o600)
        self.server=LocalOpenHAB();self.elapsed=0
        self.budget=ReadBudget(85,clock=lambda:self.elapsed,sleeper=self.advance,max_requests=96)
        token=uuid.uuid4().hex
        self.transport=self.api.ProductionTransport(base='http://127.0.0.1:8080/rest',
            token_reader=lambda:token,budget=self.budget,opener=self.server.open)
    def advance(self,seconds):self.elapsed+=seconds
    def run_worker(self,**overrides):
        args=dict(archive=self.archive,site=SITE,evidence_directory=self.evidence,shared_lock=self.lock,
            code_revision='e'*40,transport=self.transport,authorize=lambda provider:True,guard=lambda:None,
            clock=lambda:T+timedelta(minutes=30,seconds=self.elapsed),required_horizon=timedelta(hours=48))
        args.update(overrides);return self.api.run_publication(**args)
    def starts(self):return list(self.evidence.glob('*.publication-attempt-v1.json'))
    def puts(self):return [path for method,path in self.server.requests if method=='PUT']

    def test_missing_authorization_refuses_before_http_or_attempt_mutation(self):
        for grant in (None,lambda provider:False,lambda provider:1):
            with self.subTest(grant=grant),self.assertRaises(ValueError):self.run_worker(authorize=grant)
        self.assertEqual(self.server.requests,[]);self.assertEqual(self.starts(),[])

    def test_shared_lock_excludes_competing_writer_before_http(self):
        with self.lock.open('r+') as held:
            fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.run_worker()
        self.assertEqual(self.server.requests,[]);self.assertEqual(self.starts(),[])

    def test_source_and_exact_states_are_retained_before_first_state_update(self):
        def before(item,raw):
            starts=self.starts();self.assertEqual(len(starts),1)
            body=json.loads(starts[0].read_bytes())
            self.assertEqual(body['provider']['source']['snapshot_sha256'],self.snapshot)
            self.assertEqual(body['states_sha256'],identity(body['states']))
            self.assertEqual(set(body['states']),set(TYPES))
            self.assertFalse(body['automatic_actuation'])
        self.server.before_put=before
        result=self.run_worker()
        self.assertEqual(result['status'],'PUBLISHED')
        self.assertEqual(set(self.server.states),set(TYPES))
        self.assertEqual(self.puts()[0],'/items/Forecast_10Day_JSON/state')
        self.assertEqual(self.puts()[-1],'/items/Forecast_10Day_JSON/state')
        self.assertEqual(json.loads(self.server.states['Forecast_10Day_JSON'])['provider'],'weathernext3')
        self.assertEqual(self.server.states['Forecast_Temp'],'50.0 °F')
        finish=json.loads(pathlib.Path(result['result_path']).read_bytes())
        self.assertEqual(finish['attempt_sha256'],json.loads(self.starts()[0].read_bytes())['attempt_sha256'])
        self.assertEqual(finish['publication']['status'],'PUBLISHED')
        self.assertFalse(finish['release_authorized']);self.assertFalse(finish['automatic_actuation'])

    def test_linked_item_never_receives_state_updates(self):
        self.server.links=[{'itemName':'Forecast_Temp','channelUID':'synthetic:old:link'}]
        result=self.run_worker()
        self.assertEqual(result['status'],'REFUSED');self.assertEqual(self.puts(),[])
        finish=json.loads(pathlib.Path(result['result_path']).read_bytes())
        self.assertEqual(finish['failure_kind'],'CHANNEL_LINK_PRESENT')
        self.assertEqual(finish['failed_item'],'Forecast_Temp')

    def test_wrong_type_item_never_receives_state_updates(self):
        self.server.types['Forecast_Temp']='Switch'
        result=self.run_worker()
        self.assertEqual(result['status'],'REFUSED');self.assertEqual(self.puts(),[])
        finish=json.loads(pathlib.Path(result['result_path']).read_bytes())
        self.assertEqual(finish['failure_kind'],'ITEM_TYPE_OR_OWNER')
        self.assertEqual(finish['failed_item'],'Forecast_Temp')

    def test_midcycle_error_retains_failure_and_withdraws_all_owned_values(self):
        self.server.fail_once='Forecast_Radiation'
        result=self.run_worker()
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(json.loads(self.server.states['Forecast_10Day_JSON'])['providerStatus'],'UNAVAILABLE')
        self.assertTrue(all(self.server.states[item]=='UNDEF' for item in TYPES if TYPES[item]!='String'))
        finish=json.loads(pathlib.Path(result['result_path']).read_bytes())
        self.assertEqual(finish['publication']['failed_item'],'Forecast_Radiation')
        self.assertEqual(finish['publication']['unconfirmed_withdrawals'],[])

    def test_archive_change_cannot_commit_available_detail_but_can_withdraw(self):
        def change(item,raw):
            if item!='Forecast_10Day_JSON' and raw not in ('UNDEF','[]'):
                self.server.before_put=None
                (self.archive.objects/(self.snapshot+'.json')).write_bytes(b'{}')
        self.server.before_put=change
        result=self.run_worker()
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(json.loads(self.server.states['Forecast_10Day_JSON'])['providerStatus'],'UNAVAILABLE')
        self.assertTrue(all(self.server.states[item]=='UNDEF' for item in TYPES if TYPES[item]!='String'))

    def test_empty_source_withdraws_without_legacy_access_or_model_fitting(self):
        empty=Archive(self.root/'empty')
        result=self.run_worker(archive=Archive.open_readonly(empty.root))
        self.assertEqual(result['status'],'WITHDRAWN')
        self.assertEqual(json.loads(self.server.states['Forecast_10Day_JSON'])['providerReason'],'NO_ELIGIBLE_SOURCE')
        self.assertTrue(all(self.server.states[item]=='UNDEF' for item in TYPES if TYPES[item]!='String'))

    def test_fixed_transport_cannot_send_commands_or_write_other_items(self):
        for item in ('SouthOutlet_Outlet1_Switch','Thermal_Model_JSON','Forecast_Temp/state'):
            with self.subTest(item=item),self.assertRaises(ValueError):
                self.transport.put(item,'ON',before_request=lambda:None)
        self.assertEqual(self.server.requests,[])

    def test_changed_authorization_is_rechecked_after_request_pacing(self):
        written_at=[]
        self.server.before_put=lambda item,raw:written_at.append(self.elapsed)
        result=self.run_worker(authorize=lambda provider:self.elapsed<15)
        self.assertIn(result['status'],('FAILED','REFUSED'))
        self.assertTrue(all(at<15 for at in written_at))
        if 'Forecast_10Day_JSON' in self.server.states:
            self.assertNotEqual(json.loads(self.server.states['Forecast_10Day_JSON'])['providerStatus'],'AVAILABLE')

    def test_aggregate_transfer_budget_stops_before_another_http_request(self):
        with patch.object(self.api,'MAX_TRANSFER_BYTES',100):
            result=self.run_worker()
            requests=len(self.server.requests)
            with self.assertRaises(ValueError):self.transport.preflight(before_request=lambda:None)
            self.assertEqual(len(self.server.requests),requests)
        self.assertEqual(result['status'],'REFUSED')
        self.assertLessEqual(self.transport.total,101)
        self.assertEqual(self.puts(),[])

    def test_replaced_lock_inode_cannot_authorize_further_state_updates(self):
        def replace(item,raw):
            self.server.before_put=None;self.lock.unlink()
            self.lock.write_bytes(b'');self.lock.chmod(0o600)
        self.server.before_put=replace
        result=self.run_worker()
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(self.puts(),['/items/Forecast_10Day_JSON/state'])
        self.assertEqual(json.loads(self.server.states['Forecast_10Day_JSON'])['providerStatus'],'UNAVAILABLE')

    def test_google_publication_does_not_import_retired_provider_or_learning(self):
        import builtins
        original=builtins.__import__
        def guarded(name,*args,**kwargs):
            if name.split('.')[0] in {'forecast_intel','forecast_input_capture','forecast_temperature_origin'}:
                raise AssertionError('legacy forecast dependency')
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=guarded):result=self.run_worker()
        self.assertEqual(result['status'],'PUBLISHED')

    def test_cold_runtime_and_shared_lock_need_no_thermal_or_numerical_stack(self):
        code="""import builtins,pathlib,tempfile
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name.split('.')[0] in {'numpy','scipy','thermal_model'}:raise ImportError('numerical dependency')
    return original(name,*args,**kwargs)
builtins.__import__=guarded
import weather_learning.production_runtime as runtime
with tempfile.TemporaryDirectory() as directory:
    path=pathlib.Path(directory)/'lock';path.write_bytes(b'');path.chmod(0o600)
    with runtime.SharedScoreLock(path) as held:held.verify()
assert runtime.ReadBudget(5).remaining()>0
"""
        result=subprocess.run([sys.executable,'-c',code],
            env=dict(os.environ,PYTHONPATH=str(pathlib.Path(__file__).resolve().parents[2])),
            capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
