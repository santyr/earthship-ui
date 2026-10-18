"""Synthetic provider contract tests; no site skill or live Google evidence."""
from datetime import datetime,timedelta,timezone
import importlib,pathlib,sqlite3,tempfile,unittest
from unittest.mock import patch
from learning_fixtures import T,SITE,native_snapshot
from weather_learning.archive import Archive
from weather_learning.config import COLLECTIONS
from weather_learning.weathernext_ee import parse_collection_response,make_snapshot


def full_snapshot(init=T,hours=80):
    collections=[]
    for collection,bands,values in [
        (COLLECTIONS['station'],['station_head_temperature_2m_mean'],[283.15]),
        (COLLECTIONS['gridded'],['surface_solar_radiation_downwards_1hr_mean','total_sky_direct_solar_radiation_at_surface_1hr_mean','total_precipitation_1hr_mean','wind_speed_10m_mean','total_cloud_cover_mean'],[360000,180000,.001,1,.5])]:
        raw={'metadata':[],'region':[['id','longitude','latitude','time',*bands]]}
        for hour in range(1,hours+1):
            valid=init+timedelta(hours=hour)
            raw['metadata'].append({'system:index':f'fixture{hour}','start_time':init.isoformat(),'end_time':valid.isoformat(),'forecast_hour':hour,'ingestion_time_utc':init.timestamp()+900})
            raw['region'].append([f'fixture{hour}',-105.75,38.35,valid.timestamp()*1000,*values])
        collections.append(parse_collection_response(raw,collection=collection,bands=bands,site=SITE,initialized_at=init,horizon=hours))
    return make_snapshot(collections,site=SITE,initialized_at=init,first_seen_at=init+timedelta(minutes=20),completed_at=init+timedelta(minutes=21))


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.archive=Archive(pathlib.Path(self.tmp.name))
        try:self.p=importlib.import_module('weather_learning.provider')
        except ModuleNotFoundError:self.fail('Planned Google-only provider adapter is absent')
        self.now=T+timedelta(minutes=30)

    def load(self,**kwargs):
        return self.p.load_production_forecast(self.archive,decision_at=self.now,required_horizon=timedelta(hours=48),site=SITE,**kwargs)

    def test_weathernext_snapshot_can_drive_existing_normalized_forecast_contract(self):
        self.archive.store_snapshot(full_snapshot())
        provider=self.load();value=provider.to_dict()
        self.assertEqual(value['status'],'AVAILABLE')
        import forecast_intel as fi
        with patch.object(fi,'hourly_model_seed',side_effect=AssertionError('legacy seeding')),patch.object(fi,'load_state',side_effect=AssertionError('legacy state')),patch.object(fi,'fetch_forecast',side_effect=AssertionError('external fallback')):
            hourly,daily,detail=fi.build_forecast_payloads(provider,[],self.now)
        self.assertEqual(detail['version'],1)
        self.assertEqual(detail['provider'],'weathernext3')
        self.assertEqual(detail['providerSnapshotSha256'],value['provider_snapshot_sha256'])
        self.assertEqual(detail['days'][1]['summary']['highF'],50)
        self.assertAlmostEqual(detail['days'][1]['summary']['precipSumIn'],24/25.4)
        self.assertIsNone(detail['days'][0]['summary']['highF'])
        self.assertIsNone(detail['days'][0]['summary']['precipSumIn'])
        self.assertIsNone(hourly[0]['p']);self.assertIsNone(hourly[0]['w']);self.assertIsNone(hourly[0]['isDay'])
        self.assertIsNone(daily[0]['pv'])
        self.assertIsNone(detail['days'][1]['summary']['precipPct'])
        self.assertAlmostEqual(detail['days'][1]['hours'][0]['windMph'],3600/1609.344)
        self.assertEqual(detail['days'][1]['hours'][0]['radiationWm2'],100)

    def test_daily_interval_energy_uses_complete_native_days_including_dst(self):
        for init,hours in [(datetime(2026,3,8,tzinfo=timezone.utc),23),(datetime(2026,11,1,tzinfo=timezone.utc),25)]:
            with self.subTest(init=init),tempfile.TemporaryDirectory() as directory:
                archive=Archive(pathlib.Path(directory));archive.store_snapshot(full_snapshot(init))
                provider=self.p.load_production_forecast(archive,decision_at=init+timedelta(minutes=30),required_horizon=timedelta(hours=48),site=SITE)
                day=next(row for row in provider.to_dict()['days'] if row['date']==init.date().isoformat())
                self.assertAlmostEqual(day['solar_kwh_m2'],hours*.1)
                self.assertAlmostEqual(day['direct_solar_kwh_m2'],hours*.05)
                self.assertAlmostEqual(day['precip_sum_in'],hours/25.4)

    def test_stale_weathernext_is_degraded_not_openmeteo_fallback(self):
        self.archive.store_snapshot(full_snapshot())
        self.now=T+timedelta(hours=25)
        with patch('urllib.request.urlopen',side_effect=AssertionError('unexpected network')):
            value=self.load().to_dict()
        self.assertEqual(value['status'],'UNAVAILABLE');self.assertEqual(value['hours'],[])
        self.assertEqual(value['provider'],'weathernext3');self.assertIsNone(value['source'])

    def test_missing_variable_or_late_source_never_falls_back(self):
        self.archive.store_snapshot(native_snapshot(hours=80))
        self.assertEqual(self.load().to_dict()['status'],'UNAVAILABLE')
        self.now=T+timedelta(minutes=19)
        self.assertEqual(self.load(required_variables={'station_head_temperature_2m'}).to_dict()['status'],'UNAVAILABLE')

    def test_provider_identity_is_bound_to_prediction_and_learning_state(self):
        self.archive.store_snapshot(full_snapshot())
        first=self.load().to_dict();self.now+=timedelta(seconds=1);second=self.load().to_dict()
        self.assertEqual(first['learning_namespace'],'weathernext3-temperature-v1')
        self.assertEqual(first['model'],{'status':'UNTRAINED','sha256':None,'parent_artifacts':[]})
        self.assertNotEqual(first['provider_snapshot_sha256'],second['provider_snapshot_sha256'])
        self.assertNotEqual(first['issue_sha256'],second['issue_sha256'])
        from weather_learning.features import temperature_targets
        original=self.archive.read(first['source']['snapshot_sha256'])
        self.assertEqual(first['issue_sha256'],temperature_targets(original,issued_at=T+timedelta(minutes=30))[0].issue_digest)
        self.assertFalse(first['release_authorized'])
        import forecast_intel as fi
        with self.assertRaises(ValueError):fi.build_forecast_payloads(self.load(),[8.5],self.now)
        with self.assertRaises(ValueError):fi.build_forecast_payloads(self.load(),[],self.now,hourly_model={})

    def test_original_normalization_mismatch_or_wrong_site_refuses(self):
        raw=full_snapshot();raw['points'][0]['value']+=1;self.archive.store_snapshot(raw)
        self.assertEqual(self.load().to_dict()['reason'],'INVALID_SOURCE')
        with tempfile.TemporaryDirectory() as directory:
            archive=Archive(pathlib.Path(directory));archive.store_snapshot(full_snapshot())
            from weather_learning.config import Site
            value=self.p.load_production_forecast(archive,decision_at=self.now,required_horizon=timedelta(hours=48),site=Site(0,0,'UTC')).to_dict()
            self.assertEqual(value['reason'],'INVALID_SOURCE')

    def test_provider_result_is_immutable_and_nulls_are_not_zero(self):
        self.archive.store_snapshot(native_snapshot(hours=80))
        provider=self.load(required_variables={'station_head_temperature_2m'});value=provider.to_dict()
        value['hours'][0]['temp_f']=999
        self.assertEqual(provider.to_dict()['hours'][0]['temp_f'],50)
        self.assertIsNone(provider.to_dict()['hours'][0]['radiation_wm2'])
        with self.assertRaises(AttributeError):provider.status='AVAILABLE'

    def test_full_horizon_payload_fits_existing_detail_limit(self):
        self.archive.store_snapshot(full_snapshot(hours=360))
        provider=self.p.load_production_forecast(self.archive,decision_at=self.now,required_horizon=timedelta(hours=336),site=SITE)
        self.assertEqual(len(provider.to_dict()['hours']),337)
        import forecast_intel as fi
        _,_,detail=fi.build_forecast_payloads(provider,[],self.now)
        self.assertLessEqual(len(fi.serialize_detail(detail).encode()),fi.DETAIL_MAX_BYTES)

    def test_unavailable_withdraws_and_different_decision_still_refuses(self):
        import forecast_intel as fi
        unavailable=self.load()
        with patch.object(fi,'hourly_model_seed',side_effect=AssertionError('legacy seeding')):
            hourly,daily,detail=fi.build_forecast_payloads(unavailable,[],self.now)
        self.assertEqual((hourly,daily,detail['days']),([],[],[]))
        self.assertEqual(detail['providerStatus'],'UNAVAILABLE')
        self.assertEqual(detail['providerReason'],'NO_ELIGIBLE_SOURCE')
        self.assertIsNone(detail['source'])
        self.assertEqual(detail['learningNamespace'],'weathernext3-temperature-v1')
        self.archive.store_snapshot(full_snapshot())
        with self.assertRaises(ValueError):fi.build_forecast_payloads(self.load(),[],self.now+timedelta(seconds=1))

    def test_archive_contention_and_corruption_are_unavailable_without_fallback(self):
        for failure in (sqlite3.OperationalError('database is locked'),sqlite3.DatabaseError('database disk image is malformed')):
            with self.subTest(failure=type(failure).__name__),patch.object(self.archive,'eligible_snapshot',side_effect=failure),patch('urllib.request.urlopen',side_effect=AssertionError('external fallback')):
                value=self.load().to_dict()
                self.assertEqual(value['status'],'UNAVAILABLE')
                self.assertEqual(value['reason'],'ARCHIVE_UNAVAILABLE')
                self.assertEqual(value['hours'],[]);self.assertEqual(value['days'],[])
                self.assertIsNone(value['source']);self.assertFalse(value['release_authorized'])

    def test_withdrawal_serializes_all_existing_forecast_items_without_fetch_or_seed(self):
        import json
        import forecast_intel as fi
        provider=self.load()
        with patch('urllib.request.urlopen',side_effect=AssertionError('external fallback')),patch.object(fi,'hourly_model_seed',side_effect=AssertionError('old learning')):
            updates=self.p.publication_states(provider,now=self.now)
        self.assertEqual(set(updates),{'Forecast_Hourly_JSON','Forecast_Daily_JSON','Forecast_10Day_JSON'})
        self.assertEqual(json.loads(updates['Forecast_Hourly_JSON']),[])
        self.assertEqual(json.loads(updates['Forecast_Daily_JSON']),[])
        self.assertEqual(json.loads(updates['Forecast_10Day_JSON'])['providerStatus'],'UNAVAILABLE')

    def test_native_astro_drives_daylight_without_weather_code_or_probability_substitutes(self):
        from astro_serving_fixtures import astro_source
        self.archive.store_snapshot(full_snapshot())
        source=astro_source(self.now)
        provider=self.p.load_production_forecast(self.archive,decision_at=self.now,required_horizon=timedelta(hours=48),site=SITE,astro_source=source)
        hourly,daily,detail=self.p.forecast_payloads(provider,now=self.now)
        self.assertTrue(hourly[0]['isDay'])  # December 31, 18:00 Mountain.
        self.assertFalse(hourly[1]['isDay'])  # Exact native sunset at 19:00.
        next_day=next(d for d in detail['days'] if d['date']=='2026-01-01')
        self.assertEqual(next_day['summary']['daylightSeconds'],43200)
        self.assertFalse(next(h for h in next_day['hours'] if 'T06:00:' in h['at'])['isDay'])
        self.assertTrue(next(h for h in next_day['hours'] if 'T07:00:' in h['at'])['isDay'])
        self.assertEqual(detail['solarSource']['status'],'AVAILABLE')
        self.assertEqual(detail['solarSource']['availableAt'],source['available_at'].isoformat())
        self.assertIsNone(hourly[0]['w']);self.assertIsNone(hourly[0]['p']);self.assertIsNone(daily[0]['pv'])

    def test_unavailable_astro_never_invents_daylight_or_discards_google_weather(self):
        from astro_serving_fixtures import astro_source
        self.archive.store_snapshot(full_snapshot())
        for damage in ('future','expired','site','version','duplicate'):
            with self.subTest(damage=damage):
                source=astro_source(self.now,damage=damage)
                provider=self.p.load_production_forecast(self.archive,decision_at=self.now,required_horizon=timedelta(hours=48),site=SITE,astro_source=source)
                self.assertEqual(provider.to_dict()['status'],'AVAILABLE')
                hourly,_,detail=self.p.forecast_payloads(provider,now=self.now)
                self.assertTrue(all(h['isDay'] is None for h in hourly))
                self.assertEqual(detail['solarSource']['status'],'UNAVAILABLE')
                self.assertIsNone(detail['solarSource']['sourceSha256'])

    def test_python_publication_matches_cross_language_ui_fixture(self):
        import json
        from astro_serving_fixtures import astro_source
        self.archive.store_snapshot(full_snapshot())
        provider=self.p.load_production_forecast(self.archive,decision_at=self.now,required_horizon=timedelta(hours=2),site=SITE,astro_source=astro_source(self.now))
        actual={item:json.loads(raw) for item,raw in self.p.publication_states(provider,now=self.now).items()}
        root=pathlib.Path(__file__).resolve().parents[4]
        expected=json.loads((root/'tests/fixtures/weathernext-serving-v1.json').read_text())
        self.assertEqual(actual,expected)

    def test_current_day_summary_uses_complete_original_native_day_without_backdating_issue(self):
        self.archive.store_snapshot(full_snapshot())
        self.now=T+timedelta(hours=20)
        provider=self.load();value=provider.to_dict()
        today=next(day for day in value['days'] if day['date']=='2026-01-01')
        self.assertEqual(today['high_f'],50)
        self.assertEqual(today['low_f'],50)
        self.assertAlmostEqual(today['precip_sum_in'],24/25.4)
        self.assertEqual(value['decision_at'],self.now.isoformat())
        self.assertTrue(all(datetime.fromisoformat(h['at'])>self.now for h in value['hours']))

    def test_caller_horizon_and_variable_contract_are_bounded(self):
        for horizon in (timedelta(0),timedelta(hours=337),1):
            with self.subTest(horizon=horizon),self.assertRaises(ValueError):
                self.p.load_production_forecast(self.archive,decision_at=self.now,required_horizon=horizon,site=SITE)
        with self.assertRaises(ValueError):self.load(required_variables={'precipitation_probability'})


if __name__=='__main__':unittest.main()
