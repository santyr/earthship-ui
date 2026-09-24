#!/usr/bin/env python3
"""Disposable Number-Item state/JDBC/rollback/restart qualification."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_json_jdbc_qualifier', ROOT / 'scripts/qualify-forecast-json-jdbc.py')
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)

if __name__ == '__main__':
    qualifier.main(items={'Predicted_Curtailment_Hours': '2.0'},
                   source_path=ROOT / 'openhab/file-config/items/predicted-curtailment.items',
                   types={'Predicted_Curtailment_Hours': 'Number'})
