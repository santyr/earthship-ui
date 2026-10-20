#!/usr/bin/env python3
"""Evaluate the shared PV policy on retained horizon-assessment originals."""
from pathlib import Path
from datetime import datetime,timezone
from hashlib import sha256
from io import BytesIO
import argparse,gzip,json,os
from household_native_training import directory,save
from weather_source_files import _read
from weather_learning.contracts import identity,instant
from weather_learning.pv_horizon_assessment import assess_policy
from weather_learning.pv_calibration_policy import POLICY


def run(parent,output):
    pointer=json.loads(_read(Path(parent)/'last-experiment.json',8192));root=Path(pointer['path'])
    raw=_read(root/'experiment.json',1048576);experiment=json.loads(raw)
    if experiment.get('receipt_sha256')!=pointer['receipt_sha256'] or experiment['receipt_sha256']!=identity({k:v for k,v in experiment.items() if k!='receipt_sha256'}) or experiment['receipt_sha256']!=POLICY['assessment_sha256']:
        raise ValueError('original policy-development assessment required')
    model_raw=_read(root/'training-model.json',1048576);model=json.loads(model_raw)
    if model['model_sha256']!=experiment['report']['model_sha256']:raise ValueError('original earlier fitted model required')
    compressed=_read(root/(experiment['dataset_sha256']+'.pairs.json.gz'),32*1024**2)
    with gzip.GzipFile(fileobj=BytesIO(compressed)) as handle:data_raw=handle.read(32*1024**2+1)
    if len(data_raw)>32*1024**2:raise ValueError('bounded original PV pairs required')
    data=json.loads(data_raw)
    if data['dataset_sha256']!=experiment['dataset_sha256'] or data['dataset_sha256']!=identity({k:v for k,v in data.items() if k!='dataset_sha256'}):raise ValueError('original horizon pairs differ')
    report=assess_policy(model,data['pairs'],cutoff=instant(experiment['report']['holdout_start']),end=instant(experiment['report']['holdout_end']))
    scripts=Path(__file__).resolve().parent
    names=('historical_pv_policy_assess.py','weather_learning/pv_horizon_assessment.py','weather_learning/pv_calibration_policy.py','weather_learning/pv_directional_calibration.py','weather_learning/pv_calibration.py','weather_learning/contracts.py')
    originals={name:(scripts/name).read_bytes() for name in names};now=datetime.now(timezone.utc)
    value=dict(schema='earthship-pv-policy-experiment/v1',created_at=now.isoformat(),parent_experiment_sha256=experiment['receipt_sha256'],
        parent_experiment_file_sha256=sha256(raw).hexdigest(),training_model_file_sha256=sha256(model_raw).hexdigest(),dataset_file_sha256=sha256(compressed).hexdigest(),
        report=report,runtime_manifest={name:sha256(body).hexdigest() for name,body in originals.items()},automatic_actuation=False)
    value['receipt_sha256']=identity(value);output=directory(output);sources=directory(output/'sources')
    for name,body in originals.items():
        if (scripts/name).read_bytes()!=body:raise ValueError('policy runtime changed')
        target=sources/(sha256(body).hexdigest()+'.py')
        if target.exists():
            if _read(target,262144)!=body:raise ValueError('original policy source differs')
        else:target.write_bytes(body);target.chmod(0o600)
    save(output/(value['receipt_sha256']+'.experiment.json'),value);save(output/'last-experiment.json',value)
    return dict(receipt_sha256=value['receipt_sha256'],report=report)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',required=True,type=Path);p.add_argument('--output',required=True,type=Path);args=p.parse_args();os.umask(0o077)
    print(json.dumps(run(args.parent,args.output)))

if __name__=='__main__':main()
