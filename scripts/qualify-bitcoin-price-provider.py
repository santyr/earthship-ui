#!/usr/bin/env python3
"""Isolated, networkless Bitcoin price Item/link provider and rollback rehearsal.

Production is read-only. This does not qualify the million-row JDBC history or
the managed BTC_Price Group for a live transfer.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('linked_item_provider',
    ROOT / 'scripts/qualify-openmeteo-forecast-temperature-provider.py')
provider = module_from_spec(spec)
spec.loader.exec_module(provider)

provider.SOURCE = ROOT / 'openhab/file-config/items/bitcoin-price.items'
provider.CONTAINER_LABEL = 'hex.bitcoin.price.qualification'
provider.CHANNELS = {'BTC_USD_Price': 'exec:command:BTC_Price:output'}
provider.TYPES = {'BTC_USD_Price': 'Number'}
provider.GROUPS = {'BTC_USD_Price': ['BTC_Price']}
provider.BINDING = None
provider.FILE_LABELS = {'BTC_USD_Price': 'Bitcoin Price'}


if __name__ == '__main__':
    provider.main()
