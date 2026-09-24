"""Disconnected Number-Item publication probe has bounded, exact cleanup."""
import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('runtime_recovery', SCRIPTS / 'rehearse-openhab-runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


@pytest.mark.parametrize('accept_undef', [True, False])
def test_isolated_number_undef_readback_and_cleanup(accept_undef):
    state = {'exists': False, 'value': 'NULL', 'deleted': False}
    names = []

    def run(args, data=None):
        assert data == b'Authorization: Bearer test\n'
        method = args[args.index('-X') + 1]
        url = next(part for part in args if part.startswith('http://'))
        names.append(url)
        if method == 'PUT' and url.endswith('/state'):
            value = args[args.index('--data-binary') + 1]
            state['value'] = value if accept_undef or value != 'UNDEF' else '42'
        elif method == 'PUT':
            state['exists'] = True
        elif method == 'DELETE':
            state['exists'] = False
            state['deleted'] = True
        elif method == 'GET':
            return state['value'].encode()
        return b''

    if accept_undef:
        assert runtime.verify_number_undef(run, 'isolated-container',
                                           b'Authorization: Bearer test\n', 'a' * 32)
    else:
        with pytest.raises(RuntimeError, match='did not accept UNDEF'):
            runtime.verify_number_undef(run, 'isolated-container',
                                        b'Authorization: Bearer test\n', 'a' * 32)
    assert state['deleted'] and not state['exists']
    assert len(set(names)) == 2  # exact Item and its state endpoint only
