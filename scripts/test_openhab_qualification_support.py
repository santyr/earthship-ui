"""Generic qualification adapters must work without an external weather provider."""
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import tarfile

import pytest


def load(filename):
    spec = importlib.util.spec_from_file_location(filename.removesuffix('.py'), Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_managed_item_definition_preserves_optional_metadata_without_state():
    fixture = load('openhab_qualification_fixture.py')
    original = dict(name='SunPhaseIcon', type='String', label='Sun phase',
                    tags=['Point'], groupNames=['Weather'], state='DAYLIGHT')
    assert fixture.managed_item_dto(original) == dict(
        name='SunPhaseIcon', type='String', label='Sun phase', tags=['Point'], groupNames=['Weather'])
    original['category'] = 'sun'
    assert fixture.managed_item_dto(original)['category'] == 'sun'
    original.pop('name')
    with pytest.raises(ValueError):
        fixture.managed_item_dto(original)


@pytest.mark.parametrize('raw,expected', [
    (b'{"name":"SunPhaseIcon"}\nCODE:200', (200, {'name': 'SunPhaseIcon'})),
    (b'not json\nCODE:200', (None, None)),
    (b'{}\nCODE:404', (404, None)),
    (b'{}\nCODE:503', ('503', None)),
    (b'incomplete', (None, None)),
])
def test_container_read_response_preserves_missing_or_failed_status(raw, expected, monkeypatch):
    fixture = load('openhab_qualification_fixture.py')
    monkeypatch.setattr(fixture, 'run', lambda *a, **k: SimpleNamespace(stdout=raw))
    assert fixture.isolated_get('disposable', '/items/SunPhaseIcon', b'fixture-header') == expected


def test_file_install_payload_preserves_original_bytes_and_mode(monkeypatch):
    fixture = load('openhab_qualification_fixture.py')
    payloads = []
    def docker(args, data=None, **kwargs):
        payloads.append(data)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(fixture, 'run', docker)
    body = b'String SunPhaseIcon "Sun phase"\n'
    fixture.install_bytes('disposable', '/openhab/conf/items', 'sun.items', body, mode=0o640)
    with tarfile.open(fileobj=io.BytesIO(payloads[0])) as archive:
        assert archive.getnames() == ['sun.items']
        assert archive.getmember('sun.items').mode == 0o640
        assert archive.extractfile('sun.items').read() == body


def test_jdbc_rest_adapter_returns_status_and_unmodified_body(monkeypatch):
    jdbc = load('openhab_qualification_jdbc.py')
    monkeypatch.setattr(jdbc, 'run', lambda *a, **k: b'{"data":[]}\n200')
    assert jdbc.request('disposable', b'fixture-header', '/persistence/items/Weather_Radiation_Evidence_JSON') == (200, '{"data":[]}')
