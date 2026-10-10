"""Pure installed-outdoor-shade dynamics; no fitting, artifact or authority.

These ten coefficients describe the supported installed-shade domain only.
Unshaded response is undefined. Source qualification and release qualification
belong to their explicit callers; constructing this numerical model grants none.
"""
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
import math
from typing import ClassVar

import numpy as np

from .dynamics import (AIR_BOUNDS,MASS_BOUNDS,OUTPUT_RANGE_F,MAX_VENT_FORCING,
                       SOLAR_TERM_SCALE,STABILITY_TOLERANCE,VENT_FORCING_LEVELS)
from .solar import clear_sky_fraction

STEP=timedelta(minutes=5)
MAX_ROLLOUT_STEPS=2880
PARAMETER_NAMES=('outside_exchange','mass_exchange','solar_both_closed',
                 'solar_outdoor_only','vent_exchange','bias','mass_air_exchange',
                 'mass_outside_exchange','mass_solar_both_closed','mass_solar_outdoor_only')
AIR_INDICES=(0,1,3,4,5,6)
MASS_INDICES=(0,1,3,4)
LOWER=tuple(AIR_BOUNDS[0][i] for i in AIR_INDICES)+tuple(MASS_BOUNDS[0][i] for i in MASS_INDICES)
UPPER=tuple(AIR_BOUNDS[1][i] for i in AIR_INDICES)+tuple(MASS_BOUNDS[1][i] for i in MASS_INDICES)


def _number(value):
    try:
        valid=type(value) in (int,float) and math.isfinite(value)
    except OverflowError:
        valid=False
    if not valid:raise ValueError('finite numeric model input required')
    return float(value)


def _temperature(value):
    value=_number(value)
    if not OUTPUT_RANGE_F[0]<=value<=OUTPUT_RANGE_F[1]:raise ValueError('temperature outside physical bounds')
    return value


def _utc(at):
    if not isinstance(at,datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError('aware forecast time required')
    return at.astimezone(timezone.utc)


@dataclass(frozen=True)
class InstalledShadeForcing:
    at: datetime
    outdoor_f: float
    radiation_wm2: float
    indoor_shade_closed: float
    outdoor_shade_present: float
    vent_open: float


@dataclass(frozen=True)
class InstalledShadeRollout:
    states: tuple[tuple[float,float],...]
    sensitivities: tuple[tuple[tuple[float,...],tuple[float,...]],...]


@dataclass(frozen=True)
class InstalledShadeDynamics:
    coefficients: tuple[float,...]
    parameter_names: ClassVar[tuple[str,...]]=PARAMETER_NAMES

    def __post_init__(self):
        values=self.coefficients
        if type(values) is not tuple or len(values)!=len(PARAMETER_NAMES):
            raise ValueError('closed immutable ten-parameter vector required')
        for value,lower,upper in zip(values,LOWER,UPPER):
            if not lower<=_number(value)<=upper:raise ValueError('coefficient outside declared physical bounds')
        if values[2]>values[3] or values[8]>values[9]:
            raise ValueError('both-shade gain exceeds outdoor-only gain')
        if any(radius>=1-STABILITY_TOLERANCE for radius in self.physical_spectral_radii()):
            raise ValueError('unstable thermal transition')
        # Preserve the existing 72-hour zero-radiation stress guard in this domain.
        for _,vent in VENT_FORCING_LEVELS:
            air,mass=90.,50.
            for _ in range(72*12):
                air,mass=self._state_step(air,mass,70.,0.,0.,vent)
                _temperature(air);_temperature(mass)

    def _transition(self,vent):
        p=self.coefficients
        return np.asarray(((1-p[0]-p[1]-vent*p[4],p[1]),
                           (p[6],1-p[6]-p[7])),dtype=float)

    def physical_spectral_radii(self):
        return tuple(float(max(abs(np.linalg.eigvals(self._transition(vent)))))
                     for _,vent in VENT_FORCING_LEVELS)

    def _state_step(self,air,mass,outdoor,solar_both,solar_outdoor,vent):
        p=self.coefficients
        return (air+p[0]*(outdoor-air)+p[1]*(mass-air)+p[2]*solar_both+
                p[3]*solar_outdoor+p[4]*vent*(outdoor-air)+p[5],
                mass+p[6]*(air-mass)+p[7]*(outdoor-mass)+p[8]*solar_both+p[9]*solar_outdoor)

    def rollout(self,*,origin_at,air_f,mass_f,forcings):
        """Return immutable state and exact coefficient sensitivity at each step.

        Each forcing row is explicit at its own end time. Missing rows, unknown
        shade state or any outdoor-shade removal refuse the entire prediction.
        This method neither constructs sensor readings nor qualifies forecasts.
        """
        at=_utc(origin_at);air,mass=_temperature(air_f),_temperature(mass_f)
        if type(forcings) is not tuple or not 1<=len(forcings)<=MAX_ROLLOUT_STEPS:
            raise ValueError('bounded immutable explicit forcing sequence required')
        normalized=[]
        for forcing in forcings:
            if not isinstance(forcing,InstalledShadeForcing):raise ValueError('explicit installed-shade forcing required')
            next_at=_utc(forcing.at)
            if next_at!=at+STEP:raise ValueError('complete five-minute forcing grid required')
            outdoor=_temperature(forcing.outdoor_f)
            radiation=_number(forcing.radiation_wm2)
            indoor=_number(forcing.indoor_shade_closed)
            installed=_number(forcing.outdoor_shade_present)
            vent=_number(forcing.vent_open)
            if installed!=1 or not 0<=indoor<=1:raise ValueError('forcing outside installed-shade domain')
            if not 0<=radiation<=1600 or not 0<=vent<=MAX_VENT_FORCING:
                raise ValueError('forcing outside physical bounds')
            scale=SOLAR_TERM_SCALE*clear_sky_fraction(radiation,next_at)
            normalized.append((outdoor,scale*indoor,scale*(1-indoor),vent));at=next_at
        jac=np.zeros((2,10));states=[];sensitivities=[]
        for outdoor,both,outdoor_solar,vent in normalized:
            direct=np.zeros((2,10))
            direct[0]=(outdoor-air,mass-air,both,outdoor_solar,vent*(outdoor-air),1,0,0,0,0)
            direct[1]=(0,0,0,0,0,0,air-mass,outdoor-mass,both,outdoor_solar)
            jac=self._transition(vent)@jac+direct
            air,mass=self._state_step(air,mass,outdoor,both,outdoor_solar,vent)
            air,mass=_temperature(air),_temperature(mass)
            if not np.isfinite(jac).all():raise ValueError('nonfinite coefficient sensitivity')
            states.append((air,mass))
            sensitivities.append(tuple(tuple(map(float,row)) for row in jac))
        return InstalledShadeRollout(tuple(states),tuple(sensitivities))
