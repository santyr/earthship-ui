#!/usr/bin/env python3
"""Read-only live DTO comparison in disposable, network-isolated OpenHAB."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'isolated_file_provider', ROOT / 'scripts/qualify-forecast-json-file-provider.py')
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)

if __name__ == '__main__':
    provider.main(
        names=('Thermal_Model_JSON',),
        source_path=ROOT / 'openhab/file-config/items/thermal-model-shadow.items',
    )
