#!/usr/bin/env python3
"""Explicit capped provisional thermal training, publication, scoring and withdrawal."""
import argparse
import json
import os
from pathlib import Path
import sys
from thermal_installed_intel import _resource_preflight


def _train_worker(path):
    dispatched=False
    try:
        _resource_preflight()
        from datetime import datetime,timezone
        from thermal_model.policy_registration import _read_private
        from thermal_model.forcing_capture import _canonical,_private_directory
        from thermal_model.capture_guard import SharedScoreLock
        from thermal_model.training_inputs import read_training_inputs_v2
        from thermal_model.provisional_artifact import build_candidate,write_candidate,source_digest
        from thermal_model.provisional_fit import fit_inputs
        from thermal_model.provisional_live import current_runtime
        value=_read_private(Path(path))
        fields={'schema','snapshot_path','snapshot_sha256','sensor_epochs','training_start','training_end','initial_coefficients','output_directory','shared_lock'}
        if not isinstance(value,dict) or set(value)!=fields or value['schema']!='earthship-provisional-thermal-training-config/v1':raise ValueError('closed provisional training configuration required')
        _private_directory(Path(value['output_directory']))
        with SharedScoreLock(value['shared_lock']) as lock:
            runtime=current_runtime();before=source_digest(value['snapshot_path'])
            record=read_training_inputs_v2(Path(value['snapshot_path']))
            os.environ['EARTHSHIP_QUALIFICATION_FIT']='1';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
            dispatched=True
            fit=fit_inputs(record,expected_snapshot_sha256=value['snapshot_sha256'],sensor_epochs=value['sensor_epochs'],assessed_at=datetime.now(timezone.utc),
                training_start=value['training_start'],training_end=value['training_end'],initial=tuple(value['initial_coefficients']),timeout_seconds=60)
            os.environ['EARTHSHIP_QUALIFICATION_FIT']='0'
            lock.verify()
            if source_digest(value['snapshot_path'])!=before or _canonical(runtime)!=_canonical(current_runtime()) or _read_private(Path(path))!=value:
                raise ValueError('original provisional training inputs changed')
            candidate=build_candidate(fit,runtime=runtime,snapshot_path=Path(value['snapshot_path']),created_at=datetime.now(timezone.utc))
            output=write_candidate(Path(value['output_directory']),candidate,assessed_at=datetime.now(timezone.utc))
        print(json.dumps(dict(status='provisional_model',candidate_path=str(output),artifact_sha256=candidate['artifact_sha256'],fit_executed=True,graduated=False,automatic_actuation=False)))
        return 0
    except BlockingIOError:
        print(json.dumps(dict(status='busy',fit_executed=False,graduated=False)));return 75
    except Exception:
        print(json.dumps(dict(status='withheld',fit_executed=None if dispatched else False,graduated=False)));return 1
    finally:
        os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True,type=Path)
    intent=parser.add_mutually_exclusive_group()
    for name in ('publish','score','withdraw','train'):intent.add_argument('--'+name,action='store_true')
    args=parser.parse_args(argv)
    try:
        _resource_preflight()
        os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        if args.train:
            from thermal_model.training_pressure_guard import TrainingHeadroom,run_training_worker
            monitor=TrainingHeadroom(max_swapin_bytes_per_second=1048576);monitor.preflight()
            status,raw=run_training_worker([sys.executable,'-c','from provisional_thermal import _train_worker; import sys; raise SystemExit(_train_worker(sys.argv[1]))',str(args.config)],
                check=monitor.check,seconds=85,env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parent)))
            if status<0:raise ValueError('provisional training worker stopped')
            print(json.dumps(json.loads(raw),sort_keys=True));return status
        from thermal_model.provisional_live import load_settings,publish_cycle,withdraw
        from thermal_model.capture_guard import SharedScoreLock
        from thermal_model.policy_registration import _read_private
        from thermal_model.training_pressure_guard import TrainingHeadroom
        settings=load_settings(args.config,withdraw=args.withdraw)
        if not any((args.publish,args.score,args.withdraw)):
            print(json.dumps(dict(status='configuration_verified',publication_executed=False,fit_executed=False,graduated=False)));return 0
        with SharedScoreLock(settings['shared_lock']) as lock:
            monitor=TrainingHeadroom(max_swapin_bytes_per_second=1048576)
            def guard():
                lock.verify();monitor.check()
                if _read_private(args.config)!=settings:raise ValueError('original provisional configuration changed')
            if args.withdraw:result=withdraw(settings,guard=guard)
            elif args.score:
                from thermal_model.provisional_monitor import score_jobs
                result=score_jobs(settings,guard=guard)
            else:
                try:result=publish_cycle(settings,guard=guard)
                except Exception:
                    try:result=withdraw(settings,guard=guard);result['status']='withheld_and_withdrawn'
                    except Exception:result=dict(status='withheld',delivery_verified=False,automatic_actuation=False)
            print(json.dumps(result,sort_keys=True))
            return 0 if result['status'] in ('published','deferred','withdrawn','scored','waiting') else 1
    except BlockingIOError:
        print(json.dumps(dict(status='busy',publication_executed=False,fit_executed=False,automatic_actuation=False)));return 75
    except Exception:
        print(json.dumps(dict(status='withheld',publication_executed=False,fit_executed=False,automatic_actuation=False)));return 1


if __name__=='__main__':raise SystemExit(main())
