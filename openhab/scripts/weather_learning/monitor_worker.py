"""Scheduled local-outcome worker; Google access stays in the collector."""
import json,time
from dataclasses import asdict
from pathlib import Path
from datetime import datetime,timezone
from hashlib import sha256
from .cli import _parser,_context
from .contracts import canonical,instant
from .monitoring import monitor_once
from .worker import collector_lock


def observation_policy_identity(*,temperature_policy,policies,cutover,sensor_epoch):
    """Changed measurement qualification must never pool prior score support."""
    return sha256(canonical(dict(schema='earthship-weather-observation-policy/v2',
        temperature_policy=asdict(temperature_policy),policies=policies,
        cutover=cutover.isoformat(),sensor_epoch=sensor_epoch))).hexdigest()


def deadline_connection(factory,*,deadline,clock=time.monotonic):
    """Adapt the existing budgeted factory without losing its deadline."""
    def remaining():
        seconds=min(15.,deadline-clock())
        if seconds<1:raise TimeoutError('weather monitor connection deadline elapsed')
        return seconds
    def connect():
        remaining()
        return factory(remaining=remaining)
    return connect


def main(argv=None):
    parser=_parser('Score retained WeatherNext issues against qualified local measurements')
    parser.add_argument('--temperature-db-config',required=True)
    parser.add_argument('--observation-cutover',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(argv)
    try:
        from hourly_temperature_runtime import read_db_config
        from weather_temperature_history import fetch_temperature_grid_v2
        from weather_radiation_history import fetch_radiation_window
        from weather_rain_history import fetch_qualified_rain_day
        from weather_radiation_evidence import RadiationPolicy
        from weather_rain_evidence import RainPolicy
        from household_capture import _connection
        from household_observation import _private_file
        from household.measured_weather_capture import FIXED_POLICY_PATHS
        from .solar_shadow import capture_solar_window
        from .energy_shadow import capture_rain_day
        from .shadow import _read
        archive,state,site,temperature_policy,epoch=_context(args)
        config=read_db_config(args.temperature_db_config)
        cutover=instant(args.observation_cutover)
        policies={name:json.loads(_private_file(path,8192)[0]) for name,path in FIXED_POLICY_PATHS.items()}
        if any(value.get('version')!=1 for value in policies.values()):raise ValueError('known measurement policies required')
        radiation=RadiationPolicy(**{k:v for k,v in policies['radiation'].items() if k!='version'})
        rain=RainPolicy(**{k:v for k,v in policies['rain'].items() if k!='version'})
        policy_sha256=observation_policy_identity(temperature_policy=temperature_policy,policies=policies,cutover=cutover,sensor_epoch=epoch)
        deadline=time.monotonic()+90
        connect=deadline_connection(_connection('/home/sat/.config/hex/energy-power-reader.jdbc','energy_power_reader'),deadline=deadline)
        def guard():
            if time.monotonic()>=deadline:raise TimeoutError('weather monitor deadline elapsed')
        def temperatures(targets,assessed_at):
            import psycopg2
            groups={};result={}
            for at in targets:groups.setdefault(at.date(),[]).append(at)
            for group in groups.values():
                guard();result.update(fetch_temperature_grid_v2(lambda:psycopg2.connect(**config,connect_timeout=3),
                    targets=group,assessed_at=assessed_at,stream='outdoor',policy=temperature_policy,sensor_epoch=epoch))
            return result
        def solar(start,end,assessed_at):
            captured=[]
            fetch_radiation_window(connect,start=start,end=end,assessed_at=assessed_at,cutover=cutover,policy=radiation,
                source_capture=lambda **kw:captured.append(capture_solar_window(site_timezone=site.timezone,**kw)))
            return captured[0] if captured else None
        def rainfall(day,assessed_at):
            captured=[]
            fetch_qualified_rain_day(connect,local_date=day,as_of=assessed_at,cutover=cutover,policy=rain,site_timezone=site.timezone,
                source_capture=lambda **kw:captured.append(capture_rain_day(**kw)))
            return captured[0] if captured else None
        from .correction_monitor import monitor_corrections,NativeCorrectionDiscovery,solar_outcome
        from .wind_history import read_wind_hour
        from openhab_runtime_io import ReadBudget
        wind_budget=ReadBudget(90,max_requests=32,guard=guard)
        def wind(work,assessed_at):
            return read_wind_hour(start=instant(work['start']),assessed_at=assessed_at,budget=wind_budget)
        def proxy(work,assessed_at):
            value=solar(instant(work['start']),instant(work['end']),assessed_at)
            return None if value is None else solar_outcome(value,start=instant(work['start']))
        def corrections(*,now,limit,apply,guard):
            # Stage discovery is optional: its failure is named inside the
            # diagnostic rather than suppressing retained wind or temperature.
            def discover(cursor,**kwargs):
                from household_native_training import effective_selection
                guard();selection=effective_selection();guard()
                reader=NativeCorrectionDiscovery(state,stage=selection['stage'],
                    deployment_sha256=selection['deployment_sha256'],now=now,deadline=deadline)
                return reader(cursor,**kwargs)
            return monitor_corrections(state,now=now,observation_policy_sha256=policy_sha256,
                read_wind=wind,read_solar=proxy,limit=limit,apply=apply,guard=guard,discover=discover,
                clock=lambda:datetime.now(timezone.utc))
        with collector_lock(state.root/'monitor.lock'):
            report=monitor_once(archive,state,now=datetime.now(timezone.utc),site=site,sensor_epoch=epoch,code_revision=args.code_revision,
                observation_policy_sha256=policy_sha256,read_temperature=temperatures,read_solar=solar,read_rain=rainfall,apply=args.apply,guard=guard,read_corrections=corrections)
        print(json.dumps(dict(status='weather_performance_refreshed' if args.apply else 'weather_performance_prepared',
            temperature_pairs=0 if report['temperature']['raw'] is None else report['temperature']['raw']['pairs'],
            solar_pairs=len(report['solar']['pairs']),rain_days=len(report['rain']['pairs']),pending=report['pending'],
            report_sha256=report['report_sha256'],automatic_actuation=False)))
        return 0
    except Exception as error:
        print(json.dumps(dict(status='weather_monitor_unavailable',reason=type(error).__name__,automatic_actuation=False)))
        return 1
