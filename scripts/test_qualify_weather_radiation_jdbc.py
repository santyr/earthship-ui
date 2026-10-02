import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('radiation_qualification_cli',
    Path(__file__).with_name('qualify-weather-radiation-jdbc.py'))
qualifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualifier)


@pytest.mark.parametrize('arguments,code', [(['--help'], 0), (['--unsupported'], 2)])
def test_nonexecution_arguments_never_allocate_a_database(arguments, code, monkeypatch):
    def forbidden():
        pytest.fail('help/invalid arguments must not allocate a database')
    monkeypatch.setattr(qualifier, 'RadiationDatabase', forbidden)
    with pytest.raises(SystemExit) as error:
        qualifier.main(arguments)
    assert error.value.code == code
