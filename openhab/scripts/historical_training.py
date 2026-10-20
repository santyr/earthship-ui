#!/usr/bin/env python3
"""Train and chronologically assess Google/local outdoor and thermal candidates.

Only private research artifacts are written. Existing forecasts, prospective
scores, model selections and equipment remain untouched.
"""
from datetime import datetime,timezone
from pathlib import Path
from hashlib import sha256
import argparse,gzip,json,os,time,platform
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from household_native_training import directory,save
from household_observation import _private_file
from weather_learning.contracts import canonical,identity,instant
from weather_learning.archive import Archive
from weather_learning.historical_measurements import capture_temperature_day
from weather_learning.historical_pairs import pair_temperatures
from weather_learning.site_calibration import fit_residual,evaluate
from weather_learning.worker import collector_lock
from weather_temperature_evidence import TemperaturePolicy


def read_measurements(root,guard):
    root=Path(root);index_raw=_private_file(root/'temperature-index.json',65536)[0];index=json.loads(index_raw)
    if index['index_sha256']!=identity({k:v for k,v in index.items() if k!='index_sha256'}):raise ValueError('original temperature index differs')
    values={};manifest=[]
    if not 1<=len(index['days'])<=90:raise ValueError('bounded retained measurement dates required')
    for row in index['days']:
        guard();path=root/(row['grid_sha256']+'.temperature-grid.json');raw=_private_file(path,1048576)[0];grid=json.loads(raw)
        if grid['grid_sha256']!=row['grid_sha256'] or grid['grid_sha256']!=identity({k:v for k,v in grid.items() if k!='grid_sha256'}):
            raise ValueError('retained temperature grid differs from index')
        policies={k:TemperaturePolicy(**v) for k,v in grid['policy']['policies'].items()}
        replay=capture_temperature_day(root,row['date'],connection_factory=None,policies=policies,epochs=grid['policy']['epochs'],persist=False)
        if replay!=grid:raise ValueError('temperature grid differs from original receipt replay')
        manifest.append(dict(date=row['date'],grid_sha256=grid['grid_sha256'],source_sha256=grid['source_sha256']))
        for i,at in enumerate(grid['targets']):
            target=values.setdefault(at,{})
            for stream,rows in grid['streams'].items():
                value=rows[i]
                if stream in target and target[stream]!=value:raise ValueError('overlapping original temperature grids disagree')
                target[stream]=value
    from weather_learning.history_index import verify_retained_selection
    verify_retained_selection(index_raw,_private_file(root/'temperature-index.json',65536)[0])
    return values,manifest


def run(*,archive_path,measurement_path,output_path,train_end,holdout_end,numeric_path=None):
    from household_cycle_pressure import PublicationHeadroom
    started=time.monotonic();pressure=PublicationHeadroom()
    def guard():
        pressure.check()
        if time.monotonic()-started>550:raise TimeoutError('historical training deadline elapsed')
    root=Path(__file__).resolve().parents[2];sources=capture_sources(root)
    output=directory(output_path)
    with collector_lock(output/'training.lock'):
        measurements,measurement_manifest=read_measurements(measurement_path,guard)
        numeric_manifest=None
        if numeric_path is not None:
            from weather_learning.numeric_learning import read_numeric_measurements
            older,numeric_manifest=read_numeric_measurements(numeric_path,receipt_measurements=measurements,guard=guard)
            if set(older)&set(measurements):raise ValueError('numeric history cannot replace receipt coverage')
            measurements={**older,**measurements}
        archive=Archive.open_readonly(str(archive_path));rows=[];forecast_manifest=[]
        with archive._connect() as connection:refs=connection.execute('SELECT digest FROM snapshots WHERE historical=1 ORDER BY initialized,completed,digest LIMIT 1001').fetchall()
        if not 1<=len(refs)<=1000:raise ValueError('bounded original historical source list required')
        for (ref,) in refs:
            guard();snapshot=archive.read(ref)
            pairs=pair_temperatures(snapshot,measurements,target_end=holdout_end)
            rows.extend(pairs);forecast_manifest.append(ref)
        if not rows:raise ValueError('matched historical forecasts and local outcomes required')
        now=datetime.now(timezone.utc);reports={};models={};data={};run=directory(output/('experiment-'+now.strftime('%Y%m%dT%H%M%S%fZ')))
        for kind,limit in (('outdoor_temperature_c',6.),('indoor_temperature_c',8.),('wall_temperature_c',8.)):
            guard();selected=[r for r in rows if r['kind']==kind]
            if not selected:
                reports[kind]=dict(status='unavailable',reason='qualified_pairs_missing');continue
            from weather_learning.training_dataset import retain_dataset
            dataset=retain_dataset(run,metadata=dict(kind=kind,forecast_sha256s=forecast_manifest,measurement_manifest=measurement_manifest,
                numeric_manifest=numeric_manifest,prospective_score=False,automatic_actuation=False),pairs=selected)
            data[kind]=dataset['dataset_sha256']
            model=fit_residual(selected,kind=kind,cutoff=train_end,trained_at=now,correction_limit=limit)
            report=evaluate(model,selected,holdout_start=train_end,holdout_end=holdout_end)
            reports[kind]=report
            save(run/(model['model_sha256']+'.training-model.json'),model)
            final=fit_residual(selected,kind=kind,cutoff=holdout_end,trained_at=now,correction_limit=limit)
            save(run/(final['model_sha256']+'.final-model.json'),final);models[kind]=final['model_sha256']
            print(json.dumps(dict(status='historical_model_trained',kind=kind,training_pairs=model['sample_count'],training_origin_days=model['origin_days'],
                holdout_pairs=report['pairs'],holdout_origin_days=report['origin_days'],baseline_mae=report['baseline_mae'],candidate_mae=report['candidate_mae'])),flush=True)
        verify_sources(root,sources)
        runtime=retain_sources(run,sources)
        import numpy
        receipt=dict(schema='earthship-historical-training-experiment/v1',trained_at=now.isoformat(),train_end=train_end.isoformat(),holdout_end=holdout_end.isoformat(),
            datasets=data,final_models=models,reports=reports,runtime_manifest=runtime,environment=dict(python=platform.python_version(),numpy=numpy.__version__),forecast_runs=len(refs),measurement_days=len(measurement_manifest),
            prospective_score=False,automatic_actuation=False)
        receipt['receipt_sha256']=identity(receipt);save(run/'experiment.json',receipt);save(output/'last-experiment.json',dict(path=str(run),receipt_sha256=receipt['receipt_sha256']))
        guard();return receipt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','measurements','output'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--train-end',required=True);parser.add_argument('--holdout-end',required=True)
    parser.add_argument('--numeric-measurements',type=Path)
    args=parser.parse_args(argv);os.umask(0o077)
    try:
        result=run(archive_path=args.archive,measurement_path=args.measurements,output_path=args.output,
            train_end=instant(args.train_end),holdout_end=instant(args.holdout_end),numeric_path=args.numeric_measurements)
        print(json.dumps(dict(status='historical_training_complete',forecast_runs=result['forecast_runs'],measurement_days=result['measurement_days'],receipt_sha256=result['receipt_sha256'],automatic_actuation=False)),flush=True);return 0
    except Exception as error:
        print(json.dumps(dict(status='historical_training_incomplete',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
