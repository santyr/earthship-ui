import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import bitcoin_legacy as helper


class LegacyBitcoinTests(unittest.TestCase):
    def test_environment_override(self):
        with patch.dict(os.environ, {'CMC_PRO_API_KEY': 'dummy-key'}, clear=True):
            self.assertEqual(helper.load_api_key('/nonexistent'), 'dummy-key')

    def test_private_file_and_reject_permissions_symlink_missing(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            key = Path(directory) / 'key'
            key.write_text('dummy-key\n')
            key.chmod(0o600)
            self.assertEqual(helper.load_api_key(key), 'dummy-key')
            key.chmod(0o644)
            with self.assertRaises(ValueError): helper.load_api_key(key)
            key.chmod(0o600)
            link = Path(directory) / 'link'
            link.symlink_to(key)
            with self.assertRaises(OSError): helper.load_api_key(link)
            with self.assertRaises(FileNotFoundError): helper.load_api_key(Path(directory) / 'missing')

    def test_bad_configuration_does_not_echo_secret(self):
        for value in ('', 'private key', 'private\nkey', 'x' * 4097):
            with self.subTest(value_length=len(value)), patch.dict(os.environ, {'CMC_PRO_API_KEY': value}, clear=True):
                with self.assertRaisesRegex(ValueError, '^Invalid CoinMarketCap credential configuration$'):
                    helper.load_api_key()

    def test_original_output_contract_without_network(self):
        data = {'data': {'1': {'quote': {'USD': {'price': 81246.4, 'percent_change_24h': 1.25}}}}}
        for argument, expected in [('1', '81246\n'), ('2', '1.25\n')]:
            session = Mock()
            session.get.return_value.text = json.dumps(data)
            output = io.StringIO()
            with patch.object(helper, 'Session', return_value=session), patch.object(helper, 'load_api_key', return_value='dummy-key'), patch.object(helper.sys, 'argv', ['bitcoin.py', argument]), contextlib.redirect_stdout(output):
                helper.main()
            self.assertEqual(output.getvalue(), expected)
            session.get.assert_called_once_with('https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest', params={'id': argument, 'convert': 'USD'})
            session.headers.update.assert_called_once_with({'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': 'dummy-key'})


if __name__ == '__main__':
    unittest.main()
