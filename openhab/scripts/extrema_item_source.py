#!/usr/bin/env python3
"""Closed, read-only renderer for four reviewed display-only extrema Items."""
import json

NAMES = {
    'IndoorTemp_24h_High': ('Indoor temp (24h high)', 'Shelly_HT1'),
    'IndoorTemp_24h_Low': ('Indoor temp (24h low)', 'Shelly_HT1'),
    'OutdoorTemp_24h_High': ('Outdoor temp (24h high)', 'AmbientWeatherWS2902A'),
    'OutdoorTemp_24h_Low': ('Outdoor temp (24h low)', 'AmbientWeatherWS2902A'),
}


def render(items, links, provider=True):
    if len(items) != len(NAMES) or {i.get('name') for i in items} != set(NAMES):
        raise ValueError('exact four reviewed extrema Items required')
    if any(link.get('itemName') in NAMES for link in links):
        raise ValueError('linked extrema Items require separate review')
    lines = ['// Git-owned temperature extrema; deploy only to the declared ownership destination.',
             '// Preserve rolling-24h secondary-screen semantics and existing stable IDs.',
             '// Main-page current-day extrema are separate. No explicit metadata override.', '']
    for item in sorted(items, key=lambda i: i['name']):
        name = item['name']
        label, group = NAMES[name]
        if (item.get('type') != 'Number:Temperature' or item.get('editable') is not provider
                or item.get('label') != label or item.get('category') != 'temperature'
                or sorted(item.get('tags', [])) != ['Point', 'Temperature']
                or item.get('groupNames') != [group]):
            raise ValueError('extrema definition drift requires review')
        expected_metadata = {'semantics': {'value': 'Point', 'editable': False,
                              'config': {'relatesTo': 'Property_Temperature', 'isPointOf': group}}}
        if item.get('metadata') != expected_metadata:
            raise ValueError('custom or changed metadata requires explicit representation')
        if item.get('stateDescription') != {'pattern': '%.0f %unit%', 'readOnly': False, 'options': []}:
            raise ValueError('display formatter drift requires review')
        lines.append(f'Number:Temperature {name} {json.dumps(label)} <temperature> ({group}) ["Point", "Temperature"]')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    import argparse
    from openhab_sanity_check import get
    parser = argparse.ArgumentParser()
    parser.add_argument('--file-owned', action='store_true')
    args = parser.parse_args()
    print(render([get('/items/' + name + '?metadata=.*') for name in NAMES], get('/links'),
                 provider=not args.file_owned), end='')
