#!/usr/bin/env python3
"""Prepare verified shadow recovery files; does not install, publish or restart."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'openhab/scripts'))
from thermal_model.rollback import REASONS, prepare_restore, verify_prepared_restore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--reason', required=True, choices=sorted(REASONS))
    parser.add_argument('--verify-only', action='store_true', help='recheck existing recovery files without writing')
    args = parser.parse_args(argv)
    try:
        if args.verify_only:
            receipt = verify_prepared_restore(args.snapshot, args.destination)
            if receipt['reason'] != args.reason:
                raise ValueError('recovery reason differs')
        else:
            receipt = prepare_restore(args.snapshot, args.destination, reason=args.reason)
    except (OSError, RuntimeError, TypeError, ValueError):
        print('thermal recovery preparation refused; validate snapshot and compatible environment', file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
