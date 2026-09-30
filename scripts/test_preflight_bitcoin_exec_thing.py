"""Offline contract checks; no production reads or command execution."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'bitcoin_exec_preflight', ROOT / 'scripts/preflight-bitcoin-exec-thing.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def thing():
    return {
        'UID': preflight.UID, 'thingTypeUID': 'exec:command',
        'label': 'BTC_Price', 'bridgeUID': None, 'location': None,
        'editable': True, 'properties': {'thingTypeVersion': '1'},
        'configuration': deepcopy(preflight.CONFIG),
        'statusInfo': {'status': 'ONLINE', 'statusDetail': 'NONE'},
        'channels': [
            {'uid': preflight.UID + ':' + name, 'id': name,
             'channelTypeUID': 'exec:' + name, 'itemType': kind,
             'kind': 'STATE', 'configuration': {}, 'properties': {}}
            for name, kind in preflight.CHANNELS.items()
        ],
    }


def links():
    return [
        {'itemName': name, 'channelUID': preflight.UID + ':output',
         'editable': False, 'configuration': deepcopy(config)}
        for name, config in preflight.LINKS.items()
    ]


def test_exact_managed_baseline():
    preflight.validate(thing(), links())


def test_provider_neutral_definition_preserves_labels_and_ignores_membership_order():
    original = thing()
    original['channels'][0]['linkedItems'] = ['BTC_USD_Price', 'BTC_Output_Receipt_JSON']
    reordered = deepcopy(original)
    reordered['editable'] = False
    reordered['channels'][0]['linkedItems'].reverse()
    reordered['channels'].reverse()
    assert preflight.definition(original) == preflight.definition(reordered)
    reordered['channels'][0]['label'] = 'Changed label'
    assert preflight.definition(original) != preflight.definition(reordered)


@pytest.mark.parametrize('field,value', [
    ('command', '/different/script'), ('interval', 60), ('interval', True),
    ('timeout', 10), ('timeout', 15.0), ('autorun', True), ('autorun', 0),
    ('charset', 'UTF-8'),
])
def test_changed_configuration_refused(field, value):
    row = thing()
    row['configuration'][field] = value
    with pytest.raises(RuntimeError):
        preflight.validate(row, links())


@pytest.mark.parametrize('field,value', [
    ('UID', 'exec:command:other'), ('thingTypeUID', 'exec:other'),
    ('label', 'Different label'), ('location', 'New location'),
    ('bridgeUID', 'some:bridge:id'), ('editable', False),
    ('properties', {'thingTypeVersion': '2'}),
    ('statusInfo', {'status': 'OFFLINE', 'statusDetail': 'NONE'}),
])
def test_changed_thing_refused(field, value):
    row = thing()
    row[field] = value
    with pytest.raises(RuntimeError):
        preflight.validate(row, links())


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'configured', 'type', 'kind'])
def test_changed_channels_refused(change):
    row = thing()
    if change == 'missing':
        row['channels'].pop()
    elif change == 'duplicate':
        row['channels'].append(deepcopy(row['channels'][0]))
    elif change == 'configured':
        row['channels'][0]['configuration'] = {'unreviewed': 1}
    elif change == 'type':
        row['channels'][0]['itemType'] = 'Number'
    else:
        row['channels'][0]['kind'] = 'TRIGGER'
    with pytest.raises(RuntimeError):
        preflight.validate(row, links())


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'run', 'profile', 'managed'])
def test_changed_links_refused(change):
    rows = links()
    if change == 'missing':
        rows.pop()
    elif change == 'duplicate':
        rows.append(deepcopy(rows[0]))
    elif change == 'run':
        rows.append({'itemName': 'Unreviewed_Control',
                     'channelUID': preflight.UID + ':run', 'configuration': {}})
    elif change == 'profile':
        rows[1]['configuration']['profile'] = 'unreviewed'
    else:
        rows[0]['editable'] = True
    with pytest.raises(RuntimeError):
        preflight.validate(thing(), rows)


def test_other_things_links_do_not_expand_scope():
    rows = links() + [{'itemName': 'Other', 'channelUID': 'exec:command:other:run'}]
    preflight.validate(thing(), rows)


def test_exact_staged_source():
    preflight.validate_source(preflight.SOURCE)


def test_changed_source_refused(tmp_path):
    path = tmp_path / 'candidate.things'
    path.write_bytes(preflight.SOURCE.read_bytes().replace(b'interval=30', b'interval=60'))
    with pytest.raises(RuntimeError):
        preflight.validate_source(path)


def test_live_check_gets_only_target_and_links(monkeypatch, tmp_path):
    requests = []
    def get(path):
        requests.append(path)
        return links() if path == '/links' else thing()
    monkeypatch.setattr(preflight.oh, 'get', get)
    monkeypatch.setattr(preflight, 'TARGET', tmp_path / 'not-installed.things')
    report = preflight.check()
    assert requests == ['/things/' + preflight.UID + '?summary=false', '/links']
    assert report['production_writes'] == 0
    assert report['live_provider'] == 'managed'
    assert report['provider_handoff'] == 'not_qualified'


def test_existing_destination_refused_before_live_read(monkeypatch, tmp_path):
    target = tmp_path / 'installed.things'
    target.write_text('existing user definition')
    monkeypatch.setattr(preflight, 'TARGET', target)
    monkeypatch.setattr(preflight.oh, 'get', lambda _path: pytest.fail('no live read expected'))
    with pytest.raises(RuntimeError):
        preflight.check()
