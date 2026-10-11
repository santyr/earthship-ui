#!/usr/bin/env python3
"""Replay private declared resource analysis; no live reader or action transport."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import sys
from household.codec import loads,canonical
from household.control_contracts import instant
from household.resources import replay_resources,MAX_BYTES
from household_snapshot import _read
from household_outcomes import outcome_runtime_manifest,original_plan_runtime


def resource_runtime_manifest():
    result=outcome_runtime_manifest();path=Path(__file__).resolve()
    result['openhab/scripts/household_resources.py']=sha256(_read(path,262144)).hexdigest()
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        raw=_read(args.receipt,MAX_BYTES,private=True);record=loads(raw)
        if instant(record['inputs']['assessed_at'])>datetime.now(timezone.utc):raise ValueError('future analysis refused')
        executing=resource_runtime_manifest();plan=original_plan_runtime(record['inputs']['plan_receipt'],actual=executing)
        replayed=replay_resources(record,plan_runtime_manifest=plan,analysis_runtime_manifest=executing)
        if resource_runtime_manifest()!=executing or _read(args.receipt,MAX_BYTES,private=True)!=raw:
            raise ValueError('original analysis or executing runtime changed')
        sys.stdout.buffer.write(canonical(replayed)+b'\n');return 0
    except Exception:
        print('Household resource replay refused: invalid or changed original context.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
