import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_json_jdbc_qualifier', ROOT / 'scripts/qualify-forecast-json-jdbc.py')
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)
spec_migrate = importlib.util.spec_from_file_location(
    'curtailment_migration', ROOT / 'scripts/migrate-curtailment-prediction-item.py')
migration = importlib.util.module_from_spec(spec_migrate)
spec_migrate.loader.exec_module(migration)


def test_number_state_equivalence_is_numeric_only():
    assert qualifier.same_state('2', '2.0', 'Number')
    assert qualifier.same_state('0.0', '0', 'Number')
    assert not qualifier.same_state('2', '2.0', 'String')
    assert not qualifier.same_state('NaN', 'NaN', 'Number')
    assert not qualifier.same_state('NULL', '0', 'Number')


def test_staged_curtailment_item_is_unlinked_and_observational():
    source = (ROOT / 'openhab/file-config/items/predicted-curtailment.items').read_text()
    assert source.count('Number Predicted_Curtailment_Hours ') == 1
    assert '["forecast-intel"]' in source
    assert 'channel=' not in source


def test_live_number_item_adapter_is_guarded_and_preserves_numeric_state():
    assert migration.RELEASE_READY is False
    assert migration.migration.ITEM_TYPE == 'Number'
    assert migration.migration.NAMES == ('Predicted_Curtailment_Hours',)
    assert migration.migration.same_state('0', '0.0')
    assert not migration.migration.same_state('NaN', '0.0')


def test_existing_string_item_adapter_still_requires_exact_state():
    spec = importlib.util.spec_from_file_location(
        'forecast_json_migration', ROOT / 'scripts/migrate-forecast-json-items.py')
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    assert original.ITEM_TYPE == 'String'
    assert original.same_state('0', '0')
    assert not original.same_state('0', '0.0')
