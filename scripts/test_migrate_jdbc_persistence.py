import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name('migrate-jdbc-persistence.py')
SPEC = importlib.util.spec_from_file_location('migrate_jdbc_persistence', MODULE_PATH)
transfer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transfer)


class JdbcTransferTests(unittest.TestCase):
    def test_preflight_accepts_change_only_item_without_recent_rows(self):
        original = {'serviceId': 'jdbc', 'editable': True}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, 'source.persist')
            source.write_bytes(b'strategy')
            target = Path(directory, 'target.persist')
            with patch.object(transfer, 'SOURCE', source), patch.object(transfer, 'TARGET', target), \
                    patch.object(transfer, 'request', return_value=(200, original)), \
                    patch.object(transfer, 'render', return_value='strategy'), \
                    patch.object(transfer, 'inactive_jobs'), \
                    patch.object(transfer, 'history', side_effect=[[], [{'time': 1, 'state': '{}'}]]):
                result = transfer.preflight()
                self.assertEqual(result[4]['BMS_SOC'], [])
                self.assertEqual(len(result[4]['Power_Evidence_JSON']), 1)

    def test_rollback_removes_only_expected_file(self):
        original = {'serviceId': 'jdbc', 'editable': True}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, 'jdbc.persist')
            target.write_bytes(b'unexpected')
            with patch.object(transfer, 'TARGET', target), patch.object(transfer, 'request') as request:
                with self.assertRaisesRegex(RuntimeError, 'differs'):
                    transfer.restore_managed(original, b'expected')
                request.assert_not_called()
                self.assertEqual(target.read_bytes(), b'unexpected')
            target.write_bytes(b'expected')
            with patch.object(transfer, 'TARGET', target), \
                    patch.object(transfer, 'request', return_value=(201, None)) as request, \
                    patch.object(transfer, 'wait_provider') as wait:
                transfer.restore_managed(original, b'expected')
                self.assertFalse(target.exists())
                self.assertEqual(wait.call_args_list[0].args, (None,))
                self.assertEqual(wait.call_args_list[1].args, (original,))
                request.assert_called_once_with('PUT', original)


if __name__ == '__main__':
    unittest.main()
