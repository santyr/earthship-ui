import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('migration', Path(__file__).with_name('migrate-temperature-extrema.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.mark.parametrize('value', ['NULL', 'UNDEF', 'NaN °F', '75', '75 F', 'Infinity °F', None])
def test_invalid_recovery_quantities_refused(value):
    with pytest.raises(ValueError):
        m.quantity(value)


def test_unit_and_numeric_equality_are_both_required():
    assert m.quantity('75.40 °F') == m.quantity('75.4 °F')
    assert m.quantity('75.4 °F') != m.quantity('75.4 °C')


def test_provider_and_definition_changes_refused():
    original = {'name': 'Test', 'type': 'Number:Temperature', 'label': 'Temperature',
        'category': 'temperature', 'groupNames': ['Parent'], 'tags': ['Temperature', 'Point'],
        'metadata': {'semantics': {'value': 'Point'}}, 'stateDescription': {'pattern': '%.0f %unit%'}}
    actual = {**original, 'editable': False, 'tags': ['Point', 'Temperature']}
    m.validate(actual, original, False)
    for field, value in [('editable', True), ('type', 'Number'), ('metadata', {}), ('stateDescription', {})]:
        with pytest.raises(RuntimeError):
            m.validate({**actual, field: value}, original, False)


def test_wait_does_not_accept_wrong_units(monkeypatch):
    original = {'name': 'Test', 'state': '75.4 °F'}
    monkeypatch.setattr(m, 'item', lambda name: {**original, 'state': '75.4 °C', 'editable': False})
    monkeypatch.setattr(m.time, 'sleep', lambda _: None)
    with pytest.raises(RuntimeError, match='state/unit recovery timeout'):
        m.wait('Test', False, original)


def test_wait_allows_metadata_to_settle_but_requires_exact_match(monkeypatch):
    original = {'name': 'Test', 'state': '75.4 °F', 'metadata': {'semantics': {'value': 'Point'}}}
    responses = iter([{**original, 'metadata': {}, 'editable': False}, {**original, 'editable': False}])
    monkeypatch.setattr(m, 'item', lambda name: next(responses))
    monkeypatch.setattr(m.time, 'sleep', lambda _: None)
    m.wait('Test', False, original)
