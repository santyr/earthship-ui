"""Pure AQI cutover guards; no REST calls, JDBC connection or provider writes."""
import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    'aqi_item_migration', Path(__file__).with_name('migrate-openmeteo-aqi-item.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class AQIMigrationGuards(unittest.TestCase):
    def test_exact_item_requires_identity_provider_and_generated_semantics(self):
        item = {**m.EXPECTED, 'editable': True, 'metadata': m.EXPECTED_METADATA}
        self.assertTrue(m.exact_item(item, True))
        self.assertFalse(m.exact_item({**item, 'editable': False}, True))
        self.assertFalse(m.exact_item({**item, 'label': 'Other'}, True))
        self.assertFalse(m.exact_item({**item, 'metadata': {}}, True))
        self.assertFalse(m.exact_item({**item, 'metadata': {
            'semantics': {'value': 'Point_Measurement', 'editable': True}}}, True))

    def test_exact_link_rejects_wrong_channel_provider_or_profile(self):
        link = {'itemName': m.NAME, 'channelUID': m.CHANNEL,
                'editable': True, 'configuration': {}}
        self.assertTrue(m.exact_link(link, True))
        self.assertFalse(m.exact_link({**link, 'editable': False}, True))
        self.assertFalse(m.exact_link({**link, 'channelUID': m.CHANNEL + '-other'}, True))
        self.assertFalse(m.exact_link({**link, 'configuration': {'profile': 'offset'}}, True))

    def test_numeric_state_requires_finite_exact_value(self):
        self.assertTrue(m.same_number('37.708336', '37.7083360'))
        self.assertFalse(m.same_number('37.708337', '37.708336'))
        for value in ('NULL', 'UNDEF', 'NaN', 'Infinity', '', None):
            self.assertFalse(m.same_number(value, '37.708336'))


if __name__ == '__main__':
    unittest.main()
