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
