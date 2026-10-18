"""Bounded HTTP bridge for the official EE SDK; approved read operations only."""
import json,time
from urllib.parse import urlsplit,parse_qsl
import requests
from .config import AccessPolicy

class AccessRefused(ValueError):pass

class BoundedTransport:
    def __init__(self,policy,*,session=None,clock=time.monotonic):
        if not isinstance(policy,AccessPolicy) or policy.backend!='earthengine':
            raise AccessRefused('approved Earth Engine policy required')
        self.policy=policy;self.session=session or requests.Session();self.clock=clock
        self.started=clock();self.bytes_received=0;self.requests=0;self.noncommercial_verified=False
        self.trace=[]

    def request(self,uri,method='GET',body=None,headers=None,**kwargs):
        # SDK user-project routing is allowed ONLY on EE, to this dedicated
        # noncommercial project. GCS Requester Pays and other hosts are refused.
        url=urlsplit(uri);method=method.upper();headers=dict(headers or {})
        path='/v1/projects/'+self.policy.project+'/'
        if (url.scheme!='https' or url.netloc!='earthengine.googleapis.com' or url.fragment
                or any(k.lower() in ('userproject','billingproject') for k,v in parse_qsl(url.query))):
            raise AccessRefused('unapproved Google endpoint or requester billing')
        for key,value in headers.items():
            if key.lower()=='x-goog-user-project' and value!=self.policy.project:
                raise AccessRefused('unapproved quota project')
        metadata=method=='GET' and (url.path in (path+'config',path+'algorithms') or url.path=='/$discovery/rest')
        compute=method=='POST' and url.path==path+'value:compute'
        if not metadata and not compute:raise AccessRefused('only metadata and bounded point computations permitted')
        if compute and not self.noncommercial_verified:raise AccessRefused('noncommercial registration not verified')
        remaining=self.policy.max_seconds-(self.clock()-self.started)
        if remaining<=0 or self.requests>=32:raise AccessRefused('request/deadline budget exhausted')
        if body is not None and len(body.encode() if isinstance(body,str) else body)>min(self.policy.max_bytes,1024*1024):
            raise AccessRefused('request body exceeds bound')
        limit=self.policy.max_bytes-self.bytes_received
        if limit<=0:raise AccessRefused('transfer budget exhausted')
        self.requests+=1
        with self.session.request(method,uri,data=body,headers=headers,timeout=(min(5,remaining),min(15,remaining)),
                allow_redirects=False,stream=True) as response:
            data=response.raw.read(limit+1,decode_content=True)
            self.bytes_received+=len(data)
            if len(data)>limit:raise AccessRefused('response exceeds transfer bound')
            if 300<=response.status_code<400:raise AccessRefused('Google redirects refused')
            if self.clock()-self.started>self.policy.max_seconds:raise AccessRefused('total acquisition deadline exceeded')
            self.trace.append(dict(method=method,path=url.path,status=response.status_code,bytes=len(data),
                quota_project_header=any(k.lower()=='x-goog-user-project' for k in headers)))
            if response.status_code==200 and url.path==path+'config':
                try:self.noncommercial_verified=json.loads(data).get('registrationState')=='REGISTERED_NOT_COMMERCIALLY'
                except (ValueError,TypeError,AttributeError):raise AccessRefused('project registration response malformed') from None
            from httplib2 import Response
            return Response(dict(response.headers,status=str(response.status_code))),data

    def close(self):self.session.close()
