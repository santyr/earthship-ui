"""Lead/solar-group PV comparisons with explicit terrain identifiability limits."""
from datetime import timedelta
from math import fsum
from zoneinfo import ZoneInfo
from .contracts import identity,instant,finite
from .pv_calibration import _pair
from .pv_directional_calibration import validate_model,_calculate,sector

BANDS=((0,24),(24,48),(48,72),(72,120),(120,168),(168,240),(240,336))


def assess_horizons(model,rows,*,cutoff,end):
    model=validate_model(model)
    if not instant(model['cutoff'])<=cutoff<end:raise ValueError('later disjoint PV targets required')
    selected=[_pair(r) for r in rows if cutoff+timedelta(minutes=10)<=instant(r['origin'])<instant(r['start']) and instant(r['end'])<end and r['potential_proxy_eligible'] is True]
    for r in selected:
        if abs((instant(r['end'])-instant(r['origin'])).total_seconds()/3600-r['lead_hours'])>1e-7:raise ValueError('actual PV lead time required')
        if not all(finite(r.get(k)) for k in ('elevation_degrees','horizon_elevation_degrees')):raise ValueError('original native elevation required')
    zone=ZoneInfo('America/Denver')
    def metrics(values):
        def mean(key):return None if not values else fsum(abs((r['baseline_w'] if key=='raw' else _calculate(model,r['baseline_w'],r['azimuth_degrees']))-r['outcome_w']) for r in values)/len(values)
        raw,corrected=mean('raw'),mean('corrected');days=len({instant(r['end']).astimezone(zone).date() for r in values})
        return dict(pairs=len(values),independent_target_days=days,baseline_mae_w=raw,candidate_mae_w=corrected,
            supported=len(values)>=24 and days>=2 and corrected<raw)
    leads={f'{lo}-{hi}h':metrics([r for r in selected if lo<r['lead_hours']<=hi]) for lo,hi in BANDS}
    unique={}
    for r in selected:
        key=r['start'],r['end']
        if key in unique and (r['outcome_w'],r['energy_source_sha256'],r['elevation_degrees'],r['horizon_elevation_degrees'])!=(unique[key]['outcome_w'],unique[key]['energy_source_sha256'],unique[key]['elevation_degrees'],unique[key]['horizon_elevation_degrees']):raise ValueError('one original truth/geometry per target required')
        unique[key]=r
    targets=list(unique.values())
    margin=lambda r:r['elevation_degrees']-r['horizon_elevation_degrees']
    result=dict(schema='earthship-pv-horizon-assessment/v1',model_sha256=model['model_sha256'],training_cutoff=model['cutoff'],actual_trained_at=model['trained_at'],
        holdout_start=cutoff.isoformat(),holdout_end=end.isoformat(),by_lead=leads,
        supported_lead_ranges_hours=[[lo,hi] for lo,hi in BANDS if leads[f'{lo}-{hi}h']['supported']],
        by_month={str(m):metrics([r for r in selected if instant(r['end']).astimezone(zone).month==m]) for m in range(1,13)},
        by_azimuth={str(a):metrics([r for r in selected if sector(r['azimuth_degrees'])==str(a)]) for a in range(0,360,45)},
        by_elevation={name:metrics([r for r in selected if lo<r['elevation_degrees']<=hi]) for name,lo,hi in [('0-10',0,10),('10-25',10,25),('25-45',25,45),('45-90',45,90)]},
        by_horizon_margin={name:metrics([r for r in selected if lo<margin(r)<=hi]) for name,lo,hi in [('at_or_below',-180,0),('0-5',0,5),('5-15',5,15),('above_15',15,180)]},
        terrain=dict(independent_target_intervals=len(targets),independent_target_days=len({instant(r['end']).astimezone(zone).date() for r in targets}),
            near_declared_horizon_intervals=sum(abs(margin(r))<=5 for r in targets),at_or_below_declared_horizon_intervals=sum(margin(r)<=0 for r in targets),
            horizon_update_qualified=False,orientation_update_qualified=False,
            limitations=['controller_charge_mode_and_fault_receipts_absent','low_soc_positive_charge_sub_clip_selection_is_only_a_proxy',
                'minimum_100W_input_selection_excludes_zero_production_shadow_intervals','weather_geometry_meter_and_array_losses_not_independently_identified',
                'local_station_radiation_is_lux_derived_not_calibrated_GHI','seasonal_Google_coverage_does_not_create_missing_local_labels']),
        readiness_basis='retrospective_assumed_cutoff_plus_10_minutes_actual_training_clock_unchanged',
        comparison_scope='earlier_fitted_fixed_directional_algorithm_not_backdated_current_selected_weights',
        physical_calibration_qualified=False,prospective_score=False,automatic_actuation=False)
    result['report_sha256']=identity(result);return result
