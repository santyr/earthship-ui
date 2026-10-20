#!/usr/bin/env python3
"""Fit effective PV response on earlier uncensored-proxy intervals; no activation."""
from bisect import bisect_left
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
from zoneinfo import ZoneInfo
import argparse,gzip,json,os,time
from household_native_training import directory,save
from weather_source_files import _read
from weather_learning.contracts import identity,instant,canonical,finite
from weather_learning.energy_history import summarize_hour
from weather_learning.pv_calibration import assess_gain
from weather_learning.pv_refresh import effective_if_changed,previous_models
from weather_learning.pv_training_sources import weather_runs
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.worker import collector_lock


def energy_bins(root,guard):
    root=Path(root);index_raw=_read(root/'energy-index.json',1048576);index=json.loads(index_raw)
    if index['index_sha256']!=identity({k:v for k,v in index.items() if k!='index_sha256'}):raise ValueError('energy index changed')
    if not 1<=len(index['hours'])<=2160:raise ValueError('bounded energy hours required')
    bins=[]
    for row in index['hours']:
        guard();path=root/'originals'/(instant(row['start']).strftime('%Y%m%dT%H')+'.energy.json.gz');raw=_read(path,8*1024**2)
        if sha256(raw).hexdigest()!=row['file_sha256']:raise ValueError('energy original bytes differ')
        with gzip.open(path,'rb') as stream:payload=stream.read(16*1024**2+1)
        if len(payload)>16*1024**2:raise ValueError('bounded original energy hour required')
        source=json.loads(payload)
        if source['source_sha256']!=row['source_sha256']:raise ValueError('energy original identity differs')
        rebuilt=summarize_hour(source);summary=json.loads(_read(root/'summaries'/(row['summary_sha256']+'.json'),65536))
        if summary['summary_sha256']!=row['summary_sha256'] or summary['summary_sha256']!=identity({k:v for k,v in summary.items() if k!='summary_sha256'}) or rebuilt!=summary['bins']:
            raise ValueError('energy summary differs from original receipt replay')
        bins.extend(rebuilt)
    if _read(root/'energy-index.json',1048576)!=index_raw:raise ValueError('energy index changed during training')
    return bins,index




def validate_pair_dataset(data,expected):
    """A new fit requires corrected baselines; legacy originals stay replayable."""
    from household_pv_model import INTERVAL_BASELINE_RULE
    if data.get('dataset_sha256')!=expected or expected!=identity({k:v for k,v in data.items() if k!='dataset_sha256'}):
        raise ValueError('original PV paired data differ')
    if (data.get('schema') not in ('earthship-historical-pv-calibration-data/v2','earthship-pv-horizon-data/v2') or
        data.get('baseline_rule')!=INTERVAL_BASELINE_RULE or
        any(row.get('baseline_rule')!=INTERVAL_BASELINE_RULE for row in data['pairs'])):
        raise ValueError('current shared PV baseline arithmetic required; rebuild original-bound pairs')
    return data


def pair_baseline(*,start,end,hours,position,array,horizon):
    """Convert original Google units once, then use served interval arithmetic."""
    from math import fsum
    from household_pv_model import interval_power_segments,ASSUMPTIONS
    floor=start.replace(minute=0,second=0,microsecond=0)
    ceiling=end.replace(minute=0,second=0,microsecond=0)
    if ceiling<end:ceiling+=timedelta(hours=1)
    rows=[];at=floor
    while at<=ceiling:
        weather=hours.get(at.isoformat(),{});temp=weather.get('station_head_temperature_2m');wind=weather.get('wind_speed_10m')
        rows.append(dict(at=at.isoformat(),radiationWm2=weather.get('surface_solar_radiation_downwards_1hr'),
            tempF=None if not finite(temp) else temp*9/5+32,windMph=None if wind is None else wind*(3600/1609.344)))
        at+=timedelta(hours=1)
    segments=interval_power_segments(array=array,assumptions=ASSUMPTIONS,hourly_forecast=rows,
        position=position,start=start,end=end,horizon_profile=horizon)
    return fsum(value['potential_dc_w']*(stop-at).total_seconds() for at,stop,ghi,value in segments)/(end-start).total_seconds()


