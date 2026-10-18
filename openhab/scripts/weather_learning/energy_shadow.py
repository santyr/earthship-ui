"""Read-only weather/energy qualification; no fitting, promotion or controls.

Rain comparisons rederive local totals from retained original counter receipts.
The existing native validator remains the only daily measurement authority.
"""
from dataclasses import asdict
from datetime import date,datetime,time,timedelta,timezone
from itertools import islice
import math
from zoneinfo import ZoneInfo

from weather_rain_day import qualify_rain_day,MAX_ROWS
from weather_rain_evidence import RainPolicy
from .contracts import canonical,digest,finite,identity,instant
from .evidence import utc
from .features import prospective_snapshot
from .normalize import daily_rain_depth

RAIN_PRODUCTS=('total_precipitation_1hr','imerg_tp_1hr','experimental_tp_1hr')


def _bounds(day,zone):
    if not isinstance(day,date) or isinstance(day,datetime):raise ValueError('local date required')
    zone=ZoneInfo(zone)
    return (datetime.combine(day,time.min,zone).astimezone(timezone.utc),
            datetime.combine(day+timedelta(days=1),time.min,zone).astimezone(timezone.utc))


def capture_rain_day(*,local_date,as_of,cutover,policy,site_timezone,observations):
    """Seal exact source bytes and policy after native complete-day qualification."""
    start,end=_bounds(local_date,site_timezone);as_of,cutover=map(utc,(as_of,cutover))
    if not cutover<=start<end<=as_of or not isinstance(policy,RainPolicy):
        raise ValueError('post-cutover complete native rain day required')
    rows=tuple(islice(observations,MAX_ROWS+1))
    summary=qualify_rain_day(local_date,as_of=as_of,observations=rows,policy=policy,site_timezone=site_timezone)
    body=dict(schema='earthship-qualified-rain-source/v1',source_item='Weather_Rain_Evidence_JSON',
        local_date=local_date.isoformat(),site_timezone=site_timezone,cutover=cutover.isoformat(),
        policy=asdict(policy),observations=[[utc(at).isoformat(),raw] for at,raw in rows],summary=summary,
        available_at=max(utc(at) for at,_ in rows).isoformat())
    return body|dict(source_sha256=identity(body),assessed_at=as_of.isoformat())


def _rain_source(value):
    if not isinstance(value,dict) or set(value)!={'schema','source_item','local_date','site_timezone','cutover','policy','observations','summary','available_at','source_sha256','assessed_at'}:
        raise ValueError('closed original rain source capsule required')
    digest(value['source_sha256'])
    rebuilt=capture_rain_day(local_date=date.fromisoformat(value['local_date']),as_of=instant(value['assessed_at']),
        cutover=instant(value['cutover']),policy=RainPolicy(**value['policy']),site_timezone=value['site_timezone'],
        observations=((instant(at),raw) for at,raw in value['observations']))
    if canonical(rebuilt)!=canonical(value):raise ValueError('rain source summary or digest differs from original receipts')
    return rebuilt


def rain_day_forecast(snapshot,*,issued_at,completed_at,local_date):
    """One original decision's complete-day predictions, including missing heads."""
    issued_at=utc(issued_at);snapshot=prospective_snapshot(snapshot,issued_at=issued_at)
    zone=snapshot['site']['timezone'];start,end=_bounds(local_date,zone)
    completed_at=utc(completed_at)
    if not issued_at<=completed_at<start:raise ValueError('daily forecast must complete before day starts')
    points=snapshot['points'];cells=sorted({(p['latitude'],p['longitude']) for p in points if p['variable'] in RAIN_PRODUCTS})
    if len(cells)!=1:raise ValueError('one original rain grid required')
    grid=identity(dict(site=snapshot['site'],products=RAIN_PRODUCTS,cells=cells))
    body=dict(schema='earthship-weathernext-rain-day/v1',provider='weathernext3',local_date=local_date.isoformat(),
        site_timezone=zone,issued_at=issued_at.isoformat(),completed_at=completed_at.isoformat(),initialized_at=snapshot['initialized_at'],
        available_at=snapshot['ingestion_completed_at'],snapshot_sha256=snapshot['snapshot_sha256'],grid_sha256=grid,
        products={p:daily_rain_depth(points,local_date,zone,variable=p) for p in RAIN_PRODUCTS})
    return _forecast(body|{'forecast_sha256':identity(body)})


