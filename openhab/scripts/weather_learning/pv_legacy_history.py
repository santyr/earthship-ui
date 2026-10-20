"""Bounded older electrical originals and explicitly unqualified PV proxies."""
from bisect import bisect_right,bisect_left
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from io import BytesIO
from math import fsum
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
from urllib.parse import urlencode
import gzip,json,os
from uuid import uuid4
from .contracts import canonical,identity,instant,finite
from weather_source_files import _read

ITEMS={'PV_Power':6,'BMS_SOC':24,'MPPT60_Native_ChargerStatusCode':24,'BMS_SOC_Evidence_JSON':2}
MAX_RESPONSE=1048576
SOC_RECEIPT_START=instant('2026-09-10T21:51:32.812382+00:00')
POWER_RECEIPT_START=instant('2026-09-20T15:05:22.557696+00:00')


def capture_query(root,*,item,start,end,budget,token_reader,clock=lambda:datetime.now(timezone.utc),opener=None,pace=None):
    from household_native_training import directory
    from openhab_runtime_io import _NoRedirect
    from thermal_model.capture_readers import _pacer
    if item not in ITEMS:raise ValueError('explicit historical PV Item required')
    if not timedelta(0)<end-start<=timedelta(hours=ITEMS[item]) or end>clock()-timedelta(minutes=5):raise ValueError('bounded completed PV history range required')
    root=directory(root);query=dict(item=item,start=start.isoformat(),end=end.isoformat());path=root/(identity(query)+'.http.json.gz')
    if path.exists():
        with gzip.GzipFile(fileobj=BytesIO(_read(path,2*MAX_RESPONSE))) as stream:raw=stream.read(2*MAX_RESPONSE+1)
        if len(raw)>2*MAX_RESPONSE:raise ValueError('bounded retained PV response required')
        value=json.loads(raw)
    else:
        opener=opener or build_opener(ProxyHandler({}),_NoRedirect()).open
        reserve=pace or _pacer(1048576).reserve
        url='http://127.0.0.1:8080/rest/persistence/items/'+item+'?'+urlencode(dict(serviceId='jdbc',starttime=start.isoformat(),endtime=end.isoformat()))
        timeout=budget.begin();requested=clock();parts=[];size=0
        request=Request(url,headers={'Authorization':'Bearer '+token_reader()},method='GET')
        with opener(request,timeout=timeout) as response:
            if response.geturl()!=url:raise ValueError('PV history redirect refused')
            while True:
                budget.remaining();reserve(65536);part=response.read(65536)
                if not part:break
                size+=len(part)
                if size>MAX_RESPONSE:raise ValueError('bounded original PV response required')
                parts.append(part)
        value=dict(schema='earthship-pv-history-http-original/v1',**query,requested_at=requested.isoformat(),received_at=clock().isoformat(),
            raw=b''.join(parts).decode(),measurement_health_qualified=False,automatic_actuation=False)
        value['source_sha256']=identity(value)
        _query_rows(value)
        encoded=gzip.compress(canonical(value),compresslevel=3,mtime=0);temporary=path.with_name('.pv-'+uuid4().hex)
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as handle:handle.write(encoded);handle.flush();os.fsync(handle.fileno())
            os.link(temporary,path)
        finally:temporary.unlink(missing_ok=True)
    if value.get('source_sha256')!=identity({k:v for k,v in value.items() if k!='source_sha256'}):raise ValueError('PV original identity differs')
    if any(value.get(k)!=v for k,v in query.items()) or value.get('measurement_health_qualified') is not False or value.get('automatic_actuation') is not False:raise ValueError('original PV query context differs')
    _query_rows(value);return value,path


def _query_rows(value):
    payload=json.loads(value['raw']);rows=payload.get('data')
    if payload.get('name')!=value['item'] or not isinstance(rows,list) or len(rows)>10000:raise ValueError('bounded original PV Item data required')
    start,end=instant(value['start']),instant(value['end']);result=[]
    for r in rows:
        if type(r.get('time')) is not int:raise ValueError('millisecond PV persistence time required')
        at=datetime.fromtimestamp(r['time']/1000,tz=timezone.utc)
        if start<=at<end:result.append((at,r.get('state')))
    return result


