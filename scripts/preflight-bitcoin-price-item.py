#!/usr/bin/env python3
"""Read-only exact preflight for the staged Bitcoin price Item/link migration.

This cannot transfer the live Item. A private recoverable Item34 backup,
bounded history comparison, guarded rollback and natural writer check remain
mandatory before any production provider change.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402

spec = spec_from_file_location('bitcoin_history_digest',
    ROOT / 'scripts/bitcoin-price-history-digest.py')
history = module_from_spec(spec)
spec.loader.exec_module(history)

SOURCE = ROOT / 'openhab/file-config/items/bitcoin-price.items'
SOURCE_SHA256 = '3cc0bc0a95add7c5f2f38aec3357a9621b75b94012dbf37f199ef5323d790a49'
TARGET = Path('/etc/openhab/items/bitcoin-price.items')
ITEM = 'BTC_USD_Price'
CHANNEL = 'exec:command:BTC_Price:output'
THING = 'exec:command:BTC_Price'
RULE = 'hex_btc_24h_change'


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def finite_number(value):
    try:
        return Decimal(str(value)).is_finite()
    except (InvalidOperation, TypeError):
        return False


def main():
    require(not TARGET.exists() and not TARGET.is_symlink(),
            'Bitcoin price file target already exists')
    source_hash = sha256(SOURCE.read_bytes()).hexdigest()
    require(source_hash == SOURCE_SHA256, 'prepared Bitcoin price source changed')
    row = oh.get('/items/' + ITEM + '?metadata=.*')
    require(all((row.get(key) or None) == expected for key, expected in {
        'name': ITEM, 'type': 'Number', 'label': '[%.0f ]',
        'category': None, 'groupNames': ['BTC_Price'], 'metadata': None,
    }.items()) and row.get('tags') == [] and row.get('editable') is True
            and finite_number(row.get('state')),
            'live managed Bitcoin price Item or state changed')
    links = oh.get('/links')
    price_links = [link for link in links if link.get('itemName') == ITEM]
    require(len(price_links) == 1 and price_links[0].get('editable') is True
            and price_links[0].get('channelUID') == CHANNEL
            and not price_links[0].get('configuration'),
            'managed Bitcoin price link changed')
    receipt = oh.get('/items/BTC_Output_Receipt_JSON')
    receipt_links = [link for link in links
                     if link.get('itemName') == 'BTC_Output_Receipt_JSON']
    require(receipt.get('editable') is False and len(receipt_links) == 1
            and receipt_links[0].get('editable') is False
            and receipt_links[0].get('channelUID') == CHANNEL
            and receipt_links[0].get('configuration') == {
                'toItemScript': 'bitcoin_output_receipt.js',
                'profile': 'transform:JS'},
            'companion Bitcoin receipt Item/link changed')
    thing = oh.get('/things/' + THING + '?summary=false')
    require(thing.get('UID') == THING
            and thing.get('statusInfo', {}).get('status') == 'ONLINE'
            and any(channel.get('uid') == CHANNEL
                    for channel in thing.get('channels', [])),
            'Bitcoin Exec Thing or output channel unhealthy')
    group = oh.get('/items/BTC_Price?metadata=.*')
    members = {item['name'] for item in oh.get('/items?recursive=false')
               if 'BTC_Price' in item.get('groupNames', [])}
    require(group.get('editable') is True and group.get('type') == 'Group'
            and group.get('label') == 'BTC Price'
            and group.get('metadata') == {
                'semantics': {'value': 'Equipment', 'editable': False}}
            and members == {ITEM, 'BTC_Price_24h_PercentChange'},
            'managed Bitcoin Group or member references changed')
    rule = oh.get('/rules/' + RULE)
    require(rule.get('status') == {'status': 'IDLE', 'statusDetail': 'NONE'}
            and len(rule.get('triggers', [])) == 1
            and rule['triggers'][0].get('type') == 'core.ItemStateUpdateTrigger'
            and rule['triggers'][0].get('configuration', {}).get('itemName') == ITEM,
            'Bitcoin percentage rule trigger or status changed')
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
    prefix = history.digest_history(cutoff)
    require(prefix['jdbc_item_id'] == 34,
            'Bitcoin JDBC identity changed')
    print(json.dumps({'status': 'preflight_passed', 'production_writes': 0,
        'file_transfer': 'not_qualified', 'item': ITEM,
        'managed_group_members': sorted(members),
        'source_sha256': source_hash, 'history_prefix': prefix}, sort_keys=True))


if __name__ == '__main__':
    main()
