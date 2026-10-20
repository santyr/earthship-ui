#!/usr/bin/env python3
"""Compare earlier-only recent/augmented PV fits on identical later receipts."""
from pathlib import Path
from datetime import datetime,timedelta,timezone,date,time as daytime
from zoneinfo import ZoneInfo
from hashlib import sha256
from bisect import bisect_left
from io import BytesIO
import argparse,gzip,json,os,time
from household_native_training import directory,save
from weather_source_files import _read
from weather_learning.contracts import canonical,identity,instant,finite
from weather_learning.pv_legacy_history import day_labels
from weather_learning.pv_directional_calibration import fit_directional,assess_directional
from weather_learning.pv_horizon_assessment import assess_policy
from weather_learning.pv_training_sources import weather_runs
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.worker import collector_lock


def target_geometry(root,*,points,site,runtime,libraries,guard,clock,capture=None):
    import astro_geometry as geometry
    from astro_geometry_series import build_series_request,split_series_request,build_series,replay_series
    from astro_geometry_worker import capture_batch
    from household_cycle_resources import publication_geometry_policy
    root=directory(root);capture=capture or capture_batch
    key=identity(dict(points=[at.isoformat() for at in points],site=site.__dict__,native_runtime=runtime));path=root/(key+'.geometry.json')
    guard()
    if path.exists():
        raw=_read(path,4194304);value=json.loads(raw)
        request=build_series_request(points,requested_at=value['request']['requested_at'],latitude=site.latitude,longitude=site.longitude,timezone_name=site.timezone)
        return replay_series(raw,request=request,expected_series_sha256=value['series_sha256'],expected_native_runtime=runtime)
    request=build_series_request(points,requested_at=clock(),latitude=site.latitude,longitude=site.longitude,timezone_name=site.timezone);caches=[]
    for chunk in split_series_request(request):
        guard();source=geometry.build_source(chunk,observed_at=clock(),native_runtime=runtime,source_status='ONLINE',latitude=site.latitude,longitude=site.longitude,timezone_name=site.timezone,altitude_m=None)
        with publication_geometry_policy():caches.append(capture(chunk,source,library_paths=libraries,scratch=root,guard=guard,clock=clock))
    series=build_series(request,caches,expected_native_runtime=runtime);save(path,series.to_dict());return series


def _document(path,maximum,pin_field):
    raw=_read(path,maximum);value=json.loads(raw)
    if value[pin_field]!=identity({k:v for k,v in value.items() if k!=pin_field}):raise ValueError('original document identity differs')
    return value,sha256(raw).hexdigest()


def _dataset(path,expected):
    raw=_read(path,32*1024**2)
    with gzip.GzipFile(fileobj=BytesIO(raw)) as f:body=f.read(32*1024**2+1)
    if len(body)>32*1024**2:raise ValueError('bounded original PV pairs required')
    data=json.loads(body)
    if data['dataset_sha256']!=expected or data['dataset_sha256']!=identity({k:v for k,v in data.items() if k!='dataset_sha256'}):raise ValueError('original PV paired data differ')
    return data,sha256(raw).hexdigest()


def pair_older(labels,*,runs,positions,array,horizon):
    from household_pv_model import array_power,ASSUMPTIONS
    from household_solar_horizon import horizon_height
    origins=[row[0] for row in runs];pairs=[];missing=0
    for label in labels:
        start,end=instant(label['start']),instant(label['end']);i=bisect_left(origins,start)-1
        if i<0:missing+=1;continue
        origin,pin,hours,basis=runs[i];lead=(end-origin).total_seconds()/3600
        hour=end.replace(minute=0,second=0,microsecond=0)
        if hour<end:hour+=timedelta(hours=1)
        weather=hours.get(hour.isoformat(),{});position=positions.get(end.isoformat());ghi=weather.get('surface_solar_radiation_downwards_1hr');temp=weather.get('station_head_temperature_2m');wind=weather.get('wind_speed_10m')
        if not 0<lead<=48 or position is None or not finite(ghi) or not finite(temp):missing+=1;continue
        az=position['azimuth_degrees'];terrain=horizon_height(horizon,az)
        baseline=array_power(array=array,assumptions=ASSUMPTIONS,ghi_wm2=ghi,elevation_degrees=position['elevation_degrees'],azimuth_degrees=az,
            day_of_year=end.timetuple().tm_yday,temp_f=temp*9/5+32,wind_mph=None if wind is None else wind*2.2369362921,horizon_elevation_degrees=terrain)['potential_dc_w']
        row=dict(start=label['start'],end=label['end'],origin=origin.isoformat(),baseline_w=baseline,outcome_w=label['outcome_w'],azimuth_degrees=az,lead_hours=lead,
            forecast_sha256=pin,energy_source_sha256=label['source_sha256'],potential_proxy_eligible=True,availability_basis=basis,
            elevation_degrees=position['elevation_degrees'],horizon_elevation_degrees=terrain,measurement_health_qualified=False,
            censoring_basis=label['censoring_basis'],positive_charge_basis=label['positive_charge_basis'],label_duration_seconds=(end-start).total_seconds())
        row['pair_sha256']=identity(row);pairs.append(row)
    return pairs,missing


