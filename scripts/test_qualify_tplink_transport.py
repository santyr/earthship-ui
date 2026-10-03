"""Safety and durable-evidence contracts for the disconnected binding rehearsal."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import tarfile
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location(
    'tplink_transport', Path(__file__).with_name('qualify-tplink-transport.py'))
transport = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transport)


def info():
    return {'Config': {'Labels': {transport.LABEL: 'owned'}},
            'AppArmorProfile': 'docker-default',
            'HostConfig': {'NetworkMode': 'container:database', 'Privileged': False,
                'Binds': None, 'Devices': [], 'PortBindings': {}, 'ReadonlyRootfs': True,
                'Memory': 2147483648, 'MemorySwap': 2147483648,
                'NanoCpus': 2000000000, 'CapDrop': ['ALL'], 'PidsLimit': 256}}


def test_containment_exact_and_fail_closed():
    transport.check_clone(info(), 'owned', 'container:database')
    for key, value in [('NetworkMode', 'host'), ('Binds', ['/etc:/etc']),
        ('Devices', [{'PathOnHost': '/dev/sda'}]), ('Privileged', True),
        ('PortBindings', {'8080/tcp': [{}]}), ('MemorySwap', 0),
        ('ReadonlyRootfs', False), ('CapDrop', []), ('PidsLimit', 0)]:
        altered = copy.deepcopy(info())
        altered['HostConfig'][key] = value
        with pytest.raises(RuntimeError):
            transport.check_clone(altered, 'owned', 'container:database')
    with pytest.raises(RuntimeError):
        transport.check_clone(info(), 'another-owner', 'container:database')


def test_requests_never_command_or_update_items():
    transport.check_request('GET', '/items/' + transport.ITEM)
    transport.check_request('POST', '/rules')
    for method, path in [('POST', '/items/Dishwasher'),
        ('PUT', '/items/' + transport.ITEM + '/state'),
        ('POST', '/rules/' + transport.UID + '/runnow'),
        ('DELETE', '/things/' + transport.THINGS[0]), ('GET', '/things/unrelated')]:
        with pytest.raises(RuntimeError):
            transport.check_request(method, path)


def test_rule_source_and_triggers_are_original_not_mocked():
    rule = transport.rule_definition()
    assert rule['uid'] == transport.UID
    assert rule['actions'][0]['configuration']['script'] == (
        transport.ROOT / 'openhab/rules/tplink-switch-evidence.js').read_text()
    assert len(rule['triggers']) == 6
    assert 'sendCommand' not in rule['actions'][0]['configuration']['script']


def test_source_drift_is_refused(monkeypatch):
    monkeypatch.setattr(transport, 'SOURCE_SHA', '0' * 64)
    with pytest.raises(RuntimeError, match='source drift'):
        transport.rule_definition()


def test_mode_installation_is_exact_tmp_file_not_path_escape():
    runtime = Mock()
    transport.install_mode(runtime, 'owned-container', 2, 'fault')
    args, body = runtime.run.call_args.args
    assert args == ['docker', 'exec', '-i', 'owned-container', 'tar', '-xf', '-', '-C', '/']
    with tarfile.open(fileobj=io.BytesIO(body)) as archive:
        assert archive.getnames() == ['tmp/hex-tplink-mode-2']
        entry = archive.getmembers()[0]
        assert entry.mode == 0o600
        assert archive.extractfile(entry).read() == b'fault\n'
    for device, mode in ((0, 'fault'), (3, 'healthy'), (1, '../secret')):
        with pytest.raises(RuntimeError): transport.install_mode(runtime, 'owned-container', device, mode)


def test_fault_allows_explicit_undef_but_never_a_fresh_valid_value():
    fault = {'recordedAt': 1000}
    assert transport.fault_observation({'version': 1, 'value': 'OFF', 'observedAt': 990}, fault) == 'held_original_off'
    assert transport.fault_observation({'version': 1, 'value': 'UNDEF', 'observedAt': 1001}, fault) == 'explicit_unavailable_channel_update'
    with pytest.raises(RuntimeError):
        transport.fault_observation({'version': 1, 'value': 'OFF', 'observedAt': 1001}, fault)
    with pytest.raises(RuntimeError):
        transport.fault_observation({'version': 2, 'value': 'UNDEF', 'observedAt': 1001}, fault)


def test_history_validator_requires_original_rows_and_fresh_recovery():
    def receipt(seq, at, status='valid', observed=None):
        observed = at if observed is None else observed
        field = {'status': status, 'reason': 'ok' if status == 'valid' else 'source_unavailable',
                 'observedAt': observed if status == 'valid' else None,
                 'validUntil': observed + 95000 if status == 'valid' else None,
                 'value': 'OFF' if status == 'valid' else None}
        fields = {name: dict(field) for name in transport.FIELDS}
        if status == 'unavailable':
            fields[transport.FIELDS[1]] = {'status': 'valid', 'reason': 'ok',
                'observedAt': at, 'validUntil': at + 95000, 'value': 'OFF'}
        return {'version': 2, 'basis': 'tplink_hs103_switch_report_v1',
                'streamEpoch': 'isolated', 'sequence': seq, 'recordedAt': at,
                'fields': fields}
    values = [receipt(1, 1000), receipt(2, 62000),
              receipt(3, 65000, 'unavailable'), receipt(4, 67000)]
    rows = [dict(time=value['recordedAt'], state=json.dumps(value)) for value in values]
    assert transport.validate_history(rows, values[0], values[1], values[2], values[3])['source_fault_and_native_recovery']
    for fault in ('missing', 'held', 'prefix', 'epoch', 'unaffected', 'renewal_expiry'):
        altered = copy.deepcopy(rows)
        if fault == 'missing': altered.pop(2)
        if fault == 'held':
            old = copy.deepcopy(values[3]); old['fields'][transport.FIELDS[0]]['observedAt'] = 1000
            altered[3]['state'] = json.dumps(old)
        if fault == 'prefix': altered[0]['time'] = 90000
        if fault == 'epoch':
            old = copy.deepcopy(values[3]); old['streamEpoch'] = 'another'
            altered[3]['state'] = json.dumps(old)
        if fault == 'unaffected':
            old = copy.deepcopy(values[2]); old['fields'][transport.FIELDS[1]]['status'] = 'unavailable'
            altered[2]['state'] = json.dumps(old)
        if fault == 'renewal_expiry':
            old = copy.deepcopy(values[1]); old['fields'][transport.FIELDS[0]]['validUntil'] += 1
            altered[1]['state'] = json.dumps(old)
        with pytest.raises(RuntimeError):
            # Anchor byte checks cannot substitute for the semantic validator.
            anchors = [json.loads(row['state']) for row in altered] if len(altered) == 4 else values
            transport.validate_history(altered, *anchors)
