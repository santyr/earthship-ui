"""Original solar intervals versus source-qualified lux-proxy exposures.

This is diagnostic comparison, not calibrated GHI/direct-component validation,
PV calibration, fitting, production publication or equipment authority.
"""
from bisect import bisect_left,bisect_right
from dataclasses import asdict
from datetime import datetime,timedelta
from itertools import islice
import math
from zoneinfo import ZoneInfo

from weather_radiation_evidence import RadiationPolicy
from weather_radiation_reader import MAX_ROWS,select_radiation_window,select_radiation_at
from .contracts import canonical,digest,finite,identity,instant
from .evidence import utc
from .features import prospective_snapshot

SOLAR_VARIABLES=('surface_solar_radiation_downwards_1hr','total_sky_direct_solar_radiation_at_surface_1hr')


def _window(start,end):
    start,end=map(utc,(start,end))
    if not start<end<=start+timedelta(hours=25) or any((v.minute,v.second,v.microsecond)!=(0,0,0) for v in (start,end)):
        raise ValueError('positive native-hour-aligned window up to 25 hours required')
    return start,end


def capture_solar_window(*,start,end,assessed_at,history_start,cutover,policy,site_timezone,observations):
    """Retain original receipts after the existing native clean-window check."""
    start,end=_window(start,end);assessed_at,history_start,cutover=map(utc,(assessed_at,history_start,cutover))
    ZoneInfo(site_timezone)
    if not isinstance(policy,RadiationPolicy):raise ValueError('explicit native radiation policy required')
    rows=list(islice(observations,MAX_ROWS+1))
    args=dict(start=start,end=end,assessed_at=assessed_at,history_start=history_start,cutover=cutover,policy=policy)
    summary=select_radiation_window(rows,**args)
    if summary['status']!='ok' or not summary['fully_covered'] or summary['irradiance_wh_m2'] is None:
        raise ValueError('clean source-qualified proxy window required')
    initial=select_radiation_at(rows,target=start,assessed_at=assessed_at,history_start=history_start,cutover=cutover,policy=policy)
    if initial is None or initial['fault_visibility']!='verified':raise ValueError('original v2 proxy epoch required')
    # Reuse the native validator for each complete hourly exposure; never select
    # a single instantaneous reading to stand in for an accumulated interval.
    times=[utc(at) for at,_ in rows];hourly=[];left=start
    while left<end:
        right=left+timedelta(hours=1);history=left-timedelta(seconds=policy.validity_seconds)
        first=bisect_left(times,history);last=bisect_right(times,min(assessed_at,right+timedelta(seconds=policy.validity_seconds)))
        subset=rows[max(0,first-1):last]
        result=select_radiation_window(subset,start=left,end=right,assessed_at=assessed_at,history_start=history,cutover=cutover,policy=policy)
        if result['status']!='ok':raise ValueError('complete native proxy hour required')
        hourly.append(dict(end=right.isoformat(),proxy_wh_m2=result['irradiance_wh_m2']));left=right
    body=dict(schema='earthship-qualified-solar-proxy-source/v1',source_item='Weather_Radiation_Evidence_JSON',
        start=start.isoformat(),end=end.isoformat(),history_start=history_start.isoformat(),cutover=cutover.isoformat(),
        site_timezone=site_timezone,policy=asdict(policy),stream_epoch=initial['streamEpoch'],
        available_at=max(utc(at) for at,_ in rows).isoformat(),observations=[[utc(at).isoformat(),raw] for at,raw in rows],
        summary=summary,hourly=hourly,calibrated_irradiance_qualified=False)
    return body|dict(source_sha256=identity(body),assessed_at=assessed_at.isoformat())


def _source(value):
    keys={'schema','source_item','start','end','history_start','cutover','site_timezone','policy','stream_epoch','available_at','observations','summary','hourly','calibrated_irradiance_qualified','source_sha256','assessed_at'}
    if not isinstance(value,dict) or set(value)!=keys:raise ValueError('closed original solar-proxy capsule required')
    digest(value['source_sha256'])
    rebuilt=capture_solar_window(start=instant(value['start']),end=instant(value['end']),assessed_at=instant(value['assessed_at']),
        history_start=instant(value['history_start']),cutover=instant(value['cutover']),policy=RadiationPolicy(**value['policy']),
        site_timezone=value['site_timezone'],observations=((instant(at),raw) for at,raw in value['observations']))
    if canonical(rebuilt)!=canonical(value):raise ValueError('proxy summary or identity differs from original receipts')
    return rebuilt