def read_bank_epochs(path):
    from household_snapshot import _read as read_public_configuration
    raw=read_public_configuration(path,16384);value=json.loads(raw);current=[e for e in value['epochs'] if e['current_analytics']]
    if len(current)!=1:raise ValueError('unique current physical bank required')
    start=datetime.combine(date.fromisoformat(current[0]['start_local_date']),daytime.min,ZoneInfo(value['timezone'])).astimezone(timezone.utc)
    return raw,start


def source_basis():
    base=Path.home()/'.local/state/earthship-weather'
    pv,pv_file=_document(base/'legacy-pv-probe/unit-overlap.json',16384,'result_sha256')
    soc,soc_file=_document(base/'legacy-pv-more-probe/unit-overlap.json',16384,'result_sha256')
    mapper,mapper_file=_document(base/'legacy-pv-probe/mppt60_native_status_mapper.json',131072,'source_sha256')
    import re
    code='\n'.join(action.get('configuration',{}).get('script','') for action in mapper['rule']['actions'])
    if pv['pairs']<3 or pv['mae_w_by_scale']['1.0']>2 or soc['pairs']<3 or soc['mae_pct_by_scale']['1.0']>1 or not re.search(r'case\s+"769"\s*:\s*label\s*=\s*"Bulk"',code):
        raise ValueError('source-bound historical PV/SoC units and native Bulk mapping required')
    return dict(pv_unit_proof=pv,pv_unit_file_sha256=pv_file,soc_unit_proof=soc,soc_unit_file_sha256=soc_file,
        charge_mapping_source_sha256=mapper['source_sha256'],charge_mapping_file_sha256=mapper_file,bulk_code=769,
        mapping_scope='retained_current_rule_not_independently_verified_historical_hardware_identity',measurement_health_qualified=False)


