#!/usr/bin/env python3
"""Replay a compact battery score against its external original plan; offline only."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import sys
from household.codec import loads,canonical
from household.control_contracts import instant
from household.battery_outcomes import replay_battery_outcomes,MAX_SCORE_BYTES
from household_outcomes import outcome_runtime_manifest,original_plan_runtime
from household_pipeline import thermal_execution_runtime
from household_snapshot import _read


def battery_runtime_manifest():
    result=outcome_runtime_manifest();root=Path(__file__).resolve().parent
    for name in ('household_battery_outcomes.py','household_battery_source.py','household_battery_score.py'):
        result['openhab/scripts/'+name]=sha256(_read(root/name,262144)).hexdigest()
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',type=Path,required=True);parser.add_argument('--plan',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        raw=_read(args.receipt,MAX_SCORE_BYTES,private=True);source=_read(args.plan,2097152,private=True)
        record,plan=map(loads,(raw,source))
        if instant(record['inputs']['assessed_at'])>datetime.now(timezone.utc):raise ValueError('future assessment refused')
        runtime=battery_runtime_manifest();original=original_plan_runtime(plan,actual=runtime)
        thermal=thermal_execution_runtime(Path(__file__).resolve().parent,plan['inputs']['thermal_inputs'])
        result=replay_battery_outcomes(record,plan_receipt=plan,plan_runtime_manifest=original,outcome_runtime_manifest=runtime,thermal_runtime=thermal)
        if (battery_runtime_manifest()!=runtime or _read(args.receipt,MAX_SCORE_BYTES,private=True)!=raw or _read(args.plan,2097152,private=True)!=source or
            thermal_execution_runtime(Path(__file__).resolve().parent,plan['inputs']['thermal_inputs'])!=thermal):raise ValueError('original replay context changed')
        sys.stdout.buffer.write(canonical(result)+b'\n');return 0
    except Exception:
        print('Battery outcome replay refused: invalid or changed original context.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
