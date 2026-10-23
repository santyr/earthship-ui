#!/usr/bin/env python3
"""Check an externally reviewed WeatherNext release; publish only explicitly."""
import argparse,json
from weather_learning.production_worker import run_worker


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--publish',action='store_true',help='requires reviewed release, source pins and exclusive ownership')
    parser.add_argument('--near-term-profile',help='explicit private optional near24 profile; core raw forecasts stay independent')
    args=parser.parse_args(argv)
    try:
        result=run_worker(args.config,publish=args.publish,near_term_config_path=args.near_term_profile)
        print(json.dumps(result,allow_nan=False));return 0 if result['status'] in ('PREFLIGHT_PASSED','PUBLISHED','WITHDRAWN') and result.get('production_retention_status')!='FAILED_AFTER_PUBLICATION' else 1
    except Exception as error:
        # Exception text can include private paths, configuration or tokens.
        print(json.dumps(dict(status='REFUSED',failure_kind=type(error).__name__,
            release_authorized=False,automatic_actuation=False)));return 1


if __name__=='__main__':raise SystemExit(main())
