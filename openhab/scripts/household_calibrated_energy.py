"""Same-issue empirical PV and nominal-storage scenarios; no control authority."""
from datetime import timedelta
from pathlib import Path
from hashlib import sha256
from bisect import bisect_left
from math import fsum
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc
from household_energy_forecast import replay_energy_forecast,forecast_runtime_manifest
from household_profiled_forecast import replay_profiled_forecast,profiled_runtime_manifest
from household_ac_load_artifact import runtime_manifest as load_runtime
from household_pv_model import simulate_storage
from household_profiled_storage import simulate_profiled_storage
from weather_learning.pv_calibration_source import restore_calibration
from weather_learning.pv_directional_calibration import project_power

SCHEMA='earthship-household-calibrated-energy-receipt/v1'
MAX_BYTES=1048576


def runtime_manifest():
    result={**forecast_runtime_manifest(),**profiled_runtime_manifest(),**load_runtime()};root=Path(__file__).resolve().parent
    for name in ('household_calibrated_energy.py','weather_learning/pv_calibration_source.py','weather_learning/pv_directional_calibration.py','weather_learning/pv_calibration.py','weather_learning/contracts.py'):
        result['openhab/scripts/'+name]=sha256((root/name).read_bytes()).hexdigest()
    return result


def adjust_steps(steps,*,positions,model,origin):
    times=[instant(p['at']) for p in positions]
    if times!=sorted(set(times)):raise ValueError('ordered original PV geometry required')
    result=[];last=origin
    if not isinstance(steps,list) or not 1<=len(steps)<=576:raise ValueError('bounded original PV steps required')
    for row in steps:
        start,end=instant(row['start']),instant(row['end']);index=bisect_left(times,end)
        if start!=last or not timedelta(0)<end-start<=timedelta(minutes=5) or end>origin+timedelta(hours=24) or index>=len(times) or times[index]-end>=timedelta(minutes=5):raise ValueError('matching complete original PV geometry required')
        hours=(end-start).total_seconds()/3600;watts=row['potential_pv_kwh']*1000/hours
        adjusted=project_power(model,watts,azimuth_degrees=positions[index]['azimuth_degrees'],origin=origin)
        result.append(dict(row,potential_pv_kwh=adjusted*hours/1000));last=end
    return result


def storage_inputs(snapshot,*,topology_source,origin):
    """Freeze original qualified initial conditions at the forecast issue.

    A forecast published later does not relabel its measurements as current.
    The source's original age/identity/validity/skew policies remain in force
    at that issue. This module grants no live telemetry or actuator permission.
    """
    from household.energy_persistence import _reading
    from household.energy_configuration import project_energy_configuration
    from household.power_flows import _dc_scope
    doc=snapshot.to_dict();rows=doc['domains']['energy'];soc=rows['battery_soc'];load=rows['estimated_load_w'];ages=doc['temporal_policy']['max_age_seconds']
    if instant(doc['as_of'])!=origin:raise ValueError('same original storage origin required')
    reason=_reading(soc,'BMS_SOC_Evidence_JSON','percent',origin,origin,ages.get('battery_soc'))
    scope,why=_dc_scope(topology_source,origin)
    if reason is None:reason=why
    bank=project_energy_configuration(snapshot.energy_configuration,as_of=origin)['bank'];end=origin+timedelta(hours=24)
    if reason is None and (bank['status']!='declared' or bank.get('nominal_usable_kwh') is None):reason='nominal_capacity_unavailable'
    if reason is None and bank.get('effective_until') is not None and end>=instant(bank['effective_until']):reason='bank_window_does_not_cover_horizon'
    if reason is None:
        topology=loads(topology_source['raw'])
        if topology['effective_until'] is not None and end>=instant(topology['effective_until']):reason='household_topology_window_does_not_cover_horizon'
    load_reason=_reading(load,'Inverter_AC_Evidence_JSON:inverter.ac_output_w','W',origin,origin,ages.get('estimated_load_w'))
    if reason is None and load_reason is None:
        if abs(instant(soc['evidence']['observed_at'])-instant(load['evidence']['observed_at']))>timedelta(seconds=doc['temporal_policy']['max_skew_seconds']):load_reason='source_skew'
    return dict(reason=reason,initial_soc_pct=soc['value'],nominal_bank_kwh=bank.get('nominal_usable_kwh'),current_load_reason=load_reason,
        current_load_w=load['value'] if load_reason is None else None,battery_soc_evidence_sha256=None if soc.get('evidence') is None else soc['evidence']['digest'],household_dc_scope=scope)


