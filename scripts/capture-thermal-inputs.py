#!/usr/bin/env python3
"""Capture private pre-fit thermal inputs with bounded, read-only backends."""
import argparse
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'openhab/scripts'))
from thermal_model.capture_guard import run_guarded_capture,verify_resource_limits

FIELDS={'start','end','openhab_base','token_file','journal_dsn_file','native_db_config','native_policy','native_cutover'}
RECEIPT_FIELDS={'status','snapshot_sha256','collection_code_revision','fitting_executed','installed','release_authorized'}
READ_SECONDS=70


def _context(path,destination,*,receipt_version=1):
    from thermal_model.forcing_capture import _private_directory
    from thermal_model.runtime_bundle import _owned_bytes
    from thermal_model.origin_capture import _object
    from thermal_model.capture_readers import BASES,bounded_journal_dsn
    from thermal_model.training_inputs import _window,ITEMS
    from thermal_model.temperature_history import STREAMS,STEP,_ceil,POLICY
    from hourly_temperature_runtime import read_db_config
    from weather_temperature_config import load_temperature_policies,load_temperature_receiver_configuration
    from dataclasses import asdict
    from thermal_model.graduation_policy import _utc
    path=Path(path);root=_private_directory(Path(destination));_private_directory(path.parent)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved private capture config required')
    raw=_owned_bytes(path,8192)
    def reject(_):raise ValueError('nonfinite capture configuration')
    config=json.loads(raw,object_pairs_hook=_object,parse_constant=reject)
    if (not isinstance(config,dict) or set(config)!=FIELDS or
            any(not isinstance(value,str) or not 1<=len(value)<=1024 for value in config.values()) or config['openhab_base'] not in BASES):
        raise ValueError('closed bounded capture configuration required')
    if any(root.iterdir()):raise ValueError('new empty private capture destination required')
    if root==path.parent or path.is_relative_to(root):raise ValueError('capture output must be separate from configuration')
    for key in ('token_file','journal_dsn_file','native_db_config','native_policy'):
        source=Path(config[key])
        if not source.is_absolute() or source.resolve()!=source:raise ValueError('resolved capture source configuration required')
        _private_directory(source.parent)
        _owned_bytes(source,8192 if key=='native_policy' else 4096)
    token=_owned_bytes(Path(config['token_file']),4096).decode().strip()
    if not token or any(ord(char)<32 for char in token):raise ValueError('bounded private token required')
    bounded_journal_dsn(_owned_bytes(Path(config['journal_dsn_file']),4096).decode().strip())
    read_db_config(config['native_db_config'])
    if receipt_version==2:
        policies,epochs=load_temperature_receiver_configuration(config['native_policy'])
        if epochs is None:raise ValueError('explicit v2 capture policy required')
    else:policies=load_temperature_policies(config['native_policy'])
    for stream,model,sensor in STREAMS.values():
        if stream not in policies or asdict(policies[stream])!=dict(model=model,sensor_id=sensor,**POLICY):
            raise ValueError('fixed native capture policy required')
    start,end,cutover=map(_utc,(config['start'],config['end'],config['native_cutover']))
    now=datetime.now(timezone.utc);_window(start,end,now)
    if cutover!=_ceil(cutover) or cutover>now:raise ValueError('elapsed aligned native cutover required')
    days=lambda interval:max(0,math.ceil(interval/timedelta(days=1)))
    first=_ceil(max(start,cutover));targets=max(0,math.ceil((end-first)/STEP))
    requests=(len(ITEMS)-len(STREAMS))*days(end-start)+len(STREAMS)*(days(min(end,cutover)-start)+math.ceil(targets/288))+2
    if requests>=READ_SECONDS:raise ValueError('capture interval cannot fit shared request budget')
    return config,root,sha256(raw).hexdigest()


def _capture_revision():
    from thermal_intel import _release_runtime_paths
    from thermal_model.origin_capture import _source_bytes
    names=['openhab/scripts/'+name for name in _release_runtime_paths()]
    names+=['openhab/scripts/thermal_model/'+name+'.py' for name in ('training_inputs','capture_guard','capture_readers','capture_backends','environment_bundle','rollback')]
    names+=['scripts/capture-thermal-inputs.py','openhab/scripts/thermal_model/training_pressure_guard.py','openhab/scripts/thermal_installed_intel.py']
    digest=sha256()
    for name in dict.fromkeys(names):
        raw=_source_bytes(ROOT/name,maximum=2000000);encoded=name.encode()
        digest.update(len(encoded).to_bytes(4,'big'));digest.update(encoded)
        digest.update(len(raw).to_bytes(8,'big'));digest.update(raw)
    return digest.hexdigest()


