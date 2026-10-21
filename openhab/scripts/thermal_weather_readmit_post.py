#!/usr/bin/env python3
"""Cold correction promotion after the existing weather owner; never train here.

The unchanged owner deadline includes child execution and bounded readback.
Process termination does not establish whether a selector was published.
"""
from datetime import datetime,timezone
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


def _selector_bytes(path):
    try:return _read(path,16384)
    except FileNotFoundError:return None


def _identity(raw):
    return None if raw is None else sha256(raw).hexdigest()


def _uncertain(**fields):
    return dict(status='thermal_readmit_selection_uncertain',selection_outcome='unknown',
        automatic_actuation=False,**fields)


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
    try:before=_selector_bytes(config['selection'])
    except (OSError,ValueError):return _uncertain(execution_status='not_started',reason='selector_unreadable_before'),1
    # Recompute after the pre-read; the child never borrows readback/cleanup time.
    budget=remaining_budget(start_usec=start,now_monotonic=clock(),timeout_seconds=timeout)
    if not budget:return dict(status='thermal_readmit_deferred_owner_deadline',automatic_actuation=False),75
    readback_deadline=min(start/1e6+timeout-5,clock()+budget+10)
    def guard():
        if clock()>=readback_deadline:raise TimeoutError('post readback deadline elapsed')
    args=['/usr/bin/python3',str(ROOT/'scripts/run-household-job.py'),'--production','--minimum-mib','512','--preferred-mib','1024','--tasks','24','--seconds',str(budget-15),'--','/usr/bin/python3',str(worker),'--original-selection',config['candidate_selection'],'--consumer-source-root',config['consumer_source_root'],'--output',config['output'],'--selection',config['selection'],'--maximum-seconds',str(budget-20)]
    for path in config['original_source_roots']:args.extend(['--original-source-root',path])
    # Child diagnostics may name private paths; only curated evidence leaves here.
    execution='failed';code=1;child_exit=None
    try:
        result=execute(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=budget,check=False,
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT/'openhab/scripts'),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
        code=result.returncode;child_exit=code;execution='succeeded' if code==0 else 'failed'
    except subprocess.TimeoutExpired:code=124;execution='timed_out'
    except KeyboardInterrupt:code=130;execution='cancelled'
    except (OSError,ValueError,subprocess.SubprocessError):execution='launch_or_execution_failed'
    fields=dict(execution_status=execution,child_exit_code=child_exit,selection_before_sha256=_identity(before))
    try:
        guard();after=_selector_bytes(config['selection']);guard()
    except (OSError,ValueError):return _uncertain(**fields,reason='selector_readback_unavailable'),code or 1
    fields['selection_after_sha256']=_identity(after)
    if after==before:
        # This is a byte-preservation claim only. An unchanged expired/absent
        # admission is not labelled usable, nor attributed to a successful child.
        return dict(status='thermal_readmit_unchanged',selection_outcome='unchanged',
            selection_present=after is not None,automatic_actuation=False,**fields),code
    try:
        from thermal_weather_readmit import verify_selected_compatibility
        evidence=verify_selected_compatibility(selection=config['selection'],consumer_source_root=config['consumer_source_root'],
            expected_selector_raw=after,worker_sha256=config['worker_sha256'],now=datetime.now(timezone.utc),guard=guard)
        guard()
    except (OSError,ValueError,TypeError,KeyError):
        report=_uncertain(**fields,reason='selected_admission_not_verified');report['selection_outcome']='changed_unverified'
        return report,code or 1
    return dict(status='thermal_readmit_selection_changed_verified',selection_outcome='changed_verified',
        selection_writer='unattributed',automatic_actuation=False,**fields,**evidence),code


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);a=p.parse_args(argv)
    try:report,code=run(a.config)
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):report,code=_uncertain(execution_status='not_observed',reason='post_unavailable'),1
    print(json.dumps(report),flush=True);return code


if __name__=='__main__':raise SystemExit(main())
