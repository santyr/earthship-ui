"""Offline isolation and synthetic-script guards for the actual rehearsal."""
import importlib.util
import io
from pathlib import Path
import sys
import tarfile

import pytest


spec = importlib.util.spec_from_file_location('bitcoin_exec_qualifier',
    Path(__file__).with_name('qualify-bitcoin-exec-provider.py'))
q = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = q
spec.loader.exec_module(q)


def container_info():
    return {
        'Config': {'Labels': {q.LABEL: 'owned-marker'}, 'User': '9001:9001'},
        'AppArmorProfile': 'docker-default',
        'HostConfig': {
            'NetworkMode': 'none', 'Privileged': False, 'ReadonlyRootfs': True,
            'Binds': None, 'Devices': [], 'PortBindings': {},
            'Memory': 1536 * 1024**2, 'MemorySwap': 1536 * 1024**2,
            'NanoCpus': 1_000_000_000,
        },
    }


def test_exact_isolation_policy():
    q.validate_container(container_info(), 'owned-marker')


def test_create_payload_does_not_copy_enriched_read_only_channels():
    original = {'UID': q.p.UID, 'thingTypeUID': 'exec:command',
                'label': 'BTC_Price', 'configuration': dict(q.p.CONFIG),
                'properties': {'thingTypeVersion': '1'}, 'channels': ['read-only DTO']}
    result = q.managed_definition(original)
    assert set(result) == {'UID', 'thingTypeUID', 'label', 'configuration'}
    assert result['configuration'] == q.p.CONFIG
    result['configuration']['interval'] = 99
    assert original['configuration']['interval'] == 30


@pytest.mark.parametrize('separator', ['|', '│'])
@pytest.mark.parametrize('state', ['Active', 'Resolved'])
def test_public_bundle_identity_parses_actual_console_separators(separator, state):
    line = f'250 {separator} {state} {separator} 80 {separator} 5.2.1 {separator} org.openhab.binding.exec'
    assert q.binding_identity(line) == (250, state)
    assert q.binding_identity(line + '\n' + line) is None


@pytest.mark.parametrize('key,value', [
    ('NetworkMode', 'host'), ('Privileged', True), ('ReadonlyRootfs', False),
    ('Binds', ['/host:/container']), ('Devices', [{'PathOnHost': '/dev/ttyUSB0'}]),
    ('PortBindings', {'8080/tcp': [{}]}), ('Memory', 0), ('MemorySwap', -1),
    ('NanoCpus', 2_000_000_000),
])
def test_weakened_isolation_refused(key, value):
    info = container_info()
    info['HostConfig'][key] = value
    with pytest.raises(RuntimeError):
        q.validate_container(info, 'owned-marker')


def test_wrong_owner_or_user_refused():
    info = container_info()
    with pytest.raises(RuntimeError):
        q.validate_container(info, 'different-marker')
    info['Config']['User'] = 'root'
    with pytest.raises(RuntimeError):
        q.validate_container(info, 'owned-marker')


def test_only_exact_synthetic_script_is_staged(monkeypatch):
    calls = []
    monkeypatch.setattr(q.runtime, 'run', lambda args, data: calls.append((args, data)))
    q.install_probe('isolated-test-container')
    assert len(calls) == 1
    args, body = calls[0]
    assert args == ['docker', 'exec', '-i', 'isolated-test-container',
                    'tar', '-xf', '-', '-C', '/etc/openhab/scripts']
    with tarfile.open(fileobj=io.BytesIO(body)) as archive:
        assert archive.getnames() == ['bitcoin.py']
        member = archive.getmember('bitcoin.py')
        assert member.mode == 0o755
        assert archive.extractfile(member).read() == (
            q.ROOT / 'tests/fixtures/bitcoin-exec-probe.sh').read_bytes()


def test_modified_probe_refused_before_container_write(monkeypatch, tmp_path):
    fixture = tmp_path / 'tests/fixtures/bitcoin-exec-probe.sh'
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b'#!/bin/sh\nreal-feed-not-permitted\n')
    monkeypatch.setattr(q, 'ROOT', tmp_path)
    monkeypatch.setattr(q.runtime, 'run', lambda *_: pytest.fail('no write expected'))
    with pytest.raises(RuntimeError):
        q.install_probe('isolated-test-container')
