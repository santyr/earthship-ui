"""Read-only original dataset, measurement and forecast binding utilities."""
from io import BytesIO
from pathlib import Path
import gzip,json
from .contracts import identity,digest
from weather_source_files import _read


def compressed_document(path,*,read=_read,maximum=32*1024**2):
    raw=read(Path(path),maximum)
    with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:expanded=stream.read(maximum+1)
    if len(expanded)>maximum:raise ValueError('bounded retained compressed original required')
    return json.loads(expanded),len(expanded)


def document(path,field,*,read=_read,maximum=1048576):
    value=json.loads(read(Path(path),maximum))
    if value[field]!=identity({k:v for k,v in value.items() if k!=field}):raise ValueError('retained document digest differs')
    return value


def read_dataset(root,pin,*,read=_read,guard=lambda:None,maximum_rows=50000):
    root=Path(root);digest(pin);value=document(root/(pin+'.dataset.json'),'dataset_sha256',read=read)
    if value['dataset_sha256']!=pin or value['schema']!='earthship-historical-learning-dataset/v2' or type(value['pair_count']) is not int or not 1<=value['pair_count']<=maximum_rows:
        raise ValueError('bounded complete original dataset required')
    rows=[];seen=set()
    for chunk in value['chunks']:
        guard();digest(chunk['sha256']);body,length=compressed_document(root/(chunk['sha256']+'.pairs.json.gz'),read=read)
        if (set(body)!={'schema','chunk_sha256','pairs'} or body['schema']!='earthship-historical-learning-pair-chunk/v1' or
                body['chunk_sha256']!=chunk['sha256'] or body['chunk_sha256']!=identity({k:v for k,v in body.items() if k!='chunk_sha256'}) or
                len(body['pairs'])!=chunk['pair_count'] or length!=chunk['uncompressed_bytes']):raise ValueError('complete original pair chunk differs')
        for row in body['pairs']:
            if row.get('pair_sha256')!=identity({k:v for k,v in row.items() if k!='pair_sha256'}) or row['pair_sha256'] in seen:raise ValueError('unchanged unique original parent pair required')
            seen.add(row['pair_sha256']);rows.append(row)
        if len(rows)>maximum_rows:raise ValueError('bounded original pair count exceeded')
    if len(rows)!=value['pair_count']:raise ValueError('complete original dataset population differs')
    return value,rows


def temperature_receipts(root,manifest,*,read=_read,guard=lambda:None):
    from .contracts import instant
    from .historical_measurements import capture_temperature_day
    from weather_temperature_evidence import TemperaturePolicy
    root=Path(root);values={};availability={}
    for row in manifest:
        guard();grid=document(root/(row['grid_sha256']+'.temperature-grid.json'),'grid_sha256',read=read)
        source,_=compressed_document(root/(row['date']+'.temperature-source.json.gz'),read=read)
        if source['source_sha256']!=row['source_sha256'] or source['source_sha256']!=identity({k:v for k,v in source.items() if k!='source_sha256'}) or grid['source_sha256']!=row['source_sha256']:
            raise ValueError('original receipt source differs from parent dataset')
        policies={k:TemperaturePolicy(**v) for k,v in grid['policy']['policies'].items()}
        replay=capture_temperature_day(root,row['date'],connection_factory=None,policies=policies,epochs=grid['policy']['epochs'],persist=False)
        if replay!=grid:raise ValueError('original receipt grid differs from literal source replay')
        received=instant(source['received_at'])
        for i,at in enumerate(grid['targets']):
            point=values.setdefault(at,{})
            for stream,records in grid['streams'].items():
                value=records[i]
                if stream in point and point[stream]!=value:raise ValueError('conflicting original receipt grids')
                point[stream]=value
                key=(at,stream);old=availability.get(key)
                if value is not None and (old is None or received<instant(old)):availability[key]=received.isoformat()
    return values,availability


