"""Conditional constant-power battery baseline, never a qualified energy bound."""
from datetime import timedelta
from hashlib import sha256
import math
from .codec import canonical,loads,identity
from .evidence import utc
from .control_contracts import instant
from .energy_source_snapshot import EnergySourceSnapshot
from .energy_configuration import project_energy_configuration

METRIC_IDENTITY='Solar_PV/config/metric-sources.json'
METRIC_FIELDS={'schema','source_identity','raw','sha256','available_at'}
METRIC_MAX_BYTES=32768


def _metric(source,at):
    if source is None:return 'metric_source_unavailable'
    if (not isinstance(source,dict) or set(source)!=METRIC_FIELDS or
        source['schema']!='earthship-household-battery-metric-source/v1' or source['source_identity']!=METRIC_IDENTITY):
        raise ValueError('closed original battery metric source required')
    raw=source['raw']
    if (not isinstance(raw,str) or not 1<=len(raw.encode())<=METRIC_MAX_BYTES or
        sha256(raw.encode()).hexdigest()!=source['sha256'] or instant(source['available_at'])>at):
        raise ValueError('original metric bytes or availability differ')
    body=loads(raw)
    if not isinstance(body,dict) or type(body.get('version')) is not int or body['version']!=1:
        return 'unsupported_metric_configuration'
    rows=body.get('sources')
    if not isinstance(rows,list) or len(rows)>128 or any(not isinstance(row,dict) for row in rows):
        return 'unsupported_metric_configuration'
    rows=[row for row in rows if row.get('canonical_name')=='battery.dc_power_w']
    if len(rows)!=1:return 'ambiguous_battery_metric'
    row=rows[0]
    if (row.get('item_name')!='DCData_Native_Power' or row.get('raw_unit')!='W' or row.get('canonical_unit')!='W' or
        type(row.get('scale')) not in (int,float) or row['scale']!=1 or row.get('sign')!='positive_charging'):
        return 'unsupported_battery_power_semantics'
    return None


def _reading(row,identity,unit,at,now,maximum_age):
    if not isinstance(row,dict) or row.get('value') is None or row.get('reason') is not None or row.get('unit')!=unit:
        return 'required_source_unavailable'
    ref=row.get('evidence')
    if not isinstance(ref,dict) or ref.get('quality')!='qualified' or ref.get('source_identity')!=identity:
        return 'required_source_unqualified'
    if any(ref.get(k) is None for k in ('observed_at','available_at','valid_until')):
        return 'required_source_unavailable'
    if type(maximum_age) is not int or maximum_age<=0:
        raise ValueError('present battery source requires explicit original age policy')
    observed,available,until=(instant(ref[k]) for k in ('observed_at','available_at','valid_until'))
    if not observed<=available<=at or at-observed>timedelta(seconds=maximum_age) or now>=until:
        return 'required_source_expired'
    return None


def project_persistence(*,snapshot,metric_source,horizon_hours,now):
    """Freeze signed net DC power at issue over an explicit bounded horizon.

    Nominal energy is an SoC-equivalent coordinate based on declared capacity,
    not a usable-energy measurement. No hourly PV, future load, efficiency,
    protection threshold or action response is inferred from an instant sample.
    """
    if not isinstance(snapshot,EnergySourceSnapshot):raise ValueError('original configured energy snapshot required')
    if type(horizon_hours) is not int or horizon_hours not in (6,12,24):raise ValueError('supported persistence horizon required')
    now=utc(now);doc=snapshot.to_dict();at=instant(doc['as_of'])
    if now<instant(doc['created_at']):raise ValueError('baseline precedes original snapshot availability')
    metric_source=None if metric_source is None else loads(canonical(metric_source));reason=_metric(metric_source,at)
    rows=doc['domains']['energy'];soc,power=rows['battery_soc'],rows['battery_power_w']
    bank=project_energy_configuration(snapshot.energy_configuration,as_of=at)['bank']
    capacity=bank.get('nominal_usable_kwh');end=bank.get('effective_until')
    out=dict(schema='earthship-household-energy-persistence/v1',model_rule='constant_net_dc_power_nominal_capacity_v1',
        origin=at.isoformat(),assessed_at=now.isoformat(),snapshot_id=snapshot.snapshot_id,horizon_hours=horizon_hours,
        basis='conditional_current_power_persistence',status='unavailable',reason=reason,trajectory=[],
        nominal_bank_kwh=None,battery_power_w=None,initial_soc_pct=None,minimum_nominal_soc_pct=None,
        maximum_nominal_soc_pct=None,metric_source_sha256=None if metric_source is None else identity(metric_source),
        source_evidence_sha256={},confidence='unavailable',physical_calibration_qualified=False,
        forecast_forcing_qualified=False,action_effects_qualified=False,automatic_actuation=False)
    if reason is None and (bank['status']!='declared' or type(capacity) not in (int,float) or not math.isfinite(capacity) or not .001<=capacity<=10000):
        reason='nominal_capacity_unavailable'
    if reason is None and end is not None and at+timedelta(hours=horizon_hours)>=instant(end):
        reason='bank_window_does_not_cover_horizon'
    ages=doc['temporal_policy']['max_age_seconds']
    for name,row,source,unit in (('battery_soc',soc,'BMS_SOC_Evidence_JSON','percent'),
        ('battery_power_w',power,'Power_Evidence_JSON:battery.dc_power_w','W')):
        if reason is None:reason=_reading(row,source,unit,at,now,ages.get(name))
    if reason is None:
        clocks=[instant(row['evidence']['observed_at']) for row in (soc,power)]
        if max(clocks)-min(clocks)>timedelta(seconds=doc['temporal_policy']['max_skew_seconds']):reason='source_skew'
    if reason is None:
        initial=soc['value'];watts=power['value']
        if (type(initial) not in (int,float) or not math.isfinite(initial) or not 0<=initial<=100 or
            type(watts) not in (int,float) or not math.isfinite(watts) or not -32767<=watts<=32767):
            raise ValueError('original battery model inputs outside domain')
        trajectory=[]
        for hour in range(horizon_hours+1):
            energy=capacity*initial/100+watts*hour/1000
            clipped=min(capacity,max(0.,energy))
            trajectory.append(dict(at=(at+timedelta(hours=hour)).isoformat(),nominal_energy_kwh=clipped,
                nominal_soc_pct=100*clipped/capacity,above_capacity_nominal_kwh=max(0.,energy-capacity),below_zero_nominal_kwh=max(0.,-energy)))
        out.update(status='projected_nominal_baseline',nominal_bank_kwh=capacity,battery_power_w=watts,initial_soc_pct=initial,
            trajectory=trajectory,minimum_nominal_soc_pct=min(row['nominal_soc_pct'] for row in trajectory),
            maximum_nominal_soc_pct=max(row['nominal_soc_pct'] for row in trajectory),
            source_evidence_sha256={name:rows[name]['evidence']['digest'] for name in ('battery_soc','battery_power_w')})
    out['reason']=reason;out['projection_sha256']=identity(out)
    return loads(canonical(out))
