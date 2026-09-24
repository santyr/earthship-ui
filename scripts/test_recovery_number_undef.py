"""Disconnected Number-Item publication probe restores diagnostic state."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('runtime_recovery', SCRIPTS / 'rehearse-openhab-runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


@pytest.mark.parametrize('accept_undef', [True, False])
def test_isolated_number_undef_readback_and_restore(accept_undef):
    state = {'value': '4.0', 'transient_get': True}
    methods = []

    def run(args, data=None):
        assert data == b'Authorization: Bearer test\n'
        method = args[args.index('-X') + 1]
        url = next(part for part in args if part.startswith('http://'))
        methods.append(method)
        assert url.startswith('http://127.0.0.1:8080/rest/items/Forecast_Trough_Error_7d')
        if method == 'PUT' and url.endswith('/state'):
            value = args[args.index('--data-binary') + 1]
            state['value'] = value if accept_undef or value != 'UNDEF' else '42'
        elif method == 'GET':
            if state['value'] == 'UNDEF' and state['transient_get']:
                state['transient_get'] = False
                raise RuntimeError('transient REST outage')
            return json.dumps({'name': 'Forecast_Trough_Error_7d', 'type': 'Number',
                               'state': state['value']}).encode()
        return b''

    if accept_undef:
        assert runtime.verify_number_undef(run, 'isolated-container',
                                           b'Authorization: Bearer test\n',
                                           sleep=lambda _: None, attempts=3)
    else:
        with pytest.raises(RuntimeError, match='state readback failed'):
            runtime.verify_number_undef(run, 'isolated-container',
                                        b'Authorization: Bearer test\n',
                                        sleep=lambda _: None, attempts=3)
    assert state['value'] == '4.0'
    assert 'DELETE' not in methods
    assert methods.count('PUT') == 3  # numeric, UNDEF, exact original
