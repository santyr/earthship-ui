#!/usr/bin/env python3
"""Isolated JDBC, provider rollback, hot reload, and full-restart rehearsal."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'isolated_jdbc_provider', ROOT / 'scripts/qualify-forecast-json-jdbc.py')
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)

if __name__ == '__main__':
    provider.main(
        items={'Thermal_Model_JSON': json.dumps({'shadow': 'x' * 40_000})},
        source_path=ROOT / 'openhab/file-config/items/thermal-model-shadow.items',
    )