def seal(*,energy,plan,profiled,now,calibration_path=None,calibration_raw=None):
    from household.model_snapshot import restore_snapshot
    from household.weather_context import project_weather
    from weather_source_files import _read
    now=utc(now);energy=replay_energy_forecast(energy,plan_receipt=plan,runtime_manifest=forecast_runtime_manifest());pv=energy['output']['array_pv'];origin=instant(pv['origin'])
    if not instant(energy['inputs']['assessed_at'])<=now<=origin+timedelta(seconds=120):raise ValueError('bounded same-issue calibrated forecast deadline required')
    if calibration_raw is None:
        if calibration_path is None:raise ValueError('explicit original calibration required')
        calibration_raw=_read(calibration_path,262144)
    calibration=restore_calibration(calibration_raw,origin=origin,system_raw=energy['inputs']['system_source']['raw'].encode(),horizon_raw=energy['inputs']['horizon_source']['raw'].encode())
    if profiled is not None:
        profiled=replay_profiled_forecast(profiled,energy_receipt=energy,plan_receipt=plan,runtime_manifest=profiled_runtime_manifest(),energy_runtime_manifest=forecast_runtime_manifest(),load_runtime_manifest={} if profiled['inputs']['load_source'] is None else load_runtime())
    snapshot=restore_snapshot(plan['inputs']['snapshot'],plan['inputs']['source_contexts']);context=project_weather(snapshot.weather);raw_steps=pv['steps']
    out=dict(status='unavailable',reason=pv['reason'],issued_at=origin.isoformat(),raw_potential_kwh=pv['potential_pv_kwh'],calibrated_potential_kwh=None,steps=[],
        constant_load_storage=dict(status='unavailable',reason='array_potential_unavailable'),profiled_storage=dict(status='unavailable',reason='array_potential_unavailable'),
        uncalibrated_profiled_storage=None,confidence='provisional_empirical_short_horizon',physical_calibration_qualified=False,automatic_actuation=False)
    if pv['status']=='projected_provisional_array_potential':
        steps=adjust_steps(raw_steps,positions=context['solar_geometry']['positions'],model=calibration['model'],origin=origin)
        if instant(steps[-1]['end'])!=origin+timedelta(hours=24):raise ValueError('complete calibrated 24-hour PV horizon required')
        inputs=storage_inputs(snapshot,topology_source=energy['inputs']['topology_source'],origin=origin)
        out.update(status='projected_provisional_calibrated_potential',reason=None,calibrated_potential_kwh=fsum(r['potential_pv_kwh'] for r in steps),steps=steps,storage_initial_conditions=inputs)
        out['constant_load_storage']=dict(status='unavailable',reason=inputs['reason'] or inputs['current_load_reason'])
        if out['constant_load_storage']['reason'] is None:
            out['constant_load_storage']=dict(simulate_storage(steps=steps,initial_soc_pct=inputs['initial_soc_pct'],nominal_bank_kwh=inputs['nominal_bank_kwh'],load_ac_w=inputs['current_load_w']),status='conditional_nominal_simulation',reason=None)
        load=None if profiled is None else profiled['output']['load_forecast'];reason=inputs['reason'] or ('load_model_unavailable' if load is None else load['reason'])
        out['profiled_storage']=dict(status='unavailable',reason=reason)
        if reason is None:
            if instant(load['origin'])!=origin:raise ValueError('same-issue learned load required')
            for name,source_steps in (('profiled_storage',steps),('uncalibrated_profiled_storage',raw_steps)):
                out[name]=dict(simulate_profiled_storage(steps=source_steps,initial_soc_pct=inputs['initial_soc_pct'],nominal_bank_kwh=inputs['nominal_bank_kwh'],load_forecast=load),status='conditional_nominal_simulation',reason=None)
    value=dict(schema=SCHEMA,inputs=dict(original_energy_document_sha256=identity(energy),original_energy_receipt_sha256=energy['receipt_sha256'],plan_receipt_sha256=plan['receipt_sha256'],
        original_profiled_document_sha256=None if profiled is None else identity(profiled),calibration_raw=calibration_raw.decode(),calibration_file_sha256=calibration['original_file_sha256'],
        source_freshness_basis='qualified_original_issue_with_120_second_publication_deadline',assessed_at=now.isoformat()),runtime_manifest=runtime_manifest(),output=out)
    value['receipt_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded calibrated energy receipt required')
    return loads(canonical(value))


def replay(value,*,energy,plan,profiled):
    if value.get('schema')!=SCHEMA or value.get('receipt_sha256')!=identity({k:v for k,v in value.items() if k!='receipt_sha256'}) or value['runtime_manifest']!=runtime_manifest():raise ValueError('unchanged calibrated energy receipt required')
    expected=seal(energy=energy,plan=plan,profiled=profiled,calibration_raw=value['inputs']['calibration_raw'].encode(),now=instant(value['inputs']['assessed_at']))
    if canonical(expected)!=canonical(value):raise ValueError('original calibrated energy projection differs')
    return expected
