#!/usr/bin/env python3
"""Replay one private sealed shadow plan; stdout only, with no live readers."""
import argparse
from pathlib import Path
from hashlib import sha256
import sys
from household.codec import loads,canonical
from household.planning import replay_plan
from household_snapshot import _read,runtime_manifest


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',required=True,type=Path);args=parser.parse_args(argv)
    try:
        raw=_read(args.receipt,512*1024,private=True);record=loads(raw)
        expanded=record.get('schema') in ('earthship-household-shadow-plan-receipt/v2','earthship-household-shadow-plan-receipt/v3','earthship-household-shadow-plan-receipt/v4')
        if expanded:
            from household_pipeline import pipeline_runtime_manifest,verify_source_closure
            executing=pipeline_runtime_manifest(expanded=True,configured=record.get('schema')=='earthship-household-shadow-plan-receipt/v4')
            verify_source_closure(record,executing)
        else:
            executing=runtime_manifest()
            executing['openhab/scripts/household_plan.py']=sha256(_read(Path(__file__).resolve(),262144)).hexdigest()
        replayed=replay_plan(record,runtime_manifest=executing)
        if expanded:repeated=pipeline_runtime_manifest(expanded=True,configured=record.get('schema')=='earthship-household-shadow-plan-receipt/v4')
        else:
            repeated=runtime_manifest()
            repeated['openhab/scripts/household_plan.py']=sha256(_read(Path(__file__).resolve(),262144)).hexdigest()
        if repeated!=executing or _read(args.receipt,512*1024,private=True)!=raw:raise ValueError('original plan or executing runtime changed')
        sys.stdout.buffer.write(canonical(replayed)+b'\n');return 0
    except Exception:
        print('Household plan replay refused: invalid or changed original context.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
