import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[2] / 'scripts/verify-openhab-full-backup.py'
spec = importlib.util.spec_from_file_location('full_backup', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FingerprintTests(unittest.TestCase):
    def test_identifiers_are_quoted(self):
        self.assertIn('FROM "public"."items" t', module.fingerprint_query('public', 'items'))

    def test_unsafe_identifiers_refused(self):
        for value in ('x;DROP TABLE items', 'x.y', '"x"', '', '1table'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.fingerprint_query('public', value)

    def test_constant_size_multiset_accumulator(self):
        query = module.fingerprint_query('public', 'items')
        self.assertNotIn('string_agg', query)
        self.assertNotIn('DISTINCT', query)
        self.assertEqual(query.count('COALESCE(sum('), 4)
        self.assertIn('count(*)', query)
        for offset in (1, 17, 33, 49):
            self.assertIn(f'substr(h,{offset},16)', query)


if __name__ == '__main__':
    unittest.main()
