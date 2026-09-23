from openmeteo_config import mismatch_keys


def test_numeric_and_boolean_provider_serialization_is_equivalent():
    metadata = {'configParameters': [
        {'name': 'hourlyHours', 'type': 'INTEGER', 'default': '48'},
        {'name': 'current', 'type': 'BOOLEAN', 'default': 'false'},
        {'name': 'location', 'type': 'TEXT'},
    ]}
    original = {'configuration': {'hourlyHours': 48, 'current': True,
                                  'location': '38.1,-105.7', 'removedLegacyKey': 1}}
    current = {'configuration': {'hourlyHours': 48.0, 'current': 'true',
                                 'location': '38.1,-105.7'}}
    assert mismatch_keys(current, original, metadata) == []
    current['configuration']['hourlyHours'] = 49
    assert mismatch_keys(current, original, metadata) == ['hourlyHours']


def test_absent_binding_defaults_are_compared_without_guessing():
    metadata = {'configParameters': [
        {'name': 'refreshInterval', 'type': 'INTEGER', 'default': '60'},
        {'name': 'baseURI', 'type': 'TEXT', 'default': 'https://api.example/v1/'},
    ]}
    original = {'configuration': {}}
    current = {'configuration': {'refreshInterval': 60.0,
                                 'baseURI': 'https://api.example/v1/'}}
    assert mismatch_keys(current, original, metadata) == []
    current['configuration']['baseURI'] = 'https://other.example/v1/'
    assert mismatch_keys(current, original, metadata) == ['baseURI']
