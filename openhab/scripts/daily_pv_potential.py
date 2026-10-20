"""Daily provisional array potential from Google hourly means and native Astro.

This read-only presentation is independent of stored forecasts and storage
acceptance. It reuses the existing PV physics, with five-minute right-endpoint
geometry and exact elapsed time, including partial hours and DST.
"""
from datetime import date,datetime,time,timedelta,timezone
from math import fsum
from zoneinfo import ZoneInfo
from household_pv_model import array_power,ASSUMPTIONS
from household_solar_horizon import horizon_height
from household.control_contracts import instant
from household.evidence import utc
from weather_learning.pv_calibration_policy import project_power


def project_days(*,dates,hours,positions,array,horizon_profile,timezone_name,issued_at,calibration=None,steps_out=None):
    issued=utc(issued_at);zone=ZoneInfo(timezone_name)
    if (not isinstance(dates,list) or not 1<=len(dates)<=10 or dates!=sorted(set(dates)) or
            not isinstance(hours,list) or len(hours)>361 or not isinstance(positions,list) or len(positions)>3000):
        raise ValueError('bounded daily PV forecast inputs required')
    weather={row['at']:row for row in hours};geometry={row['at']:row for row in positions}
    if len(weather)!=len(hours) or len(geometry)!=len(positions):raise ValueError('unique PV source instants required')
    if calibration is not None:
        from weather_learning.pv_directional_calibration import validate_model,sector
        from weather_learning.contracts import instant as model_instant
        calibration=validate_model(calibration)
        if model_instant(calibration['trained_at'])>issued:raise ValueError('PV calibration unavailable at issue')
    result=[]
    for day_string in dates:
        day=date.fromisoformat(day_string)
        midnight=datetime.combine(day,time.min,zone).astimezone(timezone.utc)
        end=datetime.combine(day+timedelta(days=1),time.min,zone).astimezone(timezone.utc)
        if day<issued.astimezone(zone).date():raise ValueError('current or future PV day required')
        start=max(midnight,issued)
        row=dict(date=day_string,status='unavailable',reason='incomplete_weather_or_geometry',potentialKwh=None,
            fromAt=start.isoformat(),throughAt=end.isoformat(),scope='remaining' if start>midnight else 'full_day')
        if calibration is not None:row.update(uncalibratedPotentialKwh=None,calibrationScope='none')
        at=start;energy=[];raw_energy=[];adjusted=False;unadjusted=False
        try:
            while at<end:
                stop=min(end,at.replace(minute=at.minute//5*5,second=0,microsecond=0)+timedelta(minutes=5))
                hour=stop.replace(minute=0,second=0,microsecond=0)
                if hour<stop:hour+=timedelta(hours=1)
                forecast=weather[hour.isoformat()];position=geometry[stop.isoformat()]
                azimuth=position['azimuth_degrees']
                terrain=0. if horizon_profile is None else horizon_height(horizon_profile,azimuth)
                power=array_power(array=array,assumptions=ASSUMPTIONS,ghi_wm2=forecast['radiationWm2'],
                    elevation_degrees=position['elevation_degrees'],azimuth_degrees=azimuth,
                    day_of_year=stop.astimezone(zone).timetuple().tm_yday,temp_f=forecast['tempF'],wind_mph=forecast['windMph'],
                    horizon_elevation_degrees=None if horizon_profile is None else terrain)
                raw_watts=power['potential_dc_w'];watts=raw_watts;applied=False
                if calibration is not None:
                    watts,applied=project_power(calibration,raw_watts,azimuth_degrees=azimuth,elevation_degrees=position['elevation_degrees'],horizon_elevation_degrees=terrain,origin=issued,target=stop)
                adjusted=adjusted or applied and raw_watts>0
                unadjusted=unadjusted or not applied and raw_watts>0
                elapsed=(stop-at).total_seconds()/3600000
                raw_energy.append(raw_watts*elapsed);energy.append(watts*elapsed)
                if steps_out is not None:steps_out.append(dict(start=at.isoformat(),end=stop.isoformat(),uncalibrated_w=raw_watts,potential_w=watts,azimuth_degrees=azimuth,calibration_applied=applied))
                at=stop
            row.update(status='available',reason=None,potentialKwh=fsum(energy))
            if calibration is not None:row.update(uncalibratedPotentialKwh=fsum(raw_energy),calibrationScope='mixed' if adjusted and unadjusted else 'empirical_supported_horizon' if adjusted else 'none')
        except (ValueError,KeyError,TypeError,OverflowError):
            pass
        result.append(row)
    return result