def solar_window_forecast(snapshot,*,issued_at,completed_at,start,end):
    """Derive native hourly energies for one retained, prospectively safe issue."""
    issued_at,completed_at=map(utc,(issued_at,completed_at));start,end=_window(start,end)
    snapshot=prospective_snapshot(snapshot,issued_at=issued_at)
    if not issued_at<=completed_at<=start:raise ValueError('solar window must start after original issue completion')
    cells=sorted({(p['latitude'],p['longitude']) for p in snapshot['points'] if p['variable'] in SOLAR_VARIABLES})
    if len(cells)!=1:raise ValueError('one original solar grid required')
    targets=[];at=start+timedelta(hours=1)
    while at<=end:targets.append(at);at+=timedelta(hours=1)
    index={(p['variable'],instant(p['valid_at'])):p for p in snapshot['points'] if p['statistic']=='mean' and p['variable'] in SOLAR_VARIABLES}
    products={}
    for variable in SOLAR_VARIABLES:
        products[variable]=[None if (row:=index.get((variable,at))) is None or row['raw_value'] is None else row['raw_value']/3600 for at in targets]
    body=dict(schema='earthship-weathernext-solar-window/v1',provider='weathernext3',start=start.isoformat(),end=end.isoformat(),
        site_timezone=snapshot['site']['timezone'],initialized_at=snapshot['initialized_at'],issued_at=issued_at.isoformat(),completed_at=completed_at.isoformat(),
        available_at=snapshot['ingestion_completed_at'],snapshot_sha256=snapshot['snapshot_sha256'],
        grid_sha256=identity(dict(site=snapshot['site'],cells=cells,variables=SOLAR_VARIABLES)),hourly_wh_m2=products)
    return _forecast(body|{'forecast_sha256':identity(body)})


def _forecast(value):
    keys={'schema','provider','start','end','site_timezone','initialized_at','issued_at','completed_at','available_at','snapshot_sha256','grid_sha256','hourly_wh_m2','forecast_sha256'}
    if not isinstance(value,dict) or set(value)!=keys or value['schema']!='earthship-weathernext-solar-window/v1' or value['provider']!='weathernext3':
        raise ValueError('closed original Google solar window required')
    for key in ('snapshot_sha256','grid_sha256','forecast_sha256'):digest(value[key])
    if identity({k:v for k,v in value.items() if k!='forecast_sha256'})!=value['forecast_sha256']:raise ValueError('original solar forecast differs')
    start,end=_window(instant(value['start']),instant(value['end']));ZoneInfo(value['site_timezone'])
    initialized,issued,completed,available=map(instant,(value['initialized_at'],value['issued_at'],value['completed_at'],value['available_at']))
    if not initialized<=available<=issued<=completed<=start<end<=initialized+timedelta(hours=360) or issued-initialized>timedelta(hours=24):
        raise ValueError('prospectively available solar issue required')
    products=value['hourly_wh_m2'];hours=int((end-start).total_seconds()/3600)
    if not isinstance(products,dict) or set(products)!=set(SOLAR_VARIABLES):raise ValueError('two separate native solar products required')
    for values in products.values():
        if not isinstance(values,list) or len(values)!=hours or any(v is not None and (not finite(v) or v<0) for v in values):
            raise ValueError('finite original hourly interval energies required')
    return value


def _diagnostics(forecast,proxy):
    predicted=sum(forecast);observed=sum(proxy)
    centroid=lambda series,total:None if total==0 else sum((i+.5)*v for i,v in enumerate(series))/total
    a,b=centroid(forecast,predicted),centroid(proxy,observed)
    return dict(forecast_wh_m2=predicted,energy_difference_vs_proxy_wh_m2=predicted-observed,
        forecast_to_proxy_ratio=None if observed==0 else predicted/observed,
        energy_centroid_error_hours=None if len(proxy)<2 or a is None or b is None else a-b,
        normalized_hourly_shape_mae=None if len(proxy)<2 or predicted==0 or observed==0 else sum(abs(f/predicted-p/observed) for f,p in zip(forecast,proxy))/len(proxy))


