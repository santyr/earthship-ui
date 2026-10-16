#!/usr/bin/env python3
"""Verify isolated Switch state/JDBC/provider rollback and full JVM recovery."""
import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'charging_status_jdbc_qualifier',
    ROOT / 'scripts/qualify-forecast-json-jdbc.py',
)
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', choices=('ON', 'OFF'), default='ON',
                        help='Switch value written only in disposable isolation')
    args = parser.parse_args()
    qualifier.main(
        items={'BatteryChargingStatus': args.state},
        source_path=ROOT / 'openhab/file-config/items/battery-charging-status.items',
        types={'BatteryChargingStatus': 'Switch'},
    )
