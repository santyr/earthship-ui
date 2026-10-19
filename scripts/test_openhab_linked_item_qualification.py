"""An unrelated linked-Item qualifier must survive weather-provider retirement."""
import importlib.util
from pathlib import Path

import pytest


def load():
    spec = importlib.util.spec_from_file_location('linked_item_qualification', Path(__file__).with_name('openhab_linked_item_qualification.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unconfigured_engine_refuses_before_any_host_read(monkeypatch):
    engine = load()
    def forbidden(*args, **kwargs):
        pytest.fail('unconfigured qualification attempted a host read')
    monkeypatch.setattr(engine.fixture.oh, 'get', forbidden)
    with pytest.raises(RuntimeError):
        engine.main()


def test_exact_file_provider_and_channel_are_required(monkeypatch):
    engine = load()
    engine.CHANNELS = {'BTC_USD_Price': 'exec:command:BTC_Price:output'}
    original = dict(name='BTC_USD_Price', type='Number', label='Bitcoin Price',
                    category=None, tags=[], groupNames=['BTC_Price'])
    links = [dict(itemName='BTC_USD_Price', channelUID='exec:command:BTC_Price:output', editable=False, configuration={})]
    def read(container, path, header):
        return (200, links) if path == '/links' else (200, original | {'editable': False})
    monkeypatch.setattr(engine.fixture, 'isolated_get', read)
    assert engine.definitions_match('disposable', b'fixture', {'BTC_USD_Price': original}, file_owned=True)
    links[0]['channelUID'] = 'exec:command:other:output'
    assert not engine.definitions_match('disposable', b'fixture', {'BTC_USD_Price': original}, file_owned=True)


def test_file_presentation_pattern_drift_is_not_accepted(monkeypatch):
    engine = load()
    engine.CHANNELS = {'BTC_USD_Price': 'exec:command:BTC_Price:output'}
    engine.FILE_PATTERNS = {'BTC_USD_Price': '%.0f USD'}
    original = dict(name='BTC_USD_Price', type='Number', label='Bitcoin Price',
                    category=None, tags=[], groupNames=['BTC_Price'])
    item = original | {'editable': False, 'stateDescription': {'pattern': '%.0f USD'}}
    links = [dict(itemName='BTC_USD_Price', channelUID='exec:command:BTC_Price:output', editable=False, configuration={})]
    monkeypatch.setattr(engine.fixture, 'isolated_get', lambda c,p,h: (200, links if p == '/links' else item))
    assert engine.definitions_match('disposable', b'fixture', {'BTC_USD_Price': original}, file_owned=True)
    item['stateDescription']['pattern'] = '%.0f EUR'
    assert not engine.definitions_match('disposable', b'fixture', {'BTC_USD_Price': original}, file_owned=True)
