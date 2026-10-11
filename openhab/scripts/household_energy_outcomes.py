#!/usr/bin/env python3
"""Replay one private whole-night energy score, without live source reads."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import sys
from household.codec import loads,canonical
from household.control_contracts import instant
from household.energy_outcomes import replay_energy_outcomes,MAX_BYTES
from household.thermal_model import _execution_runtime
from household_snapshot import _read
from household_outcomes import original_plan_runtime,outcome_runtime_manifest


def energy_outcome_runtime_manifest():
    import advisory_windows
    import earthship_energy.trough_assessment as assessor
    result=outcome_runtime_manifest()
    for name,path in (
        ('openhab/scripts/household_energy_outcomes.py',Path(__file__).resolve()),
        ('openhab/scripts/advisory_windows.py',Path(advisory_windows.__file__)),
        ('companion/earthship_energy/trough_assessment.py',Path(assessor.__file__))):
        result[name]=sha256(_read(path,262144)).hexdigest()
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--receipt',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        raw=_read(args.receipt,MAX_BYTES,private=True);record=loads(raw);inputs=record['inputs'];now=datetime.now(timezone.utc)
        if instant(inputs['plan_receipt']['inputs']['now'])>now:raise ValueError('future original plan refused')
        if inputs['night_source'] is not None and instant(inputs['night_source']['assessed_at'])>now:
            raise ValueError('future night assessment refused')
        if inputs['forecast_source'] is not None and instant(inputs['forecast_source']['persisted_at'])>now:
            raise ValueError('future original delivery refused')
        runtime=energy_outcome_runtime_manifest();plan=original_plan_runtime(inputs['plan_receipt'],actual=runtime)
        root=Path(__file__).resolve().parent
        thermal=None if inputs['plan_receipt']['inputs']['thermal_inputs'] is None else _execution_runtime(root)
        replayed=replay_energy_outcomes(record,plan_runtime_manifest=plan,outcome_runtime_manifest=runtime,thermal_runtime=thermal)
        if (energy_outcome_runtime_manifest()!=runtime or _read(args.receipt,MAX_BYTES,private=True)!=raw or
            thermal is not None and canonical(_execution_runtime(root))!=canonical(thermal)):
            raise ValueError('original energy score or executing closure changed')
        sys.stdout.buffer.write(canonical(replayed)+b'\n');return 0
    except Exception:
        print('Household energy outcome replay refused: invalid or changed original context.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
