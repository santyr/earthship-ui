"""Explicit surveyed level-to-volume curves; no assumed tank geometry or controls."""
import math
import re
from .contract import canonical, digest


def calibrated_volume(depth,calibration,*,connected_tanks,parent_sha256):
    fields={'schema','revision','points','tank_ids','equalized','usable_reserve_litres'}
    if not isinstance(calibration,dict) or set(calibration)!=fields or calibration['schema']!='earthship-volume-calibration/v1':
        raise ValueError('explicit versioned calibration required')
    tanks=calibration['tank_ids']
    if (not isinstance(tanks,list) or not tanks or len(tanks)!=len(set(tanks)) or
        set(tanks)!=set(connected_tanks) or (len(tanks)>1 and calibration['equalized'] is not True)):
        raise ValueError('verified current hydraulic connection required')
    if not isinstance(parent_sha256,str) or not re.fullmatch('[0-9a-f]{64}',parent_sha256):
        raise ValueError('original level evidence digest required')
    if not isinstance(calibration['revision'],str) or not 1<=len(calibration['revision'])<=128:
        raise ValueError('calibration revision required')
    points=calibration['points']
    if not isinstance(points,list) or not 2<=len(points)<=256:
        raise ValueError('measured monotonic depth-volume curve required')
    for point in points:
        if not isinstance(point,list) or len(point)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in point):
            raise ValueError('finite measured calibration points required')
    if any(b[0]<=a[0] or b[1]<=a[1] for a,b in zip(points,points[1:])):
        raise ValueError('strictly increasing measured curve required')
    if type(depth) not in (int,float) or not math.isfinite(depth) or not points[0][0]<=depth<=points[-1][0]:
        raise ValueError('uncalibrated depth: extrapolation refused')
    reserve=calibration['usable_reserve_litres']
    if type(reserve) not in (int,float) or not math.isfinite(reserve) or reserve<0:
        raise ValueError('explicit unusable reserve required')
    for a,b in zip(points,points[1:]):
        if a[0]<=depth<=b[0]:
            volume=a[1]+(depth-a[0])*(b[1]-a[1])/(b[0]-a[0]);break
    return dict(schema='earthship-water-volume-estimate/v1',kind='derived_estimate',
        estimated_litres=volume,estimated_usable_litres=max(0,volume-reserve),
        calibration_revision=calibration['revision'],calibration_sha256=digest(canonical(calibration)),
        parent_sha256=parent_sha256,tank_ids=tanks,authority='none')
