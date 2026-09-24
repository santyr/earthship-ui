#!/usr/bin/env python3
"""Attended four-Item daily OpenMeteo file-provider transfer.

Uses the proven private backup, exact rollback and settled-JDBC guards of the
hourly temperature transfer. --check is read-only. Do not apply concurrently
with another forecast Item provider change.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('forecast_transfer',
    ROOT / 'scripts/migrate-openmeteo-forecast-temperature-items.py')
transfer = module_from_spec(spec)
spec.loader.exec_module(transfer)
daily_spec = spec_from_file_location('forecast_daily_units',
    ROOT / 'scripts/qualify-openmeteo-forecast-daily-jdbc.py')
units = module_from_spec(daily_spec)
daily_spec.loader.exec_module(units)

transfer.SOURCE = ROOT / 'openhab/file-config/items/openmeteo-forecast-daily.items'
transfer.SOURCE_SHA256 = '9f1236706f3e33748e9a6069ce01fe44dfebc111d699bbaa6c34f4f77f957fea'
transfer.TARGET = Path('/etc/openhab/items/openmeteo-forecast-daily.items')
transfer.BACKUP_PREFIX = 'forecast-daily-'
transfer.CHANNELS = {
    'Forecast_Daily_PrecipSum': 'openmeteo:forecast:local:site:forecastDaily#precipitation-sum',
    'Forecast_Daily_PrecipProbMax': 'openmeteo:forecast:local:site:forecastDaily#precipitation-probability-max',
    'Forecast_Daily_WeatherCode': 'openmeteo:forecast:local:site:forecastDaily#weather-code',
    'Forecast_Daily_UVIndex': 'openmeteo:forecast:local:site:forecastDaily#uv-index',
}
transfer.TYPES = {
    'Forecast_Daily_PrecipSum': 'Number:Length',
    'Forecast_Daily_PrecipProbMax': 'Number:Dimensionless',
    'Forecast_Daily_WeatherCode': 'Number',
    'Forecast_Daily_UVIndex': 'Number',
}
transfer.LABELS = {
    'Forecast_Daily_PrecipSum': 'Forecast Daily Precipitation',
    'Forecast_Daily_PrecipProbMax': 'Forecast Daily Precip Probability',
    'Forecast_Daily_WeatherCode': 'Forecast Weather Code',
    'Forecast_Daily_UVIndex': 'Forecast UV Index',
}
transfer.STATE = re.compile(r'^-?(?:\d+(?:\.\d*)?|\.\d+)(?: (?:in|mm))?$')


def valid_state(name, value):
    if not isinstance(value, str) or transfer.STATE.fullmatch(value) is None:
        return False
    try:
        _, unit = units.split_scalar(value)
    except (ValueError, ArithmeticError):
        return False
    return bool(unit) == (name == 'Forecast_Daily_PrecipSum')


def format_history_state(name, value):
    if name not in transfer.CHANNELS:
        raise ValueError('unrecognized daily forecast Item')
    return str(value) + (' in' if name == 'Forecast_Daily_PrecipSum' else '')


transfer.valid_state = valid_state
transfer.same_state = units.same_scalar
transfer.format_history_state = format_history_state

if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-openmeteo-forecast-daily-items.py --check|--apply')
    transfer.main(apply=sys.argv[1:] == ['--apply'])
