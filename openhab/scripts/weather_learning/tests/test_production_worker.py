"""Operational admission uses real private files and simulated local REST only."""
from datetime import timedelta
from hashlib import sha256
import importlib,importlib.util,json,pathlib,shutil,tempfile,unittest,uuid
from unittest.mock import patch
from urllib.error import HTTPError
from learning_fixtures import T,SITE,full_snapshot
from test_production_runtime import LocalOpenHAB
from weather_learning.archive import Archive
from weather_learning.contracts import canonical,identity
from openhab_runtime_io import ReadBudget


class ProductionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('weather_learning.production_worker'),
                             'planned operational publisher caller is absent')
        self.api=importlib.import_module('weather_learning.production_worker')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name);self.root.chmod(0o700)
        self.now=T+timedelta(minutes=30);self.elapsed=0
        self.archive=Archive(self.root/'archive');self.archive.store_snapshot(full_snapshot(hours=360))
        self.attempts=self.root/'attempts';self.attempts.mkdir(mode=0o700)
        self.lock=self.private('shared.lock',b'')
        self.token=self.private('openhab.env',('OPENHAB_TOKEN='+uuid.uuid4().hex+'\n').encode())
        self.items=self.root/'items';self.items.mkdir(mode=0o755)
        # The native CLI tests leave a private umask; freeze this reviewed fixture.
        self.items.chmod(0o755)
        self.definitions='\n'.join(kind+' '+name+' "Forecast"' for name,kind in self.api.ITEM_TYPES.items())+'\n'
        self.item=self.items/'forecast.items';self.item.write_text(self.definitions);self.item.chmod(0o644)
        self.units={unit:dict(Id=unit,LoadState='loaded',ActiveState='inactive',UnitFileState='disabled') for unit in self.api.INCUMBENT_UNITS}
        evidence=self.private('gate-evidence.json',canonical(dict(synthetic=True,status='PASS')))
        self.release=dict(schema=self.api.RELEASE_SCHEMA,provider='weathernext3',decision='APPROVED_FOR_CUTOVER',
            reviewed_at=(self.now-timedelta(minutes=1)).isoformat(),reviewed_by='synthetic-test-reviewer',
            code_revision='a'*40,runtime_sha256=identity(self.api.runtime_manifest()),site=dict(SITE.__dict__),horizon_hours=336,
            weather_lineage=['weathernext3','qualified_local_measurements'],automatic_actuation=False,
            gates={gate:dict(status='PASS',evidence_path=str(evidence),sha256=sha256(evidence.read_bytes()).hexdigest()) for gate in self.api.GATES})
        self.release_path=self.private('release.json',canonical(self.release))
        self.config=dict(schema=self.api.CONFIG_SCHEMA,openhab_base='http://127.0.0.1:8080/rest',
            archive=str(self.archive.root),evidence_directory=str(self.attempts),shared_lock=str(self.lock),
            token_file=str(self.token),release_path=str(self.release_path),release_sha256=sha256(self.release_path.read_bytes()).hexdigest(),
            items_directory=str(self.items),items_directory_metadata=dict(uid=self.items.stat().st_uid,gid=self.items.stat().st_gid,mode=0o755),item_files={'forecast.items':sha256(self.item.read_bytes()).hexdigest()},
            code_revision='a'*40,runtime_manifest=self.api.runtime_manifest())
        self.release['item_ownership_sha256']=identity({key:self.config[key] for key in ('items_directory','items_directory_metadata','item_files')})
        self.release_path.write_bytes(canonical(self.release));self.config['release_sha256']=sha256(self.release_path.read_bytes()).hexdigest()
        self.config_path=self.private('publisher.json',canonical(self.config));self.server=LocalOpenHAB();self.astro_item=None
        self.transport=self.api.ProductionTransport(base=self.config['openhab_base'],token_reader=lambda:uuid.uuid4().hex,
            budget=ReadBudget(85,clock=lambda:self.elapsed,sleeper=self.advance,max_requests=96),opener=self.open)
    def private(self,name,raw):
        path=self.root/name;path.write_bytes(raw);path.chmod(0o600);return path
    def advance(self,seconds):self.elapsed+=seconds
    def open(self,request,timeout):
        if request.full_url.endswith('/items/Astro_Forecast_Context_JSON'):
            self.assertEqual(request.get_method(),'GET')
            self.server.requests.append(('GET','/items/Astro_Forecast_Context_JSON'))
            if self.astro_item is None:raise HTTPError(request.full_url,404,'missing optional Astro',{},None)
            from test_production_runtime import Response
            return Response(request.full_url,canonical(self.astro_item))
        if request.full_url.endswith('/services/org.openhab.i18n/config'):
            from test_production_runtime import Response
            self.server.requests.append(('GET','/services/org.openhab.i18n/config'))
            return Response(request.full_url,canonical(dict(location=str(SITE.latitude)+','+str(SITE.longitude),timezone=SITE.timezone)))
        return self.server.open(request,timeout)
    def write_config(self):self.config_path.write_bytes(canonical(self.config))
    def write_release(self):
        self.release_path.write_bytes(canonical(self.release));self.config['release_sha256']=sha256(self.release_path.read_bytes()).hexdigest();self.write_config()
    def run_worker(self,**kwargs):
        return self.api.run_worker(self.config_path,guard=lambda:None,unit_reader=lambda:self.units,
            transport=self.transport,clock=lambda:self.now+timedelta(seconds=self.elapsed),**kwargs)
    def puts(self):return [row for row in self.server.requests if row[0]=='PUT']

    def test_default_is_readonly_even_with_synthetic_complete_review(self):
        result=self.run_worker()
        self.assertEqual(result['status'],'PREFLIGHT_PASSED');self.assertEqual(self.puts(),[])
        self.assertEqual(list(self.attempts.iterdir()),[]);self.assertFalse(result['automatic_actuation'])

    def test_explicit_publication_retains_admission_identity_before_writes(self):
        def inspect(item,raw):
            attempts=list(self.attempts.glob('*.publication-attempt-v1.json'))
            self.assertEqual(len(attempts),1)
            self.assertEqual(json.loads(attempts[0].read_bytes())['admission_sha256'],identity(dict(config_sha256=sha256(self.config_path.read_bytes()).hexdigest(),release_sha256=self.config['release_sha256'])))
        self.server.before_put=inspect
        result=self.run_worker(publish=True)
        self.assertEqual(result['status'],'PUBLISHED');self.assertEqual(len(self.server.states),11)

    def test_native_astro_reaches_published_daylight_with_original_identity(self):
        from astro_serving_fixtures import astro_source
        source=astro_source(self.now)
        self.astro_item=dict(name='Astro_Forecast_Context_JSON',type='String',state=source['raw'],
            lastStateUpdate=int(source['available_at'].timestamp()*1000))
        result=self.run_worker(publish=True)
        self.assertEqual(result['status'],'PUBLISHED')
        hourly=json.loads(self.server.states['Forecast_Hourly_JSON'])
        self.assertTrue(hourly[0]['isDay']);self.assertFalse(hourly[1]['isDay'])
        detail=json.loads(self.server.states['Forecast_10Day_JSON'])
        self.assertEqual(detail['solarSource']['status'],'AVAILABLE')
        self.assertEqual(detail['solarSource']['sourceSha256'],sha256(source['raw'].encode()).hexdigest())
        self.assertEqual(next(day for day in detail['days'] if day['date']=='2026-01-01')['summary']['daylightSeconds'],43200)
        attempt=json.loads(next(self.attempts.glob('*.publication-attempt-v1.json')).read_bytes())
        self.assertEqual(attempt['provider']['solar_context']['days'],json.loads(source['raw'])['days'])
        self.assertIn(('GET','/items/Astro_Forecast_Context_JSON'),self.server.requests)
        self.assertNotIn(('PUT','/items/Astro_Forecast_Context_JSON/state'),self.server.requests)

    def test_unavailable_or_future_native_astro_preserves_google_weather(self):
        from astro_serving_fixtures import astro_source
        for damage in ('missing','future-update','boolean-update','wrong-site','bad-json'):
            with self.subTest(damage=damage):
                self.transport.budget=ReadBudget(85,clock=lambda:self.elapsed,sleeper=self.advance,max_requests=96)
                source=astro_source(self.now,damage='site' if damage=='wrong-site' else None)
                self.astro_item=None if damage=='missing' else dict(name='Astro_Forecast_Context_JSON',type='String',
                    state=source['raw'],lastStateUpdate=int(source['available_at'].timestamp()*1000))
                if damage=='future-update':self.astro_item['lastStateUpdate']=int((self.now+timedelta(days=1)).timestamp()*1000)
                if damage=='boolean-update':self.astro_item['lastStateUpdate']=True
                if damage=='bad-json':self.astro_item['state']='{'
                result=self.run_worker(publish=True)
                self.assertEqual(result['status'],'PUBLISHED')
                detail=json.loads(self.server.states['Forecast_10Day_JSON'])
                self.assertEqual(detail['providerStatus'],'AVAILABLE')
                self.assertEqual(detail['solarSource']['status'],'UNAVAILABLE')
                self.assertTrue(all(row['isDay'] is None for row in json.loads(self.server.states['Forecast_Hourly_JSON'])))
                self.assertNotEqual(self.server.states['Forecast_Temp'],'UNDEF')

    def test_native_astro_validator_tamper_refuses_before_http(self):
        runtime=self.root/'runtime';runtime.mkdir(mode=0o700)
        astro='openhab/scripts/astro_forecast_context.py'
        for name in set(self.api.SOURCE_FILES)|{astro}:
            target=runtime/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(self.api.ROOT/name,target);target.chmod(0o644)
        with patch.object(self.api,'ROOT',runtime):
            path=runtime/astro;path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaises(ValueError):self.run_worker(publish=True)
        self.assertEqual(self.server.requests,[])

    def test_selected_production_source_tamper_refuses_before_any_http(self):
        runtime=self.root/'selected-runtime';runtime.mkdir(mode=0o700)
        selected='openhab/scripts/weather_learning/production_forecast.py'
        for name in set(self.api.SOURCE_FILES)|{selected}:
            target=runtime/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(self.api.ROOT/name,target);target.chmod(0o644)
        with patch.object(self.api,'ROOT',runtime):
            path=runtime/selected;path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaises(ValueError):self.run_worker(publish=True)
        self.assertEqual(self.server.requests,[])

    def test_revocation_during_native_astro_read_refuses_before_put(self):
        from astro_serving_fixtures import astro_source
        source=astro_source(self.now)
        self.astro_item=dict(name='Astro_Forecast_Context_JSON',type='String',state=source['raw'],
            lastStateUpdate=int(source['available_at'].timestamp()*1000))
        original=self.transport.opener
        def revoke(request,timeout):
            response=original(request,timeout)
            if request.full_url.endswith('/items/Astro_Forecast_Context_JSON'):self.release_path.write_bytes(b'{}')
            return response
        self.transport.opener=revoke
        with self.assertRaises(ValueError):self.run_worker(publish=True)
        self.assertEqual(self.puts(),[])

    def test_unqualified_or_missing_gate_refuses_before_any_http(self):
        for mode in ('shadow','missing','future','lineage'):
            original=json.loads(canonical(self.release))
            if mode=='shadow':self.release['decision']='SHADOW_ONLY'
            if mode=='missing':del self.release['gates']['solar']
            if mode=='future':self.release['reviewed_at']=(self.now+timedelta(days=1)).isoformat()
            if mode=='lineage':self.release['weather_lineage'].append('incumbent_weather')
            self.write_release()
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.run_worker(publish=True)
            self.release=original
        self.assertEqual(self.server.requests,[])

    def test_changed_gate_original_is_refused(self):
        evidence=pathlib.Path(self.release['gates']['access']['evidence_path']);evidence.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.run_worker(publish=True)
        self.assertEqual(self.server.requests,[])

    def test_active_or_enabled_incumbent_writer_refuses_before_http(self):
        for field,value in (('ActiveState','active'),('UnitFileState','enabled')):
            old=self.units[self.api.INCUMBENT_UNITS[0]][field];self.units[self.api.INCUMBENT_UNITS[0]][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.run_worker(publish=True)
            self.units[self.api.INCUMBENT_UNITS[0]][field]=old
        self.assertEqual(self.server.requests,[])

    def test_duplicate_file_owner_and_changed_item_bytes_refuse(self):
        duplicate=self.items/'extra.items';duplicate.write_text(self.definitions);duplicate.chmod(0o644)
        with self.assertRaises(ValueError):self.run_worker(publish=True)
        duplicate.unlink();self.item.write_text(self.definitions+'// changed\n')
        with self.assertRaises(ValueError):self.run_worker(publish=True)
        self.assertEqual(self.server.requests,[])

    def test_release_revocation_after_first_put_prevents_further_updates(self):
        def revoke(item,raw):self.release_path.write_bytes(b'{}')
        self.server.before_put=revoke
        result=self.run_worker(publish=True)
        self.assertEqual(result['status'],'FAILED');self.assertEqual(len(self.puts()),1)
        self.assertNotIn('AVAILABLE',[json.loads(value).get('providerStatus') for item,value in self.server.states.items() if item=='Forecast_10Day_JSON'])

    def test_private_config_and_exact_runtime_manifest_are_mandatory(self):
        self.config_path.chmod(0o644)
        with self.assertRaises(ValueError):self.run_worker(publish=True)
        self.config_path.chmod(0o600);self.config['runtime_manifest'].pop(next(iter(self.config['runtime_manifest'])));self.write_config()
        with self.assertRaises(ValueError):self.run_worker(publish=True)
        self.assertEqual(self.server.requests,[])

    def test_reviewed_installed_directory_permissions_are_supported(self):
        # The real /etc/openhab/items is openhab:openhab mode 2775. A reviewed
        # directory identity is permitted; each source file remains nonwritable.
        self.items.chmod(0o2775);self.config['items_directory_metadata']['mode']=0o2775
        self.release['item_ownership_sha256']=identity({key:self.config[key] for key in ('items_directory','items_directory_metadata','item_files')})
        self.write_release()
        self.assertEqual(self.run_worker()['status'],'PREFLIGHT_PASSED')
        self.items.chmod(0o2777)
        with self.assertRaises(ValueError):self.run_worker(publish=True)

    def test_service_uses_existing_shared_production_admission(self):
        import shlex
        service=self.api.ROOT/'deploy/weathernext-publish.service'
        self.assertTrue(service.is_file(),'production publisher service is absent')
        line=next(row for row in service.read_text().splitlines() if row.startswith('ExecStart='))
        args=shlex.split(line.split('=',1)[1])
        self.assertIn('--production',args);self.assertIn('--publish',args)
        self.assertIn('${EARTHSHIP_WEATHER_PRODUCTION_CONFIG}',args)
        self.assertEqual(args[args.index('--seconds')+1],'90')
        self.assertEqual(args[args.index('--minimum-mib')+1],'256')
        self.assertEqual(args[args.index('--preferred-mib')+1],'512')
        self.assertTrue((self.api.ROOT/'deploy/weathernext-publish.timer').is_file())

    def test_cli_redacts_private_failure_and_never_defaults_to_publish(self):
        import subprocess,sys
        bad=self.private('bad-config.json',b'{"private":"'+uuid.uuid4().hex.encode()+b'"}')
        process=subprocess.run([sys.executable,str(self.api.ROOT/'openhab/scripts/weather_publish.py'),'--config',str(bad)],capture_output=True,text=True)
        self.assertEqual(process.returncode,1)
        output=json.loads(process.stdout)
        self.assertEqual(output['failure_kind'],'ValueError')
        self.assertEqual(output['status'],'REFUSED');self.assertNotIn(str(bad),process.stdout)
        self.assertNotIn(json.loads(bad.read_bytes())['private'],process.stdout+process.stderr)
        self.assertFalse(output['automatic_actuation'])

    def test_installed_items_may_belong_to_the_reviewed_directory_owner(self):
        import os
        from unittest.mock import patch
        # Simulate a service UID distinct from the reviewed OpenHAB file UID.
        # No chown or real host permission changes are needed.
        different_uid=os.getuid()+1
        with patch('weather_learning.production_worker.os.getuid',return_value=different_uid):
            self.api._item_sources(self.config)

    def test_masked_and_removed_incumbent_units_are_stopped(self):
        for row in self.units.values():row.update(LoadState='masked',UnitFileState='masked')
        self.assertEqual(self.run_worker()['status'],'PREFLIGHT_PASSED')

    def test_multiline_duplicate_item_owner_is_refused(self):
        duplicate=self.items/'extra.items'
        duplicate.write_text('Number:Temperature\nForecast_Temp "Duplicate"\n');duplicate.chmod(0o644)
        with self.assertRaises(ValueError):self.run_worker(publish=True)
        self.assertEqual(self.server.requests,[])

    def test_authoritative_site_mismatch_refuses_before_state_updates(self):
        self.release['site']['latitude']+=1;self.write_release()
        with self.assertRaises(ValueError):self.run_worker(publish=True)
        self.assertEqual(self.puts(),[])

    def test_unavailable_optional_near24_profile_keeps_core_publication(self):
        result=self.run_worker(publish=True,near_term_config_path=self.root/'missing-near.json')
        self.assertEqual(result['status'],'PUBLISHED')
        self.assertEqual(result['near_term_profile_status'],'UNAVAILABLE')
        self.assertEqual(json.loads(self.server.states['Forecast_10Day_JSON'])['providerStatus'],'AVAILABLE')

    def test_optional_near24_config_is_not_opened_during_readonly_preflight(self):
        result=self.run_worker(near_term_config_path=self.root/'missing-near.json')
        self.assertEqual(result['status'],'PREFLIGHT_PASSED')
        self.assertEqual(self.puts(),[])


    def test_explicit_pinned_optional_near24_profile_retains_raw_candidate_on_origin_dependency_failure(self):
        from daily_temperature_runtime import SOURCE_POLICY
        policy=self.private('outdoor.json',canonical(dict(version=2,streams=dict(outdoor=dict(SOURCE_POLICY,sensor_epoch='00000000-0000-4000-8000-000000000001')))))
        cfg=self.private('near.json',canonical(dict(schema='earthship-near24-production-profile/v1',state=str(self.root/'near-state'),
            temperature_policy=str(policy),temperature_db_config=str(self.root/'missing-db.json'),runtime_manifest=self.api.runtime_manifest())))
        result=self.run_worker(publish=True,near_term_config_path=cfg)
        self.assertEqual(result['status'],'PUBLISHED');self.assertEqual(result['near_term_profile_status'],'CONFIGURED')
        self.assertEqual(result['refresh_status'],'retained_candidate')
        candidate=json.loads((self.root/'near-state/near-term-correction.json').read_bytes())
        self.assertEqual(candidate['status'],'RAW_FALLBACK');self.assertEqual(candidate['reason'],'MODEL_UNAVAILABLE')
        self.assertFalse(candidate['issued']);self.assertFalse(candidate['local_coverage_qualified'])
        self.assertIn('openhab/scripts/weather_learning/refresh_runtime.py',self.config['runtime_manifest'])


if __name__=='__main__':unittest.main()

class PublicationScheduleRecoveryTests(unittest.TestCase):
    def test_transient_refusal_has_bounded_service_retries_before_next_hour(self):
        import configparser
        config=configparser.ConfigParser(interpolation=None)
        config.read(pathlib.Path(__file__).resolve().parents[4]/'deploy/weathernext-publish.service')
        self.assertEqual(config['Service']['Restart'],'on-failure')
        self.assertEqual(config['Service']['RestartSec'],'60s')
        self.assertEqual(config['Unit']['StartLimitIntervalSec'],'900')
        # A rate window must contain slow failures as well as immediate lock refusals.
        latest_fourth_start=3*(int(config['Service']['TimeoutStartSec'])+int(config['Service']['RestartSec'].removesuffix('s')))
        self.assertGreater(int(config['Unit']['StartLimitIntervalSec']),latest_fourth_start)
        self.assertEqual(config['Unit']['StartLimitBurst'],'3')
        self.assertEqual(config['Service']['TimeoutStartSec'],'110')
