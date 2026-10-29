#!/usr/bin/env python3
"""Re-evaluate fresh original advice inputs after the unchanged forecast cycle.

No weather acquisition, fitting, original forecast writes or equipment I/O.
"""
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sqlite3
from household.codec import canonical, loads
from household.control_contracts import instant
from household.snapshot import HouseholdSnapshot
from household.advice import evaluate_advice
from household_advice import publish_advice, runtime_manifest, replay_retained
from household_observation import _directory, _private_file


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path.home()/'.local/state/household-intel')
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args();directory=args.directory.absolute();_directory(directory)
    now=datetime.now(timezone.utc)
    # Read only the report currently published by the cycle, not an arbitrary
    # archived issue. Its retained inputs and raw report must match exactly.
    original_raw=_private_file(directory/'advice.json',32768)[0];original=loads(original_raw)
    with sqlite3.connect('file:'+str(directory/'advice.sqlite')+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT raw,inputs FROM reports WHERE id=?',(original['report_id'],)).fetchone()
    if row is None or bytes(row[0])!=original_raw:raise ValueError('original published advice context required')
    inputs=loads(row[1]);body=inputs['snapshot']
    if not instant(inputs['now'])<=now<instant(original['valid_until']):raise ValueError('fresh original advice required')
    snapshot=HouseholdSnapshot(canonical({k:v for k,v in body.items() if k!='snapshot_id'}))
    if snapshot.snapshot_id!=body['snapshot_id']:raise ValueError('original snapshot differs')
    projections={**inputs['projections']}
    projections.setdefault('thermal_evaluation_context',None)
    source_runtime=runtime_manifest()
    def guard():
        if runtime_manifest()!=source_runtime:raise ValueError('advisory source changed')
        if datetime.now(timezone.utc)>=instant(original['valid_until']):raise ValueError('original advice expired during comparison')
    if args.publish:
        result=publish_advice(snapshot=snapshot,projections=projections,directory=directory,now=now,guard=guard)
        replay_retained(directory/'advice.sqlite',result['report_id'])
        print(canonical(result).decode())
    else:
        report=evaluate_advice(snapshot=snapshot,projections=projections,policy=inputs['policy'],action_state=inputs['action_state'],now=now)
        print(canonical(report).decode())


if __name__=='__main__':main()
