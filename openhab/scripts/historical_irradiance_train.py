#!/usr/bin/env python3
"""Chronological local irradiance-proxy assessment; no forecast or actuator writes."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
import argparse,json,os,time,traceback
from household_native_training import directory,save
from weather_source_files import _read
from weather_learning.contracts import identity,instant
from weather_learning.numeric_history import capture_numeric_day,original_series
from weather_learning.irradiance_learning import numeric_hour,qualified_hour,pair_irradiance,assess_irradiance,infer_proxy_units
from weather_learning.site_calibration import fit_residual
from weather_learning.training_dataset import retain_dataset
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.worker import collector_lock


def targets(numeric,receipts,guard):
    from historical_radiation_capture import capture_day
    from weather_radiation_evidence import RadiationPolicy
    numeric,receipts=map(Path,(numeric,receipts));nr=_read(numeric/'numeric-index.json',262144);rr=_read(receipts/'radiation-index.json',65536)
    ni,ri=map(json.loads,(nr,rr))
    for index in (ni,ri):
        if index['index_sha256']!=identity({k:v for k,v in index.items() if k!='index_sha256'}):raise ValueError('original source index differs')
    sources={};manifest=[]
    for row in ri['days']:
        guard();p=receipts/(row['date']+'.radiation-source.json.gz')
        if sha256(_read(p,32*1024**2)).hexdigest()!=row['file_sha256']:raise ValueError('radiation original bytes differ')
        # Existing source's policy is revalidated by the receipt reader below.
        import gzip
        value=json.loads(gzip.decompress(_read(p,32*1024**2)));policy=RadiationPolicy(**value['policy'])
        value,_=capture_day(receipts,row['date'],connect=None,policy=policy)
        if value['source_sha256']!=row['source_sha256']:raise ValueError('radiation source identity differs')
        sources[row['date']]=value;manifest.append(row)
    boundary=min(k for k,v in sources.items() if v['rows']);cutover=instant(boundary+'T00:00:00+00:00');result={};legacy=[]
    for row in ni['days']:
        if row['date']>=boundary:continue
        guard();p=numeric/(row['date']+'.numeric-source.json.gz')
        if sha256(_read(p,8*1024**2)).hexdigest()!=row['file_sha256']:raise ValueError('numeric source bytes differ')
        value=capture_numeric_day(numeric,row['date'],site=ni['site'],token_reader=None)
        if value['source_sha256']!=row['source_sha256']:raise ValueError('numeric source identity differs')
        rows=original_series(value,'radiation');start=instant(value['start']);legacy.append(row)
        for hour in range(24):
            left=start+timedelta(hours=hour);label=numeric_hour(rows,start=left)
            result[(left+timedelta(hours=1)).isoformat()]={**label,'start':left.isoformat(),'source_sha256':value['source_sha256'],'unit_assumed_constant_before_receipt_coverage':True}
    for day,value in sources.items():
        if day<boundary:continue
        guard();start=instant(value['start']);rows=[(instant(at),raw) for at,raw in value['rows']];policy=RadiationPolicy(**value['policy'])
        for hour in range(24):
            left=start+timedelta(hours=hour);label=qualified_hour(rows,start=left,history_start=start-timedelta(seconds=120),cutover=cutover,policy=policy,assessed_at=datetime.now(timezone.utc))
            result[(left+timedelta(hours=1)).isoformat()]={**label,'start':left.isoformat(),'source_sha256':value['source_sha256']}
    overlaps=[]
    for row in reversed(ni['days']):
        if row['date']<boundary:break
        if row['date'] not in sources:continue
        guard();p=numeric/(row['date']+'.numeric-source.json.gz')
        if sha256(_read(p,8*1024**2)).hexdigest()!=row['file_sha256']:raise ValueError('unit-overlap numeric source bytes differ')
        value=capture_numeric_day(numeric,row['date'],site=ni['site'],token_reader=None)
        if value['source_sha256']!=row['source_sha256']:raise ValueError('unit-overlap source identity differs')
        rows=original_series(value,'radiation');start=instant(value['start']);pairs=[]
        for hour in range(24):
            left=start+timedelta(hours=hour);label=result.get((left+timedelta(hours=1)).isoformat());mean=numeric_hour(rows,start=left)['mean_w_m2']
            if label is not None and label['mean_w_m2'] is not None and label['mean_w_m2']>=50 and mean is not None:pairs.append((mean,label['mean_w_m2']))
        if len(pairs)>=3:overlaps.append(dict(date=row['date'],numeric_sha256=value['source_sha256'],radiation_sha256=sources[row['date']]['source_sha256'],pairs=pairs))
        if len(overlaps)==3:break
    proof=infer_proxy_units(overlaps)
    if _read(numeric/'numeric-index.json',262144)!=nr or _read(receipts/'radiation-index.json',65536)!=rr:raise ValueError('source index changed during reading')
    return result,dict(legacy_numeric=legacy,receipt_originals=manifest,receipt_coverage_boundary=boundary,legacy_unit_proof=proof,metrology_calibrated=False)


def geometry(root,instants,*,site,runtime,libraries,guard):
    import astro_geometry as astro
    from astro_geometry_series import build_series_request,split_series_request,build_series,replay_series
    from astro_geometry_worker import capture_batch
    from household_cycle_resources import publication_geometry_policy
    positions={};pins=[];months={}
    for at in instants:months.setdefault(at.strftime('%Y-%m'),[]).append(at)
    root=directory(root)
    for month,points in sorted(months.items()):
        guard();key=identity(dict(points=[p.isoformat() for p in points],site=site.__dict__,runtime=runtime));path=root/(key+'.geometry.json')
        requested=datetime.now(timezone.utc)
        if path.exists():requested=instant(json.loads(_read(path,4*1024**2))['request']['requested_at'])
        request=build_series_request(points,requested_at=requested,latitude=site.latitude,longitude=site.longitude,timezone_name=site.timezone)
        if path.exists():
            raw=_read(path,4*1024**2);value=json.loads(raw);series=replay_series(raw,request=request,expected_series_sha256=value['series_sha256'],expected_native_runtime=runtime)
        else:
            caches=[]
            for chunk in split_series_request(request):
                guard();source=astro.build_source(chunk,observed_at=datetime.now(timezone.utc),native_runtime=runtime,source_status='ONLINE',latitude=site.latitude,longitude=site.longitude,timezone_name=site.timezone,altitude_m=None)
                with publication_geometry_policy():caches.append(capture_batch(chunk,source,library_paths=libraries,scratch=root,guard=guard))
            series=build_series(request,caches,expected_native_runtime=runtime);save(path,series.to_dict())
        pins.append(series.sha256)
        for cache in series.to_dict()['caches']:
            for row in cache['positions']:positions[row['at']]=row
        print(json.dumps(dict(status='irradiance_geometry',month=month,points=len(points))),flush=True)
    return positions,pins


def run(a):
    from weather_learning.archive import Archive
    from weather_learning.config import Site
    from weather_learning.openhab import oh_get,I18N_CONFIG_PATH
    from household_native_geometry_prepare import _library_paths
    from astro_geometry_worker import runtime_identity
    from household_solar_horizon import horizon_height
    from household_cycle_pressure import PublicationHeadroom
    root=Path(__file__).resolve().parents[2];sources=capture_sources(root);started=time.monotonic();pressure=PublicationHeadroom()
    def guard():
        pressure.check()
        if time.monotonic()-started>550:raise TimeoutError('irradiance experiment deadline elapsed')
    output=directory(a.output)
    with collector_lock(output/'training.lock'):
        labels,measurement_manifest=targets(a.numeric,a.receipts,guard);site=Site.from_openhab_config(oh_get(I18N_CONFIG_PATH));library_raw=_read(a.libraries,8192);libraries=_library_paths(library_raw)
        addon=oh_get('/addons/binding-astro');runtime=runtime_identity(libraries,binding_version=addon['version'],guard=guard)
        if addon.get('installed') is not True or oh_get('/things/astro:sun:local')['statusInfo']['status']!='ONLINE':raise ValueError('native solar geometry unavailable')
        points=sorted(instant(at)-timedelta(minutes=30) for at,label in labels.items() if label['mean_w_m2'] is not None and instant(at)<a.holdout_end)
        positions,geometry_pins=geometry(output/'geometry',points,site=site,runtime=runtime,libraries=libraries,guard=guard)
        horizon_raw=(root/'openhab/household-solar-horizon.json').read_bytes();horizon=json.loads(horizon_raw)['profile']
        for value in positions.values():value['horizon_elevation_degrees']=horizon_height(horizon,value['azimuth_degrees'])
        archive=Archive.open_readonly(str(a.archive));pairs=[];refs=[];sources_to_pair=[]
        with archive._connect() as connection:rows=connection.execute('SELECT digest FROM snapshots WHERE historical=1 ORDER BY initialized,completed,digest LIMIT 1001').fetchall()
        if not 1<=len(rows)<=1000:raise ValueError('bounded historical sources required')
        sources_to_pair.extend((archive,pin,False) for (pin,) in rows)
        if a.operational_archive is not None:
            operational=Archive.open_readonly(str(a.operational_archive))
            floor=(a.holdout_end-timedelta(days=90)).isoformat()
            with operational._connect() as connection:
                recorded=connection.execute("SELECT digest FROM (SELECT digest,initialized,ROW_NUMBER() OVER (PARTITION BY initialized ORDER BY completed DESC,digest DESC) AS n FROM snapshots WHERE historical=0 AND initialized>=? AND completed<? AND substr(initialized,12,2) IN ('00','06','12','18')) WHERE n=1 ORDER BY initialized LIMIT 361",(floor,a.holdout_end.isoformat())).fetchall()
            if len(recorded)>360:raise ValueError('bounded recorded irradiance source list required')
            known={pin for _,pin,_ in sources_to_pair};sources_to_pair.extend((operational,pin,True) for (pin,) in recorded if pin not in known)
        for selected_archive,pin,recorded in sources_to_pair:
            guard();snapshot=selected_archive.read(pin)
            if snapshot['site']!=site.__dict__:raise ValueError('historical site differs')
            pairs.extend(pair_irradiance(snapshot,labels,positions,target_end=a.holdout_end,allow_recorded_availability=recorded));refs.append(pin)
        now=datetime.now(timezone.utc);run=directory(output/('experiment-'+now.strftime('%Y%m%dT%H%M%S%fZ')))
        dataset=retain_dataset(run,metadata=dict(kind='irradiance_w_m2',forecast_sha256s=refs,measurement_manifest=measurement_manifest,geometry_sha256s=geometry_pins,
            horizon_sha256=sha256(horizon_raw).hexdigest(),geometry_basis='current_native_geometry_and_declared_terrain_retrospectively',prospective_score=False,automatic_actuation=False),pairs=pairs)
        previous=None;previous_run=None;pointer=output/'last-experiment.json'
        if pointer.exists():
            selected=json.loads(_read(pointer,8192));previous_run=Path(selected['path']);previous=json.loads(_read(previous_run/'experiment.json',1048576))
            if previous['receipt_sha256']!=selected['receipt_sha256'] or previous['receipt_sha256']!=identity({k:v for k,v in previous.items() if k!='receipt_sha256'}):raise ValueError('original prior irradiance experiment differs')
            names=('site_calibration.py','irradiance_learning.py','contracts.py','training_cache.py')
            if any(previous['runtime_manifest'].get('openhab/scripts/weather_learning/'+name)!=sha256(sources['openhab/scripts/weather_learning/'+name]).hexdigest() for name in names):previous=None
        from weather_learning.training_cache import residual_if_changed
        def earlier(name,pin):
            if previous is None:return None
            model=json.loads(_read(previous_run/name,4*1024**2))
            if model['model_sha256']!=previous[pin]:raise ValueError('original prior irradiance model differs')
            return model
        model,comparison_fit=residual_if_changed(earlier('training-model.json','training_model_sha256'),pairs,kind='irradiance_w_m2',cutoff=a.train_end,trained_at=now,correction_limit=600.)
        report=assess_irradiance(model,pairs,holdout_start=a.train_end,holdout_end=a.holdout_end)
        final,serving_fit=residual_if_changed(earlier('final-model.json','final_model_sha256'),pairs,kind='irradiance_w_m2',cutoff=a.holdout_end,trained_at=now,correction_limit=600.)
        save(run/'training-model.json',model);save(run/'comparison.json',report);save(run/'final-model.json',final)
        verify_sources(root,sources);manifest=retain_sources(run,sources)
        if _read(a.libraries,8192)!=library_raw or runtime_identity(libraries,binding_version=addon['version'],guard=guard)!=runtime or (root/'openhab/household-solar-horizon.json').read_bytes()!=horizon_raw:raise ValueError('geometry runtime or terrain changed')
        receipt=dict(schema='earthship-historical-irradiance-training/v1',trained_at=now.isoformat(),dataset_sha256=dataset['dataset_sha256'],forecast_runs=len(refs),paired_hours=len(pairs),training_pairs=model['sample_count'],report=report,
            training_model_sha256=model['model_sha256'],final_model_sha256=final['model_sha256'],fit_executed=dict(comparison=comparison_fit,serving=serving_fit),recorded_operational_runs=sum(int(v[2]) for v in sources_to_pair),runtime_manifest=manifest,production_model_changed=False,automatic_actuation=False)
        receipt['receipt_sha256']=identity(receipt);save(run/'experiment.json',receipt);save(output/'last-experiment.json',dict(path=str(run),receipt_sha256=receipt['receipt_sha256']))
        print(json.dumps(dict(status='irradiance_assessed',pairs=len(pairs),report=report,automatic_actuation=False)),flush=True)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','numeric','receipts','libraries','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--operational-archive',type=Path)
    for name in ('train-end','holdout-end'):p.add_argument('--'+name,required=True,type=instant)
    a=p.parse_args(argv);os.umask(0o077)
    try:run(a);return 0
    except Exception as e:
        directory(a.output);save(a.output/'last-error.json',dict(reason=type(e).__name__,traceback=traceback.format_exc()[-8192:]));print(json.dumps(dict(status='irradiance_assessment_incomplete',reason=type(e).__name__)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
