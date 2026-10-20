"""Matched retrospective thermal conditioning decisions, without actuation."""
from datetime import timedelta
from copy import deepcopy
from math import fsum
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from .contracts import instant,finite,identity


def correct_outdoor_hours(hours,*,model,origin,outdoor_c,timezone_name,horizon_hours):
    from .site_calibration import _model,_calculate
    from .historical_serving import temperature_features
    model=_model(model)
    if model['kind']!='outdoor_temperature_c' or instant(model['cutoff'])+timedelta(minutes=10)>origin:raise ValueError('earlier outdoor comparison model required')
    if not finite(outdoor_c) or not -40<=outdoor_c<=60 or type(horizon_hours) is not int or not 1<=horizon_hours<=24:raise ValueError('qualified original outdoor state required')
    result=deepcopy(hours);bias=outdoor_c-hours[origin.isoformat()]['station_head_temperature_2m']
    result[origin.isoformat()]['station_head_temperature_2m']=outdoor_c
    for i in range(1,horizon_hours+1):
        at=origin+timedelta(hours=i);raw=hours[at.isoformat()]['station_head_temperature_2m']
        features=temperature_features(SimpleNamespace(target_at=at,mean_c=raw),origin=origin,origin_bias_c=bias,timezone_name=timezone_name)
        result[at.isoformat()]['station_head_temperature_2m']=max(-40.,min(60.,_calculate(model,features,raw)))
    return result


def select_balanced(rows):
    stable=[r for r in rows if r['action_stratum']=='stable'];metrics={};excluded=[]
    names=sorted({name for row in rows for name in row['predictions']})
    for name in names:
        if not stable or any(row['predictions'].get(name) is None for row in stable):excluded.append(name);continue
        air=fsum(abs(row['predictions'][name][0]-row['actual'][0])*5/9 for row in stable)/len(stable)
        mass=fsum(abs(row['predictions'][name][1]-row['actual'][1])*5/9 for row in stable)/len(stable)
        metrics[name]=dict(pairs=len(stable),air_mae_c=air,mass_mae_c=mass,balanced_mae_c=(air+mass)/2)
    days=len({instant(row['origin']).astimezone(ZoneInfo('America/Denver')).date() for row in stable})
    chosen='six_hourly_physics'
    if days>=2 and chosen in metrics:
        chosen=min(metrics,key=lambda name:(metrics[name]['balanced_mae_c'],name!='six_hourly_physics',name))
    result=dict(schema='earthship-thermal-conditioning-selection/v1',selected_method=chosen,metrics=metrics,excluded_incomplete_methods=excluded,
        stable_pairs=len(stable),independent_origin_dates=days,selection_rule='minimum_equal_weight_air_mass_MAE_on_identical_stable_known_action_pairs',
        qualification='retrospective_development_selection_not_causal_or_actuator_qualification',prospective_score=False,automatic_actuation=False)
    result['report_sha256']=identity(result);return result
