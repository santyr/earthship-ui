#!/usr/bin/env python3
"""Retain bounded original energy hours and qualified five-minute summaries."""
from datetime import datetime,date,time,timedelta,timezone
from pathlib import Path
from hashlib import sha256
from zoneinfo import ZoneInfo
import argparse,json,os
from household_native_training import directory,save
from household_capture import _connection
from weather_learning.contracts import identity,instant
from weather_learning.energy_history import capture_hour,summarize_hour
from weather_learning.worker import collector_lock
from weather_source_files import _read
from household_snapshot import _read as _read_public


def rolling_rows(rows,*,start,end):
    return {key:row for key,row in rows.items() if start<=instant(key)<end}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,required=True);p.add_argument('--start',required=True);p.add_argument('--days',required=True,type=int);p.add_argument('--batch-hours',type=int,default=12);p.add_argument('--rolling-index',action='store_true')
    a=p.parse_args(argv);os.umask(0o077)
    try:
        if not 1<=a.days<=90 or not 1<=a.batch_hours<=48:raise ValueError('bounded historical energy range required')
        start=datetime.combine(date.fromisoformat(a.start),time.min,timezone.utc)
        if start+timedelta(days=a.days)>datetime.now(timezone.utc)-timedelta(minutes=5):raise ValueError('completed energy dates required')
        root=directory(a.state);originals=directory(root/'originals');summaries=directory(root/'summaries')
        policy=_read('/home/sat/Solar_PV/analytics/config/power-evidence.json',4096).decode()
        epochs=json.loads(_read_public('/home/sat/Solar_PV/analytics/config/system-epochs.json',16384));bank=next(r for r in epochs['epochs'] if r['current_analytics'])
        bank_start=datetime.combine(date.fromisoformat(bank['start_local_date']),time.min,ZoneInfo(epochs['timezone'])).astimezone(timezone.utc).isoformat()
        connect=_connection('/home/sat/.config/hex/energy-power-reader.jdbc','energy_power_reader')
        index_path=root/'energy-index.json'
        with collector_lock(root/'capture.lock'):
            rows={}
            if index_path.exists():
                index=json.loads(_read(index_path,1048576))
                if index['index_sha256']!=identity({k:v for k,v in index.items() if k!='index_sha256'}):raise ValueError('energy index changed')
                rows={r['start']:r for r in index['hours']}
                if a.rolling_index:rows=rolling_rows(rows,start=start,end=start+timedelta(days=a.days))
            requested=[start+timedelta(hours=i) for i in range(a.days*24)]
            pending=sorted([at for at in reversed(requested) if at.isoformat() not in rows][:a.batch_hours])
            for at in pending:
                source,path=capture_hour(originals,at,connect=connect,policy_raw=policy,bank_start=bank_start)
                bins=summarize_hour(source);summary=dict(schema='earthship-historical-energy-summary/v1',source_sha256=source['source_sha256'],bins=bins,automatic_actuation=False)
                summary['summary_sha256']=identity(summary);save(summaries/(summary['summary_sha256']+'.json'),summary)
                rows[at.isoformat()]=dict(start=at.isoformat(),source_sha256=source['source_sha256'],file_sha256=sha256(path.read_bytes()).hexdigest(),summary_sha256=summary['summary_sha256'])
                index=dict(schema='earthship-historical-energy-index/v1',bank=bank,hours=[rows[k] for k in sorted(rows)],automatic_actuation=False)
                index['index_sha256']=identity(index);save(index_path,index)
            print(json.dumps(dict(status='historical_energy_progress',retained_hours=len(rows),total_hours=len(requested),automatic_actuation=False)),flush=True);return 0
    except Exception as error:
        print(json.dumps(dict(status='historical_energy_incomplete',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
