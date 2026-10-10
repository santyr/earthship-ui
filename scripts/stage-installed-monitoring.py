#!/usr/bin/env python3
"""Write disabled registered monitoring units into an existing empty private directory."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'openhab/scripts'))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('sources','live-config','score-config','registration','release-reference','shared-lock'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    from thermal_model.installed_shade_schedule import stage_registered_monitoring_units,FIELDS
    try:
        values={name:getattr(args,name) for name in FIELDS}
        manifest=stage_registered_monitoring_units(template_directory=Path(__file__).resolve().parents[1]/'openhab/systemd/user',operands=values,output_directory=args.output_dir)
        print(json.dumps(dict(status='staged_for_review',unit_count=len(manifest['units']),release_authorized=False,services_enabled_by_stage=False)));return 0
    except Exception:
        print(json.dumps(dict(status='staging_refused',release_authorized=False,services_enabled_by_stage=False)));return 1


if __name__=='__main__':raise SystemExit(main())
