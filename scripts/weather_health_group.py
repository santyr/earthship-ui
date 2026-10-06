"""Exact weather-health Group guards; no network or production write entrypoint."""
from copy import deepcopy
import json

GROUP = 'gWeatherHealth'
FILE_MEMBERS = frozenset({'WeatherData_WH31E_AgeSeconds', 'WeatherData_WH32B_AgeSeconds'})
OBSERVER_FILE_MEMBERS = FILE_MEMBERS|frozenset({'SkyCondition_Diagnostic','SkyCondition_LastEval'})
FILE_MEMBER_SCOPES = (frozenset(), FILE_MEMBERS, OBSERVER_FILE_MEMBERS)
MEMBERS = frozenset({'SkyCondition_Diagnostic', 'SkyCondition_LastEval',
    'WeatherData_HealthStatus', 'WeatherData_WH31E_AgeSeconds',
    'WeatherData_WH32B_AgeSeconds', 'WeatherData_WH65B_AgeSeconds'})
ITEM_IDS = {'SkyCondition_Diagnostic': 541, 'SkyCondition_LastEval': 540,
    'WeatherData_HealthStatus': 535, 'WeatherData_WH31E_AgeSeconds': 532,
    'WeatherData_WH32B_AgeSeconds': 534, 'WeatherData_WH65B_AgeSeconds': 533}
GROUP_RECORD = {
    'class': 'org.openhab.core.items.ManagedItemProvider$PersistedItem',
    'value': {'groupNames': [], 'itemType': 'Group', 'tags': [],
              'label': 'Weather Health', 'category': ''},
}


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def members(rows):
    return {name for name, row in rows.items()
            if GROUP in row.get('value', {}).get('groupNames', [])}


def file_member_scope(registry, group):
    refs = group.get('members', [])
    require(len(refs) == len(MEMBERS) and {row.get('name') for row in refs} == MEMBERS,
            'logical member scope drift')
    require(all(type(row.get('editable')) is bool for row in refs), 'member provider unavailable')
    scope = frozenset(row['name'] for row in refs if not row['editable'])
    require(scope in FILE_MEMBER_SCOPES, 'unsupported live member providers')
    require(isinstance(registry, dict) and not scope.intersection(registry)
            and members(registry) == MEMBERS-scope, 'live and persisted member providers disagree')
    return scope


def cold_edit(body, *, remove, original, file_members=frozenset()):
    """Transform a stopped-registry copy without changing any member record.

    The caller must prove its owned JVM is stopped before installing the bytes.
    REST deletion is unsuitable: it deletes managed member references as well.
    """
    require(type(remove) is bool, 'cold operation must be boolean')
    require(original == GROUP_RECORD, 'original Group record drift')
    require(isinstance(file_members, frozenset) and file_members in FILE_MEMBER_SCOPES,
            'unsupported file member scope')
    rows = json.loads(body)
    require(isinstance(rows, dict) and not file_members.intersection(rows)
            and members(rows) == MEMBERS-file_members,
            'weather-health member references drift')
    if remove:
        require(rows.get(GROUP) == original, 'managed Group record drift')
        del rows[GROUP]
    else:
        require(GROUP not in rows, 'Group provider record already exists')
        rows[GROUP] = deepcopy(original)
    return json.dumps(rows, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode()


def validate_group(item, *, managed):
    require(type(managed) is bool and item.get('editable') is managed,
            'weather-health Group provider drift')
    expected = {'name': GROUP, 'type': 'Group', 'label': 'Weather Health',
                'tags': [], 'groupNames': [], 'state': 'NULL'}
    require(item.get('category') in (None, '') and
            all(item.get(k) == v for k, v in expected.items()),
            'weather-health Group descriptor drift')
    require(not item.get('metadata') and not item.get('groupType')
            and not item.get('function') and not item.get('stateDescription')
            and not item.get('unitSymbol'), 'weather-health Group behavior drift')
    require(len(item.get('members', [])) == len(MEMBERS)
            and {m['name'] for m in item.get('members', [])} == MEMBERS,
            'weather-health Group membership drift')
