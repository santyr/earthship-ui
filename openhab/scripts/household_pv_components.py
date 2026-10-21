"""Explicit native-component PV experiment path; incumbent v1 stays independent.

The source-hour reconstruction conserves SSRD/FDIR before terrain. Every
consumer uses the same five-minute/hour-boundary segments and interpolated
point weather. This path supplies potential array DC, never device authority.
"""
from bisect import bisect_left
from collections import Counter
from datetime import datetime, time, timedelta
from math import cos, fsum, pi, sin
from types import MappingProxyType
from zoneinfo import ZoneInfo

from household.control_contracts import instant
from household.evidence import utc
from household.codec import identity
from household_pv_model import (
    ASSUMPTIONS as LEGACY_ASSUMPTIONS, _array, _assumptions, _number,
    array_power, simulate_storage,
)
from household_solar_horizon import horizon_height
from weather_learning.solar_experiment import validate_component_input
from weather_learning.solar_components import BIN, METHOD, _geometry, reconstruct_hour

MODEL_RULE='native_fdir_ssrd_isotropic_faiman_proxy_pvwatts_dc_v2'
BENCHMARK_RULE='ending_hour_erbs_isotropic_faiman_interpolated_point_weather_v2'
ASSUMPTIONS=MappingProxyType(dict(LEGACY_ASSUMPTIONS,model=MODEL_RULE))


def _parameters(value):
    if not isinstance(value,dict) and not isinstance(value,type(ASSUMPTIONS)):
        raise ValueError('explicit component PV assumptions required')
    if value.get('model')!=MODEL_RULE:raise ValueError('component PV method identity required')
    return _assumptions(dict(value,model=LEGACY_ASSUMPTIONS['model']))


def array_power_components(*,array,ghi_wm2,dni_wm2,dhi_wm2,elevation_degrees,
                           azimuth_degrees,temp_f,wind_mph,assumptions=ASSUMPTIONS):
    """Transpose already terrain-masked components with incumbent electrical rules."""
    array=_array(array);p=_parameters(assumptions)
    ghi=_number(ghi_wm2,0,2000);dni=_number(dni_wm2,0,2000);dhi=_number(dhi_wm2,0,2000)
    elevation=_number(elevation_degrees,-90,90);azimuth=_number(azimuth_degrees,0,360)
    air=(_number(temp_f,-150,180)-32)*5/9
    wind=p['missing_wind_m_s'] if wind_mph is None else _number(wind_mph,0,250)*.44704
    projection=max(0.,sin(elevation*pi/180))
    if abs(ghi-(dhi+dni*projection))>max(1e-6,ghi*1e-9):
        raise ValueError('consistent horizontal components required')
    if elevation<=0 and (ghi or dni or dhi):raise ValueError('nighttime components must be zero')
    tilt=array['surface_tilt_degrees']*pi/180
    incidence=projection*cos(tilt)+cos(elevation*pi/180)*sin(tilt)*cos((azimuth-array['surface_azimuth_degrees'])*pi/180)
    poa=max(0.,dni*incidence)+dhi*(1+cos(tilt))/2+ghi*p['albedo']*(1-cos(tilt))/2
    proxy=air+poa/(p['faiman_u0']+p['faiman_u1']*wind)
    dc=max(0.,poa*.001*array['dc_nameplate_w']*(1+p['gamma_pdc_per_c']*(proxy-25))*p['dc_loss_multiplier'])
    return dict(dni_wm2=dni,dhi_wm2=dhi,poa_wm2=poa,temperature_proxy_c=proxy,
                potential_dc_w=dc,missing_wind_assumption_used=wind_mph is None)


def _point(rows,times,at):
    index=bisect_left(times,at)
    if index==0 or index==len(times):raise ValueError('original point weather bracket required')
    left,right=rows[index-1],rows[index];weight=(at-times[index-1]).total_seconds()/3600
    temp=_number(left['tempF'],-150,180)*(1-weight)+_number(right['tempF'],-150,180)*weight
    wind=None if left['windMph'] is None or right['windMph'] is None else (
        _number(left['windMph'],0,250)*(1-weight)+_number(right['windMph'],0,250)*weight)
    return temp,wind


