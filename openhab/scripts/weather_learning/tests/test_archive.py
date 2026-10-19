from datetime import datetime,timedelta,timezone
import pathlib,tempfile,unittest
from weather_learning.archive import Archive
from weather_learning.contracts import identity
T=datetime(2026,10,18,tzinfo=timezone.utc)
def snapshot(first_seen=T,completed=T,run='20261018_00hr_01_preds',historical=False):
 source=dict(collection='projects/gcp-public-data-weathernext/assets/run',payload={'fixture':'original retained provider rows'})
 return dict(source_originals=[source],schema='earthship-weathernext-snapshot/v1',provider='weathernext3',run_id=run,initialized_at=T.isoformat(),
  first_seen_at=first_seen.isoformat(),ingestion_completed_at=completed.isoformat(),historical=historical,
  site=dict(latitude=38.3739919,longitude=-105.7744609,timezone='America/Denver'),
  points=[dict(variable='temperature_2m',statistic='mean',valid_at=(T+timedelta(hours=1)).isoformat(),
   value=0.91,unit='degC',raw_value=274.06,raw_unit='K',period_seconds=0,
   source_ref='projects/gcp-public-data-weathernext/assets/run/image',source_digest=identity(source),latitude=38.4,longitude=-105.8)])
class ArchiveTests(unittest.TestCase):
 def setUp(self):self.directory=tempfile.TemporaryDirectory();self.archive=Archive(pathlib.Path(self.directory.name))
 def tearDown(self):self.directory.cleanup()
 def test_late_published_run_cannot_serve_earlier_decision(self):
  self.archive.store_snapshot(snapshot(first_seen=T+timedelta(minutes=30),completed=T+timedelta(minutes=31)))
  self.assertIsNone(self.archive.eligible_snapshot(T+timedelta(minutes=29),T+timedelta(hours=1)))
  self.assertIsNotNone(self.archive.eligible_snapshot(T+timedelta(minutes=32),T+timedelta(hours=1)))
 def test_backfill_without_as_issued_availability_is_retrospective_only(self):
  self.archive.store_snapshot(snapshot(historical=True))
  self.assertIsNone(self.archive.eligible_snapshot(T+timedelta(minutes=1),T+timedelta(hours=1)))
 def test_duplicate_snapshot_is_idempotent_and_source_digest_bound(self):
  raw=snapshot();a=self.archive.store_snapshot(raw);self.assertEqual(a,self.archive.store_snapshot(raw))
  raw['source_originals'][0]['payload']['revision']=2;raw['points'][0]['source_digest']=identity(raw['source_originals'][0]);self.assertNotEqual(a,self.archive.store_snapshot(raw))
 def test_interrupted_archive_write_never_replaces_last_good_snapshot(self):
  identity=self.archive.store_snapshot(snapshot())
  with self.assertRaises(ValueError):self.archive.store_snapshot(snapshot(completed=T-timedelta(hours=1)))
  self.assertEqual(self.archive.eligible_snapshot(T+timedelta(minutes=1),T+timedelta(hours=1))['snapshot_sha256'],identity)
 def test_tampered_object_refused(self):
  identity=self.archive.store_snapshot(snapshot());p=pathlib.Path(self.directory.name)/'objects'/(identity+'.json');p.write_text('{}')
  with self.assertRaises(ValueError):self.archive.eligible_snapshot(T+timedelta(minutes=1),T+timedelta(hours=1))
 def test_stale_snapshot_has_no_hidden_fallback(self):
  self.archive.store_snapshot(snapshot())
  self.assertIsNone(self.archive.eligible_snapshot(T+timedelta(hours=25),T+timedelta(hours=26)))
 def test_missing_requested_variable_or_horizon_refuses(self):
  self.archive.store_snapshot(snapshot())
  self.assertIsNone(self.archive.eligible_snapshot(T+timedelta(minutes=1),T+timedelta(hours=2)))
  self.assertIsNone(self.archive.eligible_snapshot(T+timedelta(minutes=1),T+timedelta(hours=1),required_variables={'solar_ghi'}))
if __name__=='__main__':unittest.main()

class OriginalSourceBindingTests(unittest.TestCase):
 def test_source_digest_must_resolve_retained_original(self):
  with tempfile.TemporaryDirectory() as root:
   a=Archive(pathlib.Path(root));raw=snapshot();raw['points'][0]['source_digest']='f'*64
   with self.assertRaises(ValueError):a.store_snapshot(raw)

class FractionalHorizonTests(unittest.TestCase):
 def test_missing_next_hour_cannot_bridge_fractional_target(self):
  with tempfile.TemporaryDirectory() as root:
   a=Archive(pathlib.Path(root));raw=snapshot()
   raw['points'].append(dict(raw['points'][0],valid_at=(T+timedelta(hours=3)).isoformat()))
   a.store_snapshot(raw)
   self.assertIsNone(a.eligible_snapshot(T+timedelta(minutes=15),T+timedelta(minutes=90)))