def numeric_rows(sources,*,item):
    result=[]
    for source in sources:
        if source['source_sha256']!=identity({k:v for k,v in source.items() if k!='source_sha256'}) or source['item']!=item:raise ValueError('original numeric PV source differs')
        for at,raw in _query_rows(source):
            value=None
            if isinstance(raw,str):
                cells=raw.split();allowed={'PV_Power':{'W'},'BMS_SOC':{'%'},'MPPT60_Native_ChargerStatusCode':set()}[item]
                if len(cells)==1 or len(cells)==2 and cells[1] in allowed:
                    try:value=float(cells[0])
                    except ValueError:pass
                if value is not None and not finite(value):value=None
            result.append((at,value))
    merged=[]
    for at,value in sorted(result,key=lambda row:row[0]):
        if merged and at==merged[-1][0]:
            if value!=merged[-1][1]:merged[-1]=(at,None)
        else:merged.append((at,value))
    return merged


def _ordered(rows):
    if not isinstance(rows,list) or len(rows)>40000 or [at for at,_ in rows]!=sorted({at for at,_ in rows}):raise ValueError('bounded ordered numeric PV history required')
    if any(v is not None and not finite(v) for _,v in rows):raise ValueError('finite numeric PV history or explicit invalid barrier required')


def _power(power,left,right,times):
    pieces=[]
    first=max(0,bisect_right(times,left-timedelta(seconds=15))-1);last=bisect_left(times,right)
    for i in range(first,last):
        at,value=power[i]
        stop=min(right,at+timedelta(seconds=15),power[i+1][0] if i+1<len(power) else right)
        start=max(left,at)
        if stop>start and value is not None and 0<=value<=20000:pieces.append(((stop-start).total_seconds(),value))
    covered=fsum(seconds for seconds,_ in pieces)
    return covered,None if covered==0 else fsum(s*v for s,v in pieces)/covered,max((v for _,v in pieces),default=None)


def _bulk(mode,left,right):
    times=[at for at,_ in mode];i=bisect_right(times,left)-1
    # Persistence contains state changes, not measurement heartbeats. A
    # bounded, later recorded transition brackets this historical episode.
    return i>=0 and i+1<len(mode) and mode[i][1]==769. and right<=mode[i+1][0]


def numeric_proxy_intervals(*,power,soc,mode,start,end,bank_start,soc_receipt_start=SOC_RECEIPT_START):
    for rows in (power,soc,mode):_ordered(rows)
    if not timedelta(0)<end-start<=timedelta(days=1):raise ValueError('bounded historical proxy window required')
    times=[at for at,_ in soc];power_times=[at for at,_ in power];result=[];left=start
    while left<end:
        right=min(left+timedelta(minutes=1),end);coverage,watts,maximum=_power(power,left,right,power_times);i=bisect_right(times,left)-1
        valid=False;age=None;rise=False
        if i>=1:
            at,value=soc[i];previous_at,previous=soc[i-1];age=(right-at).total_seconds()
            valid=(value is not None and previous is not None and 0<=value<=90 and 0<=previous<=100 and 0<=age<=120)
            rise=valid and value>previous and at-previous_at<=timedelta(minutes=30)
        eligible=(left>=bank_start and right<=soc_receipt_start and coverage>=.95*(right-left).total_seconds() and
            watts is not None and 100<=watts and maximum<2400 and rise and _bulk(mode,left,right))
        result.append(dict(start=left.isoformat(),end=right.isoformat(),outcome_w=watts,covered_seconds=coverage,potential_proxy_eligible=bool(eligible),
            soc_state_age_end_seconds=age,positive_charge_basis='recent_persisted_soc_increase_not_measured_DC_power',
            censoring_basis='fresh_low_numeric_soc_rise_bracketed_Bulk_sub2400W_input_proxy',
            charge_mode_basis='persisted_state_change_episode_assumed_held_until_next_recorded_transition',
            measurement_health_qualified=False,physical_calibration_qualified=False,automatic_actuation=False))
        left=right
    return result


