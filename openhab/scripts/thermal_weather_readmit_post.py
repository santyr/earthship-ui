#!/usr/bin/env python3
"""Cold correction promotion after the existing weather owner; never train here.

The unchanged owner deadline includes this hook. Failure preserves its previous
compatible serving selector, because the trainer writes a separate candidate.
"""
from pathlib import Path
from hashlib import sha256
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time

from weather_source_files import _read

ROOT=Path(__file__).resolve().parents[2]
UNIT='local-forecast-train.service'
FIELDS={'schema','consumer_source_root','original_source_roots','candidate_selection','selection','output','worker_sha256'}


def remaining_budget(*,start_usec,now_monotonic,timeout_seconds):
    if (type(start_usec) is not int or start_usec<=0 or not math.isfinite(now_monotonic)
            or timeout_seconds!=960):return 0
    elapsed=now_monotonic-start_usec/1e6
    if elapsed<0:return 0
    available=min(90,math.floor(timeout_seconds-elapsed-15))
    return available if available>=25 else 0


def _metadata():
    raw=subprocess.check_output(['systemctl','--user','show',UNIT,'-p','ExecMainStartTimestampMonotonic','-p','TimeoutStartUSec'],text=True,timeout=3)
    values=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
    if values.get('TimeoutStartUSec')!='16min':raise ValueError('unchanged owner deadline required')
    value=values.get('ExecMainStartTimestampMonotonic','')
    if not value.isdecimal():raise ValueError('current owner start required')
    return int(value),960


def run(config_path,*,clock=time.monotonic,metadata=_metadata,execute=subprocess.run):
    config=json.loads(_read(config_path,16384))
    if (not isinstance(config,dict) or set(config)!=FIELDS or config['schema']!='earthship-thermal-weather-readmit-post/v1'
            or not isinstance(config['original_source_roots'],list) or not 1<=len(config['original_source_roots'])<=4
            or not isinstance(config['worker_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',config['worker_sha256'])):raise ValueError('closed owned post configuration required')
    paths=[config[k] for k in ('consumer_source_root','candidate_selection','selection','output')]+config['original_source_roots']
    if any(not isinstance(p,str) or not Path(p).is_absolute() or '..' in Path(p).parts for p in paths):raise ValueError('explicit absolute post paths required')
    if config['candidate_selection']==config['selection']:raise ValueError('candidate and serving selectors must be separate')
    worker=ROOT/'openhab/scripts/thermal_weather_readmit.py'
    if sha256(worker.read_bytes()).hexdigest()!=config['worker_sha256']:raise ValueError('exact reviewed cold worker required')
    start,timeout=metadata();budget=remaining_budget(start_usec=start,now_monotonic=clock(),timeout_seconds=timeout)
    if not budget:return dict(status='thermal_readmit_deferred_owner_deadline',automatic_actuation=False),75
    args=['/usr/bin/python3',str(ROOT/'scripts/run-household-job.py'),'--production','--minimum-mib','512','--preferred-mib','1024','--tasks','24','--seconds',str(budget-15),'--','/usr/bin/python3',str(worker),'--original-selection',config['candidate_selection'],'--consumer-source-root',config['consumer_source_root'],'--output',config['output'],'--selection',config['selection'],'--maximum-seconds',str(budget-20)]
    for path in config['original_source_roots']:args.extend(['--original-source-root',path])
    # Child diagnostics may name private paths; only curated status leaves here.
    result=execute(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=budget,check=False,
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT/'openhab/scripts'),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
    return dict(status='thermal_readmit_verified' if result.returncode==0 else 'thermal_readmit_unavailable_previous_preserved',automatic_actuation=False),result.returncode


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);a=p.parse_args(argv)
    try:report,code=run(a.config)
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):report,code=dict(status='thermal_readmit_unavailable_previous_preserved',automatic_actuation=False),1
    print(json.dumps(report),flush=True);return code


if __name__=='__main__':raise SystemExit(main())
