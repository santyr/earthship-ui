#!/usr/bin/env python3
"""Refresh historical/recorded weather learning in the existing daily owner."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import argparse,json,os,subprocess,time,traceback,re
from household_native_training import directory,save
from weather_learning.worker import collector_lock
from weather_learning.contracts import identity
from weather_source_files import _read
from historical_weather_select import select


def context(path):
    wanted={'EARTHSHIP_WEATHER_ARCHIVE','EARTHSHIP_WEATHER_SHADOW_STATE','EARTHSHIP_WEATHER_TEMPERATURE_POLICY','EARTHSHIP_WEATHER_TEMPERATURE_DB_CONFIG'};result={}
    for line in _read(path,16384).decode().splitlines():
        key,sep,value=line.partition('=')
        if key in wanted:result[key]=value.strip().strip('\"\'')
    if set(result)!=wanted or any(not Path(v).is_absolute() for v in result.values()):raise ValueError('explicit existing weather runtime paths required')
    return result


def run(*,runtime_env,code_revision,root=None,clock=lambda:datetime.now(timezone.utc)):
    from hourly_temperature_runtime import _native_outdoor_policy
    if not re.fullmatch('[a-f0-9]{40}',code_revision):raise ValueError('immutable daily source revision required')
    root=Path(__file__).resolve().parents[2] if root is None else Path(root);cfg=context(runtime_env);base=Path.home()/'.local/state/earthship-weather';state=directory(base/'historical-daily');shadow=directory(Path(cfg['EARTHSHIP_WEATHER_SHADOW_STATE'])/'google-local-v2')
    end=clock().replace(hour=0,minute=0,second=0,microsecond=0);old=Path(base/'historical-measurements/temperature-index.json');index=json.loads(_read(old,65536));start=max(datetime.fromisoformat(index['days'][0]['date']).replace(tzinfo=timezone.utc),end-timedelta(days=90));days=(end-start).days
    deadline=time.monotonic()+800
    def command(name,args):
        left=deadline-time.monotonic()
        if left<5:raise TimeoutError('historical daily deadline elapsed')
        result=subprocess.run(['/usr/bin/python3',str(root/'openhab/scripts'/name),*map(str,args)],capture_output=True,timeout=min(left,600),env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(root/'openhab/scripts')+':/home/sat/Solar_PV/analytics/src'})
        if len(result.stdout)+len(result.stderr)>2*1024**2:raise ValueError('bounded historical step output required')
        log=state/(name+'.last.log');log.write_bytes(result.stdout+result.stderr);log.chmod(0o600)
        if result.returncode:raise RuntimeError('historical step failed: '+name)
    with collector_lock(state/'daily.lock'):
        command('historical_measurement_capture.py',['--state',base/'historical-measurements','--start',start.date().isoformat(),'--days',days,'--db-config',cfg['EARTHSHIP_WEATHER_TEMPERATURE_DB_CONFIG'],'--policy',cfg['EARTHSHIP_WEATHER_TEMPERATURE_POLICY']])
        command('historical_weather_capture.py',['--state',base/'historical-weather-inventory','--start',start.date().isoformat(),'--days',days])
        cutoff=end-timedelta(days=6)
        command('historical_training.py',['--archive',base/'historical-2026','--operational-archive',cfg['EARTHSHIP_WEATHER_ARCHIVE'],'--measurements',base/'historical-measurements','--numeric-measurements',base/'historical-numeric','--output',base/'historical-learning-current','--train-end',cutoff.isoformat(),'--holdout-end',end.isoformat()])
        command('historical_wind_rain_train.py',['--archive',base/'historical-2026','--operational-archive',cfg['EARTHSHIP_WEATHER_ARCHIVE'],'--measurements',base/'historical-weather-inventory','--output',base/'site-weather-current','--cutoff',cutoff.isoformat(),'--end',end.isoformat()])
        # Each selection revalidates its original experiment/model/runtime; a
        # worse candidate leaves the previous explicit selection in place.
        _,epoch=_native_outdoor_policy(cfg['EARTHSHIP_WEATHER_TEMPERATURE_POLICY']);results={}
        for kind,experiment_dir in [('outdoor_temperature_c','historical-learning-current'),('wind_m_s','site-weather-current')]:
            pointer=json.loads(_read(base/experiment_dir/'last-experiment.json',65536))
            try:results[kind]=select(Path(pointer['path']),kind=kind,state=shadow,sensor_epoch=epoch if kind=='outdoor_temperature_c' else None,clock=clock)
            except ValueError:results[kind]=dict(status='candidate_not_selected_previous_preserved',automatic_actuation=False)
        fallback='refreshed_or_already_current'
        try:
            command('local_forecast_train.py',['--archive',cfg['EARTHSHIP_WEATHER_ARCHIVE'],'--state',cfg['EARTHSHIP_WEATHER_SHADOW_STATE'],'--temperature-policy',cfg['EARTHSHIP_WEATHER_TEMPERATURE_POLICY'],'--temperature-db-config',cfg['EARTHSHIP_WEATHER_TEMPERATURE_DB_CONFIG'],'--code-revision',code_revision,'--apply'])
        except RuntimeError:fallback='deferred_previous_preserved'
        outcome=dict(legacy_fallback=fallback,status='historical_daily_refreshed',training_cutoff=end.isoformat(),selections=results,rain='raw_google_preserved_pending_improved_qualified_comparison',automatic_actuation=False)
        save(state/'last-result.json',outcome);return outcome


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime-env',type=Path,default=Path.home()/'.config/earthship-weather/runtime.env');p.add_argument('--code-revision',required=True);a=p.parse_args(argv);os.umask(0o077)
    try:print(json.dumps(run(runtime_env=a.runtime_env,code_revision=a.code_revision)),flush=True);return 0
    except Exception as e:
        state=directory(Path.home()/'.local/state/earthship-weather/historical-daily');save(state/'last-error.json',dict(reason=type(e).__name__,traceback=traceback.format_exc()[-8192:]));print(json.dumps(dict(status='historical_daily_incomplete',reason=type(e).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
