import unittest
from pathlib import Path
from persistence_source import render


def fixture():
    return {'serviceId': 'jdbc', 'editable': True, 'aliases': {},
            'cronStrategies': [], 'thresholdFilters': [], 'timeFilters': [],
            'equalsFilters': [], 'includeFilters': [], 'configs': [
                {'items': ['*', '!Power_Evidence_JSON'],
                 'strategies': ['everyChange', 'restoreOnStartup'], 'filters': []},
                {'items': ['gForecast*'], 'strategies': ['forecast', 'everyChange'], 'filters': []},
                {'items': ['Power_Evidence_JSON'], 'strategies': ['restoreOnStartup'], 'filters': []}]}


class SourceTests(unittest.TestCase):
    def test_exact_prepared_source(self):
        path = Path(__file__).resolve().parents[1] / 'file-config/persistence/jdbc.persist'
        self.assertEqual(render(fixture()), path.read_text())
        self.assertEqual(render({**fixture(), 'editable': False}, allow_file=True), path.read_text())

    def test_refuses_silent_loss(self):
        for key, value in [('aliases', {'I': 'alias'}), ('cronStrategies', [{}]),
                           ('timeFilters', [{}]), ('extra', 'secret'), ('editable', False)]:
            with self.subTest(key=key):
                dto = fixture(); dto[key] = value
                with self.assertRaises(ValueError):
                    render(dto)

    def test_refuses_injection_and_unknown_strategy(self):
        for field, value in [('items', ['I\n}']), ('strategies', ['custom']),
                             ('filters', ['filter']), ('items', []), ('strategies', [])]:
            dto = fixture(); dto['configs'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                render(dto)


if __name__ == '__main__':
    unittest.main()
