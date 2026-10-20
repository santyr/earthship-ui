"""Local lux-proxy targets; elapsed receipt gates remain authoritative."""
from datetime import timedelta
from math import fsum
from bisect import bisect_right
from .contracts import finite


def numeric_hour(rows,*,start):
    end=start+timedelta(hours=1);times=[at for at,_ in rows]
    if times!=sorted(set(times)) or len(rows)>10000:raise ValueError('bounded ordered original radiation states required')
    pieces=[]
    for i,(at,value) in enumerate(rows):
        stop=min(end,at+timedelta(seconds=120),rows[i+1][0] if i+1<len(rows) else end);left=max(start,at)
        if stop>left and finite(value) and 0<=value<=1200:pieces.append(((stop-left).total_seconds(),value))
    covered=fsum(seconds for seconds,value in pieces);mean=None if covered<3420 else fsum(seconds*value for seconds,value in pieces)/covered
    return dict(mean_w_m2=mean,covered_seconds=covered,quality='legacy_numeric_without_sensor_receipts',unit='W_m2_lux_proxy',measurement_health_qualified=False)


def qualified_hour(rows,*,start,history_start,cutover,policy,assessed_at):
    from weather_radiation_reader import select_radiation_window
    end=start+timedelta(hours=1);times=[at for at,_ in rows];first=max(0,bisect_right(times,start-timedelta(seconds=policy.validity_seconds))-1);last=bisect_right(times,end+timedelta(seconds=policy.validity_seconds))
    value=select_radiation_window(rows[first:last],start=start,end=end,assessed_at=assessed_at,history_start=history_start,cutover=cutover,policy=policy)
    return dict(mean_w_m2=value['irradiance_wh_m2'] if value['status']=='ok' else None,covered_seconds=value['covered_seconds'],
        quality='clean_v2_elapsed_lux_proxy' if value['status']=='ok' else 'native_receipts_unqualified',unit='W_m2_lux_proxy',
        measurement_health_qualified=value['status']=='ok',accounting=value,metrology_calibrated=False)
