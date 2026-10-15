"""Provisional array DC potential from retained forecasts and native geometry.

Scalar published Erbs/Spencer, isotropic transposition, Faiman and PVWatts
relationships; synthetic parity is checked against pvlib. No new astronomy,
measured radiation, battery acceptance or electrical authority is inferred.
"""
from bisect import bisect_left
from collections.abc import Mapping
from datetime import datetime,timedelta,time
from hashlib import sha256
from math import cos,sin,pi,isfinite
from types import MappingProxyType
from zoneinfo import ZoneInfo
from household.codec import loads,canonical,identity
from household.control_contracts import instant
from household.evidence import utc

SYSTEM_IDENTITY='earthship-ui/openhab/household-pv-system.json'
SOURCE_FIELDS={'schema','source_identity','raw','sha256','available_at'}
ARRAY_FIELDS={'module_count','module_nameplate_w','dc_nameplate_w','surface_azimuth_degrees','surface_tilt_degrees'}
ASSUMPTIONS=MappingProxyType(dict(model='erbs_spencer_isotropic_faiman_proxy_pvwatts_dc_v1',
    albedo=.2,gamma_pdc_per_c=-.004,faiman_u0=25.,faiman_u1=6.84,
    missing_wind_m_s=1.,dc_loss_multiplier=.86))


def _number(value,low,high):
    if type(value) not in (int,float) or not isfinite(value) or not low<=value<=high:
        raise ValueError('finite bounded PV model quantity required')
    return float(value)


def _array(value):
    if not isinstance(value,dict) or set(value)!=ARRAY_FIELDS:raise ValueError('closed array specification required')
    if type(value['module_count']) is not int:raise ValueError('integer module count required')
    _number(value['module_count'],1,1000);_number(value['module_nameplate_w'],1,2000)
    _number(value['dc_nameplate_w'],1,2000000);_number(value['surface_tilt_degrees'],0,90)
    _number(value['surface_azimuth_degrees'],0,360)
    if value['dc_nameplate_w']!=value['module_count']*value['module_nameplate_w']:
        raise ValueError('original array rating differs from module count')
    return dict(value)


def _assumptions(value):
    if not isinstance(value,Mapping) or set(value)!=set(ASSUMPTIONS) or value['model']!=ASSUMPTIONS['model']:
        raise ValueError('closed explicit provisional assumptions required')
    for name,low,high in (('albedo',0,1),('gamma_pdc_per_c',-.02,0),('faiman_u0',.01,1000),
        ('faiman_u1',0,100),('missing_wind_m_s',0,100),('dc_loss_multiplier',.001,1)):
        _number(value[name],low,high)
    return dict(value)


def prepare_system_source(raw,*,available_at):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=8192:raise ValueError('bounded original PV system source required')
    text=raw.decode('utf-8');loads(text)
    return dict(schema='earthship-household-pv-system-source/v1',source_identity=SYSTEM_IDENTITY,
        raw=text,sha256=sha256(raw).hexdigest(),available_at=utc(available_at).isoformat())


def system_configuration(source,origin):
    if source is None:return None,'pv_system_unavailable'
    if (not isinstance(source,dict) or set(source)!=SOURCE_FIELDS or source['schema']!='earthship-household-pv-system-source/v1' or
        source['source_identity']!=SYSTEM_IDENTITY):raise ValueError('closed original PV system source required')
    raw=source['raw']
    if (not isinstance(raw,str) or not 1<=len(raw.encode())<=8192 or sha256(raw.encode()).hexdigest()!=source['sha256'] or
        instant(source['available_at'])>utc(origin)):raise ValueError('PV source bytes or original availability differ')
    try:
        value=loads(raw)
        if (set(value)!={'schema','recorded_at','array','inventory_source','orientation_source','unverified','automatic_actuation'} or
            value['schema']!='earthship-household-pv-system/v1' or value['automatic_actuation'] is not False or
            instant(value['recorded_at'])>instant(source['available_at'])):raise ValueError()
        array=_array(value['array']);orientation=value['orientation_source'];inventory=value['inventory_source']
        if (not isinstance(orientation,dict) or orientation.get('basis')!='operator_reported' or
            type(orientation.get('inclinometer_horizontal_degrees')) not in (int,float) or
            type(orientation.get('inclinometer_reading_degrees')) not in (int,float) or
            orientation['inclinometer_horizontal_degrees']!=90 or
            abs(array['surface_tilt_degrees']-(90-orientation['inclinometer_reading_degrees']))>1e-9 or
            not isinstance(inventory,dict) or inventory.get('repository')!='santyr/Solar_PV' or
            inventory.get('path')!='docs/architecture/current-system.md' or
            inventory.get('basis')!='operator_transcription_of_original_quote' or
            not isinstance(value['unverified'],list) or any(not isinstance(x,str) for x in value['unverified'])):raise ValueError()
        return loads(canonical(value)),None
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):
        return None,'unsupported_pv_system_configuration'


