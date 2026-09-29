#!/usr/bin/env python3
"""Exercise countdown Item state/history and provider rollback in isolation."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_json_jdbc_qualifier',
    ROOT / 'scripts/qualify-forecast-json-jdbc.py',
)
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)

if __name__ == '__main__':
    qualifier.main(
        items={'DaysUntilNextSeason': '82 days until Winter ❄️'},
        source_path=ROOT / 'openhab/file-config/items/days-until-next-season.items',
        types={'DaysUntilNextSeason': 'String'},
    )
