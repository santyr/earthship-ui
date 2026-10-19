#!/usr/bin/env python3
"""Retain bounded OpenHAB temperature history for retrospective Google learning."""
from datetime import date,datetime,time,timedelta,timezone
from pathlib import Path
import argparse,json,os
from weather_temperature_config import load_temperature_receiver_configuration
from hourly_temperature_runtime import read_db_config
from weather_learning.historical_measurements import capture_temperature_day
from weather_learning.worker import collector_lock
from weather_learning.contracts import identity
from household_native_training import directory,save


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',required=True,type=Path);parser.add_argument('--start',required=True);parser.add_argument('--days',type=int,required=True)
    parser.add_argument('--db-config',default='/home/sat/.config/hex/weather-temperature-db.json')
    parser.add_argument('--policy',default='/home/sat/.config/hex/weather-temperature-policy-v2.json')
    args=parser.parse_args(argv);os.umask(0o077)
    try:
        start=date.fromisoformat(args.start)
        if not 1<=args.days<=90:raise ValueError('bounded historical measurement interval required')
        policies,epochs=load_temperature_receiver_configuration(args.policy)
        config=read_db_config(args.db_config)
        import psycopg2
        def connection():return psycopg2.connect(**config,connect_timeout=3)
        root=directory(args.state)
        with collector_lock(root/'capture.lock'):
            index=dict(schema='earthship-historical-temperature-index/v1',days=[],automatic_actuation=False)
            for i in range(args.days):
                day=(start+timedelta(days=i)).isoformat()
                grid=capture_temperature_day(root,day,connection_factory=connection,policies=policies,epochs=epochs)
                row=dict(date=day,grid_sha256=grid['grid_sha256'],source_sha256=grid['source_sha256'],
                    qualified={name:sum(v is not None for v in values) for name,values in grid['streams'].items()},targets=len(grid['targets']))
                index['days'].append(row);index['index_sha256']=identity({k:v for k,v in index.items() if k!='index_sha256'})
                save(root/'temperature-index.json',index)
                print(json.dumps(dict(status='historical_measurement_day_retained',**row)),flush=True)
        return 0
    except Exception as error:
        print(json.dumps(dict(status='historical_measurements_incomplete',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
