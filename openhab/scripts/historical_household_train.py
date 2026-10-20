#!/usr/bin/env python3
"""Chronological AC-demand, apparent-capacity and conversion experiments."""
from datetime import datetime,timezone
from pathlib import Path
import argparse,json,os,time
from household_native_training import directory,save
from historical_pv_train import energy_bins
from weather_learning.contracts import identity,instant
from weather_learning.household_calibration import hourly_from_bins,fit_load_adjustment,assess_load_adjustment,fit_storage,assess_storage,fit_conversion
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.worker import collector_lock


def run(*,energy_path,output_path,train_end,holdout_end):
    from household_cycle_pressure import PublicationHeadroom
    root=Path(__file__).resolve().parents[2];sources=capture_sources(root);output=directory(output_path);started=time.monotonic();pressure=PublicationHeadroom()
    def guard():
        pressure.check()
        if time.monotonic()-started>550:raise TimeoutError('historical household training deadline elapsed')
    with collector_lock(output/'training.lock'):
        bins,index=energy_bins(energy_path,guard);rows=hourly_from_bins(bins);now=datetime.now(timezone.utc)
        run=directory(output/('experiment-'+now.strftime('%Y%m%dT%H%M%S%fZ')));reports={};models={}
        nominal=index['bank']['nominal_usable_kwh']
        for kind in ('load','storage','conversion'):
            guard()
            try:
                def fit(cutoff):
                    if kind=='load':return fit_load_adjustment(rows,cutoff=cutoff,trained_at=now)
                    if kind=='storage':return fit_storage(rows,cutoff=cutoff,trained_at=now,nominal_kwh=nominal)
                    return fit_conversion(rows,cutoff=cutoff,trained_at=now)
                model=fit(train_end)
                if kind=='load':report=assess_load_adjustment(model,rows,start=train_end,end=holdout_end)
                elif kind=='storage':report=assess_storage(model,rows,start=train_end,end=holdout_end)
                else:
                    held=[r for r in rows if train_end<=instant(r['start']) and instant(r['end'])<=holdout_end and r['pv_input_kwh'] is not None and r['pv_output_kwh'] is not None and r['pv_input_kwh']>=.1]
                    from math import fsum
                    mae=lambda gain:None if not held else fsum(abs(r['pv_input_kwh']*gain-r['pv_output_kwh']) for r in held)/len(held)
                    report=dict(pairs=len(held),baseline_mae_kwh=mae(1),candidate_mae_kwh=mae(model['input_to_output_gain']),target=model['target'],forecasts_battery_acceptance=False,prospective_score=False,automatic_actuation=False)
                report.update(status='assessed',training_model_sha256=model['model_sha256'])
                final=fit(holdout_end);models[kind]=final['model_sha256'];save(run/(kind+'.training-model.json'),model);save(run/(kind+'.final-model.json'),final)
            except ValueError as error:
                if str(error) not in ('earlier qualified DC/SoC change windows required','earlier qualified simultaneous PV input and output required','earlier qualified load hours required','earlier chronological load validation required'):raise
                report=dict(status='unsupported',reason=str(error),automatic_actuation=False)
            reports[kind]=report
            print(json.dumps(dict(status='historical_household_case',kind=kind,report=report)),flush=True)
        verify_sources(root,sources);manifest=retain_sources(run,sources)
        import earthship_energy.power_evidence as companion
        from hashlib import sha256
        for name in ('power_evidence.py','power_intervals.py','bms_evidence.py','ac_evidence.py'):
            raw=(Path(companion.__file__).parent/name).read_bytes();path=run/'sources/companion/earthship_energy'/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);path.write_bytes(raw);path.chmod(0o600);manifest['companion/earthship_energy/'+name]=sha256(raw).hexdigest()
        dataset=dict(schema='earthship-historical-household-dataset/v1',hours=rows,energy_index=index,prospective_score=False,automatic_actuation=False);dataset['dataset_sha256']=identity(dataset);save(run/'dataset.json',dataset)
        receipt=dict(schema='earthship-historical-household-experiment/v1',created_at=now.isoformat(),train_end=train_end.isoformat(),holdout_end=holdout_end.isoformat(),
            bank=index['bank'],energy_hours=len(rows),dataset_sha256=dataset['dataset_sha256'],final_models=models,reports=reports,runtime_manifest=manifest,prospective_score=False,production_model_changed=False,automatic_actuation=False)
        receipt['receipt_sha256']=identity(receipt);save(run/'experiment.json',receipt);save(output/'last-experiment.json',dict(path=str(run),receipt_sha256=receipt['receipt_sha256']));guard();return receipt


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('energy','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--train-end',required=True);p.add_argument('--holdout-end',required=True);a=p.parse_args(argv);os.umask(0o077)
    try:
        value=run(energy_path=a.energy,output_path=a.output,train_end=instant(a.train_end),holdout_end=instant(a.holdout_end))
        print(json.dumps(dict(status='historical_household_training_complete',energy_hours=value['energy_hours'],receipt_sha256=value['receipt_sha256'],production_model_changed=False)),flush=True);return 0
    except Exception as error:
        import traceback
        directory(a.output);save(a.output/'last-error.json',dict(reason=type(error).__name__,message=str(error)[:2048],traceback=traceback.format_exc()[-8192:]))
        print(json.dumps(dict(status='historical_household_training_incomplete',reason=type(error).__name__,production_model_changed=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
