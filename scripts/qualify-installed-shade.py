#!/usr/bin/env python3
"""Recompute installed-domain qualification from private original evidence."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'openhab/scripts'))
from thermal_model.installed_shade_qualification import (
    qualify_installed_shade_candidate,write_installed_shade_qualification_report,
    qualify_calibrated_installed_shade_candidate,write_calibrated_installed_shade_qualification_report)
from thermal_model.policy_registration import _read_private


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract-version',type=int,choices=(1,2),default=1)
    parser.add_argument('--registration',type=Path)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--runtime-bundle',type=Path)
    parser.add_argument('--original-pairs',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    pairs=[] if args.original_pairs is None else _read_private(args.original_pairs)
    qualify=qualify_calibrated_installed_shade_candidate if args.contract_version==2 else qualify_installed_shade_candidate
    write=write_calibrated_installed_shade_qualification_report if args.contract_version==2 else write_installed_shade_qualification_report
    report=qualify(registration_path=args.registration,
        candidate_path=args.candidate,runtime_bundle_path=args.runtime_bundle,
        original_pairs=pairs,now=datetime.now(timezone.utc))
    paths=write(args.output_dir,report)
    print(json.dumps(dict(recommended_stage=report['recommended_stage'],
        forecast_qualified=report['forecast_qualified'],report_paths=list(map(str,paths)))))
    return 0


if __name__=='__main__':raise SystemExit(main())
