#!/usr/bin/env python3
"""Bounded retained-input thermal solar experiment; never installs a model."""
import argparse,gzip,json,math,os,time
from bisect import bisect_right
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
from astro_geometry_series import replay_series
from native_thermal_inputs import replay_native_development
from thermal_model.training_inputs import read_training_inputs_v2
from weather_source_files import _read
from weather_learning.archive import Archive
from weather_learning.config import Site
from weather_learning.contracts import canonical,identity,instant
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.solar_experiment import make_retrospective_forcing
from weather_learning.thermal_solar_experiment import eligible_window,build_trajectory,assess_response,_temperature_metrics


def run(*,base,output,root):
    began=time.monotonic();now=datetime.now(timezone.utc);runtime=capture_sources(root);pins={}
    def guard():
        if time.monotonic()-began>120:raise TimeoutError('frozen thermal solar experiment deadline elapsed')
    def read(path,limit,source=False):
        guard();raw=_read(path,limit,source=source);pins[str(path)]=(sha256(raw).hexdigest(),source);return raw
    def document(path,limit,field):
        value=json.loads(read(path,limit))
        if value[field]!=identity({k:v for k,v in value.items() if k!=field}):raise ValueError('original thermal source identity differs')
        return value
    protocol=json.loads(read(root/'docs/operations/weathernext3-capabilities/evaluation-protocol.json',65536,True))
    policy=json.loads(read(root/'docs/operations/weathernext3-capabilities/thermal-solar-protocol.json',65536,True))
    pointer=json.loads(read(base/'thermal-comparison/last-comparison.json',8192));parent=Path(pointer['path'])
    receipt=document(parent/'comparison.json',1048576,'receipt_sha256')
    if receipt['receipt_sha256']!=pointer['receipt_sha256']:raise ValueError('pinned original thermal comparison required')
    old=document(parent/'dataset.json',4194304,'dataset_sha256')
    if old['dataset_sha256']!=receipt['dataset_sha256']:raise ValueError('thermal comparison dataset differs')
    references=old['measurement_originals']['originals'];originals={}
    for role in ('dataset','geometry','snapshot'):
        raw=read(Path(references[role]['path']),32*1024**2)
        if sha256(raw).hexdigest()!=references[role]['sha256']:raise ValueError('original thermal measurement bytes differ')
        originals[role]=raw
    g=json.loads(originals['geometry']);geometry=replay_series(originals['geometry'],request=g['request'],expected_series_sha256=g['series_sha256'],expected_native_runtime=g['native_runtime'])
    record=read_training_inputs_v2(Path(references['snapshot']['path']));saved=json.loads(originals['dataset'])
    phases={role:value['sensor_epoch'] for role,value in record['temperature_evidence']['roles'].items()}
    data=replay_native_development(originals['dataset'],record=record,expected_dataset_sha256=saved['dataset_sha256'],expected_snapshot_sha256=record['snapshot_sha256'],
        sensor_epochs=phases,geometry=geometry,expected_series_sha256=geometry.sha256)
    print(json.dumps(dict(phase='sealed_history_replayed',samples=len(data.development.samples))),flush=True)
    samples={row['at']:row for row in data.to_dict()['samples']};positions={p['at']:p for cache in geometry.to_dict()['caches'] for p in cache['positions']}
    site=Site(**dict(g['request']['site'],timezone=g['request']['timezone']));horizon_doc=json.loads(read(root/'openhab/household-solar-horizon.json',16384,True));horizon=horizon_doc['profile']
    shade=json.loads(read(root/'openhab/thermal-shade-context.json',16384,True))
    if shade['nominal_shade_rejection_fraction']!=policy['nominal_shade_rejection_fraction']:raise ValueError('frozen cloth prior differs from original declaration')
    archive=Archive.open_readonly(str(base/'historical-2026'))
    with archive._connect() as c:
        refs=c.execute('SELECT initialized,digest FROM snapshots WHERE historical=1 AND initialized>=? AND initialized<? ORDER BY initialized,completed,digest',
            ((data.development.start-timedelta(hours=48)).isoformat(),data.development.end.isoformat())).fetchall()
    sources={}
    for initialized,pin in refs:sources.setdefault(instant(initialized)+timedelta(hours=9),(initialized,pin))
    available=sorted(sources);requests=defaultdict(list);excluded=Counter();attempts=Counter()
    for key,state in sorted(samples.items()):
        origin=instant(key)
        if origin.minute%policy['origin_stride_minutes'] or origin.second or origin.microsecond:continue
        index=bisect_right(available,origin)-1
        for lead in policy['horizons_hours']:
            target=origin+timedelta(hours=lead)
            if target.isoformat() not in samples:continue
            attempts[str(lead)]+=1
            eligible,reason=eligible_window(samples,origin=origin,target=target,barriers=data.development.ineligible_action_times,late_intervals=data.development.unavailable_origin_intervals)
            if not eligible:excluded[str(lead)+':'+reason]+=1;continue
            if index<0:excluded[str(lead)+':forecast_not_available_by_assumed_clock']+=1;continue
            initialized,pin=sources[available[index]];requests[pin].append((origin,target,lead))
    if sum(map(len,requests.values()))>protocol['limits']['maximum_rows_per_experiment']:raise ValueError('thermal pair count exceeds frozen cap')
    rows=[];weather_sources=[]
    for index,(pin,windows) in enumerate(sorted(requests.items())):
        guard();source=archive.read(pin);source_origin=instant(source['initialized_at'])+timedelta(hours=9)
        first=min(a for a,b,h in windows);end=max(b for a,b,h in windows);hours=math.ceil((end-source_origin).total_seconds()/3600)
        forcing=make_retrospective_forcing(source,origin=source_origin,horizon_hours=hours,site=site,assessed_at=now,availability_basis='retrospective_assumed_full_cycle_9h')
        floor=first.replace(minute=0,second=0,microsecond=0);ceiling=end.replace(minute=0,second=0,microsecond=0)
        if ceiling<end:ceiling+=timedelta(hours=1)
        native_positions=[p for at,p in positions.items() if floor<instant(at)<=ceiling];native_positions.sort(key=lambda p:p['at'])
        args=dict(forcing=forcing,positions=native_positions,start=first,end=end,horizon_profile=horizon,policy=policy)
        native=build_trajectory(**args);total=build_trajectory(**args,force_total_only=True)
        cohort=identity(dict(sensor_epochs=phases,temperature_policy=record['temperature_evidence'],solar_grid=forcing['rows'][0]['solar']['grid_sha256'],horizon_sha256=identity(horizon)))
        for origin,target,lead in windows:
            initial=samples[origin.isoformat()];actual=samples[target.isoformat()]
            a=native.features(origin_state=initial,start=origin,end=target);b=total.features(origin_state=initial,start=origin,end=target)
            row=dict(origin=origin.isoformat(),target_at=target.isoformat(),lead_hours=lead,origin_air_f=initial['air_f'],outcome_f=actual['air_f'],
                native_features=a['features'],total_features=b['features'],native_supported=a['native_supported'],
                origin_actions=[initial[k] for k in ('indoor_shade_closed','outdoor_shade_present','vent_open')],forecast_sha256=pin,
                measurement_sha256=identity(dict(snapshot=record['snapshot_sha256'],target_at=target.isoformat(),role='air',sensor_epoch=phases['air'])),
                cohort_sha256=cohort,available_at=record['captured_at'],feature_policy_sha256=identity(policy))
            row['pair_sha256']=identity(row);rows.append(row)
        weather_sources.append(dict(snapshot_sha256=pin,forcing_sha256=forcing['forecast_sha256'],initialized_at=source['initialized_at'],first_seen_at=source['first_seen_at'],
            ingestion_completed_at=source['ingestion_completed_at'],historical=source['historical']))
        if (index+1)%5==0:print(json.dumps(dict(phase='matched_thermal_forcing',sources=index+1,total=len(requests),pairs=len(rows))),flush=True)
    print(json.dumps(dict(phase='fitting_and_assessment',pairs=len(rows),attempts=dict(attempts),exclusions=dict(excluded))),flush=True)
    report=assess_response(rows,timezone_name=site.timezone,policy=policy,protocol=protocol,guard=guard)
    from zoneinfo import ZoneInfo
    predicted={(r['origin'],r['target_at'],r['forecast_sha256']):r for r in report['predictions'] if r['both_fitted']}
    incumbent=[]
    for old_row in old['pairs']:
        key=(old_row['origin'],old_row['target_at'],old_row['forecast_sha256']);matched=predicted.get(key)
        if matched is None or old_row['action_stratum']!='stable':continue
        if abs(matched['outcome_f']-old_row['actual'][0])>1e-9:raise ValueError('same measured incumbent endpoint required')
        incumbent.append(dict(matched,incumbent_f=old_row['predictions']['six_hourly_physics'][0]))
    context=dict(role='retained original six-hourly physical prediction; diagnostic matched intersection',support=len(incumbent),
        metrics={name:_temperature_metrics(incumbent,name+'_f',ZoneInfo(site.timezone)) for name in ('incumbent','native','total','persistence')})
    guard();verify_sources(root,runtime)
    for name,(pin,is_source) in pins.items():
        if sha256(_read(Path(name),32*1024**2,source=is_source)).hexdigest()!=pin:raise ValueError('thermal source changed during experiment')
    manifest={name:sha256(raw).hexdigest() for name,raw in runtime.items()};output.mkdir(parents=True,exist_ok=True,mode=0o700);source_path=output/('sources-'+identity(manifest))
    if source_path.exists():
        if any(sha256(_read(source_path/'sources'/name,1024**2)).hexdigest()!=pin for name,pin in manifest.items()):raise ValueError('retained thermal numerical source differs')
    else:retain_sources(source_path,runtime)
    result=dict(schema='earthship-retained-thermal-solar-experiment/v1',assessed_at=now.isoformat(),source_package_sha256=identity(manifest),source_runtime=manifest,
        protocol_sha256=identity(protocol),feature_policy_sha256=identity(policy),measurement_originals=old['measurement_originals'],weather_originals=weather_sources,
        attempted_windows=dict(attempts),excluded_windows=dict(excluded),matched_feature_pairs=len(rows),report=report,incumbent_context=context,
        original_state='measured air/north-wall, not latent mass target',future_actions='eligibility only; never future predictor features',
        forecast_availability='retrospective assumed initialization+9h',training_availability='earlier target order assumption; actual later source capture and fit clocks retained',
        duration_seconds=time.monotonic()-began,production_changed=False,prospective_score=False,physical_calibration_qualified=False,automatic_actuation=False)
    result['experiment_sha256']=identity(result);path=output/(result['experiment_sha256']+'.experiment.json');path.write_bytes(canonical(result));path.chmod(0o600)
    paired=dict(schema='earthship-component-thermal-response-pairs/v1',pairs=rows,measurement_snapshot_sha256=record['snapshot_sha256'],geometry_series_sha256=geometry.sha256,
        protocol_sha256=identity(protocol),feature_policy_sha256=identity(policy),automatic_actuation=False);paired['dataset_sha256']=identity(paired)
    path=output/(paired['dataset_sha256']+'.pairs.json.gz');path.write_bytes(gzip.compress(canonical(paired),mtime=0));path.chmod(0o600)
    return dict(status='retained_thermal_solar_experiment_complete',experiment_sha256=result['experiment_sha256'],duration_seconds=result['duration_seconds'],pairs=len(rows),
        horizons={h:{k:v for k,v in r.items() if k in ('support','fitted_native_support','fallback_inclusive','matched_native','disposition')} for h,r in report['horizons'].items()},production_changed=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);os.umask(0o077)
    print(json.dumps(run(base=a.base,output=a.output,root=Path(__file__).resolve().parents[2])),flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
