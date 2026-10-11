#!/usr/bin/env python3
"""Replay one private chronological score; no live readers or action transport."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import sys
from household.codec import loads,canonical
from household.outcomes import replay_outcomes,MAX_BYTES
from household.control_contracts import instant
from household.thermal_model import _execution_runtime
from household_snapshot import _read,VALIDATORS
from household_pipeline import pipeline_runtime_manifest

PLAN_MODULES=('__init__','adapters','capabilities','capture','codec','control_contracts','energy_model',
              'evidence','intents','pipeline','planning','replay','snapshot','thermal_model')


def outcome_runtime_manifest():
    result=pipeline_runtime_manifest();path=Path(__file__).resolve()
    result['openhab/scripts/household_outcomes.py']=sha256(_read(path,262144)).hexdigest()
    return result


def original_plan_runtime(plan,*,actual):
    # Verify the full original plan closure. Additional observational modules may
    # be installed later without pretending they existed in an earlier receipt.
    required={'openhab/scripts/'+name for name in VALIDATORS}
    required.update('openhab/scripts/household/'+name+'.py' for name in PLAN_MODULES)
    required.update('openhab/scripts/'+name for name in ('household_snapshot.py','household_capture.py',
        'household_plan.py','household_pipeline.py','forecast_intel.py','hourly_temperature_runtime.py'))
    required.update(('companion/earthship_energy/db.py','companion/earthship_energy/bms_evidence.py',
        'openhab/managed-resources.json','openhab/file-config/ownership.json'))
    expected=plan['runtime_manifest']
    if (not isinstance(expected,dict) or not required<=set(expected) or not set(expected)<=set(actual) or
        any(sha!=actual[name] for name,sha in expected.items())):
        raise ValueError('complete original plan execution closure differs')
    return dict(expected)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        raw=_read(args.receipt,MAX_BYTES,private=True);record=loads(raw)
        if instant(record['inputs']['assessed_at'])>datetime.now(timezone.utc):raise ValueError('future outcome assessment refused')
        executing=outcome_runtime_manifest();plan=original_plan_runtime(record['inputs']['plan_receipt'],actual=executing)
        root=Path(__file__).resolve().parent;thermal=_execution_runtime(root)
        replayed=replay_outcomes(record,plan_runtime_manifest=plan,outcome_runtime_manifest=executing,thermal_runtime=thermal)
        if (outcome_runtime_manifest()!=executing or canonical(_execution_runtime(root))!=canonical(thermal) or
            _read(args.receipt,MAX_BYTES,private=True)!=raw):raise ValueError('original score or executing runtime changed')
        sys.stdout.buffer.write(canonical(replayed)+b'\n');return 0
    except Exception:
        print('Household outcome replay refused: invalid or changed original context.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
