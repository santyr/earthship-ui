#!/usr/bin/env python3
"""Assess PV lead/terrain support using original paired electrical observations."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from zoneinfo import ZoneInfo
from io import BytesIO
import argparse,gzip,json,os,time
from household_native_training import directory,save
from weather_source_files import _read
from weather_learning.contracts import identity,instant,canonical,finite
from weather_learning.archive import Archive
from weather_learning.historical import verify_history
from weather_learning.pv_training_sources import forecast_origin,ordered_runs
from weather_learning.pv_directional_calibration import fit_directional
from weather_learning.pv_horizon_assessment import assess_horizons,BANDS
from weather_learning.pv_calibration import _pair
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.worker import collector_lock
from historical_pv_train import pair_baseline,validate_pair_dataset
from household_pv_model import INTERVAL_BASELINE_RULE


def expand_horizon_pairs(pairs,*,runs,positions,array,horizon,guard=lambda:None):
    """Pure expansion of source-bound forecast pairs across declared lead bands."""
    from household_solar_horizon import horizon_height
    runs=ordered_runs(runs);expanded=[]
    for original in pairs:
        guard();start,end=instant(original['start']),instant(original['end']);position=positions[end.isoformat()];az=position['azimuth_degrees'];terrain=horizon_height(horizon,az)
        for lo,hi in BANDS:
            choices=[r for r in runs if r[0]<start and lo<(end-r[0]).total_seconds()/3600<=hi]
            if not choices:continue
            origin,pin,hours,basis=max(choices,key=lambda r:r[0])
            try:baseline=pair_baseline(start=start,end=end,hours=hours,position=position,array=array,horizon=horizon)
            except (ValueError,KeyError,TypeError):continue
            if lo==0 and (pin!=original['forecast_sha256'] or abs(baseline-original['baseline_w'])>1e-7):raise ValueError('original near-term physics pairing differs')
            row={k:v for k,v in original.items() if k!='pair_sha256'};row.update(origin=origin.isoformat(),baseline_w=baseline,baseline_rule=INTERVAL_BASELINE_RULE,lead_hours=(end-origin).total_seconds()/3600,forecast_sha256=pin,availability_basis=basis,elevation_degrees=position['elevation_degrees'],horizon_elevation_degrees=terrain)
            row['pair_sha256']=identity(row);expanded.append(row)
    return expanded


def run(a):
    from weather_learning.config import Site
    from weather_learning.openhab import oh_get,I18N_CONFIG_PATH
    from daily_pv_worker import day_geometry
    from household_native_geometry_prepare import _library_paths
    from astro_geometry_worker import runtime_identity
    from household_pv_model import _array
    from household_solar_horizon import horizon_height
    from household_cycle_pressure import PublicationHeadroom
    root=Path(__file__).resolve().parents[2];sources=capture_sources(root);began=time.monotonic();pressure=PublicationHeadroom()
    def guard():
        pressure.check()
        if time.monotonic()-began>550:raise TimeoutError('PV horizon assessment deadline elapsed')
    output=directory(a.output)
    with collector_lock(output/'assessment.lock'):
        pointer=json.loads(_read(a.calibration/'last-experiment.json',8192));parent=Path(pointer['path']);experiment=json.loads(_read(parent/'experiment.json',1048576))
        if experiment['receipt_sha256']!=pointer['receipt_sha256'] or experiment['receipt_sha256']!=identity({k:v for k,v in experiment.items() if k!='receipt_sha256'}):raise ValueError('original PV experiment differs')
        with gzip.open(parent/(experiment['dataset_sha256']+'.pairs.json.gz'),'rb') as handle:raw=handle.read(32*1024**2+1)
        if len(raw)>32*1024**2:raise ValueError('bounded original PV paired data required')
        dataset=json.loads(raw)
        validate_pair_dataset(dataset,experiment['dataset_sha256'])
        # Check original electrical file bytes and summary identities, without
        # reparsing the same electrical streams already sealed by the fitter.
        index_raw=_read(a.energy/'energy-index.json',1048576);index=json.loads(index_raw)
        if index['index_sha256']!=dataset['energy_index_sha256'] or index['index_sha256']!=identity({k:v for k,v in index.items() if k!='index_sha256'}):raise ValueError('original energy index differs')
        for row in index['hours']:
            guard();path=a.energy/'originals'/(instant(row['start']).strftime('%Y%m%dT%H')+'.energy.json.gz')
            if sha256(_read(path,8*1024**2)).hexdigest()!=row['file_sha256']:raise ValueError('original energy bytes changed')
            summary=json.loads(_read(a.energy/'summaries'/(row['summary_sha256']+'.json'),65536))
            if summary['summary_sha256']!=row['summary_sha256'] or summary['summary_sha256']!=identity({k:v for k,v in summary.items() if k!='summary_sha256'}):raise ValueError('original qualified summary differs')
        pairs=[_pair(r) for r in dataset['pairs']];site=Site.from_openhab_config(oh_get(I18N_CONFIG_PATH));zone=ZoneInfo(site.timezone)
        library_raw=_read(a.libraries,8192);libraries=_library_paths(library_raw);binding=oh_get('/addons/binding-astro')['version'];runtime=runtime_identity(libraries,binding_version=binding,guard=guard)
        positions={};geometry_pins=[]
        for day in sorted({instant(p['end']).astimezone(zone).date().isoformat() for p in pairs}):
            guard();geometry=day_geometry(a.geometry,day,site=site,native_runtime=runtime,libraries=libraries,guard=guard,clock=lambda:datetime.now(timezone.utc));geometry_pins.append(geometry.sha256)
            positions.update({r['at']:r for cache in geometry.to_dict()['caches'] for r in cache['positions']})
        if geometry_pins!=dataset['geometry_series_sha256s']:raise ValueError('original fitted geometry differs')
        system_raw=(root/'openhab/household-pv-system.json').read_bytes();horizon_raw=(root/'openhab/household-solar-horizon.json').read_bytes()
        if system_raw.decode()!=dataset['system_raw'] or horizon_raw.decode()!=dataset['horizon_raw']:raise ValueError('array or terrain declarations changed')
        array=_array(json.loads(system_raw)['array']);horizon=json.loads(horizon_raw)['profile'];archives=[Archive.open_readonly(str(a.archive)),Archive.open_readonly(str(a.operational_archive))];runs=[]
        for pin in dataset['forecast_sha256s']:
            guard();available=[archive for archive in archives if (archive.objects/(pin+'.json')).exists()]
            if not available:raise ValueError('original Google forcing unavailable')
            snapshot=verify_history(available[0].read(pin))
            if snapshot['site']!=site.__dict__:raise ValueError('original Google site differs')
            origin=forecast_origin(snapshot,recorded=snapshot['historical'] is False);hours={}
            for p in snapshot['points']:
                if p['statistic']=='mean' and p['variable'] in ('station_head_temperature_2m','surface_solar_radiation_downwards_1hr','wind_speed_10m'):hours.setdefault(p['valid_at'],{})[p['variable']]=p['value']
            runs.append((origin,pin,hours,'recorded_ingestion' if snapshot['historical'] is False else 'assumed_full_cycle_9h'))
        expanded=expand_horizon_pairs(pairs,runs=runs,positions=positions,array=array,horizon=horizon,guard=guard)
        now=datetime.now(timezone.utc);model=fit_directional(pairs,cutoff=a.cutoff,trained_at=now);report=assess_horizons(model,expanded,cutoff=a.cutoff,end=a.end);run=directory(output/('assessment-'+now.strftime('%Y%m%dT%H%M%S%fZ')))
        data=dict(schema='earthship-pv-horizon-data/v2',baseline_rule=INTERVAL_BASELINE_RULE,pairs=expanded,parent_dataset_sha256=dataset['dataset_sha256'],parent_experiment_sha256=experiment['receipt_sha256'],system_raw=system_raw.decode(),horizon_raw=horizon_raw.decode());data['dataset_sha256']=identity(data)
        raw=canonical(data)
        if len(raw)>32*1024**2:raise ValueError('bounded PV horizon dataset required')
        path=run/(data['dataset_sha256']+'.pairs.json.gz');path.write_bytes(gzip.compress(raw,compresslevel=3,mtime=0));path.chmod(0o600)
        save(run/'training-model.json',model);save(run/'comparison.json',report);verify_sources(root,sources);manifest=retain_sources(run,sources)
        if _read(a.energy/'energy-index.json',1048576)!=index_raw or _read(a.libraries,8192)!=library_raw or runtime_identity(libraries,binding_version=binding,guard=guard)!=runtime:raise ValueError('assessment context changed')
        value=dict(schema='earthship-pv-horizon-experiment/v1',created_at=now.isoformat(),dataset_sha256=data['dataset_sha256'],parent_experiment_path=str(parent),parent_experiment_sha256=experiment['receipt_sha256'],report=report,runtime_manifest=manifest,automatic_actuation=False)
        value['receipt_sha256']=identity(value);save(run/'experiment.json',value);save(output/'last-experiment.json',dict(path=str(run),receipt_sha256=value['receipt_sha256']));return value


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','operational-archive','calibration','energy','geometry','libraries','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--cutoff',type=instant,required=True);p.add_argument('--end',type=instant,required=True);a=p.parse_args(argv);os.umask(0o077)
    try:
        value=run(a);print(json.dumps(dict(status='pv_horizon_assessed',report=value['report'],automatic_actuation=False)),flush=True);return 0
    except Exception as error:
        directory(a.output);save(a.output/'last-error.json',dict(reason=type(error).__name__,message=str(error)[:2048]));print(json.dumps(dict(status='pv_horizon_assessment_incomplete',reason=type(error).__name__)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
