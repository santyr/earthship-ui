"""Exact observational age definitions and fixture-only mutation scope."""
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

SOURCE = Path(__file__).resolve().parents[1]/'openhab/file-config/items/weather-health-ages.items'
ITEMS = {
    'WeatherData_WH31E_AgeSeconds': {'label': 'WH31E age', 'jdbc_id': 532,
        'channel': 'http:url:weatherHealth:wh31eAgeSeconds'},
    'WeatherData_WH32B_AgeSeconds': {'label': 'Indoor console age', 'jdbc_id': 534,
        'channel': 'http:url:weatherHealth:wh32bAgeSeconds'},
}
METADATA = {'value': ' ', 'config': {'pattern': '%.0f s'}}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def original_item(name):
    require(name in ITEMS, 'unknown age Item')
    return {'name': name, 'type': 'Number', 'label': ITEMS[name]['label'],
            'category': '', 'tags': [], 'groupNames': ['gWeatherHealth']}


def validate_item(row, name, *, managed):
    require(type(managed) is bool and isinstance(row, dict), 'invalid descriptor/provider')
    expected = original_item(name)
    require(row.get('editable') is managed, 'Item provider drift')
    for field, value in expected.items():
        actual = row.get(field)
        require(actual in (None, '') if field == 'category' else actual == value,
                'age Item descriptor drift: '+field)
    require(not row.get('unitSymbol'), 'age Item acquired unit semantics')
    require(row.get('stateDescription') == {'pattern': '%.0f s', 'readOnly': False, 'options': []},
            'age display format drift')
    require(row.get('metadata') == {'stateDescription': {**METADATA, 'editable': managed}},
            'metadata definition/provider drift')
    state = row.get('state')
    require(isinstance(state, str) and ' ' not in state and bool(state), 'age state unavailable')
    try:
        value = Decimal(state)
    except InvalidOperation:
        raise ValueError('invalid numeric age') from None
    require(value.is_finite() and value >= 0, 'invalid numeric age')


def validate_links(rows, name, *, managed):
    require(type(managed) is bool and name in ITEMS, 'invalid link scope/provider')
    require(isinstance(rows, list) and len(rows) == 1, 'age Item link cardinality drift')
    row = rows[0]
    require(row.get('itemName') == name and row.get('channelUID') == ITEMS[name]['channel']
            and row.get('editable') is managed and row.get('configuration') == {},
            'age link definition/provider drift')


def link_path(name):
    require(name in ITEMS, 'unknown age link')
    return '/links/'+name+'/'+quote(ITEMS[name]['channel'], safe='')


def original_link(name):
    require(name in ITEMS, 'unknown age link')
    return {'itemName': name, 'channelUID': ITEMS[name]['channel'], 'configuration': {}}


def allowed_mutation(method, path, body):
    for name in ITEMS:
        if path == '/items/'+name:
            if method == 'DELETE' and body is None:
                return
            if method == 'PUT' and body == original_item(name):
                return
        if path == '/items/'+name+'/metadata/stateDescription':
            if method == 'DELETE' and body is None:
                return
            if method == 'PUT' and body == METADATA:
                return
        if path == link_path(name):
            if method == 'DELETE' and body is None or method == 'PUT' and body == original_link(name):
                return
    raise ValueError('mutation outside exact age-definition scope')


def inert_fixture_thing(record):
    """Native identity-only fixture target; no binding endpoints or transformations."""
    from copy import deepcopy
    require(isinstance(record, dict) and record.get('class') == 'org.openhab.core.thing.internal.ThingStorageEntity',
            'unexpected native Thing record')
    value = record.get('value', {})
    require(value.get('UID') == 'http:url:weatherHealth' and value.get('thingTypeUID') == 'http:url'
            and value.get('isBridge') is False, 'unexpected fixture Thing identity')
    selected = {row['channel'] for row in ITEMS.values()}
    channels = [deepcopy(c) for c in value.get('channels', []) if c.get('uid') in selected]
    require(len(channels) == 2 and {c.get('uid') for c in channels} == selected,
            'selected native channels missing or duplicated')
    for channel in channels:
        require(channel.get('kind') == 'STATE' and channel.get('itemType') == 'Number',
                'selected channel semantics drift')
        channel['configuration'] = {}; channel['properties'] = {}
    return {'class': record['class'], 'value': {'UID': value['UID'], 'thingTypeUID': value['thingTypeUID'],
        'isBridge': False, 'label': 'Inert age link target', 'configuration': {}, 'properties': {},
        'channels': channels}}


def validate_fixture_thing(row):
    require(isinstance(row, dict) and row.get('UID') == 'http:url:weatherHealth'
            and row.get('thingTypeUID') == 'http:url' and row.get('configuration') == {}
            and row.get('properties') == {}, 'inert fixture Thing drift')
    channels = row.get('channels', [])
    require(len(channels) == 2 and {c.get('uid') for c in channels} == {s['channel'] for s in ITEMS.values()},
            'inert fixture channel scope drift')
    for name, spec in ITEMS.items():
        channel = next(c for c in channels if c['uid'] == spec['channel'])
        require(channel.get('kind') == 'STATE' and channel.get('itemType') == 'Number'
                and channel.get('configuration') == {} and channel.get('properties') == {}
                and channel.get('linkedItems') == [name], 'inert linked channel drift')
