#!/usr/bin/env python3
"""Disposable Number-Item JDBC, rollback and restart qualification."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_json_jdbc_qualifier', ROOT / 'scripts/qualify-forecast-json-jdbc.py')
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)

if __name__ == '__main__':
    qualifier.main(items={'Forecast_Trough_Error_7d': '4.0'},
                   source_path=ROOT / 'openhab/file-config/items/forecast-trough-error.items',
                   types={'Forecast_Trough_Error_7d': 'Number'})
