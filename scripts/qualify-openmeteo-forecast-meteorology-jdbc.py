#!/usr/bin/env python3
"""Rehearse hourly cloud/radiation/precipitation JDBC recovery in isolation."""
from decimal import Decimal, InvalidOperation
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('forecast_jdbc',
    ROOT / 'scripts/qualify-openmeteo-forecast-temperature-jdbc.py')
fixture = module_from_spec(spec)
spec.loader.exec_module(fixture)

fixture.SOURCE = ROOT / 'openhab/file-config/items/openmeteo-forecast-meteorology.items'
fixture.NAMES = ('Forecast_Cloudiness', 'Forecast_Radiation', 'Forecast_PrecipProb')
fixture.TYPES = {
    'Forecast_Cloudiness': 'Number:Dimensionless',
    'Forecast_Radiation': 'Number:Intensity',
    'Forecast_PrecipProb': 'Number:Dimensionless',
}
fixture.PROBE_CLASS = 'HexForecastMeteorologyProbe'
fixture.SCALARS = {
    'Forecast_Cloudiness': '0.5',
    'Forecast_Radiation': '100 W/m²',
    'Forecast_PrecipProb': '0.2',
}
fixture.SERIES = {
    'Forecast_Cloudiness': (48, 3600, 0),
    'Forecast_Radiation': (48, 3600, 100),
    'Forecast_PrecipProb': (48, 3600, 0),
}
fixture.PAST_SERIES_STATES = {
    'Forecast_Cloudiness': '0.75',
    'Forecast_Radiation': '55 W/m²',
    'Forecast_PrecipProb': '0.08',
}


def split_scalar(value):
    if not isinstance(value, str):
        raise ValueError('scalar string required')
    number, separator, unit = value.partition(' ')
    parsed = Decimal(number)
    if not parsed.is_finite() or separator and unit != 'W/m²':
        raise ValueError('unsupported scalar unit')
    return parsed, unit


def same_scalar(actual, expected):
    try:
        found, unit = split_scalar(actual)
        target, target_unit = split_scalar(expected)
        return unit == target_unit and abs(found - target) <= Decimal('0.000001')
    except (InvalidOperation, ValueError):
        return False


def stored_scalar(value, observed_unit, expected):
    try:
        target, unit = split_scalar(expected)
        if unit == 'W/m²' and observed_unit != 'W/m²':
            return False
        if not unit:
            Decimal(observed_unit)
        return abs(Decimal(str(value)) - target) <= Decimal('0.000001')
    except (InvalidOperation, ValueError):
        return False


def series_value(name, index):
    if name == 'Forecast_Cloudiness':
        return str(index / 100)
    if name == 'Forecast_Radiation':
        return str(100 + index) + ' W/m²'
    if name == 'Forecast_PrecipProb':
        return str(index / 1000)
    raise ValueError('unexpected forecast Item')


def stored_past_value(name, observed_unit):
    target, unit = split_scalar(fixture.PAST_SERIES_STATES[name])
    if unit == 'W/m²' and observed_unit != 'W/m²':
        raise ValueError('radiation storage unit mismatch')
    return str(target)


fixture.same_temperature = same_scalar
fixture.stored_temperature = stored_scalar
fixture.series_value = series_value
fixture.stored_past_value = stored_past_value

if __name__ == '__main__':
    fixture.main()
