#!/usr/bin/env python3
"""Read-only registry graph, excluding states, credentials and executable bodies.

This is a migration inventory, NOT a restorable export or atomic snapshot.
editable=false means non-managed, not necessarily file-owned. File ownership
requires a separately verified ownership manifest.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path


def provider(row):
    value = row.get('editable')
    return 'managed' if value is True else 'non-managed' if value is False else 'unknown'


def inventory(items, things, rules, links, manifest):
    result = {'schema': 'openhab-config-inventory/v1', 'atomic': False}
    result['items'] = sorted([
        {'id': x['name'], 'type': x['type'], 'provider': provider(x),
         'groups': sorted(x.get('groupNames', [])),
         'metadata_namespaces': sorted(x.get('metadata', {}))}
        for x in items], key=lambda x: x['id'])
    result['things'] = sorted([
        {'id': x['UID'], 'provider': provider(x), 'type': x['thingTypeUID'],
         'bridge': x.get('bridgeUID'),
         'channels': sorted(c['uid'] for c in x.get('channels', []))}
        for x in things], key=lambda x: x['id'])
    result['rules'] = sorted([
        {'id': x['uid'], 'provider': provider(x),
         'module_types': sorted({m['type'] for k in ('triggers', 'conditions', 'actions')
                                 for m in x.get(k, [])})}
        for x in rules], key=lambda x: x['id'])
    result['links'] = sorted([
        {'item': x['itemName'], 'channel': x['channelUID'], 'provider': provider(x)}
        for x in links], key=lambda x: (x['item'], x['channel']))
    issues = []
    for kind in ('items', 'things', 'rules'):
        counts = Counter(x['id'] for x in result[kind])
        issues.extend(f'duplicate {kind}: {name}' for name, n in counts.items() if n > 1)
    link_counts = Counter((x['item'], x['channel']) for x in result['links'])
    issues.extend(f'duplicate link: {item} -> {channel}'
                  for (item, channel), n in link_counts.items() if n > 1)
    item_ids = {x['id'] for x in result['items']}
    group_ids = {x['id'] for x in result['items'] if x['type'] == 'Group'}
    thing_ids = {x['id'] for x in result['things']}
    channel_ids = {c for x in result['things'] for c in x['channels']}
    for x in result['items']:
        for group in x['groups']:
            if group not in group_ids:
                issues.append(f'unresolved group: {x["id"]} -> {group}')
    for x in result['things']:
        if x['bridge'] and x['bridge'] not in thing_ids:
            issues.append(f'unresolved bridge: {x["id"]} -> {x["bridge"]}')
    for x in result['links']:
        if x['item'] not in item_ids or x['channel'] not in channel_ids:
            issues.append(f'unresolved link: {x["item"]} -> {x["channel"]}')
    declared = {}
    for x in manifest['resources']:
        key = (x['kind'], x['id'])
        if key in declared:
            raise ValueError('duplicate ownership declaration')
        if x['kind'] not in ('item', 'thing', 'rule') or x['provider'] not in ('file', 'managed'):
            raise ValueError('unsupported ownership declaration')
        declared[key] = x['provider']
    observed = {}
    for kind in ('item', 'thing', 'rule'):
        for x in result[kind + 's']:
            key = (kind, x['id'])
            observed[key] = x['provider']
            expected = declared.get(key)
            if expected:
                x['declared_provider'] = expected
                required = 'non-managed' if expected == 'file' else 'managed'
                if x['provider'] != required:
                    issues.append(f'ownership mismatch: {kind} {x["id"]}')
            elif x['provider'] != 'managed':
                issues.append(f'unverified provider: {kind} {x["id"]}')
    for key in declared.keys() - observed.keys():
        issues.append(f'declared resource absent: {key[0]} {key[1]}')
    if any(x['provider'] == 'unknown' for x in result['links']):
        issues.append('unknown link provider')
    result['issues'] = sorted(issues)
    result['counts'] = {k: dict(sorted(Counter(x['provider'] for x in result[k]).items()))
                        for k in ('items', 'things', 'rules', 'links')}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).resolve().parents[1]
                        / 'file-config' / 'ownership.json')
    args = parser.parse_args()
    from openhab_sanity_check import get
    started = datetime.now(timezone.utc).isoformat()
    result = inventory(get('/items?metadata=all'), get('/things'), get('/rules'),
                       get('/links'), json.loads(args.manifest.read_text()))
    result['started_at'] = started
    result['finished_at'] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
