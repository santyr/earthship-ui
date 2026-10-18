"""Bounded native-cell WeatherNext statistics through approved Earth Engine."""
from datetime import datetime,timedelta,timezone
import json,math,os,pathlib,stat
from .config import AccessPolicy,COLLECTIONS,READER,PROJECT,Site
from .contracts import canonical,identity,instant,finite,validate_snapshot
from .normalize import VARIABLES,normalize_point
from .transport import AccessRefused,BoundedTransport


def _bands(bands,collection):
    if collection not in COLLECTIONS.values() or not isinstance(bands,(tuple,list)) or not 1<=len(bands)<=48 or len(set(bands))!=len(bands):
        raise ValueError('bounded approved collection/bands required')
    result=[]
    for band in bands:
        if not isinstance(band,str) or '_' not in band:raise ValueError('native band required')
        variable,statistic=band.rsplit('_',1)
        if variable not in VARIABLES or statistic not in ('mean','p10','p25','p50','p75','p90'):
            raise ValueError('unmapped native statistics band')
        if variable.startswith('station_head_')!=(collection==COLLECTIONS['station']):
            raise ValueError('band does not belong to selected grid')
        result.append((variable,statistic))
    return result


def parse_collection_response(raw,*,collection,bands,site,initialized_at,horizon):
    variables=_bands(bands,collection)
    if not isinstance(site,Site) or type(horizon) is not int or not 1<=horizon<=360 or initialized_at.utcoffset() is None:
        raise ValueError('explicit bounded acquisition context required')
    init=initialized_at.astimezone(timezone.utc)
    if not isinstance(raw,dict) or set(raw)!={'metadata','region'}:raise ValueError('closed collection response required')
    metadata,region=raw['metadata'],raw['region']
    if not isinstance(metadata,list) or len(metadata)!=horizon or not isinstance(region,list) or len(region)!=horizon+1:
        raise ValueError('incomplete or oversized forecast targets')
    expected=['id','longitude','latitude','time',*bands]
    if region[0]!=expected:raise ValueError('source region schema/bands differ')
    originals=dict(collection=collection,payload=raw);source_digest=identity(originals)
    identities={};hours=set()
    for meta in metadata:
        if not isinstance(meta,dict) or set(meta) not in ({'system:index','start_time','end_time','forecast_hour','ingestion_time_utc'},
                {'system:index','system:time_start','start_time','end_time','forecast_hour','ingestion_time_utc'}):
            raise ValueError('original image metadata missing or changed')
        hour=meta['forecast_hour'];image_id=meta['system:index']
        if type(hour) is not int or not 1<=hour<=horizon or hour in hours or instant(meta['start_time'])!=init or instant(meta['end_time'])!=init+timedelta(hours=hour):
            raise ValueError('source run/target identity differs')
        if not isinstance(image_id,str) or not 1<=len(image_id)<=192 or '/' in image_id or image_id in identities:
            raise ValueError('unique original image ID required')
        if not finite(meta['ingestion_time_utc']):raise ValueError('original upstream ingestion timestamp required')
        if 'system:time_start' in meta:
            clock=meta['system:time_start']
            if not finite(clock) or clock not in (init.timestamp()*1000,(init+timedelta(hours=hour)).timestamp()*1000):
                raise ValueError('source image clock is neither initialization nor target')
        identities[image_id]=meta;hours.add(hour)
    points=[];seen=set();cell=None
    spacing=.05 if collection==COLLECTIONS['station'] else .1
    for row in region[1:]:
        if not isinstance(row,list) or len(row)!=len(expected) or row[0] not in identities or row[0] in seen:
            raise ValueError('unique original native-cell row required')
        seen.add(row[0]);image_id,lon,lat,valid_ms,*values=row
        if not all(finite(v) for v in (lon,lat,valid_ms)):raise ValueError('finite native cell/time required')
        if abs(lat-site.latitude)>spacing/2+1e-4 or abs((lon-site.longitude+180)%360-180)>spacing/2+1e-4:
            raise ValueError('returned native cell differs from site')
        if cell is not None and cell!=(lat,lon):raise ValueError('native cell changed within run')
        cell=(lat,lon)
        meta=identities[image_id]
        valid=instant(meta['end_time'])
        # Live WeatherNext uses initialization for system:time_start, despite
        # the guide describing valid time. Retain and bind the reported clock;
        # forecast targets come from cross-checked end_time/forecast_hour.
        expected_clock=meta.get('system:time_start',valid.timestamp()*1000)
        if valid_ms!=expected_clock:raise ValueError('point source time differs from image metadata')
        for (variable,statistic),value in zip(variables,values):
            points.append(normalize_point(variable,value,VARIABLES[variable][0],valid_at=valid.isoformat(),
                source_ref=collection+'/'+image_id,source_digest=source_digest,latitude=lat,longitude=(lon+180)%360-180,statistic=statistic))
    return originals,points


def make_snapshot(collections,*,site,initialized_at,first_seen_at,completed_at,historical=False):
    value=dict(schema='earthship-weathernext-snapshot/v1',provider='weathernext3',
        run_id='ee:'+initialized_at.astimezone(timezone.utc).isoformat(),initialized_at=initialized_at.isoformat(),
        first_seen_at=first_seen_at.isoformat(),ingestion_completed_at=completed_at.isoformat(),historical=historical,
        site=dict(latitude=site.latitude,longitude=site.longitude,timezone=site.timezone),
        points=[p for _,points in collections for p in points],source_originals=[source for source,_ in collections])
    return validate_snapshot(value)


