#!/usr/bin/env python3
"""Resume at most four historical site runs within existing Google request caps."""
import argparse,json,os,resource,traceback
from pathlib import Path
from datetime import date,datetime,time,timedelta,timezone
from weather_learning.archive import Archive
from weather_learning.config import AccessPolicy,Site
from weather_learning.weathernext_ee import EarthEngineReader
from weather_learning.historical import collect_history,cached_history,indexed_history,_historical_only
from weather_learning.openhab import oh_get,I18N_CONFIG_PATH
from household_native_training import save


def requested_initializations(start,days,*,cycles,day_step,now):
    start=datetime.combine(date.fromisoformat(start),time.min,timezone.utc)
    if (type(days) is not int or not 1<=days<=366 or type(day_step) is not int or not 1<=day_step<=31 or
        cycles!=sorted(set(cycles)) or not cycles or not set(cycles)<={0,6,12,18}):raise ValueError('bounded explicit historical dates and full cycles required')
    if start+timedelta(days=days)>now:raise ValueError('completed historical date range required')
    return [start+timedelta(days=i,hours=hour) for i in range(0,days,day_step) for hour in cycles]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--start',required=True);parser.add_argument('--days',type=int,required=True)
    parser.add_argument('--hours',type=int,default=360)
    parser.add_argument('--cycle-hours',default='0')
    parser.add_argument('--day-step',type=int,default=1)
    parser.add_argument('--batch-runs',type=int,default=4)
    parser.add_argument('--index-only',action='store_true')
    parser.add_argument('--allow-optional-gaps',action='store_true',help='require complete mean temperature and GHI; retain missing optional fields explicitly')
    parser.add_argument('--credential',default='/home/sat/.config/earthship-weather/weathernext-reader.json')
    args=parser.parse_args(argv);os.umask(0o077)
    try:
        now=datetime.now(timezone.utc)
        if not 1<=args.batch_runs<=4:raise ValueError('one to four historical runs per batch required')
        if not 1<=args.hours<=360:raise ValueError('bounded historical horizon required')
        cycles=[int(h) for h in args.cycle_hours.split(',')]
        requested=requested_initializations(args.start,args.days,cycles=cycles,day_step=args.day_step,now=now)
        archive=Archive(args.archive);_historical_only(archive)
        required={('station_head_temperature_2m','mean'),('surface_solar_radiation_downwards_1hr','mean')} if args.allow_optional_gaps else None
        if args.index_only:
            for at in requested:cached_history(archive,at,args.hours,required=required)
        indexed=indexed_history(archive,horizon=args.hours,required=required)
        pending=sorted([at for at in reversed(requested) if at.isoformat() not in indexed][:args.batch_runs])
        retained=sum(at.isoformat() in indexed for at in requested)
        if args.index_only:
            result=dict(status='historical_coverage_indexed',retained_runs=retained,total_runs=len(requested),automatic_actuation=False)
            print(json.dumps(result),flush=True);return 0
        if not pending:
            result=dict(status='historical_range_complete',retained_runs=retained,total_runs=len(requested),automatic_actuation=False)
        else:
            site=Site.from_openhab_config(oh_get(I18N_CONFIG_PATH))
            reader=EarthEngineReader(policy=AccessPolicy(backend='earthengine',noncommercial_verified=True),site=site,credential_path=args.credential)
            result=collect_history(reader,archive,initializations=pending,horizon=args.hours,now=now,required=required)
            result.update(retained_runs=retained+result['downloaded'],total_runs=len(requested),requests=reader.transport.requests,
                bytes_received=reader.transport.bytes_received,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        save(archive.root/'last-backfill.json',result)
        print(json.dumps(result),flush=True);return 0
    except Exception as error:
        if args.archive.is_dir():
            save(args.archive/'last-backfill-error.json',dict(reason=type(error).__name__,message=str(error)[:2048],traceback=traceback.format_exc()[-8192:]))
        print(json.dumps(dict(status='historical_backfill_incomplete',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
