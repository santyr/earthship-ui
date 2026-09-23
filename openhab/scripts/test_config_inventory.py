import json
import unittest
from config_inventory import inventory, extended_inventory


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

    def test_configuration_shape_without_values(self):
        args = self.fixture()
        args[1][0]['channels'][0]['configuration'] = {'command': 'SECRET'}
        args[3][0]['configuration']['profile'] = 'SECRET'
        result = inventory(*args)
        self.assertEqual(result['things'][0]['configuration_keys'], ['password'])
        self.assertEqual(result['things'][0]['channel_configuration_keys'],
                         {'t:c': ['command']})
        self.assertEqual(result['links'][0]['configuration_keys'], ['password', 'profile'])
        self.assertNotIn('SECRET', json.dumps(result))

    def test_absent_configuration_is_empty(self):
        args = self.fixture()
        args[1][0].pop('configuration')
        args[3][0].pop('configuration')
        result = inventory(*args)
        self.assertEqual(result['things'][0]['configuration_keys'], [])
        self.assertEqual(result['things'][0]['channel_configuration_keys'], {'t:c': []})
        self.assertEqual(result['links'][0]['configuration_keys'], [])

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

    def test_file_link_requires_matching_declaration(self):
        args = self.fixture(); args[3][0]['editable'] = False
        self.assertIn('unverified provider: link I -> t:c', inventory(*args)['issues'])
        args[-1]['resources'].append({'kind': 'link', 'id': 'I -> t:c', 'provider': 'file'})
        self.assertEqual(inventory(*args)['issues'], [])
        args[3][0]['editable'] = True
        self.assertIn('ownership mismatch: link I -> t:c', inventory(*args)['issues'])
        args[3].clear()
        self.assertIn('declared resource absent: link I -> t:c', inventory(*args)['issues'])

    def test_persistence_file_ownership_requires_declaration(self):
        args = self.fixture()
        service = {'serviceId': 'jdbc', 'editable': False,
                   'configs': [{'items': ['*'], 'strategies': ['everyChange'],
                                'filters': [{'secret': 'SECRET'}]}]}
        result = inventory(*args, [service])
        self.assertIn('unverified provider: persistence jdbc', result['issues'])
        args[-1]['resources'].append({'kind': 'persistence', 'id': 'jdbc', 'provider': 'file'})
        result = inventory(*args, [service])
        self.assertEqual(result['issues'], [])
        self.assertNotIn('SECRET', json.dumps(result))
        service['editable'] = True
        self.assertIn('ownership mismatch: persistence jdbc', inventory(*args, [service])['issues'])

    def test_extended_inventory_excludes_bodies_and_uninstalled_addons(self):
        result = extended_inventory(
            [{'uid': 'a', 'type': 'binding', 'installed': True, 'version': '5', 'properties': {'password': 'SECRET'}},
             {'uid': 'b', 'type': 'binding', 'installed': False}],
            [{'uid': 'p', 'component': 'page', 'editable': True, 'config': {'password': 'SECRET'},
              'props': {'password': 'SECRET'}, 'slots': {'body': 'SECRET'}}],
            [{'uid': 't', 'type': 'JS', 'editable': False, 'configuration': {'script': 'SECRET'}}])
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual([x['id'] for x in result['addons']], ['a'])
        self.assertEqual(result['pages'][0]['configuration_keys'], ['password'])
        self.assertEqual(result['transformations'][0]['configuration_keys'], ['script'])


if __name__ == '__main__':
    unittest.main()
