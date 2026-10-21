"""Retain fresh 48-hour runs and full-range runs without downloading unchanged data."""
from datetime import timedelta
from pathlib import Path
import tempfile,unittest
from unittest.mock import Mock
from learning_fixtures import T,SITE,full_snapshot
from weather_learning.worker import collect_once,DEFAULT_BANDS
from weather_learning.archive import Archive
from weather_learning.config import COLLECTIONS
from weather_learning.weathernext_ee import parse_collection_response,make_snapshot


def complete(init,hours):
    collections=[]
    for grid,bands in DEFAULT_BANDS.items():
        values=[]
        for band in bands:
            variable=band.rsplit('_',1)[0]
            value=283.15 if 'temperature' in variable else .5 if 'cloud' in variable else 90000. if 'pressure' in variable else .001 if 'tp_' in variable or 'precipitation' in variable else 360000. if 'radiation' in variable else 1.
            values.append(value)
        raw={'metadata':[],'region':[['id','longitude','latitude','time',*bands]]}
        for hour in range(1,hours+1):
            at=init+timedelta(hours=hour)
            raw['metadata'].append({'system:index':f'fixture{hour}','start_time':init.isoformat(),'end_time':at.isoformat(),'forecast_hour':hour,'ingestion_time_utc':init.timestamp()+900})
            raw['region'].append([f'fixture{hour}',-105.75,38.35,at.timestamp()*1000,*values])
        collections.append(parse_collection_response(raw,collection=COLLECTIONS[grid],bands=bands,site=SITE,initialized_at=init,horizon=hours))
    return make_snapshot(collections,site=SITE,initialized_at=init,first_seen_at=init+timedelta(minutes=20),completed_at=init+timedelta(minutes=21))


class HourlyCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.archive=Archive(Path(self.temp.name))
        self.reader=Mock();self.now=T+timedelta(hours=2)
        self.reader.discover_run.side_effect=lambda *,horizon:{'start_time':(T if horizon==360 else T+timedelta(hours=1)).isoformat()}
        self.reader.fetch_points.side_effect=lambda *,run,bands_by_grid,horizon:complete(__import__('datetime').datetime.fromisoformat(run['start_time']),horizon)
    def collect(self):return collect_once(self.reader,self.archive,probe=False,horizon=360,include_interim=True,clock=lambda:self.now,free_bytes=10**9)
    def test_latest_short_run_and_full_horizon_remain_separate_originals(self):
        result=self.collect()
        self.assertEqual(result['downloaded_snapshots'],2)
        self.assertEqual(self.reader.fetch_points.call_count,2)
        near=self.archive.eligible_snapshot(self.now,self.now+timedelta(hours=24),required_variables={'station_head_temperature_2m'})
        long=self.archive.eligible_snapshot(self.now,self.now+timedelta(hours=240),required_variables={'station_head_temperature_2m'})
        self.assertEqual(near['initialized_at'],(T+timedelta(hours=1)).isoformat())
        self.assertEqual(long['initialized_at'],T.isoformat())
    def test_repeated_catalog_check_reuses_original_availability_without_data_download(self):
        first=self.collect();self.reader.fetch_points.reset_mock();before=sorted(p.name for p in self.archive.objects.iterdir())
        result=self.collect()
        self.assertEqual(result['downloaded_snapshots'],0)
        self.reader.fetch_points.assert_not_called()
        self.assertEqual(sorted(p.name for p in self.archive.objects.iterdir()),before)
        self.assertEqual(result['snapshot_sha256'],first['snapshot_sha256'])
    def test_current_full_run_is_not_downloaded_again_as_short_run(self):
        self.reader.discover_run.side_effect=lambda **kw:{'start_time':T.isoformat()}
        result=self.collect();self.assertEqual(result['downloaded_snapshots'],1)
        self.assertEqual(self.reader.fetch_points.call_count,1)
    def test_partial_band_archive_cannot_suppress_complete_acquisition(self):
        self.archive.store_snapshot(full_snapshot(T,hours=360))
        result=self.collect();self.assertEqual(result['downloaded_snapshots'],2)

    def test_full_and_interim_batch_cannot_exceed_archive_byte_cap(self):
        from weather_learning.contracts import canonical,identity,validate_snapshot
        def padded(init,hours,mib):
            value=complete(init,hours);source=value['source_originals'][0];before=identity(source)
            source['payload']['retained_metadata_padding']=''
            padding=mib*1024**2-len(canonical(value))
            self.assertGreater(padding,0)
            source['payload']['retained_metadata_padding']='x'*padding
            after=identity(source)
            for row in value['points']:
                if row['source_digest']==before:row['source_digest']=after
            return validate_snapshot(value)
        incumbent=self.archive.store_snapshot(padded(T-timedelta(hours=6),360,7))
        self.reader.fetch_points.side_effect=lambda *,run,bands_by_grid,horizon:padded(__import__('datetime').datetime.fromisoformat(run['start_time']),horizon,5)
        cap=16*1024**2
        self.assertLess(sum(p.stat().st_size for p in self.archive.objects.glob('*.json'))+8*1024**2,cap)
        with self.assertRaisesRegex(ValueError,'capacity'):
            collect_once(self.reader,self.archive,probe=False,horizon=360,include_interim=True,
                clock=lambda:self.now,free_bytes=10**9,max_archive_bytes=cap)
        self.assertLessEqual(sum(p.stat().st_size for p in self.archive.objects.glob('*.json')),cap)
        self.assertEqual(self.archive.read(incumbent)['snapshot_sha256'],incumbent)
        self.assertEqual(len(list(self.archive.objects.glob('*.json'))),2)

    def test_exact_archive_object_cap_refuses_before_acquisition(self):
        import os
        for index in range(10000):
            path=self.archive.objects/(f'{index:064x}'+'.json')
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            os.write(fd,b'{}');os.close(fd)
        with self.assertRaisesRegex(ValueError,'object-count'):
            self.collect()
        self.reader.initialize.assert_not_called()
        self.assertEqual(len(list(self.archive.objects.glob('*.json'))),10000)

    def test_batch_at_object_capacity_keeps_first_original_and_refuses_second(self):
        import os
        for index in range(9999):
            path=self.archive.objects/(f'{index:064x}'+'.json')
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            os.write(fd,b'{}');os.close(fd)
        with self.assertRaisesRegex(ValueError,'object-count'):
            self.collect()
        self.assertEqual(len(list(self.archive.objects.glob('*.json'))),10000)
        first=self.archive.completed_run(T.isoformat(),horizon=360,
            required={tuple(band.rsplit('_',1)) for bands in DEFAULT_BANDS.values() for band in bands},as_of=self.now)
        self.assertEqual(first['initialized_at'],T.isoformat())
