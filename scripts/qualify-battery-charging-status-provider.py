#!/usr/bin/env python3
"""Verify the unchanged Switch descriptor in an owned networkless OpenHAB."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'charging_status_provider_qualifier',
    ROOT / 'scripts/qualify-forecast-json-file-provider.py',
)
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)

if __name__ == '__main__':
    qualifier.main(
        names=('BatteryChargingStatus',),
        source_path=ROOT / 'openhab/file-config/items/battery-charging-status.items',
        item_type='Switch',
    )
