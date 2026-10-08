#!/usr/bin/env python3
"""Prepare or verify a private dependency mirror; never installs or executes it."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'openhab/scripts'))
from thermal_model.environment_bundle import prepare_environment_restore, verify_environment_restore


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True,type=Path)
    parser.add_argument('--destination',required=True,type=Path)
    parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args(argv)
    try:
        operation=verify_environment_restore if args.verify_only else prepare_environment_restore
        receipt=operation(args.bundle,args.destination)
    except (OSError,RuntimeError,TypeError,ValueError):
        print('thermal environment recovery refused; verify retained bundle and private destination',file=sys.stderr)
        return 2
    print(json.dumps(receipt,sort_keys=True,separators=(',',':')))
    return 0


if __name__=='__main__':raise SystemExit(main())
