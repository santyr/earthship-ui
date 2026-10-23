"""A prepared model waits outside the original forecast's reserved warm slot."""
from datetime import datetime,timedelta,timezone
import pytest

def call(*,at,pids=lambda:['0']*3,guard=lambda:None,limit=240):
 import household_native_training as training
 state={'at':at,'seconds':0.,'sleeps':[]}
 def sleep(seconds):
  state['sleeps'].append(seconds);state['seconds']+=seconds;state['at']+=timedelta(seconds=seconds)
 issue=training.wait_for_handoff_window(guard=guard,read_pids=pids,clock=lambda:state['at'],
     monotonic=lambda:state['seconds'],sleep=sleep,seconds=limit)
 return issue,state

def test_prepared_model_waits_through_forecast_reservation_then_rechecks_idle_workers():
 import household_native_training as training
 assert hasattr(training,'wait_for_handoff_window')
 at=datetime(2026,10,23,1,24,11,tzinfo=timezone.utc);reads=[];checks=[]
 def pids():
  reads.append(True)
  # Preserve the natural worker after the :25:15 publication boundary too.
  return ['123','0','0'] if len(reads)<=67 else ['0']*3
 issue,state=call(at=at,pids=pids,guard=lambda:checks.append(True))
 assert issue==datetime(2026,10,23,1,30,15,tzinfo=timezone.utc)
 assert state['seconds']>=67 and len(reads)==len(checks)
 assert all(s==1 for s in state['sleeps'])

def test_idle_safe_window_does_not_wait_or_renew_any_model_clock():
 at=datetime(2026,10,23,1,26,tzinfo=timezone.utc)
 issue,state=call(at=at)
 assert state['seconds']==0 and issue==datetime(2026,10,23,1,30,15,tzinfo=timezone.utc)

def test_busy_workers_and_resource_failure_never_bypass_the_existing_deadline():
 with pytest.raises(TimeoutError):
  call(at=datetime(2026,10,23,1,26,tzinfo=timezone.utc),pids=lambda:['123','0','0'],limit=3)
 def refused():raise ValueError('synthetic changed resource counters')
 with pytest.raises(ValueError,match='resource'):call(at=datetime(2026,10,23,1,24,11,tzinfo=timezone.utc),guard=refused)
