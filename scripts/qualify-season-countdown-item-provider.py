#!/usr/bin/env python3
"""Check the staged countdown Item in a disposable, networkless OpenHAB."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_json_provider_qualifier',
    ROOT / 'scripts/qualify-forecast-json-file-provider.py',
)
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)

if __name__ == '__main__':
    qualifier.main(
        names=('DaysUntilNextSeason',),
        source_path=ROOT / 'openhab/file-config/items/days-until-next-season.items',
        item_type='String',
    )
