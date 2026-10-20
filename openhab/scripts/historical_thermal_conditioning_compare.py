#!/usr/bin/env python3
"""Compare thermal corrections and generic indoor regression on retained outcomes."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from io import BytesIO
import argparse,gzip,json,os,time
from household_native_training import directory,save
from weather_source_files import _read
from weather_learning.contracts import identity,instant,canonical
from weather_learning.site_calibration import _model,_calculate
from weather_learning.thermal_comparison import google_forcings,summarize,ACTIONS
from weather_learning.thermal_conditioning_comparison import correct_outdoor_hours,select_balanced
from weather_learning.irradiance_learning import correct_forcing_hours
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.worker import collector_lock
from historical_thermal_compare import load_development,load_fits


def document(path,maximum,field):
    raw=_read(path,maximum);value=json.loads(raw)
    if value[field]!=identity({k:v for k,v in value.items() if k!=field}):raise ValueError('original comparison document differs')
    return value,sha256(raw).hexdigest()


def training_pairs(root,pin):
    data,_=document(Path(root)/(pin+'.dataset.json'),1048576,'dataset_sha256')
    if data['dataset_sha256']!=pin:raise ValueError('original model training dataset differs')
    rows=[]
    for chunk in data['chunks']:
        with gzip.GzipFile(fileobj=BytesIO(_read(Path(root)/(chunk['sha256']+'.pairs.json.gz'),32*1024**2))) as f:raw=f.read(32*1024**2+1)
        if len(raw)>32*1024**2:raise ValueError('bounded original model pairs required')
        value=json.loads(raw)
        if value['chunk_sha256']!=chunk['sha256'] or value['chunk_sha256']!=identity({k:v for k,v in value.items() if k!='chunk_sha256'}) or len(value['pairs'])!=chunk['pair_count']:raise ValueError('original model pair chunk differs')
        rows+=value['pairs']
    if len(rows)!=data['pair_count'] or len(rows)>50000:raise ValueError('complete bounded original pairs required')
    return rows


def run(a):
    from weather_learning.archive import Archive
    from weather_learning.historical import verify_history
    from native_irradiance_shade import NativeIrradianceShadeDynamics
    from household_cycle_pressure import PublicationHeadroom
    root=Path(__file__).resolve().parents[2];sources=capture_sources(root);pressure=PublicationHeadroom();began=time.monotonic()
    def guard():
        pressure.check()
        if time.monotonic()-began>550:raise TimeoutError('thermal conditioning comparison deadline elapsed')
    output=directory(a.output)
    with collector_lock(output/'comparison.lock'):
        pointer=json.loads(_read(a.comparison/'last-comparison.json',8192));parent=Path(pointer['path']);old,old_file=document(parent/'comparison.json',1048576,'receipt_sha256');dataset,_=document(parent/'dataset.json',4194304,'dataset_sha256')
        if old['receipt_sha256']!=pointer['receipt_sha256'] or dataset['dataset_sha256']!=old['dataset_sha256']:raise ValueError('original matched outcome set differs')
        data,originals,_=load_development(a.stage)
        if originals!=dataset['measurement_originals']:raise ValueError('same original physical outcomes required')
        models={v['receipt_sha256']:v for v in load_fits(a.fit_index,data.geometry)};samples={instant(r['at']):r for r in data.to_dict()['samples']}
        ip=json.loads(_read(a.irradiance/'last-experiment.json',8192));ir=Path(ip['path']);ie,_=document(ir/'experiment.json',1048576,'receipt_sha256');ghi=_model(json.loads(_read(ir/'training-model.json',4194304)))
        if ie['receipt_sha256']!=dataset['irradiance_context']['experiment_sha256'] or ghi['model_sha256']!=dataset['irradiance_context']['model_sha256']:raise ValueError('same original irradiance comparison model required')
        tp=json.loads(_read(a.temperature/'last-experiment.json',8192));tr=Path(tp['path']);te,_=document(tr/'experiment.json',1048576,'receipt_sha256');temperature={}
        for kind in ('outdoor_temperature_c','indoor_temperature_c','wall_temperature_c'):
            pin=te['reports'][kind]['model_sha256'];model=_model(json.loads(_read(tr/(pin+'.training-model.json'),4194304)))
            if model['model_sha256']!=pin:raise ValueError('original earlier temperature model differs')
            temperature[kind]=model
        direct=training_pairs(tr,te['datasets']['indoor_temperature_c']);direct_map={(r['forecast_sha256'],r['origin'],r['target_at']):r for r in direct}
        positions={r['at']:r for cache in data.geometry.to_dict()['caches'] for r in cache['positions']};horizon_raw=(root/'openhab/household-solar-horizon.json').read_bytes();horizon=json.loads(horizon_raw)['profile']
        if sha256(horizon_raw).hexdigest()!=dataset['irradiance_context']['horizon_sha256']:raise ValueError('original irradiance terrain declaration differs')
        archive=Archive.open_readonly(str(a.archive));rows=[];groups={}
        for row in dataset['pairs']:groups.setdefault(row['origin'],[]).append(row)
        direct_missing=direct_target_mismatch=0
        for issue,original_rows in sorted(groups.items()):
            guard();origin=instant(issue);initial=samples[origin];ref=original_rows[0]['forecast_sha256'];snapshot=verify_history(archive.read(ref));hours={}
            for p in snapshot['points']:
                if p['statistic']=='mean':hours.setdefault(p['valid_at'],{})[p['variable']]=p['value']
            actions={k:initial[k] for k in ACTIONS};fit=models[original_rows[0]['fit_receipts']['six_hourly_physics']]
            if any(r['fit_receipts']['six_hourly_physics']!=fit['receipt_sha256'] for r in original_rows):raise ValueError('one original physical fit per origin required')
            outdoor=correct_outdoor_hours(hours,model=temperature['outdoor_temperature_c'],origin=origin,outdoor_c=(initial['outdoor_f']-32)*5/9,timezone_name=snapshot['site']['timezone'],horizon_hours=24)
            irradiation=correct_forcing_hours(hours,model=ghi,origin=origin,positions=positions,horizon_profile=horizon,horizon_hours=24)
            both=correct_forcing_hours(outdoor,model=ghi,origin=origin,positions=positions,horizon_profile=horizon,horizon_hours=24)
            model=NativeIrradianceShadeDynamics(tuple(fit['fit']['coefficients']),geometry=data.geometry,expected_series_sha256=data.geometry.sha256)
            predicted={}
            for name,forcing_hours in [('replay_original_irradiance',irradiation),('six_hourly_local_outdoor',outdoor),('six_hourly_local_outdoor_and_irradiance',both)]:
                forcings=google_forcings(forcing_hours,origin=origin,actions=actions,horizon_hours=24)
                predicted[name]=model.rollout(origin_at=origin,air_f=initial['air_f'],mass_f=initial['mass_f'],forcings=forcings,guard=guard).states
            for old_row in original_rows:
                row=json.loads(canonical(old_row));index=row['lead_hours']*12-1
                if any(abs(a-b)>1e-10 for a,b in zip(predicted['replay_original_irradiance'][index],old_row['predictions']['six_hourly_local_irradiance'])):raise ValueError('original irradiance rollout numerical parity differs')
                for name in ('six_hourly_local_outdoor','six_hourly_local_outdoor_and_irradiance'):row['predictions'][name]=list(predicted[name][index])
                key=(ref,issue,row['target_at']);paired=direct_map.get(key);generic=temperature['indoor_temperature_c'];prediction=None
                if paired is None:direct_missing+=1
                elif abs(paired['outcome']*9/5+32-row['actual'][0])>1e-8:direct_target_mismatch+=1
                elif instant(generic['cutoff'])+timedelta(minutes=10)<=origin:
                    predicted_air=_calculate(generic,paired['features'],paired['baseline'])*9/5+32
                    prediction=[predicted_air,row['predictions']['six_hourly_physics'][1]]
                row['predictions']['generic_air_with_physics_mass']=prediction
                row.pop('pair_sha256');row['pair_sha256']=identity(row);rows.append(row)
        if len(rows)!=len(dataset['pairs']):raise ValueError('all original thermal outcomes required')
        selected=select_balanced(rows);metrics=summarize(rows);now=datetime.now(timezone.utc);run=directory(output/('comparison-'+now.strftime('%Y%m%dT%H%M%S%fZ')))
        result_data=dict(schema='earthship-thermal-conditioning-comparison-data/v1',pairs=rows,parent_dataset_sha256=dataset['dataset_sha256'],physical_measurement_originals=originals,
            earlier_temperature_model_sha256s={k:v['model_sha256'] for k,v in temperature.items()},actual_temperature_model_training_clocks={k:v['trained_at'] for k,v in temperature.items()},irradiance_context=dataset['irradiance_context'],
            generic_air_missing_pairs=direct_missing,generic_air_different_truth_pairs=direct_target_mismatch,mass_semantics='existing_physical_latent_observer_state; generic_air_only_preserves_physical_mass',
            readiness_basis='retrospective_assumed_cutoff_plus_10_minutes_actual_training_clocks_unchanged',prospective_score=False,automatic_actuation=False)
        result_data['dataset_sha256']=identity(result_data);save(run/'dataset.json',result_data);verify_sources(root,sources);manifest=retain_sources(run,sources)
        result=dict(schema='earthship-thermal-conditioning-comparison/v1',created_at=now.isoformat(),dataset_sha256=result_data['dataset_sha256'],parent_comparison_sha256=old['receipt_sha256'],parent_comparison_file_sha256=old_file,
            temperature_experiment_sha256=te['receipt_sha256'],irradiance_experiment_sha256=ie['receipt_sha256'],selection=selected,report=metrics,runtime_manifest=manifest,production_model_changed=False,automatic_actuation=False)
        result['receipt_sha256']=identity(result);save(run/'comparison.json',result);save(output/'last-comparison.json',dict(path=str(run),receipt_sha256=result['receipt_sha256']))
        return dict(status='thermal_conditioning_compared',receipt_sha256=result['receipt_sha256'],selection=selected,direct_missing=direct_missing,direct_target_mismatch=direct_target_mismatch,production_model_changed=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('comparison','stage','fit-index','archive','irradiance','temperature','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();os.umask(0o077);print(json.dumps(run(a)))

if __name__=='__main__':main()
