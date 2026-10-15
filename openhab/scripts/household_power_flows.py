#!/usr/bin/env python3
"""Replay private consumption/storage observations against an external original plan."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime,timezone
import argparse,sys
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.power_flows import project_power_flows
from household.model_snapshot import restore_snapshot
from household.planning import _runtime_manifest
from household_pipeline import pipeline_runtime_manifest
from household_outcomes import original_plan_runtime
from household_snapshot import _read

MAX_BYTES=65536
REQUIRED={'openhab/scripts/household/power_flows.py','openhab/scripts/household_power_flows.py'}
FIELDS={'schema','inputs','runtime_manifest','output','receipt_sha256'}
INPUT_FIELDS={'plan_receipt_sha256','plan_document_sha256','topology_source','assessed_at'}


def flow_runtime_manifest():
    result=pipeline_runtime_manifest(expanded=True,configured=True,measured=True)
    result['openhab/scripts/household_power_flows.py']=sha256(_read(Path(__file__).resolve(),262144)).hexdigest()
    return result


def seal_flow_receipt(*,plan_receipt,topology_source,now,runtime_manifest):
    plan=loads(canonical(plan_receipt));runtime=_runtime_manifest(runtime_manifest)
    if (plan.get('schema') not in ('earthship-household-model-plan-receipt/v4','earthship-household-model-plan-receipt/v5','earthship-household-model-plan-receipt/v6') or
        identity({k:v for k,v in plan.items() if k!='receipt_sha256'})!=plan.get('receipt_sha256') or not REQUIRED<=set(runtime)):
        raise ValueError('original configured plan and complete flow source required')
    original_plan_runtime(plan,actual=runtime)
    snapshot=restore_snapshot(plan['inputs']['snapshot'],plan['inputs']['source_contexts'])
    value=dict(schema='earthship-household-power-flow-receipt/v1',inputs=dict(
        plan_receipt_sha256=plan['receipt_sha256'],plan_document_sha256=sha256(canonical(plan)).hexdigest(),
        topology_source=topology_source,assessed_at=now.isoformat()),runtime_manifest=runtime,
        output=project_power_flows(snapshot=snapshot,topology_source=topology_source,now=now))
    value['receipt_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded original flow receipt required')
    return loads(canonical(value))


def replay_flow_receipt(receipt,*,plan_receipt,runtime_manifest):
    if (not isinstance(receipt,dict) or set(receipt)!=FIELDS or receipt['schema']!='earthship-household-power-flow-receipt/v1' or
        len(canonical(receipt))>MAX_BYTES or not isinstance(receipt['inputs'],dict) or set(receipt['inputs'])!=INPUT_FIELDS or
        identity({k:v for k,v in receipt.items() if k!='receipt_sha256'})!=receipt['receipt_sha256'] or
        canonical(receipt['runtime_manifest'])!=canonical(runtime_manifest)):
        raise ValueError('closed unchanged flow receipt and runtime required')
    value=receipt['inputs']
    replayed=seal_flow_receipt(plan_receipt=plan_receipt,topology_source=value['topology_source'],
        now=instant(value['assessed_at']),runtime_manifest=runtime_manifest)
    if canonical(replayed)!=canonical(receipt):raise ValueError('original flow projection differs')
    return replayed


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--receipt',required=True,type=Path);parser.add_argument('--plan',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        raw=_read(args.receipt,MAX_BYTES,private=True);original=_read(args.plan,2097152,private=True)
        receipt,plan=loads(raw),loads(original);runtime=flow_runtime_manifest()
        if instant(receipt['inputs']['assessed_at'])>datetime.now(timezone.utc):raise ValueError('future flow assessment refused')
        replayed=replay_flow_receipt(receipt,plan_receipt=plan,runtime_manifest=runtime)
        if (flow_runtime_manifest()!=runtime or _read(args.receipt,MAX_BYTES,private=True)!=raw or
            _read(args.plan,2097152,private=True)!=original):raise ValueError('flow replay inputs changed')
        sys.stdout.buffer.write(canonical(replayed)+b'\n');return 0
    except Exception:
        print('Household power flow replay refused: invalid or changed original inputs.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
