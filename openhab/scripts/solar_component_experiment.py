#!/usr/bin/env python3
"""Read retained PV originals and write a bounded private solar experiment only."""
import argparse,gzip,json,math,os,time
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
from astro_geometry_series import replay_series
from weather_source_files import _read
from weather_learning.archive import Archive
from weather_learning.config import Site
from weather_learning.contracts import canonical,identity,instant
from weather_learning.energy_history import summarize_hour
from weather_learning.pv_directional_calibration import validate_model
from weather_learning.solar_experiment import make_retrospective_forcing
from weather_learning.solar_pairing import component_pairs
from weather_learning.solar_evaluation import assess_pv_components
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources


def _gz(path,limit):
    raw=_read(path,8*1024**2)
    import io
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:body=stream.read(limit+1)
    if len(body)>limit:raise ValueError('bounded original compressed data required')
    return json.loads(body),sha256(raw).hexdigest()


def run(*,base,parent,output,root):
    started=time.monotonic();assessed=datetime.now(timezone.utc);pins={};runtime_sources=capture_sources(root)
    import earthship_energy.power_evidence as companion
    companion_sources={name:(Path(companion.__file__).parent/name).read_bytes() for name in ('power_evidence.py','power_intervals.py','bms_evidence.py','ac_evidence.py')}
    def guard():
        if time.monotonic()-started>120:raise TimeoutError('frozen solar experiment deadline elapsed')
    def read(path,limit,*,source=False):
        guard();raw=_read(path,limit,source=source);pins[str(path)]=(sha256(raw).hexdigest(),source);return raw
    protocol=json.loads(read(root/'docs/operations/weathernext3-capabilities/evaluation-protocol.json',65536,source=True))
    receipt=json.loads(read(parent/'experiment.json',1048576))
    if receipt['receipt_sha256']!=identity({k:v for k,v in receipt.items() if k!='receipt_sha256'}):raise ValueError('original PV experiment receipt differs')
    dataset,path_sha=_gz(parent/(receipt['dataset_sha256']+'.pairs.json.gz'),32*1024**2)
    if (dataset['dataset_sha256']!=receipt['dataset_sha256'] or dataset['dataset_sha256']!=identity({k:v for k,v in dataset.items() if k!='dataset_sha256'}) or
            not 1<=len(dataset['pairs'])<=10000):raise ValueError('original bounded PV pair dataset differs')
    labels=dataset['pairs'];geometry_pins=set(dataset['geometry_series_sha256s']);positions={};geometry_refs=[];native_runtime=None;site=None
    for path in sorted((base/'pv-calibration-geometry').glob('*.geometry.json')):
        value=json.loads(read(path,524288))
        if value['series_sha256'] not in geometry_pins:continue
        if native_runtime is None:native_runtime=value['native_runtime']
        series=replay_series(canonical(value),request=value['request'],expected_series_sha256=value['series_sha256'],expected_native_runtime=native_runtime)
        geometry_refs.append(series.sha256)
        this_site=dict(value['request']['site'],timezone=value['request']['timezone'])
        if site is not None and this_site!=site:raise ValueError('retained geometry site differs')
        site=this_site
        for cache in series.to_dict()['caches']:
            for row in cache['positions']:
                previous=positions.setdefault(row['at'],row)
                if previous!=row:raise ValueError('conflicting original geometry point')
    if set(geometry_refs)!=geometry_pins:raise ValueError('complete pinned native geometry originals required')
    energy_index=json.loads(read(base/'historical-energy/energy-index.json',1048576))
    if energy_index['index_sha256']!=identity({k:v for k,v in energy_index.items() if k!='index_sha256'}):raise ValueError('energy source index differs')
    hours={r['start']:r for r in energy_index['hours']};observations={}
    required_hours=sorted({instant(r['start']).replace(minute=0,second=0,microsecond=0) for r in labels})
    for at in required_hours:
        guard();path=base/'historical-energy/originals'/(at.strftime('%Y%m%dT%H')+'.energy.json.gz')
        source,pin=_gz(path,16*1024**2)
        if pin!=hours[at.isoformat()]['file_sha256']:raise ValueError('original energy bytes differ from index')
        cohort=identity(dict(policy=source['policy_raw'],bank_start=source['bank_start'],items=source['items']))
        for b in summarize_hour(source):
            if not b['potential_proxy_eligible']:continue
            measured=b['fields']['pv.input_power_w']
            observations[(b['start'],b['end'])]=dict(start=b['start'],end=b['end'],source_sha256=source['source_sha256'],
                outcome_w=measured['positive_kwh']*3600000/measured['covered_seconds'],available_at=source['received_at'],
                potential_proxy_eligible=True,cohort_sha256=cohort)
    print(json.dumps(dict(phase='originals_verified',geometry_series=len(geometry_refs),energy_hours=len(required_hours))),flush=True)
    system_raw=dataset['system_raw'].encode();horizon_raw=dataset['horizon_raw'].encode()
    if (read(root/'openhab/household-pv-system.json',16384,source=True)!=system_raw or
            read(root/'openhab/household-solar-horizon.json',16384,source=True)!=horizon_raw):raise ValueError('original geometry declarations differ')
    array=json.loads(system_raw)['array'];horizon=json.loads(horizon_raw)['profile'];site=Site(**site)
    selected_raw=read(base/'pv-calibration/selected-directional.json',262144);selected=json.loads(selected_raw)
    if selected['receipt_sha256']!=identity({k:v for k,v in selected.items() if k!='receipt_sha256'}):raise ValueError('original selected correction receipt differs')
    model=validate_model(selected['final_model']);fixed={k:v['gain'] for k,v in model['sectors'].items()};fixed_pin=sha256(selected_raw).hexdigest()
    archives=[Archive.open_readonly(str(base/name)) for name in ('historical-2026','archive')]
    groups=defaultdict(list)
    for label in labels:groups[label['forecast_sha256']].append(label)
    paired=[];sources=[]
    for index,(pin,group) in enumerate(sorted(groups.items())):
        guard();matching=[a for a in archives if (a.objects/(pin+'.json')).is_file()]
        if len(matching)!=1:raise ValueError('one exact retained source original required')
        source=matching[0].read(pin);origin=instant(group[0]['origin']);end=max(instant(r['end']) for r in group)
        hours=math.ceil((end-origin).total_seconds()/3600)
        basis='retrospective_assumed_full_cycle_9h' if source['historical'] else 'retrospective_recorded_ingestion_next_whole_hour'
        forcing=make_retrospective_forcing(source,origin=origin,horizon_hours=hours,site=site,assessed_at=assessed,availability_basis=basis)
        first=min(instant(r['start']) for r in group).replace(minute=0,second=0,microsecond=0)
        last=end.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
        geometry=[p for at,p in positions.items() if first<instant(at)<=last];geometry.sort(key=lambda p:p['at'])
        pairs=component_pairs(labels=group,observations=observations,forcing=forcing,positions=geometry,array=array,
            horizon_profile=horizon,timezone_name=site.timezone,fixed_gain_by_sector=fixed,fixed_gain_source_sha256=fixed_pin)
        paired.extend(pairs);sources.append(dict(snapshot_sha256=pin,forcing_sha256=forcing['forecast_sha256'],
            initialized_at=source['initialized_at'],first_seen_at=source['first_seen_at'],ingestion_completed_at=source['ingestion_completed_at'],
            historical=source['historical'],availability_basis=basis))
        if (index+1)%10==0:print(json.dumps(dict(phase='source_replay',completed=index+1,total=len(groups))),flush=True)
    cohorts=defaultdict(list)
    for row in paired:cohorts[(row['cohort_sha256'],row['availability_basis'])].append(row)
    reports=[assess_pv_components(group,timezone_name=site.timezone,protocol=protocol,guard=guard) for key,group in sorted(cohorts.items())]
    for report,(key,group) in zip(reports,sorted(cohorts.items())):
        report['source_basis']=key[1];report['report_sha256']=identity({k:v for k,v in report.items() if k!='report_sha256'})
    guard()
    for name,(pin,source_mode) in pins.items():
        if sha256(_read(Path(name),8*1024**2,source=source_mode)).hexdigest()!=pin:raise ValueError('source changed during solar experiment')
    verify_sources(root,runtime_sources)
    for name,raw in companion_sources.items():
        if (Path(companion.__file__).parent/name).read_bytes()!=raw:raise ValueError('companion numerical source changed during experiment')
    retained=dict(runtime_sources,**{'companion/earthship_energy/'+name:raw for name,raw in companion_sources.items()})
    manifest={name:sha256(raw).hexdigest() for name,raw in retained.items()}
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    source_path=output/('sources-'+identity(manifest))
    if source_path.exists():
        if any(sha256(_read(source_path/'sources'/name,1024**2)).hexdigest()!=pin for name,pin in manifest.items()):raise ValueError('retained source package differs')
    else:retain_sources(source_path,retained)
    result=dict(schema='earthship-retained-solar-experiment/v1',assessed_at=assessed.isoformat(),parent_dataset_sha256=dataset['dataset_sha256'],
        parent_file_sha256=path_sha,paired_targets=len({(r['cohort_sha256'],r['start'],r['end']) for r in paired}),paired_forecasts=len(paired),original_sources=sources,geometry_series_sha256s=sorted(geometry_refs),
        fixed_correction_source_sha256=fixed_pin,fixed_correction_trained_at=model['trained_at'],
        fixed_correction_historical_availability_claim=False,protocol_sha256=identity(protocol),reports=reports,
        source_runtime=manifest,source_package_sha256=identity(manifest),
        duration_seconds=time.monotonic()-started,production_changed=False,prospective_score=False,physical_calibration_qualified=False,automatic_actuation=False)
    result['experiment_sha256']=identity(result)
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=output/(result['experiment_sha256']+'.experiment.json');path.write_bytes(canonical(result));path.chmod(0o600)
    pairs=dict(schema='earthship-matched-solar-pairs/v1',pairs=paired,original_sources=sources,protocol_sha256=identity(protocol),parent_dataset_sha256=dataset['dataset_sha256'],automatic_actuation=False)
    pairs['dataset_sha256']=identity(pairs);p=output/(pairs['dataset_sha256']+'.pairs.json.gz');p.write_bytes(gzip.compress(canonical(pairs),mtime=0));p.chmod(0o600)
    return dict(status='retained_solar_experiment_complete',experiment_sha256=result['experiment_sha256'],paired_targets=len(paired),duration_seconds=result['duration_seconds'],
        cohorts=[dict(source_basis=r['source_basis'],support=r['support'],disposition=r['disposition'],fallback_inclusive=r['fallback_inclusive'],matched_native=r['matched_native']['support']) for r in reports],production_changed=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','parent','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(argv);os.umask(0o077)
    result=run(base=a.base,parent=a.parent,output=a.output,root=Path(__file__).resolve().parents[2]);print(json.dumps(result),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
