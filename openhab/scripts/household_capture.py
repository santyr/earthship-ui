#!/usr/bin/env python3
"""Collect bounded local original evidence, emitting an offline bundle to stdout."""
import argparse
from pathlib import Path
import sys
import time
from household.codec import loads,canonical
from household.capture import collect_inputs,fetch_receipt,NATIVE_ROLES
from household_snapshot import _read

CONFIG_FIELDS={'schema','energy_db_config','native_db_config','native_policy','energy_epochs','policy'}


def _connection(path,allowed_user):
    from earthship_energy.db import parse_openhab_jdbc_config
    import psycopg2
    if not isinstance(path,str) or not Path(path).is_absolute():raise ValueError('absolute private database config required')
    original=_read(path,8192,private=True)
    if allowed_user=='weather_temperature_reader':
        from hourly_temperature_runtime import read_db_config
        kwargs=read_db_config(path)
    else:
        settings=parse_openhab_jdbc_config(path)
        if (settings.host,settings.port,settings.dbname,settings.user)!=('127.0.0.1',5432,'openhab',allowed_user):
            raise ValueError('existing restricted local database reader required')
        kwargs=settings.connect_kwargs
    if _read(path,8192,private=True)!=original:raise ValueError('database configuration changed')
    def connect(*,remaining):
        if _read(path,8192,private=True)!=original:raise ValueError('database configuration changed')
        budget=remaining()
        if type(budget) not in (int,float) or not 1<=budget<=15:raise ValueError('insufficient connection budget')
        return psycopg2.connect(**kwargs,connect_timeout=min(2,int(budget)))
    return connect


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--configuration-only',action='store_true',help='read fixed bank/topology originals only; no database access')
    modes.add_argument('--measured-weather-only',action='store_true',help='read fixed original receiver/policy snapshots only; no database access')
    args=parser.parse_args(argv)
    if (args.configuration_only or args.measured_weather_only) and args.config is not None:parser.error('--configuration-only does not accept a capture configuration')
    if not args.configuration_only and not args.measured_weather_only and args.config is None:parser.error('--config is required for the original evidence capture')
    try:
        if args.measured_weather_only:
            from household.measured_weather_capture import collect_measured_weather
            result=collect_measured_weather()
            sys.stdout.buffer.write(canonical(result.to_dict())+b'\n');return 0
        if args.configuration_only:
            from household.energy_configuration_capture import collect_configuration
            from household_snapshot import runtime_manifest
            deadline=time.monotonic()+15.
            def remaining():
                budget=deadline-time.monotonic()
                if not 0.001<=budget<=15.:raise ValueError('configuration acquisition deadline elapsed')
                return budget
            before=runtime_manifest();remaining()
            result=collect_configuration(remaining=remaining)
            if runtime_manifest()!=before:raise ValueError('configuration collector runtime or registry changed')
            remaining()
            sys.stdout.buffer.write(canonical(result.to_dict())+b'\n');return 0
        original=_read(args.config,8192,private=True);config=loads(original)
        if not isinstance(config,dict) or set(config)!=CONFIG_FIELDS or config['schema']!='earthship-household-capture-config/v1':
            raise ValueError('closed private capture configuration required')
        if not isinstance(config['energy_epochs'],dict) or any(role not in ('battery_soc','pv_day_wh') for role in config['energy_epochs']):
            raise ValueError('explicit energy source bindings required')
        energy=_connection(config['energy_db_config'],'energy_power_reader')
        native=_connection(config['native_db_config'],'weather_temperature_reader')
        from weather_temperature_config import load_temperature_receiver_configuration
        from weather_temperature_sources import fetch_temperature_source
        from thermal_model.temperature_history import STREAMS,POLICY
        policy_path=config['native_policy']
        if not isinstance(policy_path,str) or not Path(policy_path).is_absolute():raise ValueError('absolute native policy path required')
        native_original=_read(policy_path,8192,private=True)
        policies,phases=load_temperature_receiver_configuration(policy_path)
        if phases is None:raise ValueError('explicit native hardware phases required')
        epochs=dict(config['energy_epochs'])
        for role,name in NATIVE_ROLES.items():
            stream,model,sensor_id=STREAMS[name]
            from weather_temperature_evidence import TemperaturePolicy
            if policies.get(stream)!=TemperaturePolicy(model,sensor_id,**POLICY):raise ValueError('native source policy differs')
            epochs[role]=phases[stream]
        result=collect_inputs(epochs=epochs,policy=config['policy'],
            receipt_reader=lambda role,start,end,remaining:fetch_receipt(lambda:energy(remaining=remaining),role=role,start=start,end=end,remaining=remaining),
            native_reader=lambda **request:fetch_temperature_source(lambda:native(remaining=request['remaining_timeout']),**request))
        if _read(args.config,8192,private=True)!=original or _read(policy_path,8192,private=True)!=native_original:
            raise ValueError('capture configuration changed')
        sys.stdout.buffer.write(canonical(result)+b'\n');return 0
    except Exception:
        print('Household capture refused: unavailable or changed original source context.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
