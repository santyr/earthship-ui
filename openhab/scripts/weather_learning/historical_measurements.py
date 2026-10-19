"""Retrospective local targets with original v1/v2 receipt provenance.

Older evidence identifies its model and hardware ID but has no sensorEpoch.
That absence is retained, never backdated from today's configured phase.
"""
from datetime import date,datetime,time,timedelta,timezone
from pathlib import Path
import gzip,json,os
from .contracts import canonical,identity,instant
from .features import _jsonable
from weather_temperature_reader import select_temperature_grid,select_temperature_grid_v2


def temperature_grid(rows,*,targets,assessed_at,policies,epochs):
    if not isinstance(policies,dict) or not 1<=len(policies)<=4 or set(policies)!=set(epochs):raise ValueError('explicit historical stream policies required')
    if not targets:raise ValueError('nonempty historical grid required')
    result={}
    for name,policy in policies.items():
        kwargs=dict(targets=targets,assessed_at=assessed_at,history_start=targets[0]-timedelta(seconds=policy.validity_seconds),stream=name,policy=policy)
        old=select_temperature_grid(rows,**kwargs)
        new=select_temperature_grid_v2(rows,sensor_epoch=epochs[name],**kwargs)
        values=[]
        for (at,v1),(other,v2) in zip(old,new):
            if at!=other:raise ValueError('historical target grids differ')
            if v1 is not None and v2 is not None:raise ValueError('ambiguous temperature receipt schema')
            value=v2 if v2 is not None else v1
            values.append(None if value is None else _jsonable(dict(value,at=at,receiptVersion=2 if v2 is not None else 1,
                sensorEpoch=epochs[name] if v2 is not None else None,sourceModel=policy.model,sourceSensorId=policy.sensor_id)))
        result[name]=values
    return result


def capture_temperature_day(root,day,*,connection_factory,policies,epochs,clock=lambda:datetime.now(timezone.utc)):
    """One indexed day query; existing raw receipts replay without another read."""
    from household_native_training import directory,save
    from household_observation import _private_file
    from weather_temperature_history import _fetch_rows
    root=directory(root);start=datetime.combine(date.fromisoformat(day),time.min,timezone.utc)
    if start.hour or start.minute or start.second or start.microsecond:raise ValueError('UTC day required')
    end=start+timedelta(days=1);now=clock()
    if end>now-timedelta(minutes=5):raise ValueError('completed measurement day required')
    raw_path=root/(day+'.temperature-source.json.gz')
    if raw_path.exists():
        compressed=_private_file(raw_path,32*1024**2)[0]
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:raw=stream.read(32*1024**2+1)
        if len(raw)>32*1024**2:raise ValueError('bounded historical temperature source required')
        source=json.loads(raw)
        if canonical(source)!=raw or source.get('source_sha256')!=identity({k:v for k,v in source.items() if k!='source_sha256'}):
            raise ValueError('historical temperature source differs')
        if (set(source)!={'schema','start','end','requested_at','received_at','source_item','rows','source_sha256'} or
            source['schema']!='earthship-historical-temperature-day/v1' or source['source_item']!='Weather_Temperature_Evidence_JSON' or
            source['start']!=start.isoformat() or source['end']!=end.isoformat() or not end<=instant(source['requested_at'])<=instant(source['received_at'])<=now):
            raise ValueError('historical source window or acquisition differs')
        rows=[(instant(at),value) for at,value in source['rows']]
    else:
        requested=clock();history_start=start-timedelta(seconds=max(p.validity_seconds for p in policies.values()))
        rows=_fetch_rows(connection_factory,history_start,end)
        source=dict(schema='earthship-historical-temperature-day/v1',start=start.isoformat(),end=end.isoformat(),
            requested_at=requested.isoformat(),received_at=clock().isoformat(),source_item='Weather_Temperature_Evidence_JSON',rows=[[at.astimezone(timezone.utc).isoformat(),raw] for at,raw in rows])
        source['source_sha256']=identity(source);raw=canonical(source)
        if len(raw)>32*1024**2:raise ValueError('bounded historical temperature source required')
        temporary=raw_path.with_name('.'+raw_path.name+'.pending')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(gzip.compress(raw,compresslevel=3,mtime=0));stream.flush();os.fsync(stream.fileno())
            os.link(temporary,raw_path)
        finally:temporary.unlink(missing_ok=True)
    targets=[start+timedelta(minutes=5*i) for i in range(289)]
    streams=temperature_grid(rows,targets=targets,assessed_at=now,policies=policies,epochs=epochs)
    policy=dict(policies={name:policy.__dict__ for name,policy in policies.items()},epochs=epochs)
    grid=dict(schema='earthship-historical-temperature-grid/v1',source_sha256=source['source_sha256'],policy=policy,
        start=start.isoformat(),end=end.isoformat(),targets=[at.isoformat() for at in targets],streams=streams,
        prospective_score=False,automatic_actuation=False)
    grid['grid_sha256']=identity(grid);save(root/(grid['grid_sha256']+'.temperature-grid.json'),grid)
    return grid