def load_credentials(path):
    """Load only the explicit private worker identity; no ADC or key logging."""
    from google.oauth2 import service_account
    path=pathlib.Path(path)
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or not 1<=info.st_size<=16384:
            raise AccessRefused('private owned credential file required')
        with os.fdopen(descriptor,'rb',closefd=False) as stream:raw=stream.read(16385)
    finally:os.close(descriptor)
    try:
        document=json.loads(raw)
        if document.get('type')!='service_account' or document.get('client_email')!=READER or document.get('project_id')!=PROJECT or document.get('token_uri')!='https://oauth2.googleapis.com/token':
            raise ValueError('unexpected Google identity')
        return service_account.Credentials.from_service_account_info(document,scopes=['https://www.googleapis.com/auth/earthengine','https://www.googleapis.com/auth/devstorage.read_only']).with_quota_project(None)
    except Exception:raise AccessRefused('Google credential identity or encoding refused') from None


class EarthEngineReader:
    def __init__(self,*,policy,site,credential_path,clock=lambda:datetime.now(timezone.utc)):
        if not isinstance(policy,AccessPolicy) or policy.backend!='earthengine' or not isinstance(site,Site):
            raise AccessRefused('approved explicit acquisition context required')
        self.policy=policy;self.site=site;self.credential_path=credential_path;self.clock=clock
        self.transport=BoundedTransport(policy);self.ready=False;self.ee=None

    def initialize(self):
        with self.transport.deadline():self._initialize()

    def _initialize(self):
        from google.auth.transport.requests import Request
        credentials=load_credentials(self.credential_path)
        request=Request(session=self.transport.session)
        def bounded(*args,**kwargs):kwargs['timeout']=min(15,self.policy.max_seconds);return request(*args,**kwargs)
        try:credentials.refresh(bounded)
        except Exception:raise AccessRefused('Google worker authentication failed') from None
        response,content=self.transport.request('https://earthengine.googleapis.com/v1/projects/'+self.policy.project+'/config',
            headers={'Authorization':'Bearer '+credentials.token})
        if response.status!=200:
            try:reason=json.loads(content).get('error',{}).get('status','UNKNOWN')
            except ValueError:reason='INVALID_RESPONSE'
            raise AccessRefused('Earth Engine registration preflight refused: '+str(response.status)+' '+reason)
        if not self.transport.noncommercial_verified:raise AccessRefused('project is not verified noncommercial')
        import ee
        ee.Reset();ee.data.setMaxRetries(0)
        ee.Initialize(credentials=credentials,project=self.policy.project,http_transport=self.transport)
        self.ee=ee;self.ready=True

    def discover_run(self,*,horizon):
        if not self.ready or type(horizon) is not int or not 1<=horizon<=self.policy.max_targets:
            raise AccessRefused('initialized bounded reader required')
        ee=self.ee;now=self.clock().astimezone(timezone.utc)
        col=(ee.ImageCollection(COLLECTIONS['gridded'])
            .filter(ee.Filter.gte('start_time',(now-timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%SZ')))
            .filter(ee.Filter.lte('start_time',now.strftime('%Y-%m-%dT%H:%M:%SZ')))
            .filter(ee.Filter.gte('forecast_hour',horizon)).sort('start_time',False).limit(1))
        result=ee.Image(col.first()).toDictionary(['start_time','end_time','forecast_hour','ingestion_time_utc','system:index']).getInfo()
        if not isinstance(result,dict) or 'start_time' not in result or instant(result['start_time'])>now:
            raise AccessRefused('eligible source run unavailable')
        return result

    def fetch_points(self,*,run,bands_by_grid,horizon):
        if not self.ready or type(horizon) is not int or not 1<=horizon<=self.policy.max_targets:
            raise AccessRefused('initialized bounded reader required')
        if not isinstance(bands_by_grid,dict) or not 1<=len(bands_by_grid)<=2 or not set(bands_by_grid)<=set(COLLECTIONS):
            raise AccessRefused('approved fixed grid selections required')
        ee=self.ee;first_seen=self.clock();initialized=instant(run['start_time']);results=[]
        for grid,bands in bands_by_grid.items():
            collection=COLLECTIONS[grid];_bands(bands,collection)
            images=(ee.ImageCollection(collection).filter(ee.Filter.eq('start_time',run['start_time']))
                .filter(ee.Filter.gte('forecast_hour',1)).filter(ee.Filter.lte('forecast_hour',horizon)).sort('forecast_hour').limit(horizon+1))
            projection=ee.Image(images.first()).select([bands[0]]).projection()
            region=images.select(list(bands)).getRegion(ee.Geometry.Point([self.site.longitude,self.site.latitude]),crs=projection)
            metadata=images.toList(horizon+1).map(lambda image:ee.Image(image).toDictionary(['system:index','system:time_start','start_time','end_time','forecast_hour','ingestion_time_utc']))
            raw=ee.Dictionary(dict(metadata=metadata,region=region)).getInfo()
            results.append(parse_collection_response(raw,collection=collection,bands=bands,site=self.site,initialized_at=initialized,horizon=horizon))
        return make_snapshot(results,site=self.site,initialized_at=initialized,first_seen_at=first_seen,completed_at=self.clock())
