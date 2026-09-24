#!/usr/bin/env python3
"""Rehearse four mixed-unit daily forecast Items and JDBC series in isolation."""
from decimal import Decimal, InvalidOperation
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('forecast_jdbc',
    ROOT / 'scripts/qualify-openmeteo-forecast-temperature-jdbc.py')
fixture = module_from_spec(spec)
spec.loader.exec_module(fixture)

fixture.SOURCE = ROOT / 'openhab/file-config/items/openmeteo-forecast-daily.items'
fixture.NAMES = ('Forecast_Daily_PrecipSum', 'Forecast_Daily_PrecipProbMax',
                 'Forecast_Daily_WeatherCode', 'Forecast_Daily_UVIndex')
fixture.TYPES = {
    'Forecast_Daily_PrecipSum': 'Number:Length',
    'Forecast_Daily_PrecipProbMax': 'Number:Dimensionless',
    'Forecast_Daily_WeatherCode': 'Number',
    'Forecast_Daily_UVIndex': 'Number',
}
fixture.PROBE_CLASS = 'HexForecastDailyProbe'
fixture.SCALARS = {
    'Forecast_Daily_PrecipSum': '0.5 in',
    'Forecast_Daily_PrecipProbMax': '0.4',
    'Forecast_Daily_WeatherCode': '62',
    'Forecast_Daily_UVIndex': '2.9',
}
fixture.SERIES = {name: (7, 86400, 0) for name in fixture.NAMES}
fixture.PAST_SERIES_STATES = {
    'Forecast_Daily_PrecipSum': '0.9 in',
    'Forecast_Daily_PrecipProbMax': '0.7',
    'Forecast_Daily_WeatherCode': '65',
    'Forecast_Daily_UVIndex': '3.5',
}


def split_scalar(value):
    if not isinstance(value, str):
        raise ValueError('scalar string required')
    number, separator, unit = value.partition(' ')
    parsed = Decimal(number)
    if not parsed.is_finite() or separator and unit not in ('in', 'mm'):
        raise ValueError('unsupported scalar unit')
    return parsed, unit


def inches(value, unit):
    if unit == 'in':
        return value
    if unit == 'mm':
        return value / Decimal('25.4')
    raise ValueError('not a length unit')


def same_scalar(actual, expected):
    try:
        found, unit = split_scalar(actual)
        target, target_unit = split_scalar(expected)
        if bool(unit) != bool(target_unit):
            return False
        if unit:
            found = inches(found, unit)
            target = inches(target, target_unit)
        return abs(found - target) <= Decimal('0.000001')
    except (InvalidOperation, ValueError):
        return False


def stored_scalar(value, observed_unit, expected):
    try:
        target, unit = split_scalar(expected)
        if unit:
            actual = inches(Decimal(str(value)), observed_unit)
            target = inches(target, unit)
        else:
            Decimal(observed_unit)
            actual = Decimal(str(value))
        return abs(actual - target) <= Decimal('0.000001')
    except (InvalidOperation, ValueError):
        return False


def series_value(name, index):
    if name == 'Forecast_Daily_PrecipSum':
        return str((index + 1) / 10) + ' in'
    if name == 'Forecast_Daily_PrecipProbMax':
        return str((index + 1) / 10)
    if name == 'Forecast_Daily_WeatherCode':
        return str(60 + index)
    if name == 'Forecast_Daily_UVIndex':
        return str(2 + index / 10)
    raise ValueError('unexpected daily forecast Item')


def stored_past_value(name, observed_unit):
    target, unit = split_scalar(fixture.PAST_SERIES_STATES[name])
    if unit == 'in' and observed_unit == 'mm':
        return str(target * Decimal('25.4'))
    if unit and observed_unit != unit:
        raise ValueError('length storage unit mismatch')
    return str(target)


fixture.same_temperature = same_scalar
fixture.stored_temperature = stored_scalar
fixture.series_value = series_value
fixture.stored_past_value = stored_past_value

if __name__ == '__main__':
    fixture.main()