def run(*,archive_path,energy_path,output_path,geometry_path,libraries_path,train_end,holdout_end,operational_archive_path=None):
    from weather_learning.config import Site
    from weather_learning.openhab import oh_get,I18N_CONFIG_PATH
    from daily_pv_worker import day_geometry
    from household_native_geometry_prepare import _library_paths
    from astro_geometry_worker import runtime_identity
    from household_pv_model import _array,INTERVAL_BASELINE_RULE
    from household_cycle_pressure import PublicationHeadroom
    started=time.monotonic();pressure=PublicationHeadroom();root=Path(__file__).resolve().parents[2];sources=capture_sources(root)
    def guard():
        pressure.check()
        if time.monotonic()-started>550:raise TimeoutError('historical PV training deadline elapsed')
    output=directory(output_path)
    with collector_lock(output/'training.lock'):
        site=Site.from_openhab_config(oh_get(I18N_CONFIG_PATH));zone=ZoneInfo(site.timezone)
        library_raw=_read(libraries_path,8192);libraries=_library_paths(library_raw)
        addon=oh_get('/addons/binding-astro');runtime=runtime_identity(libraries,binding_version=addon['version'],guard=guard)
        bins,index=energy_bins(energy_path,guard)
        eligible=[b for b in bins if b['potential_proxy_eligible'] and instant(b['end'])<holdout_end]
        if not eligible:raise ValueError('eligible original input-power intervals required')
        floor=min(instant(b['start']) for b in eligible)-timedelta(hours=48)
        runs=weather_runs(archive_path,operational_archive_path,floor=floor,end=holdout_end,site=site.__dict__,guard=guard)
        forecast_manifest=[r[1] for r in runs]
        origins=[r[0] for r in runs]
        geometries=[];positions={};geometry_root=directory(geometry_path)
        dates=sorted({instant(b['end']).astimezone(zone).date().isoformat() for b in eligible})
        with collector_lock(geometry_root/'historical-calibration.lock'):
            for day in dates:
                guard();value=day_geometry(geometry_root,day,site=site,native_runtime=runtime,libraries=libraries,guard=guard,clock=lambda:datetime.now(timezone.utc))
                geometries.append(value.sha256)
                for cache in value.to_dict()['caches']:
                    for row in cache['positions']:positions[row['at']]=row
        system_raw=(root/'openhab/household-pv-system.json').read_bytes();horizon_raw=(root/'openhab/household-solar-horizon.json').read_bytes()
        array=_array(json.loads(system_raw)['array']);horizon=json.loads(horizon_raw)['profile'];pairs=[]
        for b in eligible:
            guard();start,end=map(instant,(b['start'],b['end']));i=bisect_left(origins,start)-1
            if i<0:continue
            origin,ref,hours,basis=runs[i];lead=(end-origin).total_seconds()/3600
            if not 0<lead<=48:continue
            position=positions.get(end.isoformat())
            if position is None:continue
            try:baseline=pair_baseline(start=start,end=end,hours=hours,position=position,array=array,horizon=horizon)
            except (ValueError,KeyError,TypeError):continue
            observed=b['fields']['pv.input_power_w'];mean=observed['positive_kwh']*3600000/observed['covered_seconds']
            row=dict(start=b['start'],end=b['end'],origin=origin.isoformat(),baseline_w=baseline,outcome_w=mean,azimuth_degrees=position['azimuth_degrees'],lead_hours=lead,
                forecast_sha256=ref,energy_source_sha256=b['source_sha256'],potential_proxy_eligible=True,availability_basis=basis,baseline_rule=INTERVAL_BASELINE_RULE)
            row['pair_sha256']=identity(row);pairs.append(row)
        now=datetime.now(timezone.utc);previous=previous_models(output,sources)
        model,comparison_fit=effective_if_changed(previous.get('training_model'),pairs,cutoff=train_end,trained_at=now)
        report=assess_gain(model,pairs,holdout_start=train_end,holdout_end=holdout_end)
        final,serving_fit=effective_if_changed(previous.get('final_model'),pairs,cutoff=holdout_end,trained_at=now)
        run=directory(output/('experiment-'+now.strftime('%Y%m%dT%H%M%S%fZ')))
        dataset=dict(schema='earthship-historical-pv-calibration-data/v2',baseline_rule=INTERVAL_BASELINE_RULE,pairs=pairs,energy_index_sha256=index['index_sha256'],forecast_sha256s=forecast_manifest,
            geometry_series_sha256s=geometries,system_raw=system_raw.decode(),horizon_raw=horizon_raw.decode(),
            geometry_basis='current_operator_array_and_terrain_declarations_assumed_constant_retrospectively',availability_basis='mixed_explicit_per_pair' if operational_archive_path is not None else 'retrospective_assumed_full_cycle_9h',prospective_score=False,automatic_actuation=False)
        dataset['dataset_sha256']=identity(dataset)
        path=run/(dataset['dataset_sha256']+'.pairs.json.gz');path.write_bytes(gzip.compress(canonical(dataset),compresslevel=3,mtime=0));path.chmod(0o600)
        verify_sources(root,sources);runtime_manifest=retain_sources(run,sources)
        import earthship_energy.power_evidence as companion
        for name in ('power_evidence.py','power_intervals.py','bms_evidence.py','ac_evidence.py'):
            raw=(Path(companion.__file__).parent/name).read_bytes();path=run/'sources/companion/earthship_energy'/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);path.write_bytes(raw);path.chmod(0o600)
            runtime_manifest['companion/earthship_energy/'+name]=sha256(raw).hexdigest()
        save(run/'training-model.json',model);save(run/'final-model.json',final);save(run/'comparison.json',report)
        receipt=dict(schema='earthship-historical-pv-training/v1',created_at=now.isoformat(),dataset_sha256=dataset['dataset_sha256'],training_model_sha256=model['model_sha256'],final_model_sha256=final['model_sha256'],report=report,
            fit_executed=dict(comparison=comparison_fit,serving=serving_fit),energy_hours=len(index['hours']),eligible_bins=len(eligible),paired_bins=len(pairs),forecast_runs=len(runs),runtime_manifest=runtime_manifest,production_model_changed=False,automatic_actuation=False)
        receipt['receipt_sha256']=identity(receipt);save(run/'experiment.json',receipt);save(output/'last-experiment.json',dict(path=str(run),receipt_sha256=receipt['receipt_sha256']))
        guard();return receipt


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('archive','energy','output','geometry','libraries'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--operational-archive',type=Path);p.add_argument('--train-end',required=True);p.add_argument('--holdout-end',required=True);a=p.parse_args(argv);os.umask(0o077)
    try:
        result=run(archive_path=a.archive,energy_path=a.energy,output_path=a.output,geometry_path=a.geometry,libraries_path=a.libraries,train_end=instant(a.train_end),holdout_end=instant(a.holdout_end),operational_archive_path=a.operational_archive)
        print(json.dumps(dict(status='historical_pv_calibration_complete',energy_hours=result['energy_hours'],paired_bins=result['paired_bins'],report=result['report'],production_model_changed=False)),flush=True);return 0
    except Exception as error:
        import traceback
        directory(a.output);save(a.output/'last-error.json',dict(reason=type(error).__name__,message=str(error)[:2048],traceback=traceback.format_exc()[-8192:]))
        print(json.dumps(dict(status='historical_pv_calibration_incomplete',reason=type(error).__name__,production_model_changed=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
