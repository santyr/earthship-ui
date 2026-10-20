from datetime import datetime,timezone
from pathlib import Path
import json
import pytest
from household_native_training import directory,save


def test_existing_daily_owner_refreshes_irradiance_and_admission_after_weather(tmp_path,monkeypatch):
    import historical_weather_daily as api
    import hourly_temperature_runtime
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    base=directory(tmp_path/'.local/state/earthship-weather')
    for sub in ('historical-measurements','historical-radiation'):
        save(directory(base/sub)/('temperature-index.json' if sub.endswith('measurements') else 'radiation-index.json'),{'days':[{'date':'2026-10-01'}]})
    shadow=directory(base/'shadow')
    for sub in ('historical-learning-current','site-weather-current'):
        save(directory(base/sub)/'last-experiment.json',{'path':str(base/sub/'experiment')})
    conf=directory(tmp_path/'.config/earthship-weather');save(conf/'unused.json',{})
    env=conf/'runtime.env';env.write_text(''.join(k+'='+str(v)+'\n' for k,v in {'EARTHSHIP_WEATHER_ARCHIVE':base/'operational','EARTHSHIP_WEATHER_SHADOW_STATE':shadow,'EARTHSHIP_WEATHER_TEMPERATURE_POLICY':conf/'policy','EARTHSHIP_WEATHER_TEMPERATURE_DB_CONFIG':conf/'db'}.items()));env.chmod(0o600)
    pv=conf/'daily-pv.env';pv.write_text('EARTHSHIP_DAILY_PV_LIBRARIES='+str(conf/'geometry.json')+'\n');pv.chmod(0o600)
    monkeypatch.setattr(hourly_temperature_runtime,'_native_outdoor_policy',lambda x:(None,'fixture-epoch'))
    monkeypatch.setattr(api,'select',lambda *a,**kw:{'status':'selected'})
    calls=[]
    def run(args,**kw):
        from types import SimpleNamespace
        calls.append(args)
        return SimpleNamespace(stdout=b'{}',stderr=b'',returncode=0)
    monkeypatch.setattr(api.subprocess,'run',run)
    out=api.run(runtime_env=env,code_revision='a'*40,root=tmp_path,clock=lambda:datetime(2026,10,20,12,35,tzinfo=timezone.utc))
    names=[Path(c[1]).name for c in calls]
    assert names[-4:]==['historical_radiation_capture.py','historical_irradiance_train.py','thermal_weather_admit.py','local_forecast_train.py']
    assert out['thermal_weather']=='refreshed_or_already_current'
    train=calls[names.index('historical_irradiance_train.py')]
    assert '--operational-archive' in train and '--libraries' in train
