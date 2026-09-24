#!/usr/bin/env python3
"""Attended file-provider transfer for three hourly OpenMeteo series Items.

Shares the exact backup, rollback and settled-JDBC guards with the previously
qualified temperature group. --check is read-only; --apply remains attended.
"""
from decimal import Decimal, InvalidOperation
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('forecast_transfer',
    ROOT / 'scripts/migrate-openmeteo-forecast-temperature-items.py')
transfer = module_from_spec(spec)
spec.loader.exec_module(transfer)

transfer.SOURCE = ROOT / 'openhab/file-config/items/openmeteo-forecast-meteorology.items'
transfer.SOURCE_SHA256 = 'b47c97c492206a51c05d5ea75b86c5be24390268a589dd0db90daaf11f64df5a'
transfer.TARGET = Path('/etc/openhab/items/openmeteo-forecast-meteorology.items')
transfer.BACKUP_PREFIX = 'forecast-meteorology-'
transfer.CHANNELS = {
    'Forecast_Cloudiness': 'openmeteo:forecast:local:site:forecastHourly#cloudiness',
    'Forecast_Radiation': 'openmeteo:forecast:local:site:forecastHourly#shortwave-radiation',
    'Forecast_PrecipProb': 'openmeteo:forecast:local:site:forecastHourly#precipitation-probability',
}
transfer.TYPES = {
    'Forecast_Cloudiness': 'Number:Dimensionless',
    'Forecast_Radiation': 'Number:Intensity',
    'Forecast_PrecipProb': 'Number:Dimensionless',
}
transfer.LABELS = {
    'Forecast_Cloudiness': 'Forecast Cloud Cover',
    'Forecast_Radiation': 'Forecast Solar Radiation',
    'Forecast_PrecipProb': 'Forecast Precipitation Probability',
}
transfer.STATE = re.compile(r'^-?(?:\d+(?:\.\d*)?|\.\d+)(?: W/m²)?$')


def split_state(value):
    number, separator, unit = value.partition(' ')
    parsed = Decimal(number)
    if not parsed.is_finite() or separator and unit != 'W/m²':
        raise ValueError('invalid scalar state or unit')
    return parsed, unit


def valid_state(name, value):
    if not isinstance(value, str) or transfer.STATE.fullmatch(value) is None:
        return False
    try:
        _, unit = split_state(value)
        return (unit == 'W/m²') == (name == 'Forecast_Radiation')
    except (InvalidOperation, ValueError):
        return False


def same_state(actual, expected):
    try:
        left, left_unit = split_state(actual)
        right, right_unit = split_state(expected)
        return left_unit == right_unit and abs(left - right) <= Decimal('0.000001')
    except (InvalidOperation, ValueError):
        return False


def format_history_state(name, value):
    if name not in transfer.CHANNELS:
        raise ValueError('unrecognized forecast Item')
    return str(value) + (' W/m²' if name == 'Forecast_Radiation' else '')


transfer.valid_state = valid_state
transfer.same_state = same_state
transfer.format_history_state = format_history_state

if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-openmeteo-forecast-meteorology-items.py --check|--apply')
    transfer.main(apply=sys.argv[1:] == ['--apply'])
