"""Contracts for the actual, disconnected Discover BMS Modbus rehearsal."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import tarfile
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location(
    'bms_transport', Path(__file__).with_name('qualify-bms-transport.py'))
transport = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transport)


def test_original_rule_and_actual_polling_contract():
    rule = transport.rule_definition()
    assert len(rule['triggers']) == 8
    assert rule['actions'][0]['configuration']['script'] == (
        transport.ROOT / 'openhab/rules/bms-aux-evidence.js').read_text()
    things = transport.thing_definition()
    assert 'host="127.0.0.1"' in things and 'port=1503' in things
    assert 'refresh=30000' in things and 'start=64' in things and 'length=34' in things
    assert 'updateUnchangedValuesEveryMillis=0' in things
    assert 'readStart="88"' in things and 'readStart="74"' in things
    assert 'writeStart' not in things


def test_source_drift_refused(monkeypatch):
    monkeypatch.setattr(transport, 'SOURCE_SHA', '0' * 64)
    with pytest.raises(RuntimeError, match='source drift'):
        transport.rule_definition()


def test_no_rest_items_commands_or_manual_execution():
    transport.check_request('POST', '/rules')
    transport.check_request('GET', '/things/' + transport.POLLER)
    for method, path in [('PUT', '/items/BMS_Temperature_Raw/state'),
        ('POST', '/items/BMS_Capacity_Remaining_Ah'),
        ('POST', '/rules/' + transport.UID + '/runnow'),
        ('GET', '/things/unrelated'), ('DELETE', '/rules/' + transport.UID)]:
        with pytest.raises(RuntimeError): transport.check_request(method, path)


def test_peer_modes_have_exact_guarded_destination():
    runtime = Mock()
    transport.install_mode(runtime, 'owned', 'fault')
    args, body = runtime.run.call_args.args
    assert args == ['docker', 'exec', '-i', 'owned', 'tar', '-xf', '-', '-C', '/']
    with tarfile.open(fileobj=io.BytesIO(body)) as archive:
        assert archive.getnames() == ['tmp/hex-bms-mode']
        assert archive.getmembers()[0].mode == 0o600
        assert archive.extractfile(archive.getmembers()[0]).read() == b'fault\n'
    with pytest.raises(RuntimeError): transport.install_mode(runtime, 'owned', '../other')


def values():
    def receipt(seq, at, failed=False):
        fields = {}
        for name, value in transport.VALUES.items():
            fields[name] = {'status': 'unavailable' if failed else 'valid',
                'reason': 'source_unavailable' if failed else 'ok',
                'observedAt': None if failed else at,
                'validUntil': None if failed else at + 120000,
                'value': None if failed else value}
        return {'version': 1, 'basis': 'discover_bms_190_native_aux_v1',
            'streamEpoch': 'isolated', 'sequence': seq, 'recordedAt': at, 'fields': fields}
    return [receipt(1, 1000), receipt(2, 62000), receipt(3, 92000, True), receipt(4, 122000)]


def rows(receipts):
    return [{'time': v['recordedAt'], 'state': json.dumps(v)} for v in receipts]


def test_original_durable_fault_barrier_and_new_native_recovery():
    receipts = values()
    proof = transport.validate_history(rows(receipts), *receipts)
    assert proof['source_fault_and_native_recovery']
    assert proof['household_physical_sources_tested'] is False
    assert proof['production_writes'] == 0
    assert proof['poll_refresh_ms'] == 30000


@pytest.mark.parametrize('fault', ['missing', 'held', 'sequence', 'epoch', 'expiry',
    'fault_value', 'fault_reason', 'renewal', 'prefix', 'wrong_value', 'no_periodic'])
def test_unproven_history_refused(fault):
    receipts = copy.deepcopy(values())
    field = transport.FIELDS[0]
    if fault == 'missing':
        with pytest.raises(RuntimeError):
            transport.validate_history(rows(receipts[:2] + receipts[3:]), *receipts)
        return
    if fault == 'held': receipts[3]['fields'][field]['observedAt'] = 1000
    if fault == 'sequence': receipts[3]['sequence'] = 5
    if fault == 'epoch': receipts[3]['streamEpoch'] = 'other'
    if fault == 'expiry': receipts[1]['fields'][field]['validUntil'] += 1
    if fault == 'fault_value': receipts[2]['fields'][field]['value'] = 320
    if fault == 'fault_reason': receipts[2]['fields'][field]['reason'] = 'input_unavailable'
    if fault == 'renewal': receipts[1]['fields'][field]['observedAt'] = 1000
    if fault == 'wrong_value': receipts[1]['fields'][field]['value'] = 321
    if fault == 'no_periodic': receipts[1]['recordedAt'] = 50000
    history = rows(receipts)
    if fault == 'prefix': history[0]['time'] = 900000
    with pytest.raises(RuntimeError): transport.validate_history(history, *receipts)


def test_live_source_configuration_drift_refused():
    fixtures = transport.expected_sources()
    transport.verify_sources(fixtures)
    altered = copy.deepcopy(fixtures)
    altered[transport.POLLER]['configuration']['refresh'] = 1000
    with pytest.raises(RuntimeError): transport.verify_sources(altered)
    altered = copy.deepcopy(fixtures)
    altered[transport.THINGS[0]]['configuration']['writeStart'] = '88'
    with pytest.raises(RuntimeError): transport.verify_sources(altered)
