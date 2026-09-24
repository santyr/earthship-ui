#!/usr/bin/env python3
"""Isolated PostgreSQL/JDBC restore and rollback for the Bitcoin price Item.

Only the disposable OpenHAB/PostgreSQL pair receives the synthetic price.
This does not validate the production million-row history or live Exec writer.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from decimal import Decimal, InvalidOperation

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('unlinked_item_jdbc',
    ROOT / 'scripts/qualify-forecast-json-jdbc.py')
fixture = module_from_spec(spec)
spec.loader.exec_module(fixture)

ITEMS = {'BTC_USD_Price': '84242'}
SOURCE = ROOT / 'openhab/file-config/items/bitcoin-price.items'
ISOLATED_GROUP = ('items/bitcoin-group-test.items',
                  b'Group BTC_Price "BTC Price" ["Equipment"]\n')


def same_numeric_state(actual, expected):
    try:
        return Decimal(str(actual)) == Decimal(str(expected))
    except (InvalidOperation, TypeError):
        return False


if __name__ == '__main__':
    fixture.same_state = same_numeric_state
    fixture.main(ITEMS, SOURCE, types={'BTC_USD_Price': 'Number'},
                 setup_sources=(ISOLATED_GROUP,))
