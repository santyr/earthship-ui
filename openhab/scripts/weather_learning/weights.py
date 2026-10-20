"""Pure measured-target weighting; forecast count supplies no independence claim.

Each original measured target has unit mass divided among its distinct forecast
pairs. Epoch/policy cohorts are never pooled and conflicting receipts are errors.
Dates are descriptive; temporal dependence has not yet been estimated.
"""
from collections import Counter
from math import fsum,sqrt
from zoneinfo import ZoneInfo
from .contracts import identity,instant

RULE='unit_measured_target_across_distinct_forecasts_v1'
TIMEZONE='America/Denver'


def context(row):
    label=row.get('label',{})
    if not isinstance(label,dict):raise ValueError('original measured-target label required')
    names=('sensorEpoch','sensor_epoch','hardware_epoch','source_epoch','measurement_policy','target_policy','policy_sha256')
    return tuple((name,identity(row.get(name,label.get(name)))) for name in names if row.get(name,label.get(name)) is not None)


def target_weights(rows,*,target,evidence,at,cohort=context,timezone=TIMEZONE,pair_id=lambda r:r['pair_sha256']):
    zone=ZoneInfo(timezone)
    seen=set();truth={};keys=[];cohorts=set();dates=set()
    for row in rows:
        pair=pair_id(row)
        if pair in seen:raise ValueError('duplicate forecast pair cannot inflate target support')
        seen.add(pair);group=cohort(row);cohorts.add(group)
        key=identity((group,target(row)));receipt=identity(evidence(row))
        if key in truth and truth[key]!=receipt:raise ValueError('conflicting measured target evidence')
        truth[key]=receipt;keys.append(key)
        dates.add(instant(at(row)).astimezone(zone).date())
    if len(cohorts)>1:raise ValueError('different measured-target epochs or policies cannot be pooled')
    counts=Counter(keys);weights=[1./counts[key] for key in keys]
    return weights,dict(weighting_rule=RULE,forecast_pairs=len(rows),unique_measured_targets=len(counts),
        target_weight_sum=len(counts),local_target_dates=len(dates),timezone=timezone,
        temporal_blocks=None,dependence='dependence_not_estimated')


def validate_support(support):
    fields={'weighting_rule','forecast_pairs','unique_measured_targets','target_weight_sum','local_target_dates','timezone','temporal_blocks','dependence'}
    if (not isinstance(support,dict) or set(support)!=fields or support.get('weighting_rule')!=RULE or support.get('temporal_blocks') is not None or
        support.get('dependence')!='dependence_not_estimated' or not isinstance(support.get('timezone'),str) or
        any(type(support.get(k)) is not int or support[k]<0 for k in ('forecast_pairs','unique_measured_targets','target_weight_sum','local_target_dates')) or
        support['target_weight_sum']!=support['unique_measured_targets'] or
        not support['local_target_dates']<=support['unique_measured_targets']<=support['forecast_pairs'] or
        (support['forecast_pairs']>0 and support['local_target_dates']==0)):
        raise ValueError('explicit measured-target weighting support required')
    try:ZoneInfo(support['timezone'])
    except (KeyError,ValueError) as exc:raise ValueError('valid target support timezone required') from exc
    return support


def pv_weights(rows):
    return target_weights(rows,target=lambda r:('controller_PV_input_power',instant(r['start']).isoformat(),instant(r['end']).isoformat()),
        evidence=lambda r:(r['outcome_w'],r['energy_source_sha256']),at=lambda r:r['start'])


def site_weights(rows,timezone=TIMEZONE):
    return target_weights(rows,target=lambda r:(r['kind'],instant(r['target_at']).isoformat()),
        evidence=lambda r:(r['outcome'],r['label']),at=lambda r:r['target_at'],timezone=timezone)


def weather_weights(rows):
    return target_weights(rows,target=lambda r:(r['kind'],instant(r['target_start']).isoformat(),instant(r['target_end']).isoformat()),
        evidence=lambda r:(r['outcome'],r['measurement_sha256'],r['measurement_quality']),at=lambda r:r['target_start'])


def temperature_weights(pairs):
    rows=[dict(pair_sha256=p.pair_digest,target_at=instant(p.outcome.target_at.isoformat()).isoformat(),sensor_epoch=p.outcome.sensor_epoch,
        outcome=p.outcome.value_c,receipt=p.outcome.receipt_digest,available_at=instant(p.outcome.available_at.isoformat()).isoformat()) for p in pairs]
    return target_weights(rows,target=lambda r:('temperature_c',r['target_at']),
        evidence=lambda r:(r['outcome'],r['receipt'],r['available_at']),at=lambda r:r['target_at'],timezone=pairs[0].forecast.site_timezone if pairs else TIMEZONE)


def metrics(errors,weights):
    mass=fsum(weights)
    return dict(count=len(errors),mae=None if not mass else fsum(w*abs(e) for w,e in zip(weights,errors))/mass,
        bias=None if not mass else fsum(w*e for w,e in zip(weights,errors))/mass,
        rmse=None if not mass else sqrt(fsum(w*e*e for w,e in zip(weights,errors))/mass))