def _forecast(value):
    keys={'schema','provider','local_date','site_timezone','issued_at','completed_at','initialized_at','available_at','snapshot_sha256','grid_sha256','products','forecast_sha256'}
    if not isinstance(value,dict) or set(value)!=keys or value['schema']!='earthship-weathernext-rain-day/v1' or value['provider']!='weathernext3':
        raise ValueError('closed original Google rain forecast required')
    for key in ('snapshot_sha256','grid_sha256','forecast_sha256'):digest(value[key])
    body={k:v for k,v in value.items() if k!='forecast_sha256'}
    if identity(body)!=value['forecast_sha256']:raise ValueError('rain forecast digest differs')
    issued,initialized,available=map(instant,(value['issued_at'],value['initialized_at'],value['available_at']))
    start,end=_bounds(date.fromisoformat(value['local_date']),value['site_timezone'])
    completed=instant(value['completed_at'])
    if not initialized<=available<=issued<=completed<start<end<=initialized+timedelta(hours=360) or issued-initialized>timedelta(hours=24):
        raise ValueError('original prospective daily forecast clocks required')
    if not isinstance(value['products'],dict) or set(value['products'])!=set(RAIN_PRODUCTS) or any(v is not None and (not finite(v) or v<0) for v in value['products'].values()):
        raise ValueError('separate finite native rain products required')
    return value


def _metrics(pairs):
    result={}
    for product in RAIN_PRODUCTS:
        errors=[p['forecast_mm'][product]-p['observed_mm'] for p in pairs]
        absolute=sorted(abs(x) for x in errors);count=len(errors)
        result[product]=dict(days=count,mae_mm=sum(absolute)/count,rmse_mm=math.sqrt(sum(x*x for x in errors)/count),
            bias_mm=sum(errors)/count,absolute_error_p95_mm=absolute[math.ceil(.95*count)-1],
            mae_lower_bound_mm=sum(max(0,abs(e)-p['boundary_uncertainty_mm']/2) for e,p in zip(errors,pairs))/count,
            mae_upper_bound_mm=sum(abs(e)+p['boundary_uncertainty_mm']/2 for e,p in zip(errors,pairs))/count)
    return result


def compare_rain_products(forecasts,outcomes):
    """Latest retained pre-day decision, selected before outcomes/missingness.

    Outcomes may stream in one at a time; raw receipt capsules are validated and
    released rather than retained in the report. Epoch/grid cohorts never pool.
    No product is selected on these diagnostics or on an opened final holdout.
    """
    if not isinstance(forecasts,(list,tuple)) or len(forecasts)>20000:raise ValueError('bounded retained forecasts required')
    decisions={};seen={}
    for raw in forecasts:
        row=_forecast(raw);key=(row['site_timezone'],row['local_date']);at=instant(row['issued_at'])
        original=(key,at);prior=seen.get(original)
        if prior is not None and prior!=row['forecast_sha256']:raise ValueError('conflicting original daily decision')
        seen[original]=row['forecast_sha256']
        if key not in decisions or at>instant(decisions[key]['issued_at']):decisions[key]=row
    if len(decisions)>366:raise ValueError('rain comparison day bound exceeded')
    labels={}
    for index,raw in enumerate(islice(outcomes,733)):
        if index==732:raise ValueError('rain outcome count bound exceeded')
        row=_rain_source(raw);key=(row['site_timezone'],row['local_date']);prior=labels.get(key)
        if prior is not None and prior['source_sha256']!=row['source_sha256']:raise ValueError('conflicting original rain outcome')
        labels[key]={k:v for k,v in row.items() if k!='observations'}
    pairs=[];withheld=[];cohorts={}
    for key,forecast in sorted(decisions.items()):
        base=dict(local_date=key[1],site_timezone=key[0],forecast_sha256=forecast['forecast_sha256'])
        if any(v is None for v in forecast['products'].values()):withheld.append(base|{'reason':'INCOMPLETE_COMMON_PRODUCTS'});continue
        outcome=labels.get(key)
        if outcome is None:withheld.append(base|{'reason':'NO_QUALIFIED_OUTCOME'});continue
        summary=outcome['summary'];observed=summary['rain_in']*25.4;uncertainty=summary['uncertainty_in']*25.4
        regime='wet' if observed-uncertainty/2>0 else 'dry' if observed+uncertainty/2==0 else 'boundary_uncertain'
        start,end=_bounds(date.fromisoformat(key[1]),key[0]);lead=(end-instant(forecast['issued_at'])).total_seconds()/3600
        horizon=next(label for limit,label in ((24,'0-24h'),(72,'24-72h'),(168,'72-168h'),(360,'168-360h')) if lead<=limit)
        # Include source policy/sensor identity as well as receiver epoch and grid.
        cohort=identity(dict(grid=forecast['grid_sha256'],epoch=summary['stream_epoch'],policy=outcome['policy'],cutover=outcome['cutover']))
        pair=base|dict(issued_at=forecast['issued_at'],snapshot_sha256=forecast['snapshot_sha256'],outcome_sha256=outcome['source_sha256'],
            source_available_at=outcome['available_at'],stream_epoch=summary['stream_epoch'],grid_sha256=forecast['grid_sha256'],
            observed_mm=observed,boundary_uncertainty_mm=uncertainty,forecast_mm=forecast['products'],observed_regime=regime,horizon=horizon,cohort_sha256=cohort)
        pairs.append(pair);cohorts.setdefault(cohort,[]).append(pair)
    scored={}
    for cohort,rows in sorted(cohorts.items()):
        groups=lambda key:{value:dict(days=len(selected),products=_metrics(selected)) for value in sorted({r[key] for r in rows}) if (selected:=[r for r in rows if r[key]==value])}
        scored[cohort]=dict(days=len(rows),products=_metrics(rows),by_observed_regime=groups('observed_regime'),by_horizon=groups('horizon'))
    body=dict(schema='earthship-weathernext-rain-comparison/v1',provider='weathernext3',qualification='SHADOW_ONLY',
        selected_product=None,primary_metric='paired_complete_day_mae_mm',selection_rule='latest_retained_issue_strictly_before_local_day_before_missingness_or_outcomes',
        scoring_status='diagnostic_comparison_only',cohorts=scored,pairs=pairs,withheld=withheld,
        decisions=[dict(local_date=r['local_date'],site_timezone=r['site_timezone'],issued_at=r['issued_at'],forecast_sha256=r['forecast_sha256']) for _,r in sorted(decisions.items())],
        automatic_actuation=False)
    return body|{'report_sha256':identity(body)}


