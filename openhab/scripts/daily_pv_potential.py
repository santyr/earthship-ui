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


def project_days(*,dates,hours,positions,array,horizon_profile,timezone_name,issued_at):
    issued=utc(issued_at);zone=ZoneInfo(timezone_name)
    if (not isinstance(dates,list) or not 1<=len(dates)<=10 or dates!=sorted(set(dates)) or
            not isinstance(hours,list) or len(hours)>361 or not isinstance(positions,list) or len(positions)>3000):
        raise ValueError('bounded daily PV forecast inputs required')
    weather={row['at']:row for row in hours};geometry={row['at']:row for row in positions}
    if len(weather)!=len(hours) or len(geometry)!=len(positions):raise ValueError('unique PV source instants required')
    result=[]
    for day_string in dates:
        day=date.fromisoformat(day_string)
        midnight=datetime.combine(day,time.min,zone).astimezone(timezone.utc)
        end=datetime.combine(day+timedelta(days=1),time.min,zone).astimezone(timezone.utc)
        if day<issued.astimezone(zone).date():raise ValueError('current or future PV day required')
        start=max(midnight,issued)
        row=dict(date=day_string,status='unavailable',reason='incomplete_weather_or_geometry',potentialKwh=None,
            fromAt=start.isoformat(),throughAt=end.isoformat(),scope='remaining' if start>midnight else 'full_day')
        at=start;energy=[]
        try:
            while at<end:
                stop=min(end,at.replace(minute=at.minute//5*5,second=0,microsecond=0)+timedelta(minutes=5))
                hour=stop.replace(minute=0,second=0,microsecond=0)
                if hour<stop:hour+=timedelta(hours=1)
                forecast=weather[hour.isoformat()];position=geometry[stop.isoformat()]
                azimuth=position['azimuth_degrees']
                power=array_power(array=array,assumptions=ASSUMPTIONS,ghi_wm2=forecast['radiationWm2'],
                    elevation_degrees=position['elevation_degrees'],azimuth_degrees=azimuth,
                    day_of_year=stop.astimezone(zone).timetuple().tm_yday,temp_f=forecast['tempF'],wind_mph=forecast['windMph'],
                    horizon_elevation_degrees=None if horizon_profile is None else horizon_height(horizon_profile,azimuth))
                energy.append(power['potential_dc_w']*(stop-at).total_seconds()/3600000);at=stop
            row.update(status='available',reason=None,potentialKwh=fsum(energy))
        except (ValueError,KeyError,TypeError,OverflowError):
            pass
        result.append(row)
    return result
