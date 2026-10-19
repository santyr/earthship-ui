"""Versioned four-regime heat gain from W/m2, with native night masking."""
from dataclasses import dataclass
from typing import ClassVar
import numpy as np
from astro_geometry_series import NativeGeometrySeries
from astro_geometry import SOLAR_RULE
from native_joint_shade import NativeJointShadeDynamics
from thermal_model.installed_shade_dynamics import (InstalledShadeForcing,InstalledShadeRollout,
    STEP,MAX_ROLLOUT_STEPS,_utc,_temperature,_number)
from thermal_model.dynamics import MAX_VENT_FORCING

RULE='earthship-native-irradiance-shade-dynamics/v4'

def solar_feature_contract():
    return dict(rule='earthship-native-daylight-irradiance/v1',geometry_rule=SOLAR_RULE,
        night_when_elevation_degrees_lte=0.,input_units='W/m2',solar_feature_units='W/m2',
        measured_radiation_source='original_station_radiation',inferred_night_provenance='native_solar_night_zero')

def normalize_forcings(*,origin_at,forcings,geometry,guard=lambda:None):
    if type(geometry) is not NativeGeometrySeries:raise ValueError('original complete native geometry required')
    at=_utc(origin_at)
    if type(forcings) is not tuple or not 1<=len(forcings)<=MAX_ROLLOUT_STEPS:raise ValueError('bounded immutable forcing grid required')
    normalized=[]
    for row in forcings:
        guard()
        if not isinstance(row,InstalledShadeForcing):raise ValueError('explicit shade forcing required')
        next_at=_utc(row.at)
        if next_at!=at+STEP:raise ValueError('complete five-minute native grid required')
        outside=_temperature(row.outdoor_f);radiation,indoor,outdoor,vent=map(_number,
            (row.radiation_wm2,row.indoor_shade_closed,row.outdoor_shade_present,row.vent_open))
        if not 0<=indoor<=1 or not 0<=outdoor<=1 or not 0<=radiation<=1600 or not 0<=vent<=MAX_VENT_FORCING:
            raise ValueError('explicit shade forcing outside physical bounds')
        # Heat input follows irradiance. Dividing by clear-sky irradiance would
        # turn this into cloudiness and amplify weak low-elevation sunlight.
        scale=radiation if geometry.elevation_sin(next_at)>0 else 0.
        normalized.append((outside,scale*(1-indoor)*(1-outdoor),scale*indoor*(1-outdoor),
            scale*(1-indoor)*outdoor,scale*indoor*outdoor,vent));at=next_at
    return tuple(normalized)

@dataclass(frozen=True)
class NativeIrradianceShadeDynamics(NativeJointShadeDynamics):
    rule:ClassVar[str]=RULE
    def rollout(self,*,origin_at,air_f,mass_f,forcings,guard=lambda:None):
        air,mass=_temperature(air_f),_temperature(mass_f);p=self.coefficients
        normalized=normalize_forcings(origin_at=origin_at,forcings=forcings,geometry=self.geometry,guard=guard)
        jac=np.zeros((2,14));states=[];sensitivities=[]
        for outside,*solar,vent in normalized:
            guard();direct=np.zeros((2,14));direct[0,:8]=(outside-air,mass-air,*solar,vent*(outside-air),1)
            direct[1,8:]=(air-mass,outside-mass,*solar);jac=self._transition(vent)@jac+direct
            air,mass=(air+p[0]*(outside-air)+p[1]*(mass-air)+sum(p[2+i]*s for i,s in enumerate(solar))+p[6]*vent*(outside-air)+p[7],
                mass+p[8]*(air-mass)+p[9]*(outside-mass)+sum(p[10+i]*s for i,s in enumerate(solar)))
            air,mass=_temperature(air),_temperature(mass)
            if not np.isfinite(jac).all():raise ValueError('nonfinite native joint sensitivity')
            states.append((air,mass));sensitivities.append(tuple(tuple(map(float,row)) for row in jac))
        return InstalledShadeRollout(tuple(states),tuple(sensitivities))