def atomic_proxy_intervals(*,power,soc,mode,start,end,bank_start):
    from earthship_energy.bms_evidence import build_soc_intervals,soc_at
    for rows in (power,mode):_ordered(rows)
    if not timedelta(0)<end-start<=timedelta(days=1):raise ValueError('bounded historical proxy window required')
    try:intervals=build_soc_intervals(soc,start-timedelta(minutes=5),end,epoch_start=bank_start)
    except ValueError:intervals=[]
    result=[];left=start;power_times=[at for at,_ in power]
    while left<end:
        right=min(left+timedelta(minutes=1),end);coverage,watts,maximum=_power(power,left,right,power_times)
        soc_coverage=fsum(max(0.,(min(v.end,right)-max(v.start,left)).total_seconds()) for v in intervals if v.start<right and left<v.end)
        values=[soc_at(intervals,at) for at in (left,left+(right-left)/2,right-timedelta(microseconds=1))]
        before=soc_at(intervals,left-timedelta(minutes=5));valid=soc_coverage>=.95*(right-left).total_seconds() and all(v is not None and v<=90 for v in values)
        rise=valid and before is not None and values[0]>before
        eligible=(left>=max(bank_start,SOC_RECEIPT_START) and coverage>=.95*(right-left).total_seconds() and watts is not None and
            100<=watts and maximum<2400 and rise and _bulk(mode,left,right))
        result.append(dict(start=left.isoformat(),end=right.isoformat(),outcome_w=watts,covered_seconds=coverage,potential_proxy_eligible=bool(eligible),
            soc_covered_seconds=soc_coverage,soc_measurement_health_qualified=bool(valid),
            positive_charge_basis='qualified_soc_increase_over_previous_five_minutes_not_measured_DC_power',
            censoring_basis='qualified_low_soc_rise_bracketed_Bulk_numeric_sub2400W_input_proxy',
            charge_mode_basis='persisted_state_change_episode_assumed_held_until_next_recorded_transition',
            measurement_health_qualified=False,physical_calibration_qualified=False,automatic_actuation=False))
        left=right
    return result


def day_labels(root,day,entry,*,bank_start):
    start,end=instant(entry['start']),instant(entry['end']);roles={}
    for ref in entry['originals']:
        path=Path(root)/'originals'/ref['file_name'];raw=_read(path,2097152)
        if ref['file_name']!=Path(ref['file_name']).name or sha256(raw).hexdigest()!=ref['file_sha256']:raise ValueError('original PV history file differs')
        with gzip.GzipFile(fileobj=BytesIO(raw)) as f:payload=f.read(2*MAX_RESPONSE+1)
        if len(payload)>2*MAX_RESPONSE:raise ValueError('bounded original PV query required')
        source=json.loads(payload)
        if source['source_sha256']!=ref['source_sha256'] or source['source_sha256']!=identity({k:v for k,v in source.items() if k!='source_sha256'}):raise ValueError('original PV query differs')
        roles.setdefault(ref['role'],[]).append(source)
    power=numeric_rows(roles['power'],item='PV_Power');mode=numeric_rows(roles['mode'],item='MPPT60_Native_ChargerStatusCode')
    rows=[]
    if start<SOC_RECEIPT_START:
        soc=numeric_rows(roles.get('soc_numeric',[]),item='BMS_SOC')
        rows.extend(numeric_proxy_intervals(power=power,soc=soc,mode=mode,start=start,end=min(end,SOC_RECEIPT_START.replace(second=0,microsecond=0)),bank_start=bank_start))
    if end>SOC_RECEIPT_START:
        soc=[row for original in roles.get('soc_atomic',[]) for row in _query_rows(original)]
        begin=max(start,SOC_RECEIPT_START.replace(second=0,microsecond=0)+timedelta(minutes=1))
        rows.extend(atomic_proxy_intervals(power=power,soc=soc,mode=mode,start=begin,end=end,bank_start=bank_start))
    source_pin=identity(entry)
    for row in rows:row.update(source_sha256=source_pin,original_date=day)
    return rows
