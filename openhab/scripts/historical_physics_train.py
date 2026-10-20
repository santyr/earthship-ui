#!/usr/bin/env python3
"""Refit native thermal physics at an earlier cutoff, without any activation."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from hashlib import sha256
import argparse,json,os
from household_native_training import NativeTraining,read,save,directory,effective_selection,daily_lock
from weather_learning.contracts import instant


def cadence_capture_state(output,cutoff):
    """Reuse long original prefixes; fresh daily state bounds six-hour fragments.

    Short fragments remain immutable. The existing eight-part, original-byte,
    two-day capture and seven-day retention policies remain unchanged.
    """
    output=Path(output);state=directory(output/('cadence-state-'+cutoff.astimezone(ZoneInfo('America/Denver')).date().isoformat()))
    legacy=output/'state/raw-parts.json';seed=[]
    if legacy.exists():
        for row in read(legacy):
            left,right=map(instant,(row['start'],row['end']))
            if len(seed)==2 or right>cutoff or right-left<timedelta(days=1):break
            seed.append(row['path'])
    return state,seed


def run(*,daily_config,cutoff,output,intraday=False):
    from thermal_model.training_inputs import read_training_inputs_v2
    from native_thermal_inputs import build_native_development
    from native_thermal_fit import fit_native_development
    from native_thermal_artifact import current_native_runtime
    if cutoff>datetime.now(timezone.utc)-timedelta(minutes=5):raise ValueError('completed physical training cutoff required')
    output=directory(output);config=read(daily_config)
    state,seed=cadence_capture_state(output,cutoff) if intraday else (directory(output/'state'),[])
    config.update(state_directory=str(state),seed_parts=seed)
    backend=NativeTraining(config);previous=effective_selection()
    with daily_lock(output/'physics.lock'):
        run=directory(output/('fit-'+cutoff.strftime('%Y%m%dT%H%M%S')+'-'+datetime.now(timezone.utc).strftime('%H%M%S%f')))
        snapshot=backend.snapshot(run,cutoff);record=read_training_inputs_v2(snapshot)
        geometry,geometry_path,libraries=backend.geometry(run,record,previous)
        phases={role:info['sensor_epoch'] for role,info in record['temperature_evidence']['roles'].items()}
        data=build_native_development(record,expected_snapshot_sha256=record['snapshot_sha256'],sensor_epochs=phases,
            geometry=geometry,expected_series_sha256=geometry.sha256,assessed_at=datetime.now(timezone.utc))
        dataset=run/(data.sha256+'.native-development.json');save(dataset,data.to_dict())
        runtime=current_native_runtime(guard=backend.guard)
        os.environ['EARTHSHIP_QUALIFICATION_FIT']='1';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        fit=fit_native_development(data,expected_dataset_sha256=data.sha256,training_start=data.development.start,training_end=data.development.end,
            guard=backend.guard,timeout_seconds=85,joint=True,irradiance=True)
        if current_native_runtime(guard=backend.guard)!=runtime:raise ValueError('native physical fitting runtime changed')
        result=dict(schema='earthship-historical-native-physics-fit/v1',cutoff=cutoff.isoformat(),created_at=datetime.now(timezone.utc).isoformat(),
            fit=fit,runtime=runtime,originals=dict(snapshot=str(snapshot),dataset=str(dataset),geometry=str(geometry_path)),
            numerical_target='physical_response_to_measured_conditions',prospective_score=False,production_model_changed=False,automatic_actuation=False)
        result['receipt_sha256']=sha256(__import__('weather_learning.contracts',fromlist=['canonical']).canonical(result)).hexdigest()
        save(run/'physics-fit.json',result);save(output/'last-fit.json',dict(path=str(run),receipt_sha256=result['receipt_sha256']))
        return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--daily-config',required=True,type=Path)
    parser.add_argument('--cutoff',required=True);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--intraday',action='store_true',help='use bounded daily experiment capture state for six-hour cutoff studies')
    args=parser.parse_args(argv);os.umask(0o077)
    try:
        value=run(daily_config=args.daily_config,cutoff=instant(args.cutoff),output=args.output,intraday=args.intraday)
        print(json.dumps(dict(status='historical_native_physics_trained',training_start=value['fit']['training_start'],training_end=value['fit']['training_end'],
            endpoint_count=value['fit']['endpoint_count'],receipt_sha256=value['receipt_sha256'],production_model_changed=False,automatic_actuation=False)),flush=True);return 0
    except Exception as error:
        import traceback
        directory(args.output);save(args.output/'last-error.json',dict(reason=type(error).__name__,message=str(error)[:2048],traceback=traceback.format_exc()[-8192:]))
        print(json.dumps(dict(status='historical_native_physics_incomplete',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
