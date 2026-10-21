import json,unittest
from weather_learning.config import AccessPolicy
from weather_learning.transport import BoundedTransport,AccessRefused
class Raw:
 def __init__(self,data):self.data=data
 def read(self,size,decode_content=False):return self.data[:size]
class Response:
 def __init__(self,data=b'{}',status=200):self.raw=Raw(data);self.headers={};self.status_code=status
 def __enter__(self):return self
 def __exit__(self,*a):pass
class Session:
 def __init__(self,response=None):self.calls=[];self.response=response or Response()
 def request(self,*a,**kw):self.calls.append((a,kw));return self.response
 def close(self):pass
class TransportTests(unittest.TestCase):
 def setUp(self):self.policy=AccessPolicy(backend='earthengine',noncommercial_verified=True)
 def transport(self,session=None,clock=lambda:0):return BoundedTransport(self.policy,session=session or Session(),clock=clock)
 def test_request_billing_and_unapproved_endpoints_refused_before_network(self):
  s=Session();t=self.transport(s)
  for uri,method,headers in [
    ('https://storage.googleapis.com/weathernext3_spatial/object','GET',{}),
    ('https://earthengine.googleapis.com/v1/projects/other/config','GET',{}),
    ('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/assets','POST',{}),
    ('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config?userProject=other','GET',{}),
    ('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config','GET',{'x-goog-user-project':'other'})]:
   with self.subTest(uri=uri),self.assertRaises(AccessRefused):t.request(uri,method,headers=headers)
  self.assertEqual(s.calls,[])
 def test_only_approved_compute_and_metadata_methods(self):
  s=Session(Response(json.dumps({'registrationState':'REGISTERED_NOT_COMMERCIALLY'}).encode()));t=self.transport(s)
  t.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config')
  t.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/value:compute','POST',body='{}')
  self.assertEqual(len(s.calls),2);self.assertFalse(s.calls[0][1]['allow_redirects'])
 def test_response_and_total_bytes_capped(self):
  t=BoundedTransport(AccessPolicy(backend='earthengine',noncommercial_verified=True,max_bytes=1024),session=Session(Response(b'a'*1025)),clock=lambda:0)
  with self.assertRaises(AccessRefused):t.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config')
 def test_access_denied_does_not_escalate_or_switch_backend(self):
  s=Session(Response(status=403));t=self.transport(s)
  response,body=t.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config')
  self.assertEqual(response.status,403);self.assertEqual(len(s.calls),1)
 def test_trace_retains_only_allowlisted_error_status_without_private_message(self):
  data=json.dumps({'error':{'status':'RESOURCE_EXHAUSTED','message':'operator-private'}}).encode()
  t=self.transport(Session(Response(data,status=403)))
  t.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config')
  self.assertEqual(t.trace[-1]['error_status'],'RESOURCE_EXHAUSTED')
  self.assertNotIn('operator-private',json.dumps(t.trace))
 def test_total_deadline_and_request_count_refused(self):
  ticks=iter([0,121]);t=self.transport(clock=lambda:next(ticks))
  with self.assertRaises(AccessRefused):t.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config')
 def test_redirect_response_never_followed(self):
  s=Session(Response(status=302));t=self.transport(s)
  with self.assertRaises(AccessRefused):t.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config')
  self.assertEqual(len(s.calls),1)
 def test_slow_compute_can_use_remaining_total_acquisition_budget(self):
  import requests
  elapsed=[0.]
  class DelayedSession(Session):
   def request(self,*args,**kwargs):
    response=super().request(*args,**kwargs)
    permitted=kwargs['timeout'][1]
    elapsed[0]+=min(20.,permitted)
    if permitted<20.:raise requests.ReadTimeout('simulated slow computation')
    return response
  session=DelayedSession(Response(json.dumps({'registrationState':'REGISTERED_NOT_COMMERCIALLY'}).encode()))
  transport=self.transport(session,clock=lambda:elapsed[0]);elapsed[0]=5.
  response,_=transport.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config')
  self.assertEqual(response.status,200)
  self.assertTrue(transport.noncommercial_verified)
  self.assertEqual(elapsed[0],25.)
  self.assertEqual(len(session.calls),1)

 def test_slow_request_cannot_reset_the_remaining_total_deadline(self):
  import requests
  elapsed=[0.]
  class DelayedSession(Session):
   def request(self,*args,**kwargs):
    super().request(*args,**kwargs)
    elapsed[0]+=kwargs['timeout'][1]
    raise requests.ReadTimeout('simulated deadline exhaustion')
  session=DelayedSession();transport=self.transport(session,clock=lambda:elapsed[0]);elapsed[0]=65.
  with self.assertRaises(requests.ReadTimeout):transport.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config')
  with self.assertRaises(AccessRefused):transport.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config')
  self.assertEqual(elapsed[0],75.)
  self.assertEqual(len(session.calls),1)

if __name__=='__main__':unittest.main()

class RegistrationTests(unittest.TestCase):
 setUp=TransportTests.setUp
 transport=TransportTests.transport
 def test_unverified_or_commercial_project_cannot_compute(self):
  for configuration in ({},{'registrationState':'REGISTERED_COMMERCIALLY'}):
   s=Session(Response(json.dumps(configuration).encode()));t=self.transport(s)
   t.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/config')
   with self.assertRaises(AccessRefused):t.request('https://earthengine.googleapis.com/v1/projects/earthship-weather-research/value:compute','POST',body='{}')
   self.assertEqual(len(s.calls),1)
