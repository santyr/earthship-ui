import copy
import pytest
from extrema_item_source import NAMES, render


def fixtures():
    return [{'name': name, 'type': 'Number:Temperature', 'editable': True, 'label': label,
             'category': 'temperature', 'tags': ['Temperature', 'Point'], 'groupNames': [group],
             'state': '75.4 °F',
             'metadata': {'semantics': {'value': 'Point', 'editable': False,
                          'config': {'relatesTo': 'Property_Temperature', 'isPointOf': group}}},
             'stateDescription': {'pattern': '%.0f %unit%', 'readOnly': False, 'options': []}}
            for name, (label, group) in NAMES.items()]


def test_exact_source_is_deterministic_and_omits_telemetry():
    items = fixtures()
    original = copy.deepcopy(items)
    source = render(items, [])
    assert source == render(list(reversed(items)), [])
    assert source.count('Number:Temperature ') == 4
    assert '75.4' not in source and '°F' not in source
    assert items == original


@pytest.mark.parametrize('change', [
    lambda i: i.update(type='Number'),
    lambda i: i.update(editable=False),
    lambda i: i.update(label='Changed'),
    lambda i: i.update(groupNames=['Other']),
    lambda i: i.update(tags=['Point']),
    lambda i: i['metadata'].update(unit={'value': '°C'}),
    lambda i: i['metadata']['semantics'].update(editable=True),
    lambda i: i['stateDescription'].update(pattern='%.2f °C'),
])
def test_drift_is_rejected(change):
    items = fixtures()
    change(items[0])
    with pytest.raises(ValueError): render(items, [])


def test_missing_duplicate_and_linked_items_are_rejected():
    items = fixtures()
    for bad in (items[:-1], items + [items[0]], [items[0]] * 4):
        with pytest.raises(ValueError): render(bad, [])
    with pytest.raises(ValueError): render(items, [{'itemName': items[0]['name']}])