def array_power(*,array,assumptions,ghi_wm2,elevation_degrees,azimuth_degrees,day_of_year,temp_f,wind_mph,horizon_elevation_degrees=None):
    array=_array(array);p=_assumptions(assumptions)
    ghi=_number(ghi_wm2,0,2000);elevation=_number(elevation_degrees,-90,90)
    azimuth=_number(azimuth_degrees,0,360);doy=_number(day_of_year,1,366)
    air=(_number(temp_f,-150,180)-32)*5/9
    wind=p['missing_wind_m_s'] if wind_mph is None else _number(wind_mph,0,250)*.44704
    horizon=None if horizon_elevation_degrees is None else _number(horizon_elevation_degrees,0,90)
    blocked=horizon is not None and elevation<=horizon
    if elevation<=0:
        return dict(dni_wm2=0.,dhi_wm2=0.,poa_wm2=0.,temperature_proxy_c=air,potential_dc_w=0.,missing_wind_assumption_used=wind_mph is None,direct_beam_blocked=blocked)
    radians=pi/180;zenith_cos=sin(elevation*radians);angle=2*pi*(doy-1)/365
    extra=1366.1*(1.00011+.034221*cos(angle)+.00128*sin(angle)+.000719*cos(2*angle)+.000077*sin(2*angle))
    kt=min(1.,max(0.,ghi/(extra*max(zenith_cos,.065))))
    diffuse=1-.09*kt if kt<=.22 else .9511-.1604*kt+4.388*kt**2-16.638*kt**3+12.336*kt**4 if kt<=.8 else .165
    dhi=diffuse*ghi;dni=(ghi-dhi)/zenith_cos
    if elevation<3 or dni<0:dni=0.;dhi=ghi
    if blocked:dni=0.
    local_ghi=dhi+dni*zenith_cos
    tilt=array['surface_tilt_degrees']*radians
    incidence=zenith_cos*cos(tilt)+cos(elevation*radians)*sin(tilt)*cos((azimuth-array['surface_azimuth_degrees'])*radians)
    poa=max(0.,dni*incidence)+dhi*(1+cos(tilt))/2+local_ghi*p['albedo']*(1-cos(tilt))/2
    proxy=air+poa/(p['faiman_u0']+p['faiman_u1']*wind)
    dc=max(0.,poa*.001*array['dc_nameplate_w']*(1+p['gamma_pdc_per_c']*(proxy-25))*p['dc_loss_multiplier'])
    return dict(dni_wm2=dni,dhi_wm2=dhi,poa_wm2=poa,temperature_proxy_c=proxy,potential_dc_w=dc,missing_wind_assumption_used=wind_mph is None,direct_beam_blocked=blocked)


