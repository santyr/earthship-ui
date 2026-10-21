"""Offline SDK/query fixture using the real bounded HTTP bridge and normalizer.

There are no credentials or live sockets. Each native grid has its own cell and
projection. Synthetic responses cover every reviewed statistic and interval.
"""
from datetime import timedelta
from types import SimpleNamespace
import json
from learning_fixtures import T,SITE
from test_transport import Session,Response
from weather_learning.config import AccessPolicy,COLLECTIONS,PROJECT
from weather_learning.contracts import instant
from weather_learning.transport import BoundedTransport
from weather_learning.weathernext_ee import EarthEngineReader

def raw_response(grid,bands,init,horizon,*,null_band=None):
    def value(band):
        variable,stat=band.rsplit('_',1);rank={'p10':0,'p25':1,'p50':2,'p75':3,'p90':4}.get(stat,2)
        if band==null_band:return None
        if 'temperature' in variable:return (278.15 if 'dewpoint' in variable else 283.15)+rank-2
        if 'radiation' in variable:return (180000 if 'direct' in variable else 360000)*(0.6+rank*.2)
        if 'cloud' in variable:return .4
        if 'pressure' in variable:return 90000
        if 'tp_' in variable or 'precipitation' in variable:return [0,0,.0005,.001,.002][rank]
        if variable.startswith('u_component'):return -1
        if variable.startswith('v_component'):return 1
        return rank
    lon,lat=(-105.75,38.35) if grid=='station' else (-105.8,38.4)
    raw=dict(metadata=[],region=[['id','longitude','latitude','time',*bands]])
    for hour in range(1,horizon+1):
        at=init+timedelta(hours=hour);image=f'offline{hour}'
        raw['metadata'].append({'system:index':image,'start_time':init.isoformat(),'end_time':at.isoformat(),
            'forecast_hour':hour,'ingestion_time_utc':init.timestamp()+900})
        raw['region'].append([image,lon,lat,at.timestamp()*1000,*map(value,bands)])
    return raw

class OfflineSDK:
    def __init__(self,reader):
        self.reader=reader;self.queries=[];self.fail_band=None;self.null_band=None;self.quota_band=None;self.quota_http_status=429;self.status=200
        self.fail_bands=set()
        self.Geometry=SimpleNamespace(Point=lambda point:tuple(point))
        self.Filter=SimpleNamespace(eq=lambda *a:('eq',*a),gte=lambda *a:('gte',*a),lte=lambda *a:('lte',*a))
        self.projections={grid:object() for grid in COLLECTIONS}

    def Image(self,value):return value
    def ImageCollection(self,collection):return Collection(self,next(g for g,c in COLLECTIONS.items() if c==collection))
    def Dictionary(self,value):return self.computation(value)
    def computation(self,value,status=None):
        def getInfo():
            self.reader.transport.session.response=Response(json.dumps(value).encode(),self.status if status is None else status)
            response,raw=self.reader.transport.request('https://earthengine.googleapis.com/v1/projects/'+PROJECT+'/value:compute','POST',body='{}')
            if response.status!=200:raise ValueError('offline provider restriction')
            return json.loads(raw)
        return SimpleNamespace(getInfo=getInfo)

class Image:
    def __init__(self,collection,metadata=None):self.collection=collection;self.metadata=metadata
    def select(self,bands):return self
    def projection(self):return self.collection.sdk.projections[self.collection.grid]
    def toDictionary(self,keys):
        if self.metadata is not None:return self.metadata
        horizon=self.collection.bound('gte','forecast_hour')
        init=T if horizon>48 else T+timedelta(hours=1)
        return self.collection.sdk.computation({'start_time':init.isoformat(),'forecast_hour':horizon,
            'end_time':(init+timedelta(hours=horizon)).isoformat(),'ingestion_time_utc':init.timestamp()+900,'system:index':'discovery'})

class Collection:
    def __init__(self,sdk,grid):self.sdk=sdk;self.grid=grid;self.filters=[];self.bands=None;self.order=None;self.maximum=None
    def filter(self,condition):self.filters.append(condition);return self
    def sort(self,*args):self.order=args;return self
    def limit(self,maximum):self.maximum=maximum;return self
    def bound(self,op,name):return next((v for kind,key,v in self.filters if (kind,key)==(op,name)),None)
    def first(self):return Image(self)
    def select(self,bands):self.bands=bands;return self
    def raw(self):return raw_response(self.grid,self.bands,instant(self.bound('eq','start_time')),self.bound('lte','forecast_hour'),null_band=self.sdk.null_band)
    def getRegion(self,point,scale=None,crs=None,crsTransform=None):
        assert point==(SITE.longitude,SITE.latitude)
        assert scale is None and crsTransform is None and crs is self.sdk.projections[self.grid]
        assert self.order==('forecast_hour',) and self.maximum==self.bound('lte','forecast_hour')+1
        self.sdk.queries.append(dict(grid=self.grid,bands=tuple(self.bands),horizon=self.bound('lte','forecast_hour'),point=point,scale=scale,crs=crs,crsTransform=crsTransform))
        if self.sdk.quota_band in self.bands:self.sdk.computation({'error':{'status':'RESOURCE_EXHAUSTED'}},status=self.sdk.quota_http_status).getInfo()
        if self.sdk.fail_band in self.bands or self.sdk.fail_bands.intersection(self.bands):raise ValueError('offline missing optional group')
        return self.raw()['region']
    def toList(self,maximum):
        assert maximum==self.maximum
        return SimpleNamespace(map=lambda fn:[fn(Image(self,metadata)) for metadata in self.raw()['metadata']])

def reader(*,clock=None):
    now=[T+timedelta(hours=2)]
    result=EarthEngineReader(policy=AccessPolicy(backend='earthengine',noncommercial_verified=True),site=SITE,
        credential_path='/unused-offline-credential',clock=clock or (lambda:now[0]))
    result.transport=BoundedTransport(result.policy,session=Session())
    result.transport.noncommercial_verified=True
    result.ee=OfflineSDK(result);result.ready=True
    result.initialize=lambda:None
    return result,now
