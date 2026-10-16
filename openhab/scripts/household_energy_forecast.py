#!/usr/bin/env python3
"""Retain and replay provisional PV and nominal-storage scenarios without live I/O."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime,timedelta,timezone
import argparse,sys
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc
from household.planning import _runtime_manifest
from household.model_snapshot import restore_snapshot
from household.power_flows import project_power_flows
from household.energy_persistence import _reading
from household.energy_configuration import project_energy_configuration
from household_outcomes import original_plan_runtime,outcome_runtime_manifest
from household_snapshot import _read
from household_pv_model import project_pv,simulate_storage

MAX_BYTES=262144
REQUIRED={'openhab/scripts/'+name for name in ('household_energy_forecast.py','household_pv_model.py','household_solar_horizon.py','household_outcomes.py')}
FIELDS={'schema','inputs','runtime_manifest','output','receipt_sha256'}
INPUT_FIELDS={'plan_receipt_sha256','plan_document_sha256','system_source','topology_source','horizon_source','assessed_at'}


def forecast_runtime_manifest():
    result=outcome_runtime_manifest();root=Path(__file__).resolve().parent
    for name in ('household_energy_forecast.py','household_pv_model.py','household_solar_horizon.py'):
        result['openhab/scripts/'+name]=sha256(_read(root/name,262144)).hexdigest()
    return result


def _storage(snapshot,pv,flows,topology_source,now):
    doc=snapshot.to_dict();at=instant(doc['as_of']);reason=None
    out=dict(status='unavailable',reason=None,trajectory=[],origin=pv['origin'],assessed_at=now.isoformat(),
        confidence='conditional_uncalibrated',household_load_rule='hold_original_current_AC_load_constant',
        physical_calibration_qualified=False,action_effects_qualified=False,balance_closed=False,automatic_actuation=False)
    if pv['status']!='projected_provisional_array_potential':reason='array_potential_unavailable'
    elif flows['household_load_w'] is None:reason='household_AC_load_unavailable'
    soc=doc['domains']['energy']['battery_soc'];load=doc['domains']['energy']['estimated_load_w']
    ages=doc['temporal_policy']['max_age_seconds']
    if reason is None:reason=_reading(soc,'BMS_SOC_Evidence_JSON','percent',at,now,ages.get('battery_soc'))
    if reason is None:
        clocks=[instant(r['evidence']['observed_at']) for r in (soc,load)]
        if max(clocks)-min(clocks)>timedelta(seconds=doc['temporal_policy']['max_skew_seconds']):reason='source_skew'
    bank=project_energy_configuration(snapshot.energy_configuration,as_of=at)['bank']
    end=instant(pv['origin'])+timedelta(hours=pv.get('horizon_hours',24))
    if reason is None and (bank['status']!='declared' or bank.get('nominal_usable_kwh') is None):reason='nominal_capacity_unavailable'
    if reason is None and bank.get('effective_until') is not None and end>=instant(bank['effective_until']):reason='bank_window_does_not_cover_horizon'
    if reason is None:
        topology=loads(topology_source['raw'])
        if topology['effective_until'] is not None and end>=instant(topology['effective_until']):reason='household_topology_window_does_not_cover_horizon'
    if reason is None:
        out.update(simulate_storage(steps=pv['steps'],initial_soc_pct=soc['value'],
            nominal_bank_kwh=bank['nominal_usable_kwh'],load_ac_w=flows['household_load_w']),status='conditional_nominal_simulation',
            energy_configuration_sha256=doc['energy_configuration_sha256'],
            source_evidence_sha256={name:row['evidence']['digest'] for name,row in (('battery_soc',soc),('household_ac_load',load))})
    out['reason']=reason;out['projection_sha256']=identity(out)
    return out


def seal_energy_forecast(*,plan_receipt,system_source,topology_source,now,runtime_manifest,horizon_source=None):
    plan=loads(canonical(plan_receipt));runtime=_runtime_manifest(runtime_manifest);now=utc(now)
    if (plan.get('schema') not in ('earthship-household-model-plan-receipt/v4','earthship-household-model-plan-receipt/v5','earthship-household-model-plan-receipt/v6') or
        identity({k:v for k,v in plan.items() if k!='receipt_sha256'})!=plan.get('receipt_sha256') or not REQUIRED<=set(runtime)):
        raise ValueError('original configured plan and complete energy forecast source required')
    original_plan_runtime(plan,actual=runtime)
    if now<instant(plan['inputs']['now']):raise ValueError('energy forecast precedes original plan')
    snapshot=restore_snapshot(plan['inputs']['snapshot'],plan['inputs']['source_contexts'])
    system_source=None if system_source is None else loads(canonical(system_source))
    topology_source=None if topology_source is None else loads(canonical(topology_source))
    horizon_source=None if horizon_source is None else loads(canonical(horizon_source))
    pv=project_pv(weather=snapshot.weather,system_source=system_source,horizon_source=horizon_source,now=now)
    flows=project_power_flows(snapshot=snapshot,topology_source=topology_source,now=now,metric_source=plan['inputs'].get('energy_persistence_source'))
    output=dict(schema='earthship-household-energy-forecast/v1',array_pv=pv,current_flows=flows,
        nominal_storage=_storage(snapshot,pv,flows,topology_source,now),automatic_actuation=False,physical_calibration_qualified=False)
    value=dict(schema='earthship-household-energy-forecast-receipt/v1',inputs=dict(plan_receipt_sha256=plan['receipt_sha256'],
        plan_document_sha256=sha256(canonical(plan)).hexdigest(),system_source=system_source,topology_source=topology_source,horizon_source=horizon_source,
        assessed_at=now.isoformat()),runtime_manifest=runtime,output=output)
    value['receipt_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded original energy forecast receipt required')
    return loads(canonical(value))


def replay_energy_forecast(receipt,*,plan_receipt,runtime_manifest):
    if (not isinstance(receipt,dict) or set(receipt)!=FIELDS or receipt['schema']!='earthship-household-energy-forecast-receipt/v1' or
        len(canonical(receipt))>MAX_BYTES or not isinstance(receipt['inputs'],dict) or set(receipt['inputs'])!=INPUT_FIELDS or
        identity({k:v for k,v in receipt.items() if k!='receipt_sha256'})!=receipt['receipt_sha256'] or
        canonical(receipt['runtime_manifest'])!=canonical(runtime_manifest)):
        raise ValueError('closed unchanged energy forecast receipt and runtime required')
    value=receipt['inputs']
    replayed=seal_energy_forecast(plan_receipt=plan_receipt,system_source=value['system_source'],topology_source=value['topology_source'],
        now=instant(value['assessed_at']),runtime_manifest=runtime_manifest,horizon_source=value['horizon_source'])
    if canonical(replayed)!=canonical(receipt):raise ValueError('original energy forecast projection differs')
    return replayed


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--receipt',required=True,type=Path);parser.add_argument('--plan',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        raw=_read(args.receipt,MAX_BYTES,private=True);original=_read(args.plan,2097152,private=True)
        receipt,plan=loads(raw),loads(original);runtime=forecast_runtime_manifest()
        if instant(receipt['inputs']['assessed_at'])>datetime.now(timezone.utc):raise ValueError('future energy forecast assessment refused')
        replayed=replay_energy_forecast(receipt,plan_receipt=plan,runtime_manifest=runtime)
        if (forecast_runtime_manifest()!=runtime or _read(args.receipt,MAX_BYTES,private=True)!=raw or
            _read(args.plan,2097152,private=True)!=original):raise ValueError('energy forecast replay inputs changed')
        sys.stdout.buffer.write(canonical(replayed)+b'\n');return 0
    except Exception:
        print('Household energy forecast replay refused: invalid or changed original inputs.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
