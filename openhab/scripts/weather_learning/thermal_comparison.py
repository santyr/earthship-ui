"""Retrospective Google-forced physics comparisons with explicit action strata."""
from datetime import timedelta
from math import fsum
from zoneinfo import ZoneInfo
from .contracts import instant,finite

MODEL_LATENCY=timedelta(minutes=10)
ACTIONS=('indoor_shade_closed','outdoor_shade_present','vent_open')


def select_fit(models,*,origin,cadence):
    if cadence not in ('daily','six_hourly'):raise ValueError('explicit thermal fitting cadence required')
    selected=[];zone=ZoneInfo('America/Denver')
    for value in models:
        cutoff=instant(value['cutoff']);local=cutoff.astimezone(zone)
        aligned=not (local.minute or local.second or local.microsecond) and local.hour%(24 if cadence=='daily' else 6)==0
        if aligned and cutoff+MODEL_LATENCY<=origin:selected.append(value)
    return max(selected,key=lambda value:instant(value['cutoff'])) if selected else None


def google_forcings(hours,*,origin,actions,horizon_hours):
    from thermal_model.installed_shade_dynamics import InstalledShadeForcing
    if type(horizon_hours) is not int or not 1<=horizon_hours<=24:raise ValueError('bounded thermal forcing horizon required')
    if set(actions)!=set(ACTIONS) or not all(finite(actions[k]) for k in ACTIONS):raise ValueError('known original action state required')
    if not 0<=actions['indoor_shade_closed']<=1 or actions['outdoor_shade_present'] not in (0,1) or not 0<=actions['vent_open']<=2:raise ValueError('bounded original action state required')
    rows=[]
    for i in range(1,horizon_hours*12+1):
        at=origin+timedelta(minutes=5*i);right=at.replace(minute=0,second=0,microsecond=0)
        if right<at:right+=timedelta(hours=1)
        left=right-timedelta(hours=1);a=hours.get(left.isoformat(),{});b=hours.get(right.isoformat(),{})
        ta=a.get('station_head_temperature_2m');tb=b.get('station_head_temperature_2m');ghi=b.get('surface_solar_radiation_downwards_1hr')
        if not all(finite(v) for v in (ta,tb,ghi)) or not -40<=ta<=60 or not -40<=tb<=60 or not 0<=ghi<=1600:
            raise ValueError('complete bounded Google thermal forcing required')
        fraction=(at-left).total_seconds()/3600;outside=(ta*(1-fraction)+tb*fraction)*9/5+32
        rows.append(InstalledShadeForcing(at,outside,ghi,**actions))
    return tuple(rows)


def action_stratum(samples,*,origin,target):
    initial=samples.get(origin)
    if initial is None or any(initial.get(k) is None for k in ACTIONS):return 'unknown'
    changed=False;at=origin
    while at<=target:
        row=samples.get(at)
        if row is None or not row.get('passive_fit_allowed') or any(row.get(k) is None for k in ACTIONS):return 'unknown'
        changed=changed or any(row[k]!=initial[k] for k in ACTIONS);at+=timedelta(minutes=5)
    return 'changed' if changed else 'stable'


def summarize(rows):
    def group(values):
        methods={}
        for name in sorted({name for r in values for name in r['predictions']}):
            selected=[r for r in values if r['predictions'].get(name) is not None]
            if not selected:continue
            metrics={}
            for index,kind in enumerate(('air','mass')):
                errors=[(r['predictions'][name][index]-r['actual'][index])*5/9 for r in selected]
                metrics[kind]=dict(mae_c=fsum(abs(v) for v in errors)/len(errors),bias_c=fsum(errors)/len(errors))
            methods[name]=dict(pairs=len(selected),origin_days=len({instant(r['origin']).astimezone(ZoneInfo('America/Denver')).date() for r in selected}),**metrics)
        return methods
    stable=[r for r in rows if r['action_stratum']=='stable']
    result=dict(all_outcomes=group(rows),stable_known_actions=group(stable),by_horizon={str(h):group([r for r in stable if r['lead_hours']==h]) for h in (1,6,12,24)},
        action_counts={kind:sum(r['action_stratum']==kind for r in rows) for kind in ('stable','changed','unknown')})
    methods=result['stable_known_actions'];daily=methods.get('daily_physics');fast=methods.get('six_hourly_physics')
    better=(daily is not None and fast is not None and daily['pairs']==fast['pairs'] and fast['origin_days']>=2 and fast['air']['mae_c']<daily['air']['mae_c'] and fast['mass']['mae_c']<=daily['mass']['mae_c'])
    result.update(cadence_decision='six_hourly' if better else 'daily',cadence_rule='improve_air_MAE_without_worsening_mass_on_same_stable_known_action_pairs',prospective_score=False,automatic_actuation=False)
    return result
