"""Four shade regimes for v2 candidates, never a legacy coefficient reinterpretation.

Partial positions interpolate the four explicitly identified regime gains.
The gain ordering makes adding either shade non-heating at fixed forcing;
it does not rank an indoor shade against an outdoor shade.
"""
import math

from .dynamics import SOLAR_TERM_SCALE, _solar_gain_pairs, _value
from .solar import clear_sky_fraction

SOLAR_NAMES = ('solar_unshaded', 'solar_indoor_closed', 'solar_outdoor', 'solar_both_closed')
SOLAR_CONTRACT = {
    'schema': 'earthship-monotone-joint-shade-solar/v1',
    'regimes': list(SOLAR_NAMES),
    'normalization': 'clear_sky_fraction_times_1000',
    'fraction_model': 'bilinear_area_fraction_assumption',
    'gain_order': [list(pair) for pair in _solar_gain_pairs(SOLAR_NAMES)],
    'interpretation': 'fixed_forcing_gain_assumption_not_causal_shade_outcome',
}


def solar_terms(row):
    indoor, outdoor = (_value(row, key) for key in
                       ('indoor_shade_closed', 'outdoor_shade_present'))
    if any(type(value) not in (int, float) or not math.isfinite(value)
           or not 0 <= value <= 1 for value in (indoor, outdoor)):
        raise ValueError('independently known shade fractions required')
    scale = SOLAR_TERM_SCALE * clear_sky_fraction(_value(row, 'radiation_wm2'), _value(row, 'at'))
    return tuple(scale * weight for weight in (
        (1-indoor)*(1-outdoor), indoor*(1-outdoor), (1-indoor)*outdoor, indoor*outdoor))
