#!/usr/bin/env python3
"""Publish a separate same-issue PV/storage scenario after original forecasts."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import argparse,json,os,time,traceback
from household_native_training import effective_selection,directory,save
from household_observation import _private_file
from weather_learning.worker import collector_lock
from household_calibrated_energy import seal,runtime_manifest,MAX_BYTES
from household_solar_score import read_forecast,unchanged
from household_profiled_score import read_forecast as read_profile,unchanged as profile_unchanged
from household.codec import canonical,loads,identity
from household.control_contracts import instant


def run(*,state,calibration,view,clock=lambda:datetime.now(timezone.utc)):
    from household_cycle_pressure import PublicationHeadroom
    from household_cycle_deploy import verify_stage
    state=directory(state);store=directory(state/'forecasts');deadline=time.monotonic()+80.;pressure=PublicationHeadroom()
    def guard():
        pressure.check()
        if time.monotonic()>deadline:raise TimeoutError('calibrated scenario deadline elapsed')
    with collector_lock(state/'worker.lock'):
        guard();selected=effective_selection();stage=Path(selected['stage']);verify_stage(stage,expected_deployment_sha256=selected['deployment_sha256']);manifest=runtime_manifest()
        paths=[];profiles=[]
        with os.scandir(stage/'evidence') as entries:
            for i,entry in enumerate(entries):
                guard()
                if i>=20000:raise ValueError('bounded original scenario inventory required')
                if not entry.is_file(follow_symlinks=False):continue
                if entry.name.endswith('.household-energy-forecast-v1.json'):paths.append(Path(entry.path))
                elif entry.name.endswith('.household-profiled-energy-v1.json'):profiles.append(Path(entry.path))
        if not paths:return dict(status='awaiting_original_energy_forecast',automatic_actuation=False)
        path=max(paths,key=lambda p:p.stat().st_mtime);energy,plan,original=read_forecast(path);origin=instant(energy['output']['array_pv']['origin']);now=clock()
        if not origin<=now<=origin+timedelta(seconds=120):return dict(status='awaiting_fresh_origin',latest_origin=origin.isoformat(),automatic_actuation=False)
        profiled=None;profile_original=None
        for p in sorted(profiles,key=lambda p:p.stat().st_mtime,reverse=True):
            value=loads(_private_file(p,262144)[0])
            if value['inputs']['original_energy_document_sha256']!=identity(energy):continue
            profiled,other_energy,other_plan,profile_original=read_profile(p)
            if canonical(other_energy)!=canonical(energy) or canonical(other_plan)!=canonical(plan):raise ValueError('same-issue original profile required')
            break
        raw_calibration=_private_file(calibration,262144)[0]
        result=seal(energy=energy,plan=plan,profiled=profiled,calibration_raw=raw_calibration,now=clock());guard();unchanged(original)
        if profile_original is not None:profile_unchanged(profile_original)
        if runtime_manifest()!=manifest or effective_selection()!=selected or _private_file(calibration,262144)[0]!=raw_calibration:raise ValueError('original scenario source changed')
        encoded=canonical(result);target=store/(sha256(encoded).hexdigest()+'.calibrated-energy-v1.json')
        try:fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:
            if _private_file(target,MAX_BYTES)[0]!=encoded:raise ValueError('original calibrated scenario changed')
        else:
            with os.fdopen(fd,'wb') as stream:stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        out=result['output'];storage=out['profiled_storage'];available=storage['status']=='conditional_nominal_simulation';generated=clock();until=origin+timedelta(minutes=15)
        if not origin<=generated<=origin+timedelta(seconds=120):raise ValueError('calibrated publication deadline elapsed')
        load=None if profiled is None else profiled['output']['load_forecast'];load_available=load is not None and load['status']=='projected'
        profile=None if profiled is None or profiled['inputs']['load_source'] is None else profiled['inputs']['load_source']['artifact']['profile']
        trajectory=[]
        if load_available:
            for i,row in enumerate(load['trajectory']):
                point=dict(at=row['at'],mean_ac_w=row['mean_ac_w'],minimum_support_days=row['minimum_support_days'],training_spread_ac_w=row['training_spread_mean_w'],
                    calibrated_soc_pct=None if not available else storage['trajectory'][i]['nominal_soc_pct'],raw_soc_pct=None if not available else out['uncalibrated_profiled_storage']['trajectory'][i]['nominal_soc_pct'])
                if available and (storage['trajectory'][i]['at']!=row['at'] or out['uncalibrated_profiled_storage']['trajectory'][i]['at']!=row['at']):raise ValueError('curated same-issue targets differ')
                trajectory.append(point)
        payload=dict(schema='earthship-household-calibrated-energy-observation/v2',generated_at=generated.isoformat(),issued_at=origin.isoformat(),valid_until=until.isoformat(),receipt_sha256=result['receipt_sha256'],
            original_energy_receipt_sha256=energy['receipt_sha256'],calibration_model_sha256=json.loads(raw_calibration)['final_model']['model_sha256'],
            status=out['status'],reason=out['reason'],load_status='projected' if load_available else 'unavailable',
            load_model_sha256=None if not load_available else profile['model_sha256'],load_trained_through=None if not load_available else profile['latest_qualified_hour_end'],
            load_training_cutoff=None if not load_available else profiled['inputs']['load_source']['artifact']['cutoff'],load_total_ac_kwh=None if not load_available else load['total_ac_kwh'],
            raw_potential_kwh=out['raw_potential_kwh'],calibrated_potential_kwh=out['calibrated_potential_kwh'],
            profiled_storage_status=storage['status'],profiled_storage_reason=storage['reason'],
            profiled_captured_pv_kwh=None if not available else storage['modeled_captured_pv_kwh'],
            raw_profiled_captured_pv_kwh=None if not available else out['uncalibrated_profiled_storage']['modeled_captured_pv_kwh'],
            initial_soc_pct=None if not available else storage['initial_soc_pct'],nominal_bank_kwh=None if not available else storage['nominal_bank_kwh'],
            trajectory=trajectory,source_freshness_basis=result['inputs']['source_freshness_basis'],
            confidence='provisional_empirical_short_horizon',physical_calibration_qualified=False,automatic_actuation=False)
        payload['view_sha256']=identity(payload);directory(Path(view).parent);guard()
        try:previous=loads(_private_file(view,32768)[0])
        except FileNotFoundError:previous=None
        if previous is not None and previous.get('schema') not in ('earthship-household-calibrated-energy-observation/v1',payload['schema']):raise ValueError('calibrated view belongs to another producer')
        save(view,payload)
        return dict(status='calibrated_energy_published',issued_at=origin.isoformat(),profiled_storage_status=storage['status'],receipt_sha256=result['receipt_sha256'],automatic_actuation=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,default=Path.home()/'.local/state/household-intel/calibrated-energy');p.add_argument('--calibration',type=Path,default=Path.home()/'.local/state/earthship-weather/pv-calibration/selected-directional.json');p.add_argument('--view',type=Path,default=Path.home()/'.local/state/household-intel/calibrated-energy-observation.json');a=p.parse_args(argv);os.umask(0o077)
    try:
        result=run(state=a.state,calibration=a.calibration,view=a.view);save(a.state/'last-result.json',dict(result,checked_at=datetime.now(timezone.utc).isoformat()));print(json.dumps(result),flush=True);return 0
    except Exception as error:
        directory(a.state);save(a.state/'last-error.json',dict(reason=type(error).__name__,traceback=traceback.format_exc()[-8192:]));print(json.dumps(dict(status='calibrated_energy_unavailable',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
