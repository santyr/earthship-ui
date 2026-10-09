#!/usr/bin/env python3
"""Check private scoring settings or explicitly collect one mature horizon."""
import argparse
import json
import os
from pathlib import Path


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--collect',action='store_true')
    parser.add_argument('--origin',type=Path)
    parser.add_argument('--horizon',type=int,choices=(1,6,12,24))
    args=parser.parse_args(argv)
    if args.collect and (args.origin is None or args.horizon is None):parser.error('explicit original publication and mature horizon required')
    if not args.collect and (args.origin is not None or args.horizon is not None):parser.error('source reads require explicit --collect')
    try:
        if args.collect:
            from thermal_installed_intel import _resource_preflight
            _resource_preflight()
            os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        from thermal_model.installed_shade_score_inputs import load_score_settings,ScoreReader
        settings=load_score_settings(args.config)
        if not args.collect:
            print(json.dumps(dict(status='configuration_verified',collection_executed=False,release_authorized=False)));return 0
        from thermal_model.installed_shade_score_collection import collect_published_score
        result=collect_published_score(origin_path=args.origin,horizon_hours=args.horizon,
            output_directory=settings['output_directory'],backend=ScoreReader(settings))
        print(json.dumps(result,sort_keys=True));return 0 if result['status'] in ('scored','pending','busy') else 1
    except Exception:
        # Never emit credential/config/transport exception bytes or tracebacks.
        print(json.dumps(dict(status='withheld',collection_executed=False,release_authorized=False)));return 1


if __name__=='__main__':raise SystemExit(main())
