"""Replace the original task slot before adding it elsewhere; fixed loads remain."""
from datetime import timedelta
from copy import deepcopy
from ..control_contracts import instant
from ..codec import identity
from .contracts import number


def compare_load_windows(*,inputs,load,now,reserve):
    from . import _compare
    from household_profiled_storage import simulate_profiled_storage
    forecast=inputs['baseline_load_forecast'];steps=inputs['steps']
    if not isinstance(forecast,dict) or not isinstance(steps,list) or not 1<=len(steps)<=576:raise ValueError('bounded original scenarios required')
    start=instant(load['baseline_start']);deadline=instant(load['deadline']);duration=timedelta(minutes=load['duration_minutes']);end=start+duration
    rows=forecast['trajectory']
    if not isinstance(rows,list) or not 1<=len(rows)<=24:raise ValueError('bounded load trajectory required')
    origin=instant(forecast['origin'])
    # Use elapsed hours from the original forecast, not local wall-clock hours.
    if start<now or load['duration_minutes']%60 or (start-origin).total_seconds()%3600:
        return dict(reason='task_window_outside_supported_hourly_resolution',comparison=[],baseline=None,best=None)
    horizon=instant(rows[-1]['at'])
    if end>deadline or deadline>horizon:return dict(reason='task_deadline_infeasible',comparison=[],baseline=None,best=None)
    starts=sorted({start,*(origin+timedelta(hours=i) for i in range(len(rows)) if now<=origin+timedelta(hours=i))})
    starts=[at for at in starts if at+duration<=deadline]
    evaluated=[]
    for candidate in starts[:24]:
        alt=deepcopy(forecast)
        for i,row in enumerate(alt['trajectory']):
            b=instant(row['at']);a=b-timedelta(hours=1);hours=1.
            old=max(timedelta(0),min(b,end)-max(a,start)).total_seconds()/3600
            new=max(timedelta(0),min(b,candidate+duration)-max(a,candidate)).total_seconds()/3600
            row['mean_ac_w']=number(row['mean_ac_w']+load['power_w']*(new-old)/hours,0,20000)
            # Existing forecast carries cumulative kWh; recompute consistently.
        for row in alt['trajectory']:row['ac_kwh']=row['mean_ac_w']/1000
        alt['total_ac_kwh']=sum(row['ac_kwh'] for row in alt['trajectory'])
        alt['forecast_sha256']=identity({k:v for k,v in alt.items() if k!='forecast_sha256'})
        result=simulate_profiled_storage(steps=steps,initial_soc_pct=inputs['initial_soc_pct'],nominal_bank_kwh=inputs['nominal_bank_kwh'],load_forecast=alt)
        values=[inputs['initial_soc_pct'],*(r['nominal_soc_pct'] for r in result['trajectory'])]
        evaluated.append(dict(start=candidate.isoformat(),minimum_soc=min(values),reserve_ok=min(values)>=reserve,output=result))
    baseline=next(r for r in evaluated if r['start']==start.isoformat())
    feasible=[r for r in evaluated if r['reserve_ok']]
    best=max(feasible,key=lambda r:(r['minimum_soc'],r['start']==baseline['start'],-instant(r['start']).timestamp())) if feasible else baseline
    comparison=[_compare('Leave unchanged' if r is baseline else 'Run at '+r['start'],'Completes the useful task; nominal reserve '+('met' if r['reserve_ok'] else 'shortfall'),horizon,r['minimum_soc'],'minimum_nominal_soc','percent') for r in evaluated[:8]]
    return dict(reason=None if feasible else 'no_feasible_reserve_window',comparison=comparison,baseline=baseline,best=best)
