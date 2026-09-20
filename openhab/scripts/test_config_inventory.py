import json
import unittest
from config_inventory import inventory


class InventoryTests(unittest.TestCase):
    def fixture(self):
        return ([{'name': 'I', 'type': 'String', 'editable': False,
                  'state': 'SECRET', 'label': 'SECRET',
                  'metadata': {'unit': {'value': 'SECRET'}}}],
                [{'UID': 't', 'thingTypeUID': 'http:url', 'editable': True,
                  'configuration': {'password': 'SECRET'}, 'channels': [{'uid': 't:c'}]}],
                [{'uid': 'r', 'editable': True,
                  'actions': [{'type': 'script', 'configuration': {'script': 'SECRET'}}]}],
                [{'itemName': 'I', 'channelUID': 't:c', 'editable': True,
                  'configuration': {'password': 'SECRET'}}],
                {'resources': [{'kind': 'item', 'id': 'I', 'provider': 'file'}]})

    def test_excludes_values_and_preserves_graph(self):
        result = inventory(*self.fixture())
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(result['issues'], [])
        self.assertEqual(result['items'][0]['provider'], 'non-managed')
        self.assertEqual(result['items'][0]['declared_provider'], 'file')
        self.assertFalse(result['atomic'])

    def test_nonmanaged_not_assumed_file(self):
        args = self.fixture(); args[-1]['resources'] = []
        self.assertIn('unverified provider: item I', inventory(*args)['issues'])

    def test_provider_drift_and_absent(self):
        args = self.fixture(); args[0][0]['editable'] = True
        args[-1]['resources'].append({'kind': 'rule', 'id': 'absent', 'provider': 'file'})
        issues = inventory(*args)['issues']
        self.assertIn('ownership mismatch: item I', issues)
        self.assertIn('declared resource absent: rule absent', issues)

    def test_broken_graph(self):
        args = self.fixture(); args[0][0]['groupNames'] = ['missing']
        args[1][0]['bridgeUID'] = 'missing'; args[3][0]['channelUID'] = 'missing'
        self.assertEqual(len(inventory(*args)['issues']), 3)

    def test_duplicates_and_unknown(self):
        args = self.fixture(); args[0].append(dict(args[0][0]))
        args[3].append(dict(args[3][0])); args[3][0].pop('editable')
        issues = inventory(*args)['issues']
        self.assertIn('duplicate items: I', issues)
        self.assertIn('duplicate link: I -> t:c', issues)
        self.assertIn('unknown link provider', issues)

    def test_manifest_duplicate_refused(self):
        args = self.fixture(); args[-1]['resources'] *= 2
        with self.assertRaises(ValueError):
            inventory(*args)


if __name__ == '__main__':
    unittest.main()