def numeric_measurements(root,manifest,receipts,*,site,read=_read,guard=lambda:None):
    from datetime import timedelta
    from hashlib import sha256
    from .contracts import instant
    from .numeric_history import original_series,temperature_targets,infer_temperature_unit
    from thermal_model.schema import THERMAL_ITEMS
    roles={'air':'indoor','mass':'north_wall','outdoor':'outdoor'};root=Path(root);sources={};unit_ready={};values={};availability={}
    if manifest['receipt_coverage_start']!=min(receipts) or manifest['unit_assumed_constant_before_receipt_coverage'] is not True:raise ValueError('original unit-inference and receipt coverage required')
    def source(day,expected):
        if day in sources:return sources[day]
        guard();value,_=compressed_document(root/(day+'.numeric-source.json.gz'),read=read,maximum=8*1024**2)
        if value['source_sha256']!=expected or value['source_sha256']!=identity({k:v for k,v in value.items() if k!='source_sha256'}) or value['site']!=site or value['automatic_actuation'] is not False:
            raise ValueError('original numeric source/site differs')
        start,end=map(instant,(value['start'],value['end']))
        if start.isoformat()[:10]!=day or end-start!=timedelta(days=1):raise ValueError('original numeric source target window differs')
        for role in roles:
            for original in value['originals'][role]:
                if not end<=instant(original['requested_at'])<=instant(original['received_at']):raise ValueError('original numeric acquisition clocks differ')
        sources[day]=value;return value
    for role,stream in roles.items():
        ready=[]
        for proof in manifest['unit_overlap'][role]:
            original=source(proof['date'],proof['source_sha256']);labels={at:p[stream] for at,p in receipts.items() if at[:10]==proof['date'] and p.get(stream) is not None}
            result=infer_temperature_unit(original_series(original,role),labels)
            if result!={k:v for k,v in proof.items() if k not in ('date','source_sha256')} or result['unit']!=manifest['units'][role]:raise ValueError('numeric unit inference differs from original receipt overlap')
            ready.extend(instant(r['received_at']) for r in original['originals'][role])
        if len(manifest['unit_overlap'][role])<3:raise ValueError('complete original unit support required')
        unit_ready[role]=max(ready)
    for row in manifest['days']:
        path=root/(row['date']+'.numeric-source.json.gz')
        if sha256(read(path,8*1024**2)).hexdigest()!=row['file_sha256']:raise ValueError('original numeric file bytes differ')
        original=source(row['date'],row['source_sha256']);start=instant(original['start']);targets=[start+timedelta(minutes=5*i) for i in range(288)]
        if row['date']>=manifest['receipt_coverage_start'][:10]:raise ValueError('numeric fallback cannot replace receipt-era observations')
        for role,stream in roles.items():
            labels=temperature_targets(original_series(original,role),targets,item=THERMAL_ITEMS[role],source_sha256=original['source_sha256'],unit=manifest['units'][role])
            arrived=max(unit_ready[role],*(instant(r['received_at']) for r in original['originals'][role]))
            for at,label in zip(targets,labels):
                key=at.isoformat();values.setdefault(key,{})[stream]=label
                if label is not None:availability[(key,stream)]=arrived.isoformat()
    return values,availability


def wind_measurements(root,manifest,*,read=_read,guard=lambda:None):
    from datetime import datetime,timedelta,timezone
    from hashlib import sha256
    from .contracts import instant,finite
    from .weather_response import wind_hour
    root=Path(root);values={};item='AmbientWeatherWS2902A_WindSpeed'
    for day in manifest['days']:
        guard();start=instant(day['date']+'T00:00:00+00:00');end=start+timedelta(days=1);path=root/(day['date']+'.'+item+'.json.gz');pin=day['sources'][item]
        if sha256(read(path,8*1024**2)).hexdigest()!=pin['file_sha256']:raise ValueError('wind original HTTP bytes differ')
        original,_=compressed_document(path,read=read,maximum=8*1024**2)
        if (original['source_sha256']!=pin['source_sha256'] or original['source_sha256']!=identity({k:v for k,v in original.items() if k!='source_sha256'}) or
                original['schema']!='earthship-historical-weather-inventory-source/v1' or original['item']!=item or original['automatic_actuation'] is not False or
                not end<=instant(original['requested_at'])<=instant(original['received_at'])):raise ValueError('original wind acquisition context differs')
        payload=json.loads(original['raw'])
        if payload.get('name')!=item or payload.get('unit')!='mph' or not isinstance(payload.get('data'),list) or len(payload['data'])>10000:raise ValueError('bounded original mph wind states required')
        rows=[]
        for row in payload['data']:
            at=datetime.fromtimestamp(row['time']/1000,timezone.utc)
            if not start-timedelta(seconds=120)<=at<=end+timedelta(seconds=120):raise ValueError('wind state outside original query')
            try:value=float(row['state'].split()[0])
            except (ValueError,AttributeError,TypeError,IndexError):value=None
            if not finite(value):value=None
            if rows and at<rows[-1][0]:raise ValueError('ordered original wind states required')
            if rows and at==rows[-1][0]:
                if value!=rows[-1][1]:rows[-1]=(at,None)
            else:rows.append((at,value))
        for hour in range(24):
            left=start+timedelta(hours=hour);label=wind_hour(rows,start=left)
            if label['mean_m_s'] is not None:values[(left+timedelta(hours=1)).isoformat()]=dict(label,source_sha256=original['source_sha256'],actual_available_at=original['received_at'])
    return values