def project_window_components(*,array,forecast,positions,start,end,timezone_name,horizon_profile=None,
                              assumptions=ASSUMPTIONS,force_total_only=False):
    """Integrate a complete requested window; missing full source hours fall back.

    Point weather uses each original geometry bin's right endpoint, split at
    source hours. Slicing a segment never changes that segment's power. This
    makes training intervals and fractional daily/serving windows comparable.
    force_total_only is the matched experiment benchmark on exactly this grid.
    """
    if type(force_total_only) is not bool:raise ValueError('explicit benchmark choice required')
    forecast,evidence_class=validate_component_input(forecast)
    array=_array(array);p=_parameters(assumptions);start,end=utc(start),utc(end)
    origin=instant(forecast['origin'])
    if not origin<=start<end<=origin+timedelta(hours=forecast['horizon_hours']):
        raise ValueError('requested window outside original forecast horizon')
    bins=_geometry(positions,start,end)
    if bins is None:raise ValueError('complete requested native geometry required')
    rows=forecast['rows'];times=[instant(r['at']) for r in rows]
    position_times=[instant(r['at']) for r in positions]
    zone=ZoneInfo(timezone_name)
    midnight=datetime.combine(start.astimezone(zone).date()+timedelta(days=1),time.min,zone).astimezone(start.tzinfo)
    hours={};fallbacks=Counter();native=0;steps=[];details=[];energies=[];horizontal=[];today=[]
    missing_wind=False;blocked=0;sun_windows=[];sun_start=None
    for geometry in bins:
        at=instant(geometry['start']);stop=instant(geometry['end'])
        source_position=positions[bisect_left(position_times,stop)]
        while at<stop:
            hour_end=at.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
            right=min(stop,hour_end);hour_start=hour_end-timedelta(hours=1)
            if hour_end not in hours:
                row=rows[bisect_left(times,hour_end)]
                solar=row['solar']
                if force_total_only:
                    reconstructed=dict(status='total_only_fallback',reason='total_only_benchmark',segments=[])
                else:
                    reconstructed=reconstruct_hour(start=hour_start,end=hour_end,
                        total_j_m2=solar['total_j_m2'],direct_j_m2=solar['direct_j_m2'],
                        positions=positions,horizon_profile=horizon_profile)
                hours[hour_end]=reconstructed
                if reconstructed['status']=='native_components':native+=1
                else:fallbacks[reconstructed['reason']]+=1
            reconstructed=hours[hour_end]
            sample_at=min(instant(source_position['at']),hour_end)
            temp,wind=_point(rows,times,sample_at)
            elevation=source_position['elevation_degrees'];azimuth=source_position['azimuth_degrees']
            skyline=None if horizon_profile is None else horizon_height(horizon_profile,azimuth)
            visible=elevation>(0 if skyline is None else skyline)
            if visible and sun_start is None:sun_start=at
            if not visible and sun_start is not None:
                sun_windows.append(dict(start=sun_start.isoformat(),end=at.isoformat()));sun_start=None
            if skyline is not None and 0<elevation<=skyline:blocked+=1
            if reconstructed['status']=='native_components':
                component=next((r for r in reconstructed['segments']
                    if instant(r['start'])<=at and right<=instant(r['end'])),None)
                if component is None:raise ValueError('complete native component segment required')
                power=array_power_components(array=array,assumptions=assumptions,
                    ghi_wm2=component['ghi_w_m2'],dni_wm2=component['dni_w_m2'],dhi_wm2=component['dhi_w_m2'],
                    elevation_degrees=elevation,azimuth_degrees=azimuth,temp_f=temp,wind_mph=wind)
                raw_ghi=component['raw_ghi_w_m2']
            else:
                raw_ghi=rows[bisect_left(times,hour_end)]['radiationWm2']
                power=array_power(array=array,assumptions=p,ghi_wm2=raw_ghi,elevation_degrees=elevation,
                    azimuth_degrees=azimuth,day_of_year=sample_at.astimezone(zone).timetuple().tm_yday,
                    temp_f=temp,wind_mph=wind,horizon_elevation_degrees=skyline)
            elapsed=(right-at).total_seconds()/3600000;energy=power['potential_dc_w']*elapsed
            steps.append(dict(start=at.isoformat(),end=right.isoformat(),potential_pv_kwh=energy))
            details.append(dict(start=at.isoformat(),end=right.isoformat(),method=reconstructed['status'],
                reason=reconstructed['reason'],raw_ghi_w_m2=raw_ghi,potential_dc_w=power['potential_dc_w'],
                dni_wm2=power['dni_wm2'],dhi_wm2=power['dhi_wm2'],poa_wm2=power['poa_wm2']))
            energies.append(energy);horizontal.append(raw_ghi*elapsed)
            if at<midnight:today.append(power['potential_dc_w']*max(0.,(min(right,midnight)-at).total_seconds())/3600000)
            missing_wind=missing_wind or power['missing_wind_assumption_used'];at=right
    if sun_start is not None:sun_windows.append(dict(start=sun_start.isoformat(),end=end.isoformat()))
    out=dict(schema='earthship-household-component-pv/v1',model_rule=BENCHMARK_RULE if force_total_only else MODEL_RULE,reconstruction_method=METHOD,
        benchmark='total_only' if force_total_only else 'native_with_total_only_fallback',
        evidence_class=evidence_class,prospective_score=False,
        origin=start.isoformat(),through=end.isoformat(),horizon_hours=(end-start).total_seconds()/3600,
        timezone=timezone_name,forecast_sha256=forecast['forecast_sha256'],geometry_sha256=identity(positions),
        horizon_sha256=None if horizon_profile is None else identity(horizon_profile),array=array,assumptions=dict(assumptions),
        potential_pv_kwh=fsum(energies),remaining_today_potential_kwh=fsum(today),
        forecast_horizontal_irradiation_kwh_m2=fsum(horizontal),steps=steps,segments=details,
        source_support=dict(native_hours=native,fallback_hours=sum(fallbacks.values()),fallback_reasons=dict(fallbacks)),
        direct_sun_windows=sun_windows,terrain_blocked_geometry_steps=blocked,
        terrain_rule='direct_beam_and_direct_ground_reflection_mask_diffuse_sky_view_unmodeled',
        missing_wind_assumption_used=missing_wind,
        prediction_target='modeled_potential_array_DC_after_assumed_losses_before_acceptance',
        measured_irradiance_used=False,physical_calibration_qualified=False,captured_pv_kwh=None,automatic_actuation=False)
    out['projection_sha256']=identity(out)
    return out


