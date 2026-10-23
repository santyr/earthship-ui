"""Source-bound atmospheric diagnostics, independent of forecast/control models."""
from math import atan2,degrees,hypot
from .config import Site,COLLECTIONS
from .contracts import finite,identity,instant
from .evidence import utc
from .features import prospective_snapshot
from household_job_budget import AdmissionDeferred

HUMIDITY_FORMULA='NWS_Tetens_over_water_6.11_times_10_power_7.5T_over_237.3plusT/v1'
HUMIDITY_REFERENCE='https://www.weather.gov/media/epz/wxcalc/vaporPressure.pdf'
VARIABLES={
    'temperature':('station_head_temperature_2m','station','degC',-100,70),
    'dewpoint':('station_head_dewpoint_temperature_2m','station','degC',-100,70),
    'pressure':('mean_sea_level_pressure','gridded','hPa',400,1200),
    'speed':('wind_speed_10m','gridded','m s-1',0,200),
    'u':('u_component_of_wind_10m','gridded','m s-1',-200,200),
    'v':('v_component_of_wind_10m','gridded','m s-1',-200,200),
    'total':('total_cloud_cover','gridded','percent',0,100),
    'high':('high_cloud_cover','gridded','percent',0,100),
    'medium':('medium_cloud_cover','gridded','percent',0,100),
    'low':('low_cloud_cover','gridded','percent',0,100),
}


def wind_from(u,v):
    """Meteorological direction from which the vector blows; no gust inference."""
    if any(not finite(x) or abs(x)>200 for x in (u,v)):
        return dict(from_degrees=None,magnitude_m_s=None,reason='mean_components_unavailable')
    magnitude=hypot(u,v)
    return dict(from_degrees=None if magnitude<=1e-6 else degrees(atan2(-u,-v))%360,
        magnitude_m_s=magnitude,reason='calm_or_cancelling_mean_vector' if magnitude<=1e-6 else None)


def vapor_pressure_hpa(temperature_c):
    """NWS diagnostic over-water approximation; no ice/surface safety inference."""
    if not finite(temperature_c) or not -100<=temperature_c<=70:raise ValueError('bounded temperature for moisture diagnostic required')
    return 6.11*10**(7.5*temperature_c/(237.3+temperature_c))


def _compatible(a,b):
    return a is not None and b is not None and all(a[k]==b[k] for k in ('run_id','initialized_at','valid_at','grid_sha256','native_asset_sha256'))


def _field(body,point,name):
    variable,grid,unit,low,high=VARIABLES[name]
    if (point['unit']!=unit or point['period_seconds']!=0 or not point['source_ref'].startswith(COLLECTIONS[grid]+'/') or
            not finite(point['value']) or not low<=point['value']<=high):return None
    result=dict(value=point['value'],unit=unit,valid_at=point['valid_at'],source_sha256=body['snapshot_sha256'],
        source_digest=point['source_digest'],run_id=body['run_id'],initialized_at=body['initialized_at'],
        first_seen_at=body['first_seen_at'],available_at=body['ingestion_completed_at'],
        grid_sha256=identity(dict(collection=COLLECTIONS[grid],latitude=point['latitude'],longitude=point['longitude'])),
        native_asset_sha256=identity(point['source_ref']))
    if name=='pressure':result['basis']='mean_sea_level'
    return result


def build_atmospheric_context(snapshots,*,decision,target,site,guard=lambda:None):
    return build_atmospheric_series(snapshots,decision=decision,targets=(target,),site=site,guard=guard)[0]


def build_atmospheric_series(snapshots,*,decision,targets,site,guard=lambda:None):
    decision=utc(decision);targets=tuple(map(utc,targets))
    if (not isinstance(site,Site) or not isinstance(snapshots,(list,tuple)) or len(snapshots)>8 or
            not 1<=len(targets)<=24 or list(targets)!=sorted(set(targets)) or any(at<=decision for at in targets)):
        raise ValueError('bounded original prospective atmospheric context required')
    by_variable={v[0]:name for name,v in VARIABLES.items()};withheld=0
    all_fields={at:{name:[] for name in VARIABLES} for at in targets}
    for source in snapshots:
        guard()
        try:
            body=prospective_snapshot(source,issued_at=decision)
            if body['site']!=site.__dict__:raise ValueError('atmospheric original site differs')
            for point in body['points']:
                at=instant(point['valid_at'])
                if point['statistic']!='mean' or at not in all_fields or point['variable'] not in by_variable:continue
                name=by_variable[point['variable']];field=_field(body,point,name)
                if field is not None:all_fields[at][name].append(field)
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except (ValueError,TypeError,KeyError):withheld+=1
    return [_context_from_fields(all_fields[at],decision,at,withheld) for at in targets]


def _context_from_fields(candidates,decision,target,withheld):
    selected={}
    for name,fields in candidates.items():
        selected[name]=max(fields,key=lambda f:(instant(f['initialized_at']),instant(f['available_at']),f['source_sha256'])) if fields else None
    temperature,dew=selected['temperature'],selected['dewpoint']
    rh=dict(value_pct=None,reason='compatible_station_pair_unavailable',scope='diagnostic_from_mean_T_and_mean_Td_not_ensemble_mean_RH',
        formula=HUMIDITY_FORMULA,reference=HUMIDITY_REFERENCE,locally_calibrated=False,source_sha256s=[])
    if _compatible(temperature,dew):
        if dew['value']>temperature['value']:rh['reason']='dewpoint_above_temperature'
        else:
            rh.update(value_pct=100*vapor_pressure_hpa(dew['value'])/vapor_pressure_hpa(temperature['value']),reason=None,
                source_sha256s=sorted({temperature['source_sha256'],dew['source_sha256']}))
    u,v=selected['u'],selected['v']
    vector=wind_from(u['value'],v['value']) if _compatible(u,v) else wind_from(None,None)
    vector.update(u=u,v=v,quantity='magnitude_and_direction_of_mean_u_v_vector')
    result=dict(schema='earthship-atmospheric-context/v1',valid_at=target.isoformat(),assessed_at=decision.isoformat(),
        temperature=temperature,dewpoint=dew,relative_humidity=rh,pressure=selected['pressure'],
        wind=dict(scalar_speed=selected['speed'],vector=vector,quantity_semantics='scalar_mean_speed_and_mean_vector_are_distinct; neither_is_gust'),
        clouds={name:selected[name] for name in ('total','high','medium','low')},
        cloud_semantics='independent_layer_cover; layers_overlap_and_are_not_summed',withheld_sources=withheld,
        temperature_model_uses_fields=False,moisture_advisory='qualified_indoor_temperature_and_humidity_required',
        condensation_safety_qualified=False,automatic_actuation=False,release_authorized=False)
    result['context_sha256']=identity(result);return result


def compare_pressure(forecast,*,observed_hpa,observed_basis):
    difference=None;reason='incompatible_pressure_convention'
    if (isinstance(forecast,dict) and forecast.get('basis')=='mean_sea_level' and forecast.get('unit')=='hPa' and
            observed_basis=='mean_sea_level' and finite(observed_hpa) and 400<=observed_hpa<=1200):
        difference=forecast['value']-observed_hpa;reason=None
    return dict(difference_hpa=difference,reason=reason,conversion_assumed=False,qualification='diagnostic_on_explicit_matching_conventions')