def _worker(config,root,*,receipt_version=1):
    from thermal_model.capture_readers import ReadBudget,BoundedJDBCReader
    from thermal_model.capture_backends import configured_capture_history,configured_capture_history_v2,configured_capture_journal
    from thermal_model.training_inputs import capture_training_inputs,write_training_inputs,capture_training_inputs_v2,write_training_inputs_v2
    from thermal_model.runtime_bundle import _owned_bytes,_write_private,_sync_directory
    from thermal_model.forcing_capture import _canonical
    from thermal_model.graduation_policy import _utc
    clock=datetime.now(timezone.utc);revision=_capture_revision();budget=ReadBudget(READ_SECONDS,max_requests=READ_SECONDS)
    legacy=BoundedJDBCReader(base=config['openhab_base'],token_reader=lambda:_owned_bytes(Path(config['token_file']),4096).decode().strip(),budget=budget)
    history_builder=configured_capture_history_v2 if receipt_version==2 else configured_capture_history
    native=history_builder(legacy,clock,environ=dict(THERMAL_TEMP_QUALIFIED_ENABLE='1',
        THERMAL_TEMP_EVIDENCE_CUTOVER=config['native_cutover'],THERMAL_TEMP_DB_CONFIG=config['native_db_config'],THERMAL_TEMP_POLICY=config['native_policy']),budget=budget)
    journal=configured_capture_journal(dsn=_owned_bytes(Path(config['journal_dsn_file']),4096).decode().strip(),budget=budget)
    capture=capture_training_inputs_v2 if receipt_version==2 else capture_training_inputs
    writer=write_training_inputs_v2 if receipt_version==2 else write_training_inputs
    record=capture(start=_utc(config['start']),end=_utc(config['end']),series_reader=native,journal=journal,clock=lambda:clock,revision_reader=lambda:revision)
    if _capture_revision()!=revision:raise ValueError('capture code changed during collection')
    writer(root,record)
    receipt={key:record[key] for key in RECEIPT_FIELDS-{'status'}};receipt['status']='inputs_captured'
    _write_private(root/'capture-receipt.json',_canonical(receipt));_sync_directory(root)


def _pressure_preflight():
    from thermal_installed_intel import _resource_preflight
    _resource_preflight()


def _run_pressure_worker(argv,*,seconds):
    from thermal_model.training_pressure_guard import run_collection_worker
    return run_collection_worker(argv,seconds=seconds)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path)
    parser.add_argument('--destination',required=True,type=Path)
    parser.add_argument('--check-only',action='store_true')
    parser.add_argument('--pressure-aware',action='store_true',help='explicit 256 MiB pressure-supervised acquisition profile')
    parser.add_argument('--receipt-version',type=int,choices=(1,2),default=1)
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--expected-config-digest',help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    try:
        if not args.check_only and os.environ.get('EARTHSHIP_THERMAL_INPUT_CAPTURE')!='1':raise ValueError('explicit capture intent required')
        verify_resource_limits()
        if args.pressure_aware:_pressure_preflight()
        if args.worker and (args.check_only or os.environ.get('EARTHSHIP_GUARDED_CAPTURE_WORKER')!='1' or
                            os.environ.get('EARTHSHIP_REMOTE_QUALIFICATION_FIT')!='0' or
                            os.environ.get('EARTHSHIP_QUALIFICATION_FIT','0')!='0' or os.getpriority(os.PRIO_PROCESS,0)<15):
            raise ValueError('guarded capture worker context required')
        config,root,digest=_context(args.config,args.destination,receipt_version=args.receipt_version)
        if args.check_only:receipt=dict(status='capture_config_verified',release_authorized=False)
        elif args.worker:
            if args.expected_config_digest!=digest:raise ValueError('capture configuration changed')
            _worker(config,root,receipt_version=args.receipt_version);return 0
        else:
            worker=[sys.executable,str(Path(__file__).resolve()),'--config',str(args.config),
                '--destination',str(root),'--receipt-version',str(args.receipt_version),'--worker','--expected-config-digest',digest]
            if args.pressure_aware:worker+=['--pressure-aware']
            run=_run_pressure_worker if args.pressure_aware else run_guarded_capture
            status=run(worker,seconds=90)
            if status!=0:raise ValueError('capture worker refused')
            from thermal_model.runtime_bundle import _owned_bytes
            from thermal_model.origin_capture import _object
            from thermal_model.graduation_policy import _sha
            receipt=json.loads(_owned_bytes(root/'capture-receipt.json',2048),object_pairs_hook=_object)
            if (set(receipt)!=RECEIPT_FIELDS or receipt['status']!='inputs_captured' or
                    any(receipt[key] is not False for key in ('fitting_executed','installed','release_authorized'))):raise ValueError('closed capture receipt required')
            _sha(receipt['snapshot_sha256']);_sha(receipt['collection_code_revision'])
    except (OSError,RuntimeError,TypeError,ValueError):
        print('thermal input capture refused; check private configuration, source permissions, caps and bounded interval',file=sys.stderr)
        return 2
    print(json.dumps(receipt,sort_keys=True,separators=(',',':')))
    return 0


if __name__=='__main__':raise SystemExit(main())
