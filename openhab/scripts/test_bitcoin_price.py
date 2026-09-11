"""Offline feed contract: dummy credential file and mocked curl, no network."""
import json
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).with_name('bitcoin_price.sh')


def run_feed(tmp_path, payload, curl_exit=0):
    credential = tmp_path / 'strike.env'
    credential.write_text('STRIKE_API_KEY=offline-fixture\n')
    curl = tmp_path / 'curl'
    curl.write_text('#!/bin/bash\nprintf "%s" "$OFFLINE_RESPONSE"\nexit "$OFFLINE_CURL_EXIT"\n')
    curl.chmod(0o700)
    source = SCRIPT.read_text().replace('/etc/openhab/misc/strike_api.env', str(credential))
    return subprocess.run(['bash', '-c', source], capture_output=True, text=True,
        timeout=3, env={'PATH': f'{tmp_path}:/usr/bin:/bin',
        'OFFLINE_RESPONSE': payload, 'OFFLINE_CURL_EXIT': str(curl_exit)})


def response(amount):
    return json.dumps([{'sourceCurrency': 'BTC', 'targetCurrency': 'USD', 'amount': amount}])


@pytest.mark.parametrize('amount,expected', [('76960.4', '76960'), ('76960.5', '76961'), (76960, '76960')])
def test_valid_whole_dollar_output(tmp_path, amount, expected):
    result = run_feed(tmp_path, response(amount))
    assert result.returncode == 0 and result.stdout == expected + '\n'
    assert result.stderr == ''


@pytest.mark.parametrize('amount', ['not-a-price', None, -5, 0, True, [], {},
    '1;system("echo bad")', 'NaN', 'Infinity', '1e999', '0.1', 9007199254740992])
def test_invalid_prices_fail_without_numeric_output(tmp_path, amount):
    result = run_feed(tmp_path, response(amount))
    assert result.returncode != 0 and result.stdout == ''
    assert result.stderr == 'Error: invalid BTC rate response\n'


@pytest.mark.parametrize('payload', ['not-json', 'null', '{}', '[]',
    response('12')[:-1] + ',' + response('13')[1:],
    '[{"sourceCurrency":"USD","targetCurrency":"BTC","amount":"1"}]'])
def test_bad_or_ambiguous_responses_fail(tmp_path, payload):
    result = run_feed(tmp_path, payload)
    assert result.returncode != 0 and result.stdout == ''


def test_http_failure_rejects_even_valid_body(tmp_path):
    result = run_feed(tmp_path, response('76960'), curl_exit=22)
    assert result.returncode != 0 and result.stdout == ''
    assert result.stderr == 'Error: BTC rate request failed\n'


def test_transport_is_bounded_and_no_price_is_interpolated_into_code():
    source = SCRIPT.read_text()
    assert '--fail --connect-timeout 3 --max-time 10' in source
    assert 'awk' not in source
    assert 'eval' not in source
