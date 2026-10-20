#!/usr/bin/env python3
"""Compare site wind/rain gains on retained originals; no live forecast writes."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from io import BytesIO
import argparse,gzip,json,os,time,traceback
from household_native_training import directory,save
from weather_source_files import _read
from weather_learning.contracts import identity,instant,canonical,finite
from weather_learning.archive import Archive
from weather_learning.historical import verify_history
from weather_learning.weather_response import wind_hour,fit_gain,evaluate_gain
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.training_dataset import retain_dataset
from weather_learning.worker import collector_lock

ITEMS=('AmbientWeatherWS2902A_WindSpeed','Weather_Rain_Evidence_JSON')


def measurements(root,guard):
    from weather_rain_day import qualify_rain_day
    from weather_rain_evidence import RainPolicy
    root=Path(root);raw_index=_read(root/'weather-index.json',1048576);index=json.loads(raw_index)
    if index['index_sha256']!=identity({k:v for k,v in index.items() if k!='index_sha256'}) or not 1<=len(index['days'])<=90:raise ValueError('unchanged weather source index required')
    wind={};rain={};manifest=[];now=datetime.now(timezone.utc)
    policy_raw=_read(Path.home()/'.config/hex/weather-rain-policy.json',4096);policy_doc=json.loads(policy_raw);policy=RainPolicy(**{k:v for k,v in policy_doc.items() if k!='version'})
    for day in index['days']:
        start=instant(day['date']+'T00:00:00+00:00');end=start+timedelta(days=1);sources={};source_pins={}
        if day['query_start']!=(start-timedelta(seconds=120)).isoformat() or day['query_end']!=(end+timedelta(seconds=120)).isoformat():raise ValueError('original HTTP request range differs')
        for item in ITEMS:
            guard();raw=_read(root/(day['date']+'.'+item+'.json.gz'),8*1024**2)
            if sha256(raw).hexdigest()!=day['sources'][item]['file_sha256']:raise ValueError('weather original bytes differ')
            with gzip.GzipFile(fileobj=BytesIO(raw)) as handle:expanded=handle.read(8*1024**2+1)
            if len(expanded)>8*1024**2:raise ValueError('bounded weather source required')
            source=json.loads(expanded)
            if source['source_sha256']!=identity({k:v for k,v in source.items() if k!='source_sha256'}) or source['source_sha256']!=day['sources'][item]['source_sha256'] or source['item']!=item or source['automatic_actuation'] is not False or not end<=instant(source['requested_at'])<=instant(source['received_at'])<=now:raise ValueError('original weather capture context differs')
            payload=json.loads(source['raw'])
            if payload.get('name')!=item or not isinstance(payload.get('data'),list) or len(payload['data'])>10000:raise ValueError('bounded original weather payload required')
            sources[item]=payload;source_pins[item]=source['source_sha256']
        payload=sources[ITEMS[0]]
        if payload.get('unit')!='mph':raise ValueError('explicit original wind unit required')
        rows=[]
        for row in payload['data']:
            at=datetime.fromtimestamp(row['time']/1000,timezone.utc)
            if not start-timedelta(seconds=120)<=at<=end+timedelta(seconds=120):raise ValueError('wind state outside original query')
            try:value=float(row['state'].split()[0])
            except (ValueError,AttributeError,TypeError,IndexError):value=None
            if not finite(value):value=None
            if rows and at<rows[-1][0]:raise ValueError('ordered original wind states required')
            if rows and at==rows[-1][0]:
                if value!=rows[-1][1]:rows[-1]=(at,None)
            else:rows.append((at,value))
        for hour in range(24):
            left=start+timedelta(hours=hour);label=wind_hour(rows,start=left)
            if label['mean_m_s'] is not None:wind[(left+timedelta(hours=1)).isoformat()]={**label,'source_sha256':source_pins[ITEMS[0]]}
        rows=[(datetime.fromtimestamp(r['time']/1000,timezone.utc),r['state']) for r in sources[ITEMS[1]]['data']];carry=[r for r in rows if r[0]<start];rows=carry[-1:]+[r for r in rows if start<=r[0]<=end+timedelta(seconds=policy.validity_seconds)]
        try:qualified=qualify_rain_day(start.date(),as_of=now,observations=rows,policy=policy,site_timezone='UTC')
        except ValueError:qualified=None
        if (qualified is not None)!=(day['rain']['status']=='qualified') or qualified is not None and qualified!={k:v for k,v in day['rain'].items() if k!='status'}:raise ValueError('rain qualification differs from original replay')
        if qualified is not None:rain[start.isoformat()]=dict(rain_mm=qualified['rain_in']*25.4,source_sha256=source_pins[ITEMS[1]],qualification=qualified)
        manifest.append(dict(date=day['date'],sources=day['sources'],rain_status=day['rain']['status']))
    if _read(root/'weather-index.json',1048576)!=raw_index or _read(Path.home()/'.config/hex/weather-rain-policy.json',4096)!=policy_raw:raise ValueError('weather source selection or policy changed')
    return wind,rain,dict(days=manifest,rain_policy_raw=policy_raw.decode(),index_sha256=index['index_sha256'])


def row(kind,*,origin,start,end,baseline,outcome,source,label,quality,basis):
    value=dict(kind=kind,origin=origin.isoformat(),target_start=start.isoformat(),target_end=end.isoformat(),baseline=baseline,outcome=outcome,
        availability_basis=basis,source_sha256=source,measurement_sha256=label['source_sha256'],measurement_quality=quality,prospective_score=False,automatic_actuation=False)
    value['pair_sha256']=identity(value);return value


def run(a):
    from household_cycle_pressure import PublicationHeadroom
    began=time.monotonic();pressure=PublicationHeadroom();root=Path(__file__).resolve().parents[2];sources=capture_sources(root)
    def guard():
        pressure.check()
        if time.monotonic()-began>550:raise TimeoutError('weather comparison deadline elapsed')
    output=directory(a.output)
    with collector_lock(output/'training.lock'):
        wind,rain,manifest=measurements(a.measurements,guard);archive=Archive.open_readonly(str(a.archive));runs=[];wind_pairs=[];rain_pairs=[];seen=set()
        floor=min(instant(k) for k in wind)-timedelta(days=15)
        with archive._connect() as c:refs=c.execute('SELECT digest FROM snapshots WHERE historical=1 AND initialized>=? AND initialized<? ORDER BY initialized,completed,digest LIMIT 1001',(floor.isoformat(),a.end.isoformat())).fetchall()
        source_refs=[(archive,pin,False) for (pin,) in refs]
        if a.operational_archive is not None:
            operational=Archive.open_readonly(str(a.operational_archive));op_floor=max(floor,a.end-timedelta(days=90)).isoformat()
            with operational._connect() as c:
                selected=c.execute("SELECT digest FROM (SELECT digest,initialized,ROW_NUMBER() OVER (PARTITION BY initialized ORDER BY completed DESC,digest DESC) AS n FROM snapshots WHERE historical=0 AND initialized>=? AND completed<? AND substr(initialized,12,2) IN ('00','06','12','18')) WHERE n=1 ORDER BY initialized LIMIT 361",(op_floor,a.end.isoformat())).fetchall()
            if len(selected)>360:raise ValueError('bounded recorded operational sources required')
            source_refs.extend((operational,pin,True) for (pin,) in selected)
        if not 1<=len(source_refs)<=1000:raise ValueError('bounded original weather runs required')
        for selected_archive,pin,recorded in source_refs:
            guard();snapshot=verify_history(selected_archive.read(pin));origin=instant(snapshot['initialized_at'])+timedelta(hours=9);basis='retrospective_assumed_full_cycle_9h'
            if recorded:
                available=instant(snapshot['ingestion_completed_at']);origin=available.replace(minute=0,second=0,microsecond=0)
                if origin<available:origin+=timedelta(hours=1)
                basis='retrospective_recorded_ingestion_next_whole_hour'
            if origin in seen:continue
            seen.add(origin);hours={}
            for p in snapshot['points']:
                if p['statistic']!='mean' or p['variable'] not in ('wind_speed_10m','total_precipitation_1hr'):continue
                unit,period=('m s-1',0) if p['variable']=='wind_speed_10m' else ('mm',3600)
                if p['unit']!=unit or p['period_seconds']!=period:raise ValueError('native wind/rain units or period differ')
                hours.setdefault(p['valid_at'],{})[p['variable']]=p['value']
            runs.append((origin,pin,hours,basis))
            for lead in (*range(1,25),48,72,120,168):
                end=origin+timedelta(hours=lead);start=end-timedelta(hours=1);label=wind.get(end.isoformat());a0=hours.get(start.isoformat(),{}).get('wind_speed_10m');b0=hours.get(end.isoformat(),{}).get('wind_speed_10m')
                if end>=a.end or label is None or not all(finite(v) and v>=0 for v in (a0,b0)):continue
                wind_pairs.append(row('wind_m_s',origin=origin,start=start,end=end,baseline=(a0+b0)/2,outcome=label['mean_m_s'],source=pin,label=label,quality='numeric_mph_without_sensor_health_receipts',basis=basis))
        for at,label in rain.items():
            start=instant(at);end=start+timedelta(days=1)
            if end>=a.end:continue
            # One original forecast per daily target and predeclared lead band.
            for lag in (0,2,6):
                eligible=[r for r in runs if r[0]<=start-timedelta(days=lag)]
                if not eligible:continue
                origin,pin,hours,basis=max(eligible,key=lambda r:r[0]);values=[hours.get((start+timedelta(hours=i)).isoformat(),{}).get('total_precipitation_1hr') for i in range(1,25)]
                if any(not finite(v) or v<0 for v in values):continue
                value=row('rain_24h_mm',origin=origin,start=start,end=end,baseline=sum(values),outcome=label['rain_mm'],source=pin,label=label,quality='qualified_native_rain_counter_day',basis=basis)
                if not any(r['pair_sha256']==value['pair_sha256'] for r in rain_pairs):rain_pairs.append(value)
        now=datetime.now(timezone.utc);run=directory(output/('experiment-'+now.strftime('%Y%m%dT%H%M%S%fZ')));reports={};models={};fits_executed={};previous=None;previous_run=None
        pointer=output/'last-experiment.json'
        if pointer.exists():
            selected=json.loads(_read(pointer,65536));previous_run=Path(selected['path']);previous=json.loads(_read(previous_run/'experiment.json',262144))
            if previous['receipt_sha256']!=selected['receipt_sha256'] or previous['receipt_sha256']!=identity({k:v for k,v in previous.items() if k!='receipt_sha256'}):raise ValueError('previous weather experiment differs')
            names=('weather_response.py','contracts.py','training_cache.py','weights.py')
            if any(previous['runtime_manifest'].get('openhab/scripts/weather_learning/'+name)!=sha256(sources['openhab/scripts/weather_learning/'+name]).hexdigest() for name in names):previous=None
        from weather_learning.training_cache import gain_if_changed
        dataset=retain_dataset(run,metadata=dict(kind='site_wind_rain',measurement_manifest=manifest,forecast_sha256s=[r[1] for r in runs],availability_basis='retrospective_mixed_recorded_and_assumed_availability' if a.operational_archive is not None else 'retrospective_assumed_full_cycle_9h',wind_target='hour_mean_m_s_from_adjacent_native_instant_forecasts',rain_target='qualified_UTC_24h_total_mm',prospective_score=False,automatic_actuation=False),pairs=wind_pairs+rain_pairs)
        for kind,pairs,prior in [('wind_m_s',wind_pairs,24),('rain_24h_mm',rain_pairs,7)]:
            guard();old=None if previous is None else json.loads(_read(previous_run/(kind+'.training-model.json'),4*1024**2))
            model,comparison_fitted=gain_if_changed(old,pairs,kind=kind,cutoff=a.cutoff,trained_at=now,prior_pairs=prior);report=evaluate_gain(model,pairs,start=a.cutoff,end=a.end)
            old=None if previous is None else json.loads(_read(previous_run/(kind+'.final-model.json'),4*1024**2))
            final,serving_fitted=gain_if_changed(old,pairs,kind=kind,cutoff=a.end,trained_at=now,prior_pairs=prior);fits_executed[kind]=dict(comparison=comparison_fitted,serving=serving_fitted);save(run/(kind+'.training-model.json'),model);save(run/(kind+'.final-model.json'),final);reports[kind]=report;models[kind]=final['model_sha256']
            print(json.dumps(dict(status='site_weather_assessed',kind=kind,training_pairs=model['training_pairs'],training_target_days=model['training_target_days'],gain=model['gain'],report=report)),flush=True)
        verify_sources(root,sources);runtime=retain_sources(run,sources)
        result=dict(schema='earthship-historical-site-weather-experiment/v1',created_at=now.isoformat(),cutoff=a.cutoff.isoformat(),end=a.end.isoformat(),dataset_sha256=dataset['dataset_sha256'],reports=reports,final_models=models,fit_executed=fits_executed,runtime_manifest=runtime,source_runs=len(runs),wind_hours=len(wind),qualified_rain_days=len(rain),production_forecasts_changed=False,automatic_actuation=False)
        result['receipt_sha256']=identity(result);save(run/'experiment.json',result);save(output/'last-experiment.json',dict(path=str(run),receipt_sha256=result['receipt_sha256']));return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','measurements','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--operational-archive',type=Path)
    for name in ('cutoff','end'):p.add_argument('--'+name,required=True,type=instant)
    a=p.parse_args(argv);os.umask(0o077)
    try:run(a);return 0
    except Exception as e:
        directory(a.output);save(a.output/'last-error.json',dict(reason=type(e).__name__,traceback=traceback.format_exc()[-8192:]));print(json.dumps(dict(status='site_weather_assessment_incomplete',reason=type(e).__name__)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
