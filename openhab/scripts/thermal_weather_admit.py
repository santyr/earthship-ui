#!/usr/bin/env python3
"""Admit original selected thermal corrections once, outside inference."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import argparse,json,os,time
from household.codec import canonical,identity
from household_native_training import directory,save
from household.thermal_weather_conditioning import capsule,validate_admission
from thermal_weather_source import conditioning_runtime,hash_reference
from weather_source_files import _read
from weather_learning.contracts import instant
from weather_learning.site_calibration import _model,fit_residual
from weather_learning.historical_serving import load_selection
from historical_thermal_conditioning_compare import training_pairs,document


def reproduce(model,pairs):
    """Verify retained original arithmetic; never replace its creation clock."""
    model=_model(model)
    replay=fit_residual(pairs,kind=model['kind'],cutoff=instant(model['cutoff']),trained_at=instant(model['trained_at']),
        correction_limit=model['correction_limit'],ridge=model['ridge'],timezone_name=model['timezone'])
    if canonical(replay)!=canonical(model):raise ValueError('current numerical fitter does not reproduce original thermal model')
    return model['model_sha256']


def admit(*,outdoor_selection,irradiance,comparison,output,selection,horizon,clock=lambda:datetime.now(timezone.utc),guard=lambda:None):
    now=clock();runtime=conditioning_runtime();refs={}
    def original(path,maximum):
        path=Path(path).resolve();raw=_read(path,maximum)
        refs[str(path)]=dict(path=str(path),sha256=sha256(raw).hexdigest(),maximum=maximum,source=False)
        return json.loads(raw)
    cp=original(Path(comparison)/'last-comparison.json',8192);cr=Path(cp['path']);decision=original(cr/'comparison.json',1048576)
    if (decision['receipt_sha256']!=cp['receipt_sha256'] or decision['receipt_sha256']!=identity({k:v for k,v in decision.items() if k!='receipt_sha256'}) or
            decision['selection']['selected_method']!='six_hourly_local_outdoor_and_irradiance' or decision['automatic_actuation'] is not False):
        raise ValueError('original winning matched thermal comparison required')
    sel=json.loads(_read(outdoor_selection,16384));epoch=sel['sensor_epoch']
    outside,selected=load_selection(outdoor_selection,kind='outdoor_temperature_c',now=now,sensor_epoch=epoch)
    # Selector is mutable; retain its original experiment and model, not its path.
    te=original(selected['experiment_path'],1048576);original(selected['model_path'],4*1024**2)
    ip=json.loads(_read(Path(irradiance)/'last-experiment.json',8192));ir=Path(ip['path']);ie=original(ir/'experiment.json',1048576);solar=original(ir/'final-model.json',4*1024**2)
    if (ie['receipt_sha256']!=ip['receipt_sha256'] or ie['receipt_sha256']!=identity({k:v for k,v in ie.items() if k!='receipt_sha256'}) or
            ie['final_model_sha256']!=solar['model_sha256'] or solar['kind']!='irradiance_w_m2' or
            not ie['report']['candidate']['mae']<ie['report']['baseline']['mae'] or ie['report']['independent_target_days']<2):
        raise ValueError('original improved irradiance experiment required')
    for root,pin,model in ((Path(selected['experiment_path']).parent,te['datasets']['outdoor_temperature_c'],outside),(ir,ie['dataset_sha256'],solar)):
        guard();data=original(root/(pin+'.dataset.json'),1048576)
        for chunk in data['chunks']:
            path=root/(chunk['sha256']+'.pairs.json.gz');raw=_read(path,32*1024**2)
            refs[str(path)]=dict(path=str(path),sha256=sha256(raw).hexdigest(),maximum=32*1024**2,source=False)
        # Reproduction explicitly resolves a changed fitter source without
        # weakening any training-data/model identity or forging a fitted time.
        reproduce(model,training_pairs(root,pin));guard()
    horizon=Path(horizon).resolve();horizon_raw=horizon.read_bytes();profile=json.loads(horizon_raw)['profile']
    refs[str(horizon)]=dict(path=str(horizon),sha256=sha256(horizon_raw).hexdigest(),maximum=65536,source=True)
    # Mutable pointers are not as-issued original sources.
    refs.pop(str((Path(comparison)/'last-comparison.json').resolve()))
    value=dict(schema='earthship-thermal-weather-admission/v1',admitted_at=now.isoformat(),
        expires_at=min(instant(m['trained_at'])+timedelta(days=14) for m in (outside,solar)).isoformat(),
        models={m['kind']:capsule(m) for m in (outside,solar)},source_sensor_epoch=epoch,horizon_profile=profile,originals=list(refs.values()),runtime_manifest=runtime,
        source_experiments=dict(comparison=decision['receipt_sha256'],outdoor=te['receipt_sha256'],irradiance=ie['receipt_sha256'],
            cold_validator_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),original_fit_reproduced=True),physical_calibration_qualified=False,automatic_actuation=False)
    value['admission_sha256']=identity(value);validate_admission(value,issue=now)
    for ref in value['originals']:hash_reference(ref,guard=guard)
    if runtime!=conditioning_runtime() or sel!=json.loads(_read(outdoor_selection,16384)) or ip!=json.loads(_read(Path(irradiance)/'last-experiment.json',8192)):raise ValueError('thermal sources changed during admission')
    path=directory(Path(output)/'admissions')/(value['admission_sha256']+'.json');save(path,value)
    chosen=dict(schema='earthship-thermal-weather-selection/v1',admission_path=str(path),admission_file_sha256=sha256(_read(path,32768)).hexdigest(),available_at=clock().isoformat(),automatic_actuation=False)
    chosen['selection_sha256']=identity(chosen);directory(Path(selection).parent);save(selection,chosen)
    return dict(status='thermal_weather_admitted',admission_sha256=value['admission_sha256'],models={k:v['model_sha256'] for k,v in value['models'].items()},expires_at=value['expires_at'],automatic_actuation=False)


def main(argv=None):
    base=Path.home()/'.local/state/earthship-weather';p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdoor-selection',type=Path,default=base/'shadow/google-local-v2/historical-outdoor.json')
    p.add_argument('--irradiance',type=Path,default=base/'irradiance-calibration');p.add_argument('--comparison',type=Path,default=base/'thermal-conditioning-comparison')
    p.add_argument('--output',type=Path,default=base/'thermal-weather');p.add_argument('--selection',type=Path,default=Path.home()/'.config/earthship-weather/thermal-weather-selection.json')
    p.add_argument('--horizon',type=Path,default=Path(__file__).resolve().parents[1]/'household-solar-horizon.json');a=p.parse_args(argv);os.umask(0o077)
    from household_cycle_pressure import PublicationHeadroom
    pressure=PublicationHeadroom();began=time.monotonic()
    def guard():
        pressure.check()
        if time.monotonic()-began>150:raise TimeoutError('bounded thermal admission deadline elapsed')
    try:print(json.dumps(admit(**vars(a),guard=guard)),flush=True);return 0
    except (OSError,ValueError,KeyError,TimeoutError) as e:
        print(json.dumps(dict(status='thermal_weather_admission_incomplete',reason=type(e).__name__,message=str(e),automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
