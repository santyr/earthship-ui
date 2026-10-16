"""Pure nominal storage with a frozen hourly AC-output forecast.

Reuse the original integrator for every complete elapsed hour. Original PV and
constant-load forecast code remain unchanged and independently replayable.
"""
from datetime import timedelta
import math
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household_pv_model import simulate_storage
from household_ac_load_model import RULE

TOTALS=('potential_pv_kwh','modeled_captured_pv_kwh','modeled_unaccepted_pv_kwh','modeled_unserved_dc_kwh')
CUMULATIVE=('cumulative_potential_pv_kwh','cumulative_modeled_captured_pv_kwh','cumulative_modeled_unaccepted_pv_kwh','cumulative_modeled_unserved_dc_kwh')


def simulate_profiled_storage(*,steps,initial_soc_pct,nominal_bank_kwh,load_forecast):
    if (not isinstance(load_forecast,dict) or load_forecast.get('schema')!='earthship-ac-load-forecast/v1' or
        load_forecast.get('model_rule')!=RULE or load_forecast.get('status')!='projected' or
        identity({k:v for k,v in load_forecast.items() if k!='forecast_sha256'})!=load_forecast.get('forecast_sha256') or
        not isinstance(load_forecast.get('trajectory'),list) or len(load_forecast['trajectory'])!=24):
        raise ValueError('original projected AC load required')
    if not isinstance(steps,list) or not 1<=len(steps)<=576:raise ValueError('bounded original PV steps required')
    origin=instant(load_forecast['origin']);groups=[[] for _ in range(24)];last=origin;loads_w=[]
    for hour,row in enumerate(load_forecast['trajectory']):
        if not isinstance(row,dict) or instant(row.get('at'))!=origin+timedelta(hours=hour+1):raise ValueError('matched original load targets required')
        watts=row.get('mean_ac_w');energy=row.get('ac_kwh')
        if (type(watts) not in (int,float) or not math.isfinite(watts) or not 0<=watts<=20000 or
            type(energy) not in (int,float) or not math.isfinite(energy) or not math.isclose(energy,watts/1000,rel_tol=0,abs_tol=1e-10)):
            raise ValueError('original hourly AC units differ')
        loads_w.append(watts)
    if not math.isclose(load_forecast['total_ac_kwh'],math.fsum(loads_w)/1000,rel_tol=0,abs_tol=1e-10):raise ValueError('original AC total differs')
    for row in steps:
        if not isinstance(row,dict) or set(row)!={'start','end','potential_pv_kwh'}:raise ValueError('closed original PV step required')
        start,end=instant(row['start']),instant(row['end']);hour=int((start-origin).total_seconds()//3600)
        if start!=last or not 0<=hour<24 or not start<end<=origin+timedelta(hours=hour+1):raise ValueError('complete matching elapsed-hour PV grid required')
        groups[hour].append(row);last=end
    if last!=origin+timedelta(hours=24) or any(not rows for rows in groups):raise ValueError('complete original 24-hour PV horizon required')
    total={key:0. for key in TOTALS};trajectory=[];soc=initial_soc_pct;first=None
    for hour,rows in enumerate(groups):
        part=simulate_storage(steps=rows,initial_soc_pct=soc,nominal_bank_kwh=nominal_bank_kwh,load_ac_w=loads_w[hour])
        if first is None:first=part
        if len(part['trajectory'])!=1:raise ValueError('one complete original storage hour required')
        point=dict(part['trajectory'][0]);soc=point['nominal_soc_pct']
        for field,key in zip(CUMULATIVE,TOTALS):total[key]+=part[key];point[field]=total[key]
        trajectory.append(point)
    result={key:value for key,value in first.items() if key not in {'trajectory',*TOTALS,'household_ac_load_w_assumption'}}
    result.update(model_rule='array_potential_profiled_AC_load_nominal_storage_v1',load_assumption='profiled_mean_held_within_each_elapsed_hour',
        load_forecast_sha256=load_forecast['forecast_sha256'],load_model_sha256=load_forecast['model_sha256'],
        household_ac_load_w_assumptions=loads_w,trajectory=trajectory,**total)
    return loads(canonical(result))
