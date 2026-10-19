from datetime import datetime,timezone
from pathlib import Path
import tempfile,unittest
from unittest.mock import Mock
from weather_learning.archive import Archive
from weather_learning.worker import collect_once,collector_lock
from test_archive import snapshot
class WorkerTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.archive=Archive(Path(self.tmp.name));self.reader=Mock();self.reader.discover_run.return_value={'start_time':'2026-10-18T00:00:00Z'};self.reader.fetch_points.return_value=snapshot()
 def tearDown(self):self.tmp.cleanup()
 def test_default_probe_has_no_archive_or_production_writes(self):
  result=collect_once(self.reader,self.archive,probe=True,free_bytes=10**9)
  self.assertEqual(result['status'],'PROBE_PASSED');self.assertFalse(result['production_writes'])
  self.assertEqual(list(self.archive.objects.glob('*.json')),[])
  self.assertEqual(self.reader.fetch_points.call_args.kwargs['horizon'],1)
 def test_collect_retains_original_before_success(self):
  result=collect_once(self.reader,self.archive,probe=False,horizon=1,free_bytes=10**9)
  self.assertEqual(result['status'],'ARCHIVED');self.assertEqual(self.archive.read(result['snapshot_sha256'])['provider'],'weathernext3')
 def test_scheduled_capture_requests_all_rain_products_for_later_selection(self):
  collect_once(self.reader,self.archive,probe=False,horizon=1,free_bytes=10**9)
  selected=self.reader.fetch_points.call_args.kwargs['bands_by_grid']['gridded']
  for required in ('total_precipitation_1hr_mean','imerg_tp_1hr_mean','experimental_tp_1hr_mean'):
   with self.subTest(required=required):self.assertIn(required,selected)
 def test_disk_refusal_does_not_query_upstream(self):
  with self.assertRaises(ValueError):collect_once(self.reader,self.archive,free_bytes=0)
  self.reader.initialize.assert_not_called()
 def test_network_failure_does_not_overwrite_prior_archive(self):
  original=self.archive.store_snapshot(snapshot());self.reader.fetch_points.side_effect=TimeoutError
  with self.assertRaises(TimeoutError):collect_once(self.reader,self.archive,probe=False,free_bytes=10**9)
  self.assertTrue((self.archive.objects/(original+'.json')).exists())
 def test_concurrent_collection_is_refused(self):
  with collector_lock(Path(self.tmp.name)/'collector.lock'):
   with self.assertRaises(BlockingIOError):
    with collector_lock(Path(self.tmp.name)/'collector.lock'):pass
if __name__=='__main__':unittest.main()
