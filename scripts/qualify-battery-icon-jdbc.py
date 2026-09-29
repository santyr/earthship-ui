#!/usr/bin/env python3
"""Disposable BatteryIcon file/managed/JDBC/restart rehearsal; no live writes."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_jdbc_rehearsal', ROOT / 'scripts/qualify-forecast-json-jdbc.py')
rehearsal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehearsal)


if __name__ == '__main__':
    rehearsal.main(items={'BatteryIcon': 'iconify:mdi:battery-70'},
                   source_path=ROOT / 'openhab/file-config/items/battery-icon.items',
                   metadata_names=('BatteryIcon',))
