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
import re


def provider(row):
    value = row.get('editable')
    return 'managed' if value is True else 'non-managed' if value is False else 'unknown'


def inventory(items, things, rules, links, manifest, persistence=()):
    result = {'schema': 'openhab-config-inventory/v1', 'atomic': False}
    result['items'] = sorted([
        {'id': x['name'], 'type': x['type'], 'provider': provider(x),
         'groups': sorted(x.get('groupNames', [])),
         'metadata_namespaces': sorted(x.get('metadata', {}))}
        for x in items], key=lambda x: x['id'])
    result['things'] = sorted([
        {'id': x['UID'], 'provider': provider(x), 'type': x['thingTypeUID'],
         'bridge': x.get('bridgeUID'),
         'configuration_keys': sorted(x.get('configuration', {})),
         'channel_configuration_keys': {
             c['uid']: sorted(c.get('configuration', {}))
             for c in sorted(x.get('channels', []), key=lambda c: c['uid'])},
         'channels': sorted(c['uid'] for c in x.get('channels', []))}
        for x in things], key=lambda x: x['id'])
    result['rules'] = sorted([
        {'id': x['uid'], 'provider': provider(x),
         'module_types': sorted({m['type'] for k in ('triggers', 'conditions', 'actions')
                                 for m in x.get(k, [])})}
        for x in rules], key=lambda x: x['id'])
    result['links'] = sorted([
        {'item': x['itemName'], 'channel': x['channelUID'], 'provider': provider(x),
         'configuration_keys': sorted(x.get('configuration', {}))}
        for x in links], key=lambda x: (x['item'], x['channel']))
    result['persistence'] = sorted([
        {'id': x['serviceId'], 'provider': provider(x),
         'configuration_count': len(x.get('configs', []))}
        for x in persistence], key=lambda x: x['id'])
    issues = []
    for kind in ('items', 'things', 'rules', 'persistence'):
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
        if x['kind'] not in ('item', 'thing', 'rule', 'link', 'persistence') or x['provider'] not in ('file', 'managed'):
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
    if any(x['provider'] == 'unknown' for x in result['links']):
        issues.append('unknown link provider')
    for x in result['links']:
        identity = f'{x["item"]} -> {x["channel"]}'
        key = ('link', identity)
        expected = declared.get(key)
        if expected:
            x['declared_provider'] = expected
            required = 'non-managed' if expected == 'file' else 'managed'
            if x['provider'] != required:
                issues.append(f'ownership mismatch: link {identity}')
        elif x['provider'] != 'managed':
            issues.append(f'unverified provider: link {identity}')
        observed[key] = x['provider']
    for x in result['persistence']:
        key = ('persistence', x['id'])
        observed[key] = x['provider']
        expected = declared.get(key)
        if expected:
            x['declared_provider'] = expected
            required = 'non-managed' if expected == 'file' else 'managed'
            if x['provider'] != required:
                issues.append(f'ownership mismatch: persistence {x["id"]}')
        elif x['provider'] != 'managed':
            issues.append(f'unverified provider: persistence {x["id"]}')
    for key in declared.keys() - observed.keys():
        issues.append(f'declared resource absent: {key[0]} {key[1]}')
    result['issues'] = sorted(issues)
    result['counts'] = {k: dict(sorted(Counter(x['provider'] for x in result[k]).items()))
                        for k in ('items', 'things', 'rules', 'links', 'persistence')}
    return result


def extended_inventory(addons, pages, transformations):
    """Names/shapes only: never UI props/slots, transform scripts or settings."""
    return {
        'addons': sorted([
            {'id': x['uid'], 'type': x['type'], 'version': x.get('version')}
            for x in addons if x.get('installed') is True], key=lambda x: x['id']),
        'pages': sorted([
            {'id': x['uid'], 'component': x['component'], 'provider': provider(x),
             'configuration_keys': sorted(x.get('config', {}))}
            for x in pages], key=lambda x: x['id']),
        'transformations': sorted([
            {'id': x['uid'], 'type': x['type'], 'provider': provider(x),
             'configuration_keys': sorted(x.get('configuration', {}))}
            for x in transformations], key=lambda x: x['id']),
    }


def rule_item_reference_census(items, rules, links):
    """Conservative literal-name census; absence never proves an Item unused.

    Only exact Item-name tokens from rule module configuration values are
    reported. Script bodies and all configuration values stay in memory.
    Dynamically assembled names and external publishers are not discoverable.
    """
    names = {item['name'] for item in items}
    mentions = {name: set() for name in names}

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for child in value.values():
                yield from strings(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                yield from strings(child)

    for rule in rules:
        uid = rule['uid']
        for section in ('triggers', 'conditions', 'actions'):
            for module in rule.get(section, []):
                for value in strings(module.get('configuration', {})):
                    for token in set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', value)) & names:
                        mentions[token].add(uid)

    linked = {link['itemName'] for link in links}
    candidates = sorted(item['name'] for item in items
                        if item.get('editable') is True and item.get('type') != 'Group'
                        and not item.get('groupNames') and item['name'] not in linked
                        and not mentions[item['name']])
    return {
        'scope': 'literal_rule_names_only; external_writers_and_dynamic_names_not_covered',
        'not_migration_approval': True,
        'rule_item_mentions': [
            {'item': name, 'rules': sorted(uids)} for name, uids in sorted(mentions.items())
            if uids],
        'unlinked_ungrouped_unmentioned_managed_items': candidates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).resolve().parents[1]
                        / 'file-config' / 'ownership.json')
    parser.add_argument('--extended', action='store_true', help='Include installed add-ons, UI pages and registered transformations')
    parser.add_argument('--rule-references', action='store_true',
                        help='Census literal Item-name mentions in live rules; not a safety classification')
    parser.add_argument('--summary', action='store_true', help='Print only counts and issues')
    args = parser.parse_args()
    from openhab_sanity_check import get
    started = datetime.now(timezone.utc).isoformat()
    services = get('/persistence')
    items, things, rules, links = (get('/items?metadata=all'), get('/things'),
                                  get('/rules'), get('/links'))
    result = inventory(items, things, rules,
                       links, json.loads(args.manifest.read_text()),
                       [get('/persistence/' + x['id']) for x in services])
    if args.rule_references:
        census = rule_item_reference_census(items, rules, links)
        result['rule_references'] = census
        result['rule_reference_counts'] = {
            'items_mentioned': len(census['rule_item_mentions']),
            'structural_candidates': len(census['unlinked_ungrouped_unmentioned_managed_items']),
        }
    if args.extended:
        result['extended'] = extended_inventory(get('/addons'), get('/ui/components/ui:page'), get('/transformations'))
        result['extended_counts'] = {k: len(v) for k, v in result['extended'].items()}
    result['started_at'] = started
    result['finished_at'] = datetime.now(timezone.utc).isoformat()
    output = ({k: v for k, v in result.items() if k in
              ('schema', 'atomic', 'counts', 'extended_counts', 'rule_reference_counts',
               'issues', 'started_at', 'finished_at')}
              if args.summary else result)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 1 if result['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