def compare_fixed_energy(reference,*,plan_receipt,google_snapshot,assessed_at,profiled_reference=None,clock=lambda:datetime.now(timezone.utc)):
    """Replay a retained physical array/storage control, changing only weather.

    Execute with the original numerical runtime on sys.path. Its current full
    manifest must match the retained receipts; never pass a saved manifest as
    though it were the executing source. This temporary pre-cutover attribution
    adapter cannot fit a model, select a production provider or operate equipment.
    """
    from household_energy_forecast import forecast_runtime_manifest,replay_energy_forecast,_storage
    from household.model_snapshot import restore_snapshot
    from household.weather_context import project_weather
    from household_pv_model import integrate_array
    from household_solar_horizon import horizon_configuration
    from hashlib import sha256
    from pathlib import Path
    def attribution_manifest():
        directory=Path(__file__).resolve().parent
        names=('energy_shadow.py','features.py','contracts.py','config.py','normalize.py','weathernext_ee.py','evidence.py')
        return {'weather_learning/'+name:sha256((directory/name).read_bytes()).hexdigest() for name in names}
    assessed_at=utc(assessed_at)
    attribution_runtime=attribution_manifest()
    runtime=forecast_runtime_manifest()
    reference=replay_energy_forecast(reference,plan_receipt=plan_receipt,runtime_manifest=runtime)
    reference_at=instant(reference['inputs']['assessed_at'])
    if assessed_at<reference_at:raise ValueError('comparison precedes original control availability')
    profiled=None;profiled_runtime=load_runtime=None
    if profiled_reference is not None:
        from household_profiled_forecast import profiled_runtime_manifest,replay_profiled_forecast
        from household_ac_load_artifact import runtime_manifest as load_runtime_manifest
        profiled_runtime=profiled_runtime_manifest()
        load_runtime={} if profiled_reference['inputs']['load_source'] is None else load_runtime_manifest()
        profiled=replay_profiled_forecast(profiled_reference,energy_receipt=reference,plan_receipt=plan_receipt,
            runtime_manifest=profiled_runtime,energy_runtime_manifest=runtime,load_runtime_manifest=load_runtime)
        if assessed_at<instant(profiled['inputs']['assessed_at']):raise ValueError('comparison precedes original load-profile availability')
    original=reference['output'];pv=original['array_pv'];origin=instant(pv['origin'])
    snapshot=restore_snapshot(plan_receipt['inputs']['snapshot'],plan_receipt['inputs']['source_contexts'])
    context=project_weather(snapshot.weather)
    body=dict(schema='earthship-weathernext-fixed-energy-attribution/v1',qualification='SHADOW_ONLY',
        status='UNAVAILABLE',reason=None,origin=origin.isoformat(),assessed_at=assessed_at.isoformat(),
        original_energy_sha256=identity(reference),original_plan_sha256=identity(plan_receipt),
        fixed_runtime_sha256=identity(runtime),attribution_source_manifest=attribution_runtime,geometry_series_sha256=context.get('geometry_series_sha256'),
        original_profiled_sha256=None if profiled is None else identity(profiled),
        fixed_profiled_runtime_sha256=None if profiled_runtime is None else identity(profiled_runtime),
        fixed_load_runtime_sha256=None if load_runtime is None else identity(load_runtime),
        control=dict(provider='openmeteo',array_pv=pv,nominal_storage=original['nominal_storage'],profiled=None if profiled is None else profiled['output']),google=None,
        changed_inputs=['hourly_ghi','hourly_station_temperature','hourly_wind'],native_direct_radiation_used=False,
        model_rule='original_fixed_Erbs_array_and_constant_AC_nominal_storage',weather_weights_imported=False,
        comparison_scope='fixed_model_weather_forcing_attribution_only',
        outcomes=dict(score_status='NOT_SCORED',measured_available_pv_kwh=None,measured_captured_pv_kwh=None,
            measured_evening_soc_pct=None,measured_overnight_trough_soc_pct=None,measured_full_charge=None),
        prospective_ending_hours={},physical_calibration_qualified=False,automatic_actuation=False)
    if pv['status']!='projected_provisional_array_potential':
        body['reason']='ORIGINAL_ARRAY_CONTROL_UNAVAILABLE'
    else:
        try:
            google=prospective_snapshot(google_snapshot,issued_at=origin)
            geometry=context['solar_geometry'];site=geometry['site']
            if (google['site']['latitude'],google['site']['longitude'],google['site']['timezone'])!=(site['latitude'],site['longitude'],geometry['timezone']):
                raise ValueError('authoritative energy/Google site differs')
            index={(p['variable'],instant(p['valid_at'])):p['value'] for p in google['points'] if p['statistic']=='mean'}
            rows=[]
            for original_row in context['hourly_forecast']:
                at=instant(original_row['at']);values=[]
                for variable in ('surface_solar_radiation_downwards_1hr','station_head_temperature_2m','wind_speed_10m'):
                    value=index.get((variable,at))
                    if value is None:raise ValueError('complete Google GHI/temperature/wind required')
                    values.append(value)
                ghi,temp_c,wind_ms=values
                rows.append(dict(at=at.isoformat(),radiationWm2=ghi,tempF=temp_c*9/5+32,windMph=wind_ms/.44704))
            horizon,reason=horizon_configuration(reference['inputs']['horizon_source'],origin=origin,site=site,timezone_name=geometry['timezone'])
            if horizon is None:raise ValueError('same original horizon profile required')
            replacement=integrate_array(array=pv['array'],assumptions=pv['assumptions'],hourly_forecast=rows,
                positions=geometry['positions'],origin=origin,horizon_hours=context['horizon_hours'],timezone_name=geometry['timezone'],
                horizon_profile=horizon['profile'])
            replacement.update(status='projected_provisional_array_potential',reason=None)
            storage=_storage(snapshot,replacement,original['current_flows'],reference['inputs']['topology_source'],reference_at)
            profiled_storage=None
            if profiled is not None:
                fixed=profiled['output'];profiled_storage=dict(status=fixed['status'],reason=fixed['reason'],profiled_storage=None,
                    load_forecast_sha256=None if fixed['load_forecast'] is None else fixed['load_forecast']['forecast_sha256'])
                if fixed['status']=='conditional_nominal_simulation':
                    from household_profiled_storage import simulate_profiled_storage
                    initial=original['nominal_storage']
                    profiled_storage['profiled_storage']=simulate_profiled_storage(steps=replacement['steps'],
                        initial_soc_pct=initial['initial_soc_pct'],nominal_bank_kwh=initial['nominal_bank_kwh'],load_forecast=fixed['load_forecast'])
            body.update(status='COMPARED',google=dict(provider='weathernext3',array_pv=replacement,nominal_storage=storage,profiled=profiled_storage),
                google_snapshot_sha256=google['snapshot_sha256'],google_initialized_at=google['initialized_at'],
                google_available_at=google['ingestion_completed_at'],
                retained_context_sha256=context['weather_context_sha256'])
        except (ValueError,KeyError,TypeError,OverflowError):
            body['reason']='GOOGLE_FORCING_UNAVAILABLE_OR_INCOMPATIBLE'
    if forecast_runtime_manifest()!=runtime or attribution_manifest()!=attribution_runtime:
        raise ValueError('fixed numerical or attribution source changed during comparison')
    if profiled is not None and (profiled_runtime_manifest()!=profiled_runtime or ({} if profiled['inputs']['load_source'] is None else load_runtime_manifest())!=load_runtime):
        raise ValueError('fixed profiled/load source changed during comparison')
    completed=utc(clock())
    if completed<assessed_at:raise ValueError('comparison completion precedes assessment')
    body['completed_at']=completed.isoformat()
    if body['status']=='COMPARED':
        for hour in range(1,context['horizon_hours']+1):
            body['prospective_ending_hours'][str(hour)]=completed<=origin+timedelta(hours=hour-1)
    return body|{'report_sha256':identity(body)}
