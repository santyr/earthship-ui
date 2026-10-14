"""Approved one-second PSI policy; kernel inputs are temporary synthetic files."""
import importlib.util,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
import native_inference_pressure as policy
class Window(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.clock=[10.]
  self.patch=patch.object(policy,'monotonic',lambda:self.clock[0]);self.patch.start();self.addCleanup(self.patch.stop)
  self.paths={key:self.root/key for key in ('meminfo','vmstat','pressure')};self.sample(10.)
  self.guard=policy.NativeInferenceHeadroom(**self.paths,worker_check=lambda:None);self.guard.check()
 def sample(self,at,*,some=0,full=0,pages=0,out=0,oom=0,reserve=1572864,avg='0.00'):
  self.clock[0]=at;self.paths['meminfo'].write_text(f'MemAvailable: {reserve} kB\nSwapTotal: 2048 kB\nSwapFree: 1024 kB\n');self.paths['vmstat'].write_text(f'pswpin {pages}\npswpout {out}\noom_kill {oom}\n');self.paths['pressure'].write_text(f'some avg10={avg} avg60=0.00 avg300=0.00 total={some}\nfull avg10=0.00 avg60=0.00 avg300=0.00 total={full}\n')
 def test_measured_124_microsecond_stall_fits_one_second_budget(self):
  self.sample(10.1,some=125,full=124);self.guard.check()
 def test_full_one_millisecond_cap_and_refusal_latch(self):
  self.sample(10.1,full=1000);self.guard.check();self.sample(10.2,full=1001)
  with self.assertRaisesRegex(ValueError,'trailing one-second memory pressure'):self.guard.check()
  self.sample(12,full=1001)
  with self.assertRaisesRegex(ValueError,'previously refused'):self.guard.check()
 def test_some_five_millisecond_cap(self):
  self.sample(10.1,some=5000);self.guard.check();self.sample(10.2,some=5001)
  with self.assertRaisesRegex(ValueError,'trailing one-second memory pressure'):self.guard.check()
 def test_partial_interval_retained_without_interpolation(self):
  self.sample(10.5,full=500);self.guard.check();self.sample(11.2,full=1000);self.guard.check()
  self.assertEqual(self.guard.pressure_samples[0][0],10.)
  self.sample(11.3,full=1001)
  with self.assertRaises(ValueError):self.guard.check()
 def test_expiry_requires_observed_sample(self):
  self.sample(10.5,full=1000);self.guard.check();self.sample(11.5,full=1000);self.guard.check();self.sample(11.6,full=2000);self.guard.check()
  self.sample(11.7,full=2001)
  with self.assertRaises(ValueError):self.guard.check()
 def test_pressure_counter_regression_refuses(self):
  self.sample(10.1,full=100);self.guard.check();self.sample(10.2,full=99)
  with self.assertRaisesRegex(ValueError,'regressed'):self.guard.check()
 def test_swap_read_budget_unchanged(self):
  self.sample(10.000719,pages=1);self.guard.check();self.sample(10.2,pages=257)
  with self.assertRaisesRegex(ValueError,'swap-read'):self.guard.check()
 def test_all_existing_host_and_worker_barriers(self):
  for change in ({'out':1},{'oom':1},{'reserve':1572863},{'avg':'0.51'}):
   with self.subTest(change=change):
    self.guard=policy.NativeInferenceHeadroom(**self.paths,worker_check=lambda:None);self.sample(10.);self.guard.check();self.sample(10.1,**change)
    with self.assertRaises(ValueError):self.guard.check()
  self.sample(10.);self.guard=policy.NativeInferenceHeadroom(**self.paths,worker_check=lambda:None);self.guard.check()
  self.guard.worker_check=lambda:(_ for _ in ()).throw(ValueError('worker cap'))
  self.sample(10.1)
  with self.assertRaisesRegex(ValueError,'worker cap'):self.guard.check()
 def test_fitting_pressure_guard_stays_strict(self):
  import thermal_model.training_pressure_guard as fitting
  with patch.object(fitting,'monotonic',lambda:self.clock[0]):
   original=fitting.TrainingHeadroom(**self.paths,max_swapin_bytes_per_second=1048576);original.check();self.sample(10.1,full=124)
   with self.assertRaisesRegex(ValueError,'memory pressure'):original.check()
 def test_five_second_preflight_is_preserved(self):
  import thermal_model.training_pressure_guard as training
  waits=[]
  def sleep(seconds):waits.append(seconds);self.sample(self.clock[0]+seconds)
  self.sample(10.1)
  with patch.object(training,'sleep',sleep):self.guard.preflight()
  self.assertEqual(waits,[1]*5)
if __name__=='__main__':unittest.main(verbosity=2)
