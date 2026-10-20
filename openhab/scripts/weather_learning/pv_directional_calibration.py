"""Fixed azimuth sectors for provisional site-response calibration.

Each supported sector shrinks toward unchanged physics with a fixed 24-pair
prior. Unsupported sectors retain physics. This does not identify a horizon
height, a metrology calibration, array azimuth or independent array losses.
"""
from math import fsum
from .contracts import identity,instant,finite
from .pv_calibration import _pair,independent_days,TIMEZONE,DAY_BASIS

SCHEMA='earthship-pv-directional-calibration/v2'
LEGACY_SCHEMA='earthship-pv-directional-calibration/v1'
PRIOR_PAIRS=24


def sector(azimuth):
    if not finite(azimuth) or not 0<=azimuth<=360:raise ValueError('bounded solar azimuth required')
    return str(min(7,int((azimuth%360)//45))*45)


def fit_directional(rows,*,cutoff,trained_at):
    if not cutoff<=trained_at or not isinstance(rows,list) or len(rows)>20000:raise ValueError('bounded earlier directional training required')
    selected=[_pair(r) for r in rows if instant(r['end'])<cutoff]
    selected=[r for r in selected if r['potential_proxy_eligible'] is True and r['baseline_w']>=20]
    if not selected:raise ValueError('earlier uncensored-proxy PV pairs required')
    if len({r['pair_sha256'] for r in selected})!=len(selected):raise ValueError('unique directional PV pairs required')
    sectors={}
    for edge in range(0,360,45):
        group=[r for r in selected if sector(r['azimuth_degrees'])==str(edge)];n=len(group);days=independent_days(group)
        supported=n>=24 and days>=3;gain=1.
        if supported:
            xx=fsum(r['baseline_w']**2 for r in group);xy=fsum(r['baseline_w']*r['outcome_w'] for r in group);prior=xx*PRIOR_PAIRS/n
            gain=max(.5,min(1.5,(xy+prior)/(xx+prior)))
        sectors[str(edge)]=dict(gain=gain,pairs=n,training_days=days,supported=supported)
    value=dict(schema=SCHEMA,rule='fixed_45_degree_effective_gain_with_24_pair_physics_prior_v2',timezone=TIMEZONE,independent_day_basis=DAY_BASIS,cutoff=cutoff.isoformat(),trained_at=trained_at.isoformat(),
        training_start=min((r['start'] for r in selected),key=instant),training_end=max((r['end'] for r in selected),key=instant),sectors=sectors,training_pair_sha256s=[r['pair_sha256'] for r in selected],
        dataset_sha256=identity(selected),pairs=len(selected),training_days=independent_days(selected),target='controller_PV_input_power',
        censoring_basis='low_soc_charging_below_controller_clip_proxy',identifiability='combined_forecast_irradiance_geometry_array_and_meter_response',
        physical_calibration_qualified=False,automatic_actuation=False)
    value['model_sha256']=identity(value);return value


def validate_model(model):
    if (model.get('schema') not in (SCHEMA,LEGACY_SCHEMA) or model.get('model_sha256')!=identity({k:v for k,v in model.items() if k!='model_sha256'}) or
        model.get('physical_calibration_qualified') is not False or model.get('automatic_actuation') is not False or
        not instant(model['training_end'])<instant(model['cutoff'])<=instant(model['trained_at']) or set(model.get('sectors',{}))!={str(v) for v in range(0,360,45)}):raise ValueError('unchanged directional PV calibration required')
    if model['schema']==SCHEMA and (model.get('timezone')!=TIMEZONE or model.get('independent_day_basis')!=DAY_BASIS):
        raise ValueError('explicit directional PV support calendar required')
    for row in model['sectors'].values():
        if not finite(row.get('gain')) or not .5<=row['gain']<=1.5 or type(row.get('supported')) is not bool or not row['supported'] and row['gain']!=1.:
            raise ValueError('supported bounded PV sector required')
    return model


def _calculate(model,watts,azimuth):
    if not finite(watts) or not 0<=watts<=20000:raise ValueError('bounded physical PV baseline required')
    return watts*model['sectors'][sector(azimuth)]['gain']


def project_power(model,watts,*,azimuth_degrees,origin):
    model=validate_model(model)
    if instant(model['trained_at'])>origin:raise ValueError('directional PV calibration not available at origin')
    return _calculate(model,watts,azimuth_degrees)


def assess_directional(model,rows,*,holdout_start,holdout_end):
    model=validate_model(model)
    if not instant(model['cutoff'])<=holdout_start<holdout_end:raise ValueError('later disjoint directional PV holdout required')
    selected=[_pair(r) for r in rows if holdout_start<=instant(r['origin'])<instant(r['start']) and instant(r['end'])<holdout_end and r['potential_proxy_eligible'] is True]
    def metrics(values):
        base=[r['baseline_w']-r['outcome_w'] for r in values];candidate=[_calculate(model,r['baseline_w'],r['azimuth_degrees'])-r['outcome_w'] for r in values]
        mean=lambda xs:None if not xs else fsum(abs(x) for x in xs)/len(xs)
        return dict(pairs=len(values),baseline_mae_w=mean(base),candidate_mae_w=mean(candidate),baseline_bias_w=None if not base else fsum(base)/len(base),candidate_bias_w=None if not candidate else fsum(candidate)/len(candidate))
    days=independent_days(selected);result=metrics(selected)
    out=dict(schema='earthship-pv-directional-comparison/v2',timezone=TIMEZONE,independent_day_basis=DAY_BASIS,model_sha256=model['model_sha256'],holdout_start=holdout_start.isoformat(),holdout_end=holdout_end.isoformat(),
        **result,independent_target_days=days,selected=len(selected)>=24 and days>=2 and result['candidate_mae_w']<result['baseline_mae_w'],
        by_azimuth={str(edge):metrics([r for r in selected if sector(r['azimuth_degrees'])==str(edge)]) for edge in range(0,360,45)},
        qualification='retrospective_development_assessment_not_prospective_or_metrology',physical_calibration_qualified=False,prospective_score=False,automatic_actuation=False)
    out['report_sha256']=identity(out);return out
