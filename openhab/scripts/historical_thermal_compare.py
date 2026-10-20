#!/usr/bin/env python3
"""Compare true daily/six-hourly physics on later Google-forced outcomes."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
import argparse,json,os,time
from household_native_training import directory,save
from weather_source_files import _read
from weather_learning.contracts import identity,instant
from weather_learning.historical import verify_history
from weather_learning.archive import Archive
from weather_learning.thermal_comparison import select_fit,google_forcings,action_stratum,summarize,ACTIONS
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.worker import collector_lock


def load_development(stage):
    from astro_geometry_series import replay_series
    from thermal_model.training_inputs import read_training_inputs_v2
    from native_thermal_inputs import replay_native_development
    cycle=json.loads(_read(Path(stage)/'cycle.json',8192));settings=json.loads(_read(cycle['forecast_config'],8192));candidate=json.loads(_read(settings['candidate_path'],262144))
    refs=candidate['originals'];raw={}
    for role in ('dataset','geometry','snapshot'):
        raw[role]=_read(refs[role]['path'],32*1024**2)
        if sha256(raw[role]).hexdigest()!=refs[role]['sha256']:raise ValueError('original held-out source bytes differ')
    g=json.loads(raw['geometry']);geometry=replay_series(raw['geometry'],request=g['request'],expected_series_sha256=g['series_sha256'],expected_native_runtime=g['native_runtime'])
    record=read_training_inputs_v2(Path(refs['snapshot']['path']));value=json.loads(raw['dataset'])
    phases={role:info['sensor_epoch'] for role,info in record['temperature_evidence']['roles'].items()}
    data=replay_native_development(raw['dataset'],record=record,expected_dataset_sha256=value['dataset_sha256'],expected_snapshot_sha256=record['snapshot_sha256'],sensor_epochs=phases,geometry=geometry,expected_series_sha256=geometry.sha256)
    return data,dict(originals=refs,dataset_sha256=data.sha256,source_snapshot_sha256=record['snapshot_sha256'],geometry_series_sha256=geometry.sha256),record


def load_fits(path,geometry):
    rows=json.loads(_read(path,65536));models=[]
    for row in rows:
        raw=_read(Path(row['path'])/'physics-fit.json',262144);value=json.loads(raw)
        if value['receipt_sha256']!=row['receipt_sha256'] or value['receipt_sha256']!=identity({k:v for k,v in value.items() if k!='receipt_sha256'}) or value['cutoff']!=row['cutoff']:
            raise ValueError('original earlier physics fit differs')
        if value['fit']['training_end']!=value['cutoff']:raise ValueError('physical fitting cutoff differs')
        dataset=json.loads(_read(value['originals']['dataset'],8*1024**2));g=json.loads(_read(value['originals']['geometry'],4*1024**2))
        if (dataset['dataset_sha256']!=value['fit']['dataset_sha256'] or dataset['dataset_sha256']!=identity({k:v for k,v in dataset.items() if k!='dataset_sha256'}) or
            dataset['source_snapshot_sha256']!=value['fit']['source_snapshot_sha256'] or g['native_runtime']!=geometry.to_dict()['native_runtime']):raise ValueError('physical fitting source or solar runtime differs')
        models.append(value)
    return models


def run(*,stage,fit_index,archive_path,output_path,start,end):
    from native_irradiance_shade import NativeIrradianceShadeDynamics,RULE
    from household_cycle_pressure import PublicationHeadroom
    began=time.monotonic();pressure=PublicationHeadroom();root=Path(__file__).resolve().parents[2];sources=capture_sources(root)
    def guard():
        pressure.check()
        if time.monotonic()-began>550:raise TimeoutError('thermal comparison deadline elapsed')
    output=directory(output_path)
    with collector_lock(output/'comparison.lock'):
        data,originals,record=load_development(stage);guard();models=load_fits(fit_index,data.geometry)
        if len(models)!=12:raise ValueError('complete predeclared twelve-fit cadence schedule required')
        samples={instant(r['at']):r for r in data.to_dict()['samples']};archive=Archive.open_readonly(str(archive_path));pairs=[];sources_used=[];skipped={}
        with archive._connect() as c:refs=c.execute('SELECT digest FROM snapshots WHERE historical=1 AND initialized>=? AND initialized<? ORDER BY initialized,completed,digest',( (start-timedelta(hours=9)).isoformat(),end.isoformat())).fetchall()
        seen=set()
        for (ref,) in refs:
            guard();snapshot=verify_history(archive.read(ref));origin=instant(snapshot['initialized_at'])+timedelta(hours=9)
            if not start<=origin<end or origin in seen:continue
            seen.add(origin);initial=samples.get(origin)
            if initial is None or any(initial.get(k) is None for k in ACTIONS):skipped['origin_state_unavailable']=skipped.get('origin_state_unavailable',0)+1;continue
            hours={}
            for point in snapshot['points']:
                if point['statistic']=='mean':hours.setdefault(point['valid_at'],{})[point['variable']]=point['value']
            forecast=google_forcings(hours,origin=origin,actions={k:initial[k] for k in ACTIONS},horizon_hours=24)
            chosen={name:select_fit(models,origin=origin,cadence=cadence) for name,cadence in (('daily_physics','daily'),('six_hourly_physics','six_hourly'))}
            if any(value is None for value in chosen.values()):continue
            predictions={}
            for name,value in chosen.items():
                if value['fit']['model_rule']!=RULE:raise ValueError('physical model numerical rule differs')
                model=NativeIrradianceShadeDynamics(tuple(value['fit']['coefficients']),geometry=data.geometry,expected_series_sha256=data.geometry.sha256)
                predictions[name]=model.rollout(origin_at=origin,air_f=initial['air_f'],mass_f=initial['mass_f'],forcings=forecast,guard=guard).states
            for lead in (1,6,12,24):
                target=origin+timedelta(hours=lead);actual=samples.get(target)
                if actual is None:continue
                row=dict(origin=origin.isoformat(),target_at=target.isoformat(),lead_hours=lead,forecast_sha256=ref,
                    actual=[actual['air_f'],actual['mass_f']],action_stratum=action_stratum(samples,origin=origin,target=target),
                    origin_actions={k:initial[k] for k in ACTIONS},predictions={name:list(values[lead*12-1]) for name,values in predictions.items()},
                    fit_receipts={name:value['receipt_sha256'] for name,value in chosen.items()})
                row['predictions']['temperature_persistence']=[initial['air_f'],initial['mass_f']];row['pair_sha256']=identity(row);pairs.append(row)
            sources_used.append(ref)
        if not pairs:raise ValueError('later matched thermal outcomes required')
        now=datetime.now(timezone.utc);run=directory(output/('comparison-'+now.strftime('%Y%m%dT%H%M%S%fZ')));report=summarize(pairs)
        dataset=dict(schema='earthship-historical-thermal-comparison-data/v1',pairs=pairs,fit_sources=[dict(cutoff=v['cutoff'],receipt_sha256=v['receipt_sha256'],originals=v['originals']) for v in models],
            measurement_originals=originals,forecast_sha256s=sources_used,forecast_availability_basis='retrospective_assumed_full_cycle_9h',model_availability_basis='retrospective_assumed_cutoff_plus_10_minutes',
            action_state_basis='retained_collective_journal_not_individual_shade_sensors',current_selected_weights_used=False,prospective_score=False,automatic_actuation=False)
        dataset['dataset_sha256']=identity(dataset);save(run/'dataset.json',dataset)
        verify_sources(root,sources);manifest=retain_sources(run,sources)
        receipt=dict(schema='earthship-historical-thermal-cadence-comparison/v1',created_at=now.isoformat(),start=start.isoformat(),end=end.isoformat(),dataset_sha256=dataset['dataset_sha256'],report=report,skipped=skipped,
            fit_count=len(models),forecast_runs=len(sources_used),runtime_manifest=manifest,prospective_score=False,production_model_changed=False,automatic_actuation=False)
        receipt['receipt_sha256']=identity(receipt);save(run/'comparison.json',receipt);save(output/'last-comparison.json',dict(path=str(run),receipt_sha256=receipt['receipt_sha256']));return receipt


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('stage','fit-index','archive','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--start',required=True);p.add_argument('--end',required=True);a=p.parse_args(argv);os.umask(0o077)
    try:
        result=run(stage=a.stage,fit_index=a.fit_index,archive_path=a.archive,output_path=a.output,start=instant(a.start),end=instant(a.end))
        print(json.dumps(dict(status='thermal_cadence_assessed',report=result['report'],forecast_runs=result['forecast_runs'],production_model_changed=False)));return 0
    except Exception as error:
        import traceback
        directory(a.output);save(a.output/'last-error.json',dict(reason=type(error).__name__,message=str(error)[:2048],traceback=traceback.format_exc()[-8192:]))
        print(json.dumps(dict(status='thermal_comparison_incomplete',reason=type(error).__name__,production_model_changed=False)));return 1

if __name__=='__main__':raise SystemExit(main())