def run(a):
    from weather_learning.config import Site
    from weather_learning.openhab import oh_get,I18N_CONFIG_PATH
    from household_native_geometry_prepare import _library_paths
    from astro_geometry_worker import runtime_identity
    from household_cycle_pressure import PublicationHeadroom
    root=Path(__file__).resolve().parents[2];sources=capture_sources(root);pressure=PublicationHeadroom();began=time.monotonic()
    import earthship_energy.bms_evidence as bms
    companion_path=Path(bms.__file__);companion_raw=companion_path.read_bytes()
    epochs_raw,bank_start=read_bank_epochs('/home/sat/Solar_PV/analytics/config/system-epochs.json');units=source_basis()
    def guard():
        pressure.check()
        if time.monotonic()-began>550:raise TimeoutError('legacy PV assessment deadline elapsed')
    output=directory(a.output)
    with collector_lock(output/'assessment.lock'):
        source_index,source_index_file=_document(a.legacy/'index.json',1048576,'index_sha256');labels=[];by_date={}
        for day,entry in sorted(source_index['dates'].items()):
            guard();all_rows=day_labels(a.legacy,day,entry,bank_start=bank_start);eligible=[r for r in all_rows if r['potential_proxy_eligible']];labels+=eligible
            by_date[day]=dict(total_minutes=len(all_rows),eligible_minutes=len(eligible),soc_receipt_minutes=sum(r.get('soc_measurement_health_qualified',False) for r in eligible))
        if not labels:raise ValueError('supported older electrical labels required')
        pointer=json.loads(_read(a.horizon/'last-experiment.json',8192));parent=Path(pointer['path']);experiment,_=_document(parent/'experiment.json',1048576,'receipt_sha256')
        if experiment['receipt_sha256']!=pointer['receipt_sha256']:raise ValueError('original horizon experiment differs')
        tests,test_file=_dataset(parent/(experiment['dataset_sha256']+'.pairs.json.gz'),experiment['dataset_sha256'])
        recent_root=Path(experiment['parent_experiment_path']);recent_exp,_=_document(recent_root/'experiment.json',1048576,'receipt_sha256')
        if recent_exp['receipt_sha256']!=experiment['parent_experiment_sha256']:raise ValueError('original recent experiment differs')
        recent,recent_file=_dataset(recent_root/(recent_exp['dataset_sha256']+'.pairs.json.gz'),recent_exp['dataset_sha256'])
        system_raw=(root/'openhab/household-pv-system.json').read_bytes();horizon_raw=(root/'openhab/household-solar-horizon.json').read_bytes()
        if recent['system_raw'].encode()!=system_raw or recent['horizon_raw'].encode()!=horizon_raw:raise ValueError('original array/terrain declarations changed')
        site=Site.from_openhab_config(oh_get(I18N_CONFIG_PATH));library_raw=_read(a.libraries,8192);libraries=_library_paths(library_raw);binding=oh_get('/addons/binding-astro')['version'];runtime=runtime_identity(libraries,binding_version=binding,guard=guard)
        points=sorted({instant(r['end']) for r in labels});geometry=target_geometry(directory(a.legacy/'geometry'),points=points,site=site,runtime=runtime,libraries=libraries,guard=guard,clock=lambda:datetime.now(timezone.utc))
        positions={r['at']:r for cache in geometry.to_dict()['caches'] for r in cache['positions']}
        runs=weather_runs(a.archive,None,floor=min(instant(r['start']) for r in labels)-timedelta(hours=48),end=max(instant(r['end']) for r in labels)+timedelta(minutes=1),site=site.__dict__,guard=guard)
        older,missing=pair_older(labels,runs=runs,positions=positions,array=json.loads(system_raw)['array'],horizon=json.loads(horizon_raw)['profile'])
        if not older:raise ValueError('historical Google overlap required')
        now=datetime.now(timezone.utc);cutoff=instant(experiment['report']['holdout_start']);end=instant(experiment['report']['holdout_end'])
        earlier=fit_directional(recent['pairs'],cutoff=cutoff,trained_at=now);augmented=fit_directional(recent['pairs']+older,cutoff=cutoff,trained_at=now)
        base_report=assess_policy(earlier,tests['pairs'],cutoff=cutoff,end=end);augmented_report=assess_policy(augmented,tests['pairs'],cutoff=cutoff,end=end)
        selected=augmented_report['aggregate']['pairs']>=24 and augmented_report['aggregate']['independent_target_days']>=2 and augmented_report['aggregate']['policy_mae_w']<base_report['aggregate']['policy_mae_w']
        run=directory(output/('experiment-'+now.strftime('%Y%m%dT%H%M%S%fZ')))
        dataset=dict(schema='earthship-pv-legacy-augmented-pairs/v1',older_pairs=older,legacy_source_index_sha256=source_index['index_sha256'],recent_dataset_sha256=recent['dataset_sha256'],holdout_dataset_sha256=tests['dataset_sha256'],geometry_series=geometry.to_dict(),geometry_sha256=geometry.sha256,
            system_raw=system_raw.decode(),horizon_raw=horizon_raw.decode(),bank_epochs_raw=epochs_raw.decode(),bank_start=bank_start.isoformat(),unit_and_mapping_basis=units,by_date=by_date,missing_forecast_pairs=missing,geometry_basis='current_operator_array_and_terrain_declarations_assumed_constant_retrospectively',source_quality='older_numeric_controller_input_with_recent_SoC_rise_and_assumed_held_Bulk_episode',
            measurement_health_qualified=False,physical_calibration_qualified=False,prospective_score=False,automatic_actuation=False)
        dataset['dataset_sha256']=identity(dataset);save(run/'dataset.json',dataset);save(run/'recent-training-model.json',earlier);save(run/'augmented-training-model.json',augmented)
        verify_sources(root,sources);manifest=retain_sources(run,sources)
        if companion_path.read_bytes()!=companion_raw:raise ValueError('battery decoder changed during historical assessment')
        companion_target=run/'sources/companion/earthship_energy/bms_evidence.py';companion_target.parent.mkdir(parents=True,mode=0o700);companion_target.write_bytes(companion_raw);companion_target.chmod(0o600);manifest['companion/earthship_energy/bms_evidence.py']=sha256(companion_raw).hexdigest()
        report=dict(schema='earthship-pv-legacy-augmentation-comparison/v1',recent_only=base_report,augmented=augmented_report,selected=selected,
            selection_basis='lower_matched_heldout_policy_MAE_over_all_retained_lead_groups',one_minute_legacy_pairs=len(older),five_minute_recent_pairs=len(recent['pairs']),
            limitation='mixed_interval_lengths_and_unknown_older_meter_health_development_comparison_not_independent_or_metrology',physical_calibration_qualified=False,prospective_score=False,automatic_actuation=False)
        report['report_sha256']=identity(report)
        if sha256(_read(a.legacy/'index.json',1048576)).hexdigest()!=source_index_file or read_bank_epochs('/home/sat/Solar_PV/analytics/config/system-epochs.json')[0]!=epochs_raw or source_basis()!=units or runtime_identity(libraries,binding_version=binding,guard=guard)!=runtime:raise ValueError('legacy assessment context changed')
        result=dict(schema='earthship-pv-legacy-augmentation-experiment/v1',created_at=now.isoformat(),dataset_sha256=dataset['dataset_sha256'],legacy_source_index_file_sha256=source_index_file,recent_dataset_file_sha256=recent_file,holdout_dataset_file_sha256=test_file,
            parent_horizon_receipt_sha256=experiment['receipt_sha256'],report=report,runtime_manifest=manifest,production_model_changed=False,automatic_actuation=False)
        result['receipt_sha256']=identity(result);save(run/'experiment.json',result);save(output/'last-experiment.json',dict(path=str(run),receipt_sha256=result['receipt_sha256']))
        return dict(status='legacy_pv_augmentation_assessed',receipt_sha256=result['receipt_sha256'],legacy_pairs=len(older),by_date=by_date,selected=selected,recent_policy_mae_w=base_report['aggregate']['policy_mae_w'],augmented_policy_mae_w=augmented_report['aggregate']['policy_mae_w'],production_model_changed=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('legacy','archive','horizon','libraries','output'):p.add_argument('--'+key,required=True,type=Path)
    a=p.parse_args();os.umask(0o077);print(json.dumps(run(a)))

if __name__=='__main__':main()
