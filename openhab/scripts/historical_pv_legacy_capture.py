#!/usr/bin/env python3
"""Resume a bounded batch of original older PV, SoC and native mode history."""
from pathlib import Path
from datetime import date,datetime,time,timedelta,timezone
from hashlib import sha256
import argparse,json,os
from household_native_training import directory,save
from weather_source_files import _read
from weather_learning.contracts import identity,instant
from weather_learning.pv_legacy_history import capture_query,SOC_RECEIPT_START,POWER_RECEIPT_START
from weather_learning.openhab import auth_token
from weather_learning.worker import collector_lock
from openhab_runtime_io import ReadBudget


def run(root,dates):
    root=directory(root);originals=directory(root/'originals');budget=ReadBudget(85,max_requests=48)
    if not isinstance(dates,list) or not 1<=len(dates)<=3 or dates!=sorted(set(dates)):raise ValueError('one to three ordered historical dates required')
    with collector_lock(root/'capture.lock'):
        try:index=json.loads(_read(root/'index.json',1048576))
        except FileNotFoundError:index=dict(schema='earthship-pv-legacy-source-index/v1',dates={},automatic_actuation=False)
        if index.get('schema')!='earthship-pv-legacy-source-index/v1' or index.get('automatic_actuation') is not False:raise ValueError('owned historical PV index required')
        if 'index_sha256' in index and index['index_sha256']!=identity({k:v for k,v in index.items() if k!='index_sha256'}):raise ValueError('historical PV index differs')
        for day in dates:
            start=datetime.combine(date.fromisoformat(day),time.min,timezone.utc);end=start+timedelta(days=1)
            if start<instant('2026-07-20T00:00:00+00:00') or end>POWER_RECEIPT_START:raise ValueError('current bank epoch before power receipts required')
            queries=[('power','PV_Power',start+timedelta(hours=h),start+timedelta(hours=h+6)) for h in range(0,24,6)]
            queries.append(('mode','MPPT60_Native_ChargerStatusCode',start,end))
            if start<SOC_RECEIPT_START:queries.append(('soc_numeric','BMS_SOC',start,end))
            if end>SOC_RECEIPT_START:
                queries.extend(('soc_atomic','BMS_SOC_Evidence_JSON',start+timedelta(hours=h),start+timedelta(hours=h+2)) for h in range(0,24,2) if start+timedelta(hours=h+2)>SOC_RECEIPT_START)
            refs=[]
            for role,item,left,right in queries:
                source,path=capture_query(originals,item=item,start=left,end=right,budget=budget,token_reader=auth_token)
                refs.append(dict(role=role,item=item,file_name=path.name,file_sha256=sha256(_read(path,2097152)).hexdigest(),source_sha256=source['source_sha256'],start=source['start'],end=source['end']))
            index['dates'][day]=dict(start=start.isoformat(),end=end.isoformat(),originals=refs,measurement_health_qualified=False,automatic_actuation=False)
            index.pop('index_sha256',None);index['index_sha256']=identity(index);save(root/'index.json',index)
            print(json.dumps(dict(date=day,originals=len(refs),new_requests=budget.requests,automatic_actuation=False)),flush=True)
    return dict(status='legacy_pv_sources_captured',retained_dates=len(index['dates']),new_requests=budget.requests,index_sha256=index['index_sha256'],automatic_actuation=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--dates',required=True);args=p.parse_args();os.umask(0o077)
    print(json.dumps(run(args.root,args.dates.split(','))))

if __name__=='__main__':main()
