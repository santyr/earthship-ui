"""Separate measured consumption from storage without closing an unmetered balance.

The operator declaration describes topology. It cannot qualify a power sample,
conversion efficiency, solar availability, usable capacity or an actuator.
"""
from hashlib import sha256
import math
from .codec import canonical,loads,identity
from .control_contracts import instant
from .evidence import utc
from .energy_source_snapshot import EnergySourceSnapshot
from .energy_persistence import _reading,_metric

TOPOLOGY_IDENTITY='earthship-ui/openhab/household-energy-topology.json'
SOURCE_FIELDS={'schema','source_identity','raw','sha256','available_at'}
DECLARATION_FIELDS={'schema','confirmed_by','confirmed_at','effective_from','effective_until','household_loads','dc_loads'}


def prepare_topology_source(raw,*,available_at):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=4096:
        raise ValueError('bounded original topology declaration required')
    text=raw.decode('utf-8');loads(text)
    return dict(schema='earthship-household-load-topology-source/v1',source_identity=TOPOLOGY_IDENTITY,
        raw=text,sha256=sha256(raw).hexdigest(),available_at=utc(available_at).isoformat())


def _dc_scope(source,at):
    if source is None:return 'unknown','household_dc_scope_unavailable'
    if (not isinstance(source,dict) or set(source)!=SOURCE_FIELDS or
        source['schema']!='earthship-household-load-topology-source/v1' or source['source_identity']!=TOPOLOGY_IDENTITY):
        raise ValueError('closed original household topology source required')
    raw=source['raw']
    if (not isinstance(raw,str) or not 1<=len(raw.encode())<=4096 or
        sha256(raw.encode()).hexdigest()!=source['sha256'] or instant(source['available_at'])>at):
        raise ValueError('original topology bytes or availability differ')
    value=loads(raw)
    if (set(value)!=DECLARATION_FIELDS or value['schema']!='earthship-household-load-topology/v1' or
        value['confirmed_by']!='operator' or value['household_loads']!='ac_only' or value['dc_loads']!='battery_and_solar_pv_system'):
        return 'unknown','unsupported_household_topology'
    try:
        confirmed,start=(instant(value[k]) for k in ('confirmed_at','effective_from'))
        end=None if value['effective_until'] is None else instant(value['effective_until'])
    except (ValueError,TypeError,OverflowError):
        return 'unknown','invalid_household_topology_clock'
    if (confirmed>instant(source['available_at']) or not start<=at or end is not None and
        (end<=start or at>=end)):
        return 'unknown','household_topology_window_mismatch'
    return 'none_operator_declared',None


def project_power_flows(*,snapshot,topology_source,now,metric_source=None):
    if not isinstance(snapshot,EnergySourceSnapshot):raise ValueError('original configured energy snapshot required')
    now=utc(now);doc=snapshot.to_dict();at=instant(doc['as_of'])
    if now<instant(doc['created_at']):raise ValueError('flow projection precedes original snapshot availability')
    topology_source=None if topology_source is None else loads(canonical(topology_source))
    scope,scope_reason=_dc_scope(topology_source,at)
    metric_source=None if metric_source is None else loads(canonical(metric_source))
    metric_reason=_metric(metric_source,at)
    rows=doc['domains']['energy'];ages=doc['temporal_policy']['max_age_seconds'];values={};refs={};reasons={}
    for output,role,source in (
        ('battery_net_dc_w','battery_power_w','Power_Evidence_JSON:battery.dc_power_w'),
        ('pv_controller_output_w','pv_output_power_w','Power_Evidence_JSON:pv.output_power_w'),
        ('inverter_ac_output_w','inverter_output_w','Inverter_AC_Evidence_JSON:inverter.ac_output_w'),
        ('household_ac_load_w','estimated_load_w','Inverter_AC_Evidence_JSON:inverter.ac_output_w')):
        row=rows[role];reason=_reading(row,source,'W',at,now,ages.get(role))
        number=row['value']
        if reason is None and (type(number) not in (int,float) or not math.isfinite(number)):
            raise ValueError('finite original power quantity required')
        if reason is None and output!='battery_net_dc_w' and number<0:reason='unsupported_export_flow'
        values[output]=number if reason is None else None;reasons[output]=reason
        if reason is None:refs[output]=row['evidence']['digest']
    if metric_reason is not None:
        values['battery_net_dc_w']=None;reasons['battery_net_dc_w']=metric_reason
        refs.pop('battery_net_dc_w',None)
    battery=values['battery_net_dc_w'];ac=values['household_ac_load_w']
    values.update(battery_charge_w=None if battery is None else max(0,battery),
        battery_discharge_w=None if battery is None else max(0,-battery),
        household_load_w=ac if scope_reason is None else None,
        system_dc_consumption_w=None,conversion_losses_w=None)
    reasons['household_load_w']=reasons['household_ac_load_w'] if scope_reason is None else scope_reason
    available=all(values[k] is not None for k in ('battery_net_dc_w','household_load_w','pv_controller_output_w'))
    measured=any(values[k] is not None for k in ('battery_net_dc_w','inverter_ac_output_w','pv_controller_output_w'))
    out=dict(schema='earthship-household-power-flows/v1',snapshot_id=snapshot.snapshot_id,origin=at.isoformat(),assessed_at=now.isoformat(),
        status='available' if available else 'partial' if measured else 'unavailable',**values,
        household_dc_scope=scope,household_load_basis='attested_inverter_only_ac_load_and_operator_dc_scope' if values['household_load_w'] is not None else None,
        storage_basis=None if battery is None else 'signed_net_battery_dc_power_positive_charging',solar_scope='reported_controller_output_not_total_available_solar',
        topology_source_sha256=None if topology_source is None else identity(topology_source),
        metric_source_sha256=None if metric_source is None else identity(metric_source),
        energy_configuration_sha256=doc['energy_configuration_sha256'],source_evidence_sha256=refs,reasons=reasons,
        balance_closed=False,physical_calibration_qualified=False,action_effects_qualified=False,automatic_actuation=False)
    out['projection_sha256']=identity(out)
    return loads(canonical(out))
