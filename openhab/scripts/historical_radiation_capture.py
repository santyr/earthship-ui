#!/usr/bin/env python3
"""Retain historical original radiation receipts through the existing RO role."""
from datetime import datetime,date,time,timedelta,timezone
from pathlib import Path
from hashlib import sha256
from uuid import uuid4
import argparse,gzip,json,os
from household_native_training import directory,save
from household_capture import _connection
from weather_source_files import _read
from weather_learning.contracts import canonical,identity,instant
from weather_learning.worker import collector_lock
from weather_radiation_config import load_radiation_policy


def capture_day(root,day,*,connect,policy,clock=lambda:datetime.now(timezone.utc)):
    from weather_radiation_history import _fetch
    root=directory(root);start=datetime.combine(date.fromisoformat(day),time.min,timezone.utc);end=start+timedelta(days=1);path=root/(day+'.radiation-source.json.gz')
    if end>clock()-timedelta(minutes=5):raise ValueError('completed mature radiation day required')
    if path.exists():
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(_read(path,32*1024**2))) as stream:raw=stream.read(32*1024**2+1)
        if len(raw)>32*1024**2:raise ValueError('bounded original radiation day required')
        source=json.loads(raw)
        if canonical(source)!=raw or source['source_sha256']!=identity({k:v for k,v in source.items() if k!='source_sha256'}):raise ValueError('original radiation source differs')
    else:
        if connect is None:raise ValueError('retained radiation original required')
        requested=clock();rows=_fetch(lambda:connect(remaining=lambda:14.),start-timedelta(seconds=120),end+timedelta(seconds=120));received=clock()
        source=dict(schema='earthship-historical-radiation-source/v1',start=start.isoformat(),end=end.isoformat(),requested_at=requested.isoformat(),received_at=received.isoformat(),policy=policy.__dict__,
            rows=[[at.isoformat(),raw] for at,raw in rows],automatic_actuation=False);source['source_sha256']=identity(source);raw=canonical(source)
        if len(raw)>32*1024**2:raise ValueError('bounded original radiation bytes required')
        temporary=path.with_name('.radiation-'+uuid4().hex);fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as handle:handle.write(gzip.compress(raw,compresslevel=3,mtime=0));handle.flush();os.fsync(handle.fileno())
            os.link(temporary,path)
        finally:temporary.unlink(missing_ok=True)
    if (source.get('schema')!='earthship-historical-radiation-source/v1' or source['start']!=start.isoformat() or source['end']!=end.isoformat() or source.get('automatic_actuation') is not False or
        not end<=instant(source['requested_at'])<=instant(source['received_at'])<=clock()):raise ValueError('original radiation context differs')
    return source,path


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,required=True);p.add_argument('--start',required=True);p.add_argument('--days',type=int,required=True);a=p.parse_args(argv);os.umask(0o077)
    try:
        if not 1<=a.days<=90:raise ValueError('bounded radiation days required')
        root=directory(a.state);start=date.fromisoformat(a.start);connect=_connection('/home/sat/.config/hex/energy-power-reader.jdbc','energy_power_reader');policy=load_radiation_policy('/home/sat/.config/hex/weather-radiation-policy.json');rows=[]
        with collector_lock(root/'capture.lock'):
            for i in range(a.days):
                day=(start+timedelta(days=i)).isoformat();source,path=capture_day(root,day,connect=connect,policy=policy)
                rows.append(dict(date=day,source_sha256=source['source_sha256'],file_sha256=sha256(_read(path,32*1024**2)).hexdigest(),rows=len(source['rows'])))
                index=dict(schema='earthship-historical-radiation-index/v1',days=rows,automatic_actuation=False);index['index_sha256']=identity(index);save(root/'radiation-index.json',index)
            print(json.dumps(dict(status='historical_radiation_retained',days=len(rows),original_rows=sum(r['rows'] for r in rows),automatic_actuation=False)));return 0
    except Exception as error:
        import traceback
        directory(a.state);save(a.state/'last-error.json',dict(reason=type(error).__name__,message=str(error)[:2048],traceback=traceback.format_exc()[-8192:]))
        print(json.dumps(dict(status='historical_radiation_incomplete',reason=type(error).__name__,automatic_actuation=False)));return 1

if __name__=='__main__':raise SystemExit(main())