def integrate_array_components(*,array,forecast,positions,origin,horizon_hours,timezone_name,horizon_profile=None,
                               assumptions=ASSUMPTIONS,force_total_only=False):
    if type(horizon_hours) is not int or not 1<=horizon_hours<=24:raise ValueError('bounded storage/PV horizon required')
    return project_window_components(array=array,forecast=forecast,positions=positions,start=origin,
        end=utc(origin)+timedelta(hours=horizon_hours),timezone_name=timezone_name,horizon_profile=horizon_profile,
        assumptions=assumptions,force_total_only=force_total_only)


def interval_baseline_components(*,array,forecast,positions,start,end,horizon_profile=None,timezone_name='UTC',
                                 assumptions=ASSUMPTIONS,force_total_only=False):
    if not timedelta(0)<utc(end)-utc(start)<=BIN:raise ValueError('bounded historical pair interval required')
    result=project_window_components(array=array,forecast=forecast,positions=positions,start=start,end=end,
        timezone_name=timezone_name,horizon_profile=horizon_profile,assumptions=assumptions,force_total_only=force_total_only)
    return dict(baseline_w=result['potential_pv_kwh']*3600000/(utc(end)-utc(start)).total_seconds(),
        baseline_rule=result['model_rule'],benchmark=result['benchmark'],forecast_sha256=result['forecast_sha256'],projection_sha256=result['projection_sha256'],
        source_support=result['source_support'],physical_calibration_qualified=False,automatic_actuation=False)


def storage_from_components(pv_projection,*,initial_soc_pct,nominal_bank_kwh,load_ac_w):
    if (not isinstance(pv_projection,dict) or pv_projection.get('schema')!='earthship-household-component-pv/v1' or
            pv_projection.get('model_rule') not in (MODEL_RULE,BENCHMARK_RULE) or
            pv_projection.get('projection_sha256')!=identity({k:v for k,v in pv_projection.items() if k!='projection_sha256'})):
        raise ValueError('original component PV projection required')
    result=simulate_storage(steps=pv_projection['steps'],initial_soc_pct=initial_soc_pct,
        nominal_bank_kwh=nominal_bank_kwh,load_ac_w=load_ac_w)
    result.update(pv_model_rule=pv_projection['model_rule'],pv_projection_sha256=pv_projection['projection_sha256'],
        source_support=pv_projection['source_support'],end_soc_pct=result['trajectory'][-1]['nominal_soc_pct'])
    return result
