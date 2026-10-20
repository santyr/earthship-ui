#!/usr/bin/env python3
"""Select an explicitly improved historical candidate for read-only serving."""
from pathlib import Path
from datetime import datetime,timezone
from hashlib import sha256
from io import BytesIO
from zoneinfo import ZoneInfo
import argparse,json,gzip,os
from household_native_training import directory,save
from weather_source_files import _read
from weather_learning.contracts import identity,instant
from weather_learning.historical_serving import load_selection


def select(experiment,*,kind,state,sensor_epoch=None,clock=lambda:datetime.now(timezone.utc)):
    experiment=Path(experiment);raw=_read(experiment/'experiment.json',262144);value=json.loads(raw)
    if value['receipt_sha256']!=identity({k:v for k,v in value.items() if k!='receipt_sha256'}):raise ValueError('original historical experiment required')
    pin=value['final_models'][kind];path=experiment/(pin+'.final-model.json' if kind=='outdoor_temperature_c' else kind+'.final-model.json');raw_model=_read(path,4*1024**2);model=json.loads(raw_model)
    if model['model_sha256']!=pin:raise ValueError('original final candidate differs')
    if kind=='outdoor_temperature_c':
        dataset_pin=value['datasets'][kind];dataset=json.loads(_read(experiment/(dataset_pin+'.dataset.json'),32*1024**2))
        if dataset['dataset_sha256']!=dataset_pin or dataset_pin!=identity({k:v for k,v in dataset.items() if k!='dataset_sha256'}):raise ValueError('original training dataset manifest differs')
        expected=set(model['training_pair_sha256s']);seen=set();dates=set();zone=ZoneInfo(model['timezone'])
        for ref in dataset['chunks']:
            with gzip.GzipFile(fileobj=BytesIO(_read(experiment/(ref['sha256']+'.pairs.json.gz'),32*1024**2))) as f:expanded=f.read(32*1024**2+1)
            if len(expanded)>32*1024**2:raise ValueError('bounded original training chunk required')
            part=json.loads(expanded)
            if part['chunk_sha256']!=ref['sha256'] or part['chunk_sha256']!=identity({k:v for k,v in part.items() if k!='chunk_sha256'}):raise ValueError('original training chunk differs')
            for row in part['pairs']:
                if row['pair_sha256'] in expected:
                    if row['pair_sha256']!=identity({k:v for k,v in row.items() if k!='pair_sha256'}) or row['kind']!=kind:raise ValueError('original selected training pair differs')
                    seen.add(row['pair_sha256']);dates.add(instant(row['target_at']).astimezone(zone).date())
        if seen!=expected:raise ValueError('complete original trained target-date evidence required')
        count=len(dates);name='historical-outdoor.json'
    elif kind=='wind_m_s':count=model['training_target_days'];name='historical-wind.json'
    else:raise ValueError('supported explicit historical selection required')
    now=clock();record=dict(schema='earthship-historical-weather-selection/v1',kind=kind,experiment_path=str(experiment/'experiment.json'),experiment_file_sha256=sha256(raw).hexdigest(),
        experiment_receipt_sha256=value['receipt_sha256'],model_path=str(path),model_file_sha256=sha256(raw_model).hexdigest(),model_sha256=pin,target_dates=count,sensor_epoch=sensor_epoch,available_at=now.isoformat(),automatic_actuation=False)
    record['selection_sha256']=identity(record);state=directory(state);check=state/('.check-'+name);save(check,record)
    try:load_selection(check,kind=kind,now=now,sensor_epoch=sensor_epoch)
    finally:check.unlink(missing_ok=True)
    save(state/name,record);return dict(status='historical_candidate_selected',kind=kind,model_sha256=pin,target_dates=count,automatic_actuation=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True,type=Path);p.add_argument('--kind',required=True,choices=['outdoor_temperature_c','wind_m_s']);p.add_argument('--state',required=True,type=Path);p.add_argument('--temperature-policy',default='/home/sat/.config/hex/weather-temperature-policy-v2.json');a=p.parse_args(argv);os.umask(0o077)
    try:
        epoch=None
        if a.kind=='outdoor_temperature_c':
            from hourly_temperature_runtime import _native_outdoor_policy
            _,epoch=_native_outdoor_policy(a.temperature_policy)
        print(json.dumps(select(a.experiment,kind=a.kind,state=a.state,sensor_epoch=epoch)));return 0
    except Exception as e:print(json.dumps(dict(status='historical_selection_refused',reason=type(e).__name__,automatic_actuation=False)));return 1

if __name__=='__main__':raise SystemExit(main())