def integrate_array(*,array,assumptions,hourly_forecast,positions,origin,horizon_hours,timezone_name,horizon_profile=None):
    """Integrate ending-hour radiation means on the retained five-minute grid.

    Geometry and temperature use the right endpoint of each five-minute step.
    Radiation is split at actual UTC hour boundaries, including fractional
    first/last hours. This is an explicit numerical approximation, not a claim
    that an hourly mean is an instantaneous irradiance measurement.
    """
    array=_array(array);p=_assumptions(assumptions);origin=utc(origin)
    if type(horizon_hours) is not int or not 1<=horizon_hours<=24:raise ValueError('bounded elapsed-hour horizon required')
    if not isinstance(hourly_forecast,list) or not 2<=len(hourly_forecast)<=50:raise ValueError('bounded original hourly forecast required')
    rows=loads(canonical({'rows':hourly_forecast}))['rows'];times=[instant(r['at']) for r in rows]
    if (any(t.minute or t.second or t.microsecond for t in times) or any(b-a!=timedelta(hours=1) for a,b in zip(times,times[1:])) or
        times[0]>origin or times[-1]<origin+timedelta(hours=horizon_hours)):raise ValueError('complete ordered hourly weather coverage required')
    if not isinstance(positions,list) or len(positions)!=horizon_hours*12:raise ValueError('complete native five-minute geometry required')
    for i,row in enumerate(positions,1):
        if set(row)!={'at','elevation_degrees','azimuth_degrees'} or instant(row['at'])!=origin+timedelta(minutes=5*i):
            raise ValueError('exact original future geometry grid required')
    zone=ZoneInfo(timezone_name);day=origin.astimezone(zone).date()
    midnight=datetime.combine(day+timedelta(days=1),time.min,tzinfo=zone).astimezone(origin.tzinfo)
    total=today=horizontal=hour_energy=0.;missing_wind=False;trajectory=[];steps=[]
    from household_solar_horizon import horizon_height
    windows=[];window=None;blocked_steps=0
    start=origin
    for i,position in enumerate(positions,1):
        end=instant(position['at']);index=bisect_left(times,end)
        skyline=None if horizon_profile is None else horizon_height(horizon_profile,position['azimuth_degrees'])
        direct=position['elevation_degrees']>(0 if skyline is None else skyline)
        if direct and window is None:window=start
        if not direct and window is not None:windows.append(dict(start=window.isoformat(),end=start.isoformat()));window=None
        if skyline is not None and 0<position['elevation_degrees']<=skyline:blocked_steps+=1
        if index==0:raise ValueError('weather interpolation lacks original earlier point')
        left,right=rows[index-1],rows[index];weight=(end-times[index-1]).total_seconds()/3600
        temp=_number(left['tempF'],-150,180)*(1-weight)+_number(right['tempF'],-150,180)*weight
        wind=None if left['windMph'] is None or right['windMph'] is None else _number(left['windMph'],0,250)*(1-weight)+_number(right['windMph'],0,250)*weight
        at=start
        while at<end:
            stop=min(end,at.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1))
            midpoint=at+(stop-at)/2;weather_index=bisect_left(times,midpoint)
            ghi=_number(rows[weather_index]['radiationWm2'],0,2000)
            value=array_power(array=array,assumptions=p,ghi_wm2=ghi,elevation_degrees=position['elevation_degrees'],
                azimuth_degrees=position['azimuth_degrees'],day_of_year=end.timetuple().tm_yday,temp_f=temp,wind_mph=wind,horizon_elevation_degrees=skyline)
            hours=(stop-at).total_seconds()/3600;energy=value['potential_dc_w']*hours/1000
            steps.append(dict(start=at.isoformat(),end=stop.isoformat(),potential_pv_kwh=energy))
            total+=energy;hour_energy+=energy;horizontal+=ghi*hours/1000
            if at<midnight:today+=value['potential_dc_w']*max(0.,(min(stop,midnight)-at).total_seconds())/3600000
            missing_wind=missing_wind or value['missing_wind_assumption_used'];at=stop
        if i%12==0:
            trajectory.append(dict(start=(origin+timedelta(hours=i//12-1)).isoformat(),end=end.isoformat(),potential_pv_kwh=hour_energy,
                cumulative_potential_pv_kwh=total));hour_energy=0.
        start=end
    if window is not None:windows.append(dict(start=window.isoformat(),end=start.isoformat()))
    return dict(model_rule=p['model'],direct_sun_windows=windows,terrain_blocked_geometry_steps=blocked_steps,
        terrain_rule='direct_beam_and_direct_ground_reflection_mask_diffuse_sky_view_unmodeled' if horizon_profile is not None else 'unobstructed_reference',
        origin=origin.isoformat(),horizon_hours=horizon_hours,timezone=timezone_name,
        potential_pv_kwh=total,remaining_today_potential_kwh=today,forecast_horizontal_irradiation_kwh_m2=horizontal,
        trajectory=trajectory,steps=steps,array=array,assumptions=p,missing_wind_assumption_used=missing_wind,
        integration_rule='ending_hour_means_split_at_UTC_boundaries_right_endpoint_five_minute_geometry',
        prediction_target='modeled_potential_array_DC_after_assumed_losses_before_acceptance',
        measured_irradiance_used=False,physical_calibration_qualified=False,captured_pv_kwh=None,automatic_actuation=False)


STORAGE_ASSUMPTIONS=MappingProxyType(dict(inverter_efficiency=.95,charge_efficiency=.95,discharge_efficiency=.95,
    system_dc_overhead_w=0.,charging_power_limit_w=None,charging_taper_modeled=False))


def simulate_storage(*,steps,initial_soc_pct,nominal_bank_kwh,load_ac_w):
    """Conditional nominal-energy scenario, with current AC load held constant.

    Zero overhead, fixed efficiencies, no controller/BMS rate limit or taper
    are model assumptions only. These are not measured losses or qualified
    bounds on captured production, usable energy or equipment permission.
    """
    soc=_number(initial_soc_pct,0,100);capacity=_number(nominal_bank_kwh,.001,10000)
    load=_number(load_ac_w,0,100000);p=dict(STORAGE_ASSUMPTIONS)
    if not isinstance(steps,list) or not 1<=len(steps)<=576:raise ValueError('bounded PV integration steps required')
    energy=capacity*soc/100;pv_total=captured=unaccepted=unserved=0.;trajectory=[];origin=last=None
    for row in steps:
        if not isinstance(row,dict) or set(row)!={'start','end','potential_pv_kwh'}:raise ValueError('closed PV integration step required')
        start,end=instant(row['start']),instant(row['end']);pv=_number(row['potential_pv_kwh'],0,100000)
        if origin is None:origin=start
        if (last is not None and start!=last or not timedelta(0)<end-start<=timedelta(hours=1) or
            end-origin>timedelta(hours=24)):raise ValueError('contiguous bounded PV integration steps required')
        hours=(end-start).total_seconds()/3600;demand=(load/p['inverter_efficiency']+p['system_dc_overhead_w'])*hours/1000
        net=pv-demand;excess=0.
        if net>=0:
            stored=min(capacity-energy,net*p['charge_efficiency'])
            excess=max(0.,net-stored/p['charge_efficiency']);energy+=stored
        else:
            drain=-net/p['discharge_efficiency'];used=min(energy,drain);energy-=used
            unserved+=(drain-used)*p['discharge_efficiency']
        pv_total+=pv;unaccepted+=excess;captured+=pv-excess;last=end
        if (end-origin).total_seconds()%3600==0:
            trajectory.append(dict(at=end.isoformat(),nominal_soc_pct=min(100.,max(0.,100*energy/capacity)),
                nominal_energy_kwh=energy,cumulative_potential_pv_kwh=pv_total,cumulative_modeled_captured_pv_kwh=captured,
                cumulative_modeled_unaccepted_pv_kwh=unaccepted,cumulative_modeled_unserved_dc_kwh=unserved))
    if (last-origin).total_seconds()%3600:raise ValueError('complete elapsed-hour storage horizon required')
    return dict(model_rule='array_potential_constant_AC_load_nominal_storage_v1',initial_soc_pct=soc,
        nominal_bank_kwh=capacity,household_ac_load_w_assumption=load,assumptions=p,trajectory=trajectory,
        potential_pv_kwh=pv_total,modeled_captured_pv_kwh=captured,modeled_unaccepted_pv_kwh=unaccepted,
        modeled_unserved_dc_kwh=unserved,system_dc_overhead_measured=False,balance_closed=False,
        physical_calibration_qualified=False,action_effects_qualified=False,automatic_actuation=False)


def project_pv(*,weather,system_source,now,horizon_source=None):
    from household.weather_context import PreparedWeatherContext,project_weather
    if not isinstance(weather,PreparedWeatherContext):raise ValueError('original frozen weather context required')
    now=utc(now);model=weather.prepared.to_dict()
    if now<instant(model['snapshot']['created_at']):raise ValueError('PV model precedes original context availability')
    context=project_weather(weather);origin=instant(context['origin'])
    source=None if system_source is None else loads(canonical(system_source))
    system,reason=system_configuration(source,origin)
    from household_solar_horizon import horizon_configuration
    horizon_source=None if horizon_source is None else loads(canonical(horizon_source))
    geometry=context.get('solar_geometry');horizon=None;terrain_reason='solar_horizon_unavailable'
    if geometry is not None:
        horizon,terrain_reason=horizon_configuration(horizon_source,origin=origin,site=geometry['site'],timezone_name=geometry['timezone'])
    if horizon_source is not None and horizon is None and reason is None:reason=terrain_reason
    out=dict(schema='earthship-household-pv-projection/v1',status='unavailable',reason=reason,origin=origin.isoformat(),
        assessed_at=now.isoformat(),weather_context_sha256=context['weather_context_sha256'],
        original_capture_sha256=context['original_capture_sha256'],weather_rows_sha256=context['weather_rows_sha256'],
        system_source_sha256=None if source is None else identity(source),geometry_series_sha256=context.get('geometry_series_sha256'),
        horizon_source_sha256=None if horizon_source is None else identity(horizon_source),
        terrain_status='unobstructed_reference_horizon_unavailable' if horizon is None else horizon['validation_status'],
        potential_pv_kwh=None,remaining_today_potential_kwh=None,captured_pv_kwh=None,trajectory=[],steps=[],
        confidence='provisional_uncalibrated',physical_calibration_qualified=False,action_effects_qualified=False,automatic_actuation=False)
    if reason is None:
        geometry=context.get('solar_geometry')
        if geometry is None:reason='native_solar_geometry_unavailable'
        else:
            try:
                result=integrate_array(array=system['array'],assumptions=ASSUMPTIONS,hourly_forecast=context['hourly_forecast'],
                    positions=geometry['positions'],origin=origin,horizon_hours=context['horizon_hours'],timezone_name=geometry['timezone'],
                    horizon_profile=None if horizon is None else horizon['profile'])
                out.update(result,status='projected_provisional_array_potential')
            except (ValueError,KeyError,TypeError,OverflowError):reason='unsupported_pv_weather_or_geometry'
    out['reason']=reason
    out['projection_sha256']=identity(out)
    return out
