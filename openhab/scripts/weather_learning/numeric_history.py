"""Older numeric persistence, explicitly distinct from qualified sensor receipts."""
from bisect import bisect_right
from datetime import date,datetime,time,timedelta,timezone
from math import isfinite,fsum
from pathlib import Path
import gzip,io,json,os
from uuid import uuid4
from .contracts import canonical,identity,digest,instant
from thermal_model.schema import THERMAL_ITEMS

MAX_STATE_AGE=timedelta(minutes=30)
ROLES=('air','mass','outdoor','radiation')


def temperature_targets(rows,targets,*,item,source_sha256,unit):
    if item not in [THERMAL_ITEMS[k] for k in ('air','mass','outdoor')] or unit not in ('F','C'):raise ValueError('explicit historical Item/unit required')
    digest(source_sha256)
    if len(rows)>10000 or len(targets)>289:raise ValueError('bounded numeric temperature grid required')
    times=[at for at,_ in rows]
    if times!=sorted(set(times)):raise ValueError('unique ordered numeric history required')
    result=[]
    for target in targets:
        i=bisect_right(times,target)-1;value=None
        if i>=0:
            at,raw=rows[i];age=target-at
            if raw is not None and type(raw) in (int,float) and isfinite(raw) and timedelta(0)<=age<=MAX_STATE_AGE:
                fahrenheit=raw if unit=='F' else raw*9/5+32
                if -40<=fahrenheit<=140:
                    value=dict(at=target.isoformat(),temperatureF=fahrenheit,provenance='persisted_numeric_state',
                        sourceItem=item,snapshotSha256=source_sha256,storedAt=at.isoformat(),stateAgeSeconds=age.total_seconds(),
                        receivedAt=None,validUntil=None,receiptVersion=None,sensorEpoch=None,sourceModel=None,sourceSensorId=None,
                        unit=unit,unit_basis='receipt_overlap_inference',measurement_health_qualified=False)
        result.append(value)
    return result


def infer_temperature_unit(rows,receipts):
    targets=sorted(instant(at) for at in receipts)
    targets=targets[:289]
    labels=temperature_targets(rows,targets,item=THERMAL_ITEMS['air'],source_sha256='0'*64,unit='F')
    pairs=[(v['temperatureF'],receipts[v['at']]['temperatureF']) for v in labels if v is not None and receipts.get(v['at']) is not None]
    if len(pairs)<3:return dict(unit=None,pairs=len(pairs),mae_f=None,reason='receipt_overlap_required')
    errors={unit:fsum(abs((raw if unit=='F' else raw*9/5+32)-actual) for raw,actual in pairs)/len(pairs) for unit in ('F','C')}
    unit=min(errors,key=errors.get);other='C' if unit=='F' else 'F'
    if errors[unit]>2 or errors[other]-errors[unit]<5:return dict(unit=None,pairs=len(pairs),mae_f=errors[unit],reason='unit_or_source_mismatch')
    return dict(unit=unit,pairs=len(pairs),mae_f=errors[unit],alternative_mae_f=errors[other],reason=None)


def original_series(source,role):
    if source['source_sha256']!=identity({k:v for k,v in source.items() if k!='source_sha256'}):raise ValueError('numeric source identity differs')
    if role not in ROLES:raise ValueError('explicit numeric history role required')
    rows=[];start,end=map(instant,(source['start'],source['end']))
    for original in source['originals'][role]:
        payload=json.loads(original['raw'])
        if not isinstance(payload,dict) or not isinstance(payload.get('data'),list):raise ValueError('original numeric response required')
        if payload.get('name')!=THERMAL_ITEMS[role]:raise ValueError('numeric response Item differs')
        for point in payload['data']:
            at=datetime.fromtimestamp(point['time']/1000,tz=timezone.utc)
            if not start<=at<end:continue
            raw=point['state']
            try:value=float(raw.split()[0])
            except (ValueError,IndexError,TypeError,AttributeError):value=None
            if value is not None and not isfinite(value):value=None
            rows.append((at,value))
    if len(rows)>10000:raise ValueError('bounded numeric history required')
    merged=[]
    for at,value in rows:
        if merged and at<merged[-1][0]:raise ValueError('ordered original numeric history required')
        if merged and at==merged[-1][0]:
            if value!=merged[-1][1]:merged[-1]=(at,None)
        else:merged.append((at,value))
    return merged


def capture_numeric_day(root,day,*,site,token_reader,clock=lambda:datetime.now(timezone.utc)):
    from household_native_training import directory
    from weather_source_files import _read
    root=directory(root);start=datetime.combine(date.fromisoformat(day),time.min,timezone.utc);end=start+timedelta(days=1)
    if end>clock()-timedelta(minutes=5):raise ValueError('completed numeric measurement day required')
    path=root/(day+'.numeric-source.json.gz')
    if path.exists():
        with gzip.GzipFile(fileobj=io.BytesIO(_read(path,8*1024**2))) as stream:raw=stream.read(8*1024**2+1)
        if len(raw)>8*1024**2:raise ValueError('bounded original numeric history required')
        source=json.loads(raw)
        if source['site']!=site or source['start']!=start.isoformat() or source['end']!=end.isoformat() or canonical(source)!=raw:
            raise ValueError('original numeric context differs')
    else:
        from urllib.request import build_opener,ProxyHandler
        from openhab_runtime_io import _NoRedirect,ReadBudget
        from thermal_model.capture_readers import BoundedJDBCReader
        opener=build_opener(ProxyHandler({}),_NoRedirect()).open
        source=dict(schema='earthship-historical-numeric-source/v1',start=start.isoformat(),end=end.isoformat(),site=site,
            source_quality='numeric_history_without_sensor_receipts',originals={},automatic_actuation=False)
        role=None
        class Response:
            def __init__(self,response,requested,role):
                self.response=response;self.requested=requested;self.role=role;self.parts=[]
            def __enter__(self):return self
            def __exit__(self,kind,error,traceback):
                try:
                    if kind is None:
                        source['originals'][self.role].append(dict(requested_at=self.requested.isoformat(),received_at=clock().isoformat(),raw=b''.join(self.parts).decode('utf-8')))
                finally:self.response.close()
            def geturl(self):return self.response.geturl()
            def read(self,size):
                # The existing reader reserves bandwidth and enforces byte
                # bounds before every delegated network read.
                raw=self.response.read(size);self.parts.append(raw);return raw
        def capture(request,timeout):
            requested=clock();return Response(opener(request,timeout=timeout),requested,role)
        reader=BoundedJDBCReader(base='http://127.0.0.1:8080/rest',token_reader=token_reader,budget=ReadBudget(45,max_requests=4),opener=capture)
        for role in ROLES:
            source['originals'][role]=[];reader(THERMAL_ITEMS[role],start,end)
        source['source_sha256']=identity(source)
        for role in ROLES:original_series(source,role)
        raw=canonical(source)
        if len(raw)>8*1024**2:raise ValueError('bounded original numeric day required')
        temporary=path.with_name('.numeric-'+uuid4().hex)
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(gzip.compress(raw,compresslevel=3,mtime=0));stream.flush();os.fsync(stream.fileno())
            os.link(temporary,path)
        finally:temporary.unlink(missing_ok=True)
    for role in ROLES:original_series(source,role)
    return source
