#!/usr/bin/env python3
"""Check private offline build settings or explicitly fit an installed-shade candidate."""
import argparse
import json
from pathlib import Path


def _resource_preflight():
    from thermal_installed_intel import _resource_preflight as strict_caps
    from thermal_model.capture_guard import verify_host_headroom
    strict_caps()
    verify_host_headroom()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--fit',action='store_true')
    args=parser.parse_args(argv)
    dispatched=False
    try:
        if args.fit:_resource_preflight()
        from thermal_model.installed_shade_training import load_training_settings
        settings=load_training_settings(args.config)
        if not args.fit:
            print(json.dumps(dict(status='configuration_verified',fit_executed=False,release_authorized=False)))
            return 0
        from thermal_model.capture_guard import SharedScoreLock
        with SharedScoreLock(settings['shared_lock']) as held:
            from thermal_model.installed_shade_training import run_candidate_training
            dispatched=True
            result=run_candidate_training(settings,guard=held.verify)
        print(json.dumps(result,sort_keys=True));return 0
    except BlockingIOError:
        print(json.dumps(dict(status='busy',fit_executed=False,release_authorized=False)));return 75
    except Exception:
        print(json.dumps(dict(status='withheld',fit_executed=None if dispatched else False,release_authorized=False)));return 1


if __name__=='__main__':raise SystemExit(main())
