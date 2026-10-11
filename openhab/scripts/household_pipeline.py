#!/usr/bin/env python3
"""Rederive a private model/plan receipt; no live readers or action transport."""
import argparse
from pathlib import Path
from hashlib import sha256
import sys
from household.codec import loads,canonical
from household.pipeline import replay_pipeline,MAX_BYTES
from household_snapshot import _read,runtime_manifest
from household.thermal_model import _execution_runtime


def pipeline_runtime_manifest():
    result=runtime_manifest();root=Path(__file__).resolve().parent
    for name in ('household_plan.py','household_pipeline.py','forecast_intel.py'):
        result['openhab/scripts/'+name]=sha256(_read(root/name,262144)).hexdigest()
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',required=True,type=Path);args=parser.parse_args(argv)
    try:
        raw=_read(args.receipt,MAX_BYTES,private=True);record=loads(raw)
        executing=pipeline_runtime_manifest();root=Path(__file__).resolve().parent
        thermal=_execution_runtime(root) if record['inputs']['thermal_inputs'] is not None else None
        replayed=replay_pipeline(record,runtime_manifest=executing,thermal_runtime=thermal)
        repeated_thermal=_execution_runtime(root) if thermal is not None else None
        if (pipeline_runtime_manifest()!=executing or canonical(repeated_thermal)!=canonical(thermal) or
            _read(args.receipt,MAX_BYTES,private=True)!=raw):raise ValueError('original or executing model/plan runtime changed')
        sys.stdout.buffer.write(canonical(replayed)+b'\n');return 0
    except Exception:
        print('Household model/plan replay refused: invalid or changed original context.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
