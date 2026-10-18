"""Synthetic provider contract tests; no site skill or live Google evidence."""
from datetime import datetime,timedelta,timezone
import importlib,pathlib,tempfile,unittest
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

    def test_unavailable_or_different_decision_cannot_generate_payloads(self):
        import forecast_intel as fi
        unavailable=self.load()
        with patch.object(fi,'hourly_model_seed',side_effect=AssertionError('legacy seeding')),self.assertRaises(ValueError):
            fi.build_forecast_payloads(unavailable,[],self.now)
        self.archive.store_snapshot(full_snapshot())
        with self.assertRaises(ValueError):fi.build_forecast_payloads(self.load(),[],self.now+timedelta(seconds=1))

    def test_caller_horizon_and_variable_contract_are_bounded(self):
        for horizon in (timedelta(0),timedelta(hours=337),1):
            with self.subTest(horizon=horizon),self.assertRaises(ValueError):
                self.p.load_production_forecast(self.archive,decision_at=self.now,required_horizon=horizon,site=SITE)
        with self.assertRaises(ValueError):self.load(required_variables={'precipitation_probability'})


if __name__=='__main__':unittest.main()
