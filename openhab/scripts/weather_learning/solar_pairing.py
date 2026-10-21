"""Rebuild matched solar pairs through the same component projection as serving."""
from math import fsum
from .contracts import identity,instant,finite,digest


def component_pairs(*,labels,observations,forcing,positions,array,horizon_profile,timezone_name,
                    fixed_gain_by_sector=None,fixed_gain_source_sha256=None):
    from household_pv_components import project_window_components
    if not isinstance(labels,list) or not 1<=len(labels)<=10000:raise ValueError('bounded original PV pair labels required')
    if fixed_gain_by_sector is None:fixed_gain_by_sector={str(i):1. for i in range(0,360,45)}
    if (set(fixed_gain_by_sector)!={str(i) for i in range(0,360,45)} or
            any(not finite(g) or not .5<=g<=1.5 for g in fixed_gain_by_sector.values())):
        raise ValueError('bounded fixed electrical correction required')
    if fixed_gain_source_sha256 is not None:digest(fixed_gain_source_sha256)
    for label in labels:
        observation=observations.get((label['start'],label['end']))
        if (observation is None or label.get('potential_proxy_eligible') is not True or
                observation.get('potential_proxy_eligible') is not True or
                label['energy_source_sha256']!=observation['source_sha256'] or
                label['forecast_sha256']!=forcing['snapshot_sha256'] or label['origin']!=forcing['origin'] or
                abs(label['outcome_w']-observation['outcome_w'])>1e-9):
            raise ValueError('qualified original label/measurement/forcing mismatch')
    start=min(instant(r['start']) for r in labels);end=max(instant(r['end']) for r in labels)
    args=dict(array=array,forecast=forcing,positions=positions,start=start,end=end,timezone_name=timezone_name,horizon_profile=horizon_profile)
    native=project_window_components(**args);total=project_window_components(**args,force_total_only=True)
    geometry={p['at']:p for p in positions};out=[]
    for label in labels:
        start,end=map(instant,(label['start'],label['end']));seconds=(end-start).total_seconds()
        if not 0<seconds<=300:raise ValueError('at most five-minute measured target required')
        def select(projection):
            pieces=[(max(start,instant(r['start'])),min(end,instant(r['end'])),r) for r in projection['segments'] if instant(r['start'])<end and start<instant(r['end'])]
            if fsum((b-a).total_seconds() for a,b,r in pieces)!=seconds:raise ValueError('complete matched PV projection required')
            return fsum((b-a).total_seconds()*r['potential_dc_w'] for a,b,r in pieces)/seconds,pieces
        native_w,pieces=select(native);total_w,_=select(total)
        reasons=sorted({r['reason'] for a,b,r in pieces if r['reason'] is not None})
        if len(reasons)>1:raise ValueError('single source-hour fallback reason required per target')
        point=geometry.get(label['end'])
        if point is None:raise ValueError('original target endpoint geometry required')
        azimuth=point['azimuth_degrees']%360;observation=observations[(label['start'],label['end'])]
        row=dict(start=label['start'],end=label['end'],origin=label['origin'],native_w=native_w,total_only_w=total_w,
            outcome_w=observation['outcome_w'],fixed_gain=fixed_gain_by_sector[str(int(azimuth//45)*45)],
            fixed_gain_source_sha256=fixed_gain_source_sha256,forecast_sha256=label['forecast_sha256'],
            energy_source_sha256=observation['source_sha256'],outcome_available_at=observation['available_at'],
            cohort_sha256=identity(dict(measurement=observation['cohort_sha256'],solar_grid=forcing['rows'][0]['solar']['grid_sha256'])),
            availability_basis=forcing.get('availability_basis','recorded_operational_original'),
            native_supported=not reasons,fallback_reason=reasons[0] if reasons else None,azimuth_degrees=azimuth)
        row['pair_sha256']=identity(row);out.append(row)
    return out
