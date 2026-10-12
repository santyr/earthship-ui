"""Native solar forcing with unchanged installed-shade physical equations.

This numerical model is neither calibrated nor released by construction. Source
availability and forecast publication qualification belong to explicit callers.
"""
from dataclasses import dataclass, field
from typing import ClassVar
import numpy as np
from astro_geometry_series import NativeGeometrySeries
from native_thermal_inputs import native_clear_sky_fraction
from thermal_model.graduation_policy import _sha
from thermal_model.installed_shade_dynamics import (InstalledShadeDynamics,
    InstalledShadeForcing, InstalledShadeRollout, PARAMETER_NAMES, STEP,
    MAX_ROLLOUT_STEPS, _number, _temperature, _utc)
from thermal_model.dynamics import MAX_VENT_FORCING, SOLAR_TERM_SCALE
from thermal_model.solar import SITE_LATITUDE, SITE_LONGITUDE

RULE = 'earthship-native-installed-shade-dynamics/v2'


def normalize_forcings(*, origin_at, forcings, geometry, guard=lambda: None):
    if type(geometry) is not NativeGeometrySeries:
        raise ValueError('original complete native geometry required')
    at = _utc(origin_at)
    if type(forcings) is not tuple or not 1 <= len(forcings) <= MAX_ROLLOUT_STEPS:
        raise ValueError('bounded immutable explicit native forcing sequence required')
    normalized = []
    for forcing in forcings:
        guard()
        if not isinstance(forcing, InstalledShadeForcing):
            raise ValueError('explicit installed-shade forcing required')
        next_at = _utc(forcing.at)
        if next_at != at + STEP: raise ValueError('complete five-minute native forcing grid required')
        outdoor = _temperature(forcing.outdoor_f)
        radiation, indoor, installed, vent = map(_number, (forcing.radiation_wm2,
            forcing.indoor_shade_closed, forcing.outdoor_shade_present, forcing.vent_open))
        if installed != 1 or not 0 <= indoor <= 1:
            raise ValueError('native forcing outside installed-shade domain')
        if not 0 <= radiation <= 1600 or not 0 <= vent <= MAX_VENT_FORCING:
            raise ValueError('native forcing outside physical bounds')
        scale = SOLAR_TERM_SCALE * native_clear_sky_fraction(radiation, next_at, geometry=geometry)
        normalized.append((outdoor, scale*indoor, scale*(1-indoor), vent)); at = next_at
    return tuple(normalized)


@dataclass(frozen=True)
class NativeInstalledShadeDynamics:
    coefficients: tuple[float, ...]
    geometry: NativeGeometrySeries
    expected_series_sha256: str
    _equations: InstalledShadeDynamics = field(init=False, repr=False, compare=False)
    rule: ClassVar[str] = RULE
    parameter_names: ClassVar[tuple[str, ...]] = PARAMETER_NAMES
    release_authorized: ClassVar[bool] = False
    automatic_actuation: ClassVar[bool] = False

    def __post_init__(self):
        if type(self.geometry) is not NativeGeometrySeries or self.geometry.sha256 != _sha(self.expected_series_sha256):
            raise ValueError('original native model geometry pin required')
        source = self.geometry.descriptor()
        if (source['site']['latitude'] != SITE_LATITUDE or source['site']['longitude'] != SITE_LONGITUDE or
                source['timezone'] != 'America/Denver'):
            raise ValueError('native model site/timezone differs from thermal domain')
        # The old object validates the same coefficient bounds, gain order,
        # stability and 72-hour zero-solar physical stress; no v1 position is used.
        object.__setattr__(self, '_equations', InstalledShadeDynamics(self.coefficients))

    def physical_spectral_radii(self): return self._equations.physical_spectral_radii()

    def rollout(self, *, origin_at, air_f, mass_f, forcings, guard=lambda: None):
        air, mass = _temperature(air_f), _temperature(mass_f)
        normalized = normalize_forcings(origin_at=origin_at, forcings=forcings, geometry=self.geometry, guard=guard)
        jac = np.zeros((2, 10)); states = []; sensitivities = []
        for outdoor, both, outdoor_solar, vent in normalized:
            guard(); direct = np.zeros((2, 10))
            direct[0] = (outdoor-air, mass-air, both, outdoor_solar, vent*(outdoor-air), 1, 0, 0, 0, 0)
            direct[1] = (0, 0, 0, 0, 0, 0, air-mass, outdoor-mass, both, outdoor_solar)
            jac = self._equations._transition(vent) @ jac + direct
            air, mass = self._equations._state_step(air, mass, outdoor, both, outdoor_solar, vent)
            air, mass = _temperature(air), _temperature(mass)
            if not np.isfinite(jac).all(): raise ValueError('nonfinite native coefficient sensitivity')
            states.append((air, mass)); sensitivities.append(tuple(tuple(map(float, row)) for row in jac))
        return InstalledShadeRollout(tuple(states), tuple(sensitivities))