def compare_solar_windows(forecasts,outcomes):
    """Latest completed pre-window issue before missingness/outcome selection.

    Qualified source capsules can stream; raw observations are not copied into
    reports. Different durations have separate diagnostics, and overlapping
    paired windows cannot inflate support in a source/grid cohort.
    """
    if not isinstance(forecasts,(list,tuple)) or len(forecasts)>20000:raise ValueError('bounded original solar forecasts required')
    decisions={};seen={}
    for raw in forecasts:
        row=_forecast(raw);key=(row['site_timezone'],row['start'],row['end']);at=instant(row['issued_at']);original=(key,at)
        if original in seen and seen[original]!=row['forecast_sha256']:raise ValueError('conflicting original solar decision')
        seen[original]=row['forecast_sha256']
        if key not in decisions or at>instant(decisions[key]['issued_at']):decisions[key]=row
    labels={}
    for index,raw in enumerate(islice(outcomes,20001)):
        if index==20000:raise ValueError('solar outcome count bound exceeded')
        row=_source(raw);key=(row['site_timezone'],row['start'],row['end'])
        if key in labels and labels[key]['source_sha256']!=row['source_sha256']:raise ValueError('conflicting original proxy source')
        labels[key]={k:v for k,v in row.items() if k!='observations'}
    pairs=[];withheld=[];groups={};periods={}
    for key,forecast in sorted(decisions.items()):
        base=dict(site_timezone=key[0],start=key[1],end=key[2],forecast_sha256=forecast['forecast_sha256'])
        if any(v is None for values in forecast['hourly_wh_m2'].values() for v in values):withheld.append(base|{'reason':'INCOMPLETE_COMMON_SOLAR'});continue
        source=labels.get(key)
        if source is None:withheld.append(base|{'reason':'NO_QUALIFIED_PROXY_OUTCOME'});continue
        cohort=identity(dict(grid=forecast['grid_sha256'],policy=source['policy'],cutover=source['cutover'],epoch=source['stream_epoch']))
        start,end=map(instant,(key[1],key[2]));prior=periods.get(cohort)
        if prior is not None and start<prior:raise ValueError('overlapping proxy windows cannot inflate support')
        periods[cohort]=end
        proxy=[row['proxy_wh_m2'] for row in source['hourly']]
        pair=base|dict(issued_at=forecast['issued_at'],completed_at=forecast['completed_at'],snapshot_sha256=forecast['snapshot_sha256'],
            outcome_sha256=source['source_sha256'],outcome_available_at=source['available_at'],history_sha256=source['summary']['history_sha256'],
            stream_epoch=source['stream_epoch'],grid_sha256=forecast['grid_sha256'],cohort_sha256=cohort,window_hours=len(proxy),
            proxy_wh_m2=sum(proxy),proxy_hourly_wh_m2=proxy,
            diagnostics={variable:_diagnostics(values,proxy) for variable,values in forecast['hourly_wh_m2'].items()})
        pairs.append(pair);groups.setdefault(cohort,{}).setdefault(len(proxy),[]).append(pair)
    cohorts={}
    for cohort,durations in sorted(groups.items()):
        summaries={}
        for duration,rows in sorted(durations.items()):
            products={}
            for variable in SOLAR_VARIABLES:
                results=[row['diagnostics'][variable] for row in rows];errors=[r['energy_difference_vs_proxy_wh_m2'] for r in results]
                timings=[r['energy_centroid_error_hours'] for r in results if r['energy_centroid_error_hours'] is not None]
                tail=lambda values:None if not values else sorted(abs(v) for v in values)[math.ceil(.95*len(values))-1]
                products[variable]=dict(energy_mae_vs_proxy_wh_m2=sum(abs(v) for v in errors)/len(errors),
                    energy_bias_vs_proxy_wh_m2=sum(errors)/len(errors),energy_rmse_vs_proxy_wh_m2=math.sqrt(sum(v*v for v in errors)/len(errors)),
                    energy_absolute_error_p95_vs_proxy_wh_m2=tail(errors),centroid_absolute_error_p95_vs_proxy_hours=tail(timings),
                    timing_windows=len(timings),centroid_mae_vs_proxy_hours=None if not timings else sum(abs(v) for v in timings)/len(timings))
            summaries[str(duration)]=dict(windows=len(rows),products=products)
        cohorts[cohort]=dict(windows=sum(len(rows) for rows in durations.values()),by_window_hours=summaries)
    body=dict(schema='earthship-weathernext-solar-proxy-comparison/v1',provider='weathernext3',qualification='SHADOW_ONLY',
        selection_rule='latest_retained_issue_completed_by_window_start_before_missingness_or_outcomes',
        observation_basis='persisted_sample_and_hold_lux_proxy',calibrated_ghi_skill_qualified=False,direct_component_skill_qualified=False,
        direct_comparison_basis='direct_beam_vs_total_lux_proxy_diagnostic_only',pv_calibration_changed=False,
        pairs=pairs,withheld=withheld,cohorts=cohorts,
        decisions=[dict(start=r['start'],end=r['end'],issued_at=r['issued_at'],completed_at=r['completed_at'],forecast_sha256=r['forecast_sha256']) for _,r in sorted(decisions.items())],
        automatic_actuation=False)
    return body|{'report_sha256':identity(body)}
