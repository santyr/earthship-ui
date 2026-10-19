#!/usr/bin/env python3
"""Resume at most four historical site runs within existing Google request caps."""
import argparse,json,os,resource
from pathlib import Path
from datetime import date,datetime,time,timedelta,timezone
from weather_learning.archive import Archive
from weather_learning.config import AccessPolicy,Site
from weather_learning.weathernext_ee import EarthEngineReader
from weather_learning.historical import collect_history,cached_history,_historical_only
from weather_learning.openhab import oh_get,I18N_CONFIG_PATH
from household_native_training import save


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--start',required=True);parser.add_argument('--days',type=int,required=True)
    parser.add_argument('--hours',type=int,default=360)
    parser.add_argument('--credential',default='/home/sat/.config/earthship-weather/weathernext-reader.json')
    args=parser.parse_args(argv);os.umask(0o077)
    try:
        start=datetime.combine(date.fromisoformat(args.start),time.min,timezone.utc)
        if (start.hour or start.minute or start.second or start.microsecond or
            type(args.days) is not int or not 1<=args.days<=90 or not 1<=args.hours<=360):raise ValueError('bounded historical date range required')
        now=datetime.now(timezone.utc)
        if start+timedelta(days=args.days)>now:raise ValueError('completed historical date range required')
        archive=Archive(args.archive);_historical_only(archive)
        pending=[];retained=0
        for i in range(args.days):
            at=start+timedelta(days=i)
            if cached_history(archive,at,args.hours) is None:
                if len(pending)<4:pending.append(at)
            else:retained+=1
        if not pending:
            result=dict(status='historical_range_complete',retained_runs=retained,total_runs=args.days,automatic_actuation=False)
        else:
            site=Site.from_openhab_config(oh_get(I18N_CONFIG_PATH))
            reader=EarthEngineReader(policy=AccessPolicy(backend='earthengine',noncommercial_verified=True),site=site,credential_path=args.credential)
            result=collect_history(reader,archive,initializations=pending,horizon=args.hours,now=now)
            result.update(retained_runs=retained+result['downloaded'],total_runs=args.days,requests=reader.transport.requests,
                bytes_received=reader.transport.bytes_received,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        save(archive.root/'last-backfill.json',result)
        print(json.dumps(result),flush=True);return 0
    except Exception as error:
        print(json.dumps(dict(status='historical_backfill_incomplete',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
