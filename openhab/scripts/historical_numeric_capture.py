#!/usr/bin/env python3
"""Resume bounded older numeric history capture; no learned-state or live writes."""
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
import argparse,json,os
from household_native_training import directory,save
from weather_source_files import _read
from weather_learning.config import Site
from weather_learning.openhab import oh_get,auth_token,I18N_CONFIG_PATH
from weather_learning.worker import collector_lock
from weather_learning.numeric_history import capture_numeric_day,original_series,ROLES
from weather_learning.contracts import identity


def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--state',required=True,type=Path);parser.add_argument('--start',required=True);parser.add_argument('--days',required=True,type=int)
 parser.add_argument('--batch-days',type=int,default=10)
 args=parser.parse_args(argv);os.umask(0o077)
 try:
  start=date.fromisoformat(args.start)
  if not 1<=args.days<=366 or not 1<=args.batch_days<=20:raise ValueError('bounded numeric capture range required')
  root=directory(args.state);site=Site.from_openhab_config(oh_get(I18N_CONFIG_PATH)).__dict__
  index_path=root/'numeric-index.json';index={}
  with collector_lock(root/'capture.lock'):
   if index_path.exists():
    value=json.loads(_read(index_path,262144))
    if value['index_sha256']!=identity({k:v for k,v in value.items() if k!='index_sha256'}):raise ValueError('numeric index changed')
    index={r['date']:r for r in value['days']}
   dates=[(start+timedelta(days=i)).isoformat() for i in range(args.days)]
   for day,row in index.items():
    raw=_read(root/(day+'.numeric-source.json.gz'),8*1024**2)
    if sha256(raw).hexdigest()!=row['file_sha256']:raise ValueError('retained numeric original bytes differ')
   pending=sorted([d for d in reversed(dates) if d not in index][:args.batch_days])
   for day in pending:
    source=capture_numeric_day(root,day,site=site,token_reader=auth_token)
    path=root/(day+'.numeric-source.json.gz')
    row=dict(date=day,source_sha256=source['source_sha256'],file_sha256=sha256(_read(path,8*1024**2)).hexdigest(),
      rows={role:len(original_series(source,role)) for role in ROLES})
    index[day]=row
    value=dict(schema='earthship-historical-numeric-index/v1',site=site,days=[index[d] for d in sorted(index)],automatic_actuation=False)
    value['index_sha256']=identity(value);save(index_path,value)
    print(json.dumps(dict(status='numeric_day_retained',**row)),flush=True)
   print(json.dumps(dict(status='numeric_history_progress',retained_days=sum(d in index for d in dates),total_days=args.days,automatic_actuation=False)),flush=True)
  return 0
 except Exception as error:
  print(json.dumps(dict(status='numeric_history_incomplete',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
