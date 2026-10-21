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
    return rain_comparison_report(pairs=pairs,withheld=withheld,cohorts=scored,
        decisions=[dict(local_date=r['local_date'],site_timezone=r['site_timezone'],issued_at=r['issued_at'],forecast_sha256=r['forecast_sha256']) for _,r in sorted(decisions.items())])


def rain_comparison_report(*,pairs,withheld,cohorts,decisions):
    """Closed report envelope, also used when aggregation is explicitly withheld."""
    body=dict(schema='earthship-weathernext-rain-comparison/v1',provider='weathernext3',qualification='SHADOW_ONLY',
        selected_product=None,primary_metric='paired_complete_day_mae_mm',selection_rule='latest_retained_issue_strictly_before_local_day_before_missingness_or_outcomes',
        scoring_status='diagnostic_comparison_only',cohorts=cohorts,pairs=pairs,withheld=withheld,
        decisions=decisions,
        automatic_actuation=False)
    return body|{'report_sha256':identity(body)}
