#!/usr/bin/env python3
"""Recompute installed-domain qualification from private original evidence."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import json
import os
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'openhab/scripts'))


def _resource_preflight():
    from thermal_installed_intel import _resource_preflight as verify
    verify()


def _run(args,*,guard=lambda:None):
    guard()
    from thermal_model import installed_shade_qualification as qualification
    from thermal_model.policy_registration import _read_private
    pairs=[] if args.original_pairs is None else _read_private(args.original_pairs)
    profiles={1:(qualification.qualify_installed_shade_candidate,qualification.write_installed_shade_qualification_report),
        2:(qualification.qualify_calibrated_installed_shade_candidate,qualification.write_calibrated_installed_shade_qualification_report),
        3:(qualification.qualify_published_installed_shade_candidate,qualification.write_published_installed_shade_qualification_report),
        4:(qualification.qualify_raw_published_installed_shade_candidate,qualification.write_raw_published_installed_shade_qualification_report),
        5:(qualification.qualify_complete_raw_installed_shade_candidate,qualification.write_complete_raw_installed_shade_qualification_report),
        7:(qualification.qualify_compressed_installed_shade_candidate,qualification.write_compressed_installed_shade_qualification_report)}
    qualify,write=profiles[args.contract_version]
    guard()
    report=qualify(registration_path=args.registration,candidate_path=args.candidate,
        runtime_bundle_path=args.runtime_bundle,original_pairs=pairs,now=datetime.now(timezone.utc))
    guard();paths=write(args.output_dir,report);guard()
    print(json.dumps(dict(recommended_stage=report['recommended_stage'],
        forecast_qualified=report['forecast_qualified'],report_paths=list(map(str,paths)))))
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract-version',type=int,choices=(1,2,3,4,5,7),default=1)
    parser.add_argument('--registration',type=Path)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--runtime-bundle',type=Path)
    parser.add_argument('--original-pairs',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--shared-lock',type=Path)
    args=parser.parse_args(argv)
    if args.contract_version in (4,5,7) and args.shared_lock is None:parser.error('v4/v5/v7 require the existing shared consumer lock')
    if args.contract_version not in (4,5,7) and args.shared_lock is not None:parser.error('--shared-lock is reserved for the v4/v5/v7 raw-source profiles')
    if args.contract_version not in (4,5,7):return _run(args)
    saved={key:os.environ.get(key) for key in ('EARTHSHIP_QUALIFICATION_FIT','EARTHSHIP_REMOTE_QUALIFICATION_FIT')}
    try:
        _resource_preflight()
        os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        from thermal_model.capture_guard import SharedScoreLock
        with SharedScoreLock(args.shared_lock) as held:return _run(args,guard=held.verify)
    except BlockingIOError:
        print(json.dumps(dict(status='busy',release_authorized=False)));return 75
    except Exception:
        print(json.dumps(dict(status='withheld',release_authorized=False)));return 1
    finally:
        for key,value in saved.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


if __name__=='__main__':raise SystemExit(main())
