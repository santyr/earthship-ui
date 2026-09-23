"""Pure checks for the observational thermal Item transfer adapter."""
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'thermal_item_migration', ROOT / 'scripts/migrate-thermal-model-item.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class ThermalItemMigrationTests(unittest.TestCase):
    def test_exact_transfer_scope(self):
        self.assertEqual(migration.migration.NAMES, ('Thermal_Model_JSON',))
        self.assertEqual(migration.migration.TIMER, 'thermal-model-shadow.timer')
        self.assertEqual(migration.migration.SERVICE, 'thermal-model-shadow.service')
        self.assertEqual(migration.migration.TARGET,
                         Path('/etc/openhab/items/thermal-model-shadow.items'))

    def test_empty_managed_category_matches_absent_file_category_only(self):
        original = dict(name='Thermal_Model_JSON', type='String',
                        label='Thermal model shadow output', category='',
                        tags=[], groupNames=[], metadata=None,
                        stateDescription={'pattern': '%s', 'readOnly': False, 'options': []})
        file_owned = {**original, 'category': None, 'editable': False}
        self.assertTrue(migration.migration.definition(file_owned, original, False))
        self.assertFalse(migration.migration.definition(
            {**file_owned, 'label': 'changed'}, original, False))
        self.assertFalse(migration.migration.definition(
            {**file_owned, 'editable': True}, original, False))


if __name__ == '__main__':
    unittest.main()
