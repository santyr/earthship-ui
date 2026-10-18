from pathlib import Path
import shlex,time,unittest
from unittest.mock import patch
from weather_learning.config import AccessPolicy
from weather_learning.transport import BoundedTransport,AccessRefused
from test_transport import Session,Response

class RuntimeTests(unittest.TestCase):
 def test_service_matches_existing_collection_admission(self):
  from household_job_launch import launch_job
  line=next(x for x in (Path(__file__).resolve().parents[4]/'deploy/weathernext-ingest.service').read_text().splitlines() if x.startswith('ExecStart='))
  args=shlex.split(line.split('=',1)[1]);value=lambda name:int(args[args.index(name)+1])
  class ReachedAdmission(Exception):pass
  with patch('household_job_launch.admission_gate',side_effect=ReachedAdmission):
   with self.assertRaises(ReachedAdmission):
    launch_job(['/usr/bin/true'],pool_path=Path('/unused'),lock_path=Path('/unused'),collection=True,
     minimum_bytes=value('--minimum-mib')*1024**2,preferred_bytes=value('--preferred-mib')*1024**2,tasks=value('--tasks'),seconds=value('--seconds'))
  self.assertLessEqual(AccessPolicy().max_seconds,value('--seconds')-10)
 def test_progressing_body_read_is_interrupted_by_total_deadline(self):
  class ProgressingBody:
   def read(self,*args,**kwargs):
    for i in range(100):time.sleep(.03)
    return b'{}'
  response=Response();response.raw=ProgressingBody()
  transport=BoundedTransport(AccessPolicy(backend='earthengine',noncommercial_verified=True,max_seconds=1),session=Session(response))
  started=time.monotonic()
  with self.assertRaises(AccessRefused):transport.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config')
  self.assertLess(time.monotonic()-started,2)
if __name__=='__main__':unittest.main()
