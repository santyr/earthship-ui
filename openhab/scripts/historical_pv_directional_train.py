#!/usr/bin/env python3
"""Assess the fixed directional variant on an unchanged retained PV dataset."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,gzip,json,os
from weather_source_files import _read
from household_native_training import directory,save
from weather_learning.contracts import identity,instant
from weather_learning.pv_directional_calibration import fit_directional,assess_directional
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.worker import collector_lock


def run(state):
    state=Path(state);output=directory(state/'directional');root=Path(__file__).resolve().parents[2];sources=capture_sources(root)
    with collector_lock(output/'training.lock'):
        pointer=json.loads(_read(state/'last-experiment.json',8192));parent_path=Path(pointer['path']);parent=json.loads(_read(parent_path/'experiment.json',1048576))
        if parent['receipt_sha256']!=pointer['receipt_sha256'] or parent['receipt_sha256']!=identity({k:v for k,v in parent.items() if k!='receipt_sha256'}):raise ValueError('original PV experiment differs')
        data_path=parent_path/(parent['dataset_sha256']+'.pairs.json.gz')
        with gzip.open(data_path,'rb') as stream:raw=stream.read(32*1024**2+1)
        if len(raw)>32*1024**2:raise ValueError('bounded original PV dataset required')
        dataset=json.loads(raw)
        if dataset['dataset_sha256']!=parent['dataset_sha256'] or dataset['dataset_sha256']!=identity({k:v for k,v in dataset.items() if k!='dataset_sha256'}):raise ValueError('original PV paired data differ')
        start,end=map(instant,(parent['report']['holdout_start'],parent['report']['holdout_end']));now=datetime.now(timezone.utc)
        model=fit_directional(dataset['pairs'],cutoff=start,trained_at=now);report=assess_directional(model,dataset['pairs'],holdout_start=start,holdout_end=end)
        final=fit_directional(dataset['pairs'],cutoff=end,trained_at=now)
        run=directory(output/('experiment-'+now.strftime('%Y%m%dT%H%M%S%fZ')))
        save(run/'training-model.json',model);save(run/'final-model.json',final);save(run/'comparison.json',report)
        verify_sources(root,sources);runtime=retain_sources(run,sources)
        receipt=dict(schema='earthship-historical-pv-directional-experiment/v1',created_at=now.isoformat(),parent_experiment_path=str(parent_path),parent_receipt_sha256=parent['receipt_sha256'],dataset_sha256=parent['dataset_sha256'],
            final_model=final,training_model_sha256=model['model_sha256'],report=report,runtime_manifest=runtime,model_selection_scope='development_variant_on_retained_chronological_split_requires_prospective_monitoring',
            system_raw=dataset['system_raw'],horizon_raw=dataset['horizon_raw'],prospective_score=False,production_model_changed=False,automatic_actuation=False)
        receipt['receipt_sha256']=identity(receipt);save(run/'experiment.json',receipt);save(output/'last-experiment.json',dict(path=str(run),receipt_sha256=receipt['receipt_sha256']))
        return receipt


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,required=True);a=p.parse_args(argv);os.umask(0o077)
    result=run(a.state);print(json.dumps(dict(status='directional_pv_assessed',report=result['report'],sector_gains=result['final_model']['sectors'],production_model_changed=False)));return 0

if __name__=='__main__':raise SystemExit(main())
