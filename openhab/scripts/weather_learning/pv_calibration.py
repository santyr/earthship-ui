"""Effective Google-to-controller-input gain, with explicit censoring limits.

The scalar cannot separately identify forecast irradiance bias, transposition
error, meter bias and array loss. It calibrates their combined response only.
"""
from math import fsum
from zoneinfo import ZoneInfo
from .contracts import identity,instant,finite,digest

SCHEMA='earthship-pv-effective-calibration/v2'
LEGACY_SCHEMA='earthship-pv-effective-calibration/v1'
TIMEZONE='America/Denver'
DAY_BASIS='interval_start_local_date'


def independent_days(rows):
    """One interval-start date in the declared site timezone is one day."""
    zone=ZoneInfo(TIMEZONE)
    return len({instant(row['start']).astimezone(zone).date() for row in rows})


def _pair(row):
    if (row.get('pair_sha256')!=identity({k:v for k,v in row.items() if k!='pair_sha256'}) or
        not instant(row['origin'])<instant(row['start'])<instant(row['end']) or
        not all(finite(row[k]) for k in ('baseline_w','outcome_w','azimuth_degrees','lead_hours')) or
        not 0<=row['baseline_w']<=20000 or not 0<=row['outcome_w']<=20000):raise ValueError('unchanged PV calibration pair required')
    digest(row['forecast_sha256']);digest(row['energy_source_sha256']);return row


def fit_gain(rows,*,cutoff,trained_at):
    if not cutoff<=trained_at or not isinstance(rows,list) or len(rows)>20000:raise ValueError('bounded past PV calibration required')
    selected=[_pair(r) for r in rows if instant(r['end'])<cutoff]
    selected=[r for r in selected if r['potential_proxy_eligible'] is True and r['baseline_w']>=20]
    if not selected:raise ValueError('earlier uncensored-proxy PV pairs required')
    if len({r['pair_sha256'] for r in selected})!=len(selected):raise ValueError('unique PV calibration pairs required')
    denominator=fsum(r['baseline_w']**2 for r in selected)
    gain=max(.5,min(1.5,fsum(r['baseline_w']*r['outcome_w'] for r in selected)/denominator))
    value=dict(schema=SCHEMA,rule='least_squares_effective_gain_bounded_0.5_1.5_v2',timezone=TIMEZONE,independent_day_basis=DAY_BASIS,gain=gain,
        cutoff=cutoff.isoformat(),trained_at=trained_at.isoformat(),training_start=min((r['start'] for r in selected),key=instant),training_end=max((r['end'] for r in selected),key=instant),
        pairs=len(selected),training_days=independent_days(selected),training_pair_sha256s=[r['pair_sha256'] for r in selected],
        forecast_sha256s=sorted({r['forecast_sha256'] for r in selected}),energy_source_sha256s=sorted({r['energy_source_sha256'] for r in selected}),
        dataset_sha256=identity(selected),target='controller_PV_input_power',censoring_basis='low_soc_charging_below_controller_clip_proxy',
        identifiability='combined_forecast_irradiance_geometry_array_and_meter_response',physical_calibration_qualified=False,automatic_actuation=False)
    value['model_sha256']=identity(value);return value


def validate_model(model):
    if (model.get('schema') not in (SCHEMA,LEGACY_SCHEMA) or model.get('model_sha256')!=identity({k:v for k,v in model.items() if k!='model_sha256'}) or
        not finite(model.get('gain')) or not .5<=model['gain']<=1.5 or model.get('physical_calibration_qualified') is not False or model.get('automatic_actuation') is not False or
        not instant(model['training_end'])<instant(model['cutoff'])<=instant(model['trained_at'])):raise ValueError('unchanged past PV calibration model required')
    if model['schema']==SCHEMA and (model.get('timezone')!=TIMEZONE or model.get('independent_day_basis')!=DAY_BASIS):
        raise ValueError('explicit PV support calendar required')
    return model


def calibrated_power(model,watts,*,origin):
    model=validate_model(model)
    if instant(model['trained_at'])>origin:raise ValueError('PV calibration not available at forecast origin')
    if not finite(watts) or not 0<=watts<=20000:raise ValueError('bounded physical PV baseline required')
    return watts*model['gain']


def assess_gain(model,rows,*,holdout_start,holdout_end):
    model=validate_model(model)
    if not instant(model['cutoff'])<=holdout_start<holdout_end:raise ValueError('later disjoint PV holdout required')
    selected=[_pair(r) for r in rows if holdout_start<=instant(r['origin'])<instant(r['start']) and instant(r['end'])<holdout_end and r['potential_proxy_eligible'] is True]
    def metrics(values):
        raw=[r['baseline_w']-r['outcome_w'] for r in values];errors=[r['baseline_w']*model['gain']-r['outcome_w'] for r in values]
        mean=lambda xs:None if not xs else fsum(abs(x) for x in xs)/len(xs)
        return dict(pairs=len(values),baseline_mae_w=mean(raw),candidate_mae_w=mean(errors),baseline_bias_w=None if not raw else fsum(raw)/len(raw),candidate_bias_w=None if not errors else fsum(errors)/len(errors))
    days=independent_days(selected);result=metrics(selected)
    selected_for_serving=(len(selected)>=24 and days>=2 and model['training_days']>=3 and result['candidate_mae_w']<result['baseline_mae_w'])
    value=dict(schema='earthship-pv-calibration-comparison/v2',timezone=TIMEZONE,independent_day_basis=DAY_BASIS,model_sha256=model['model_sha256'],holdout_start=holdout_start.isoformat(),holdout_end=holdout_end.isoformat(),
        **result,independent_target_days=days,selected=selected_for_serving,
        by_azimuth={str(edge):metrics([r for r in selected if edge<=r['azimuth_degrees']<edge+45]) for edge in range(0,360,45)},
        by_lead={name:metrics([r for r in selected if lo<r['lead_hours']<=hi]) for name,lo,hi in [('0-24h',0,24),('24-48h',24,48)]},
        target='controller_PV_input_power_on_uncensored_proxy_intervals',prospective_score=False,physical_calibration_qualified=False,automatic_actuation=False)
    value['report_sha256']=identity(value);return value
