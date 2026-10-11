"""Deployment guards use fixture state only; never touch live sources."""
import importlib.util
from pathlib import Path
import subprocess,sys,types
import pytest

SCRIPT=Path(__file__).with_name('household_energy_source_install.py')

@pytest.mark.parametrize('bad', ['command','success','json_command','pre_dusk_command'])
def test_wrong_effective_contract_refuses_even_dry_run(monkeypatch,bad):
    spec=importlib.util.spec_from_file_location('source_install_fixture',SCRIPT)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    command=['/usr/bin/flock','--wait','90','--conflict-exit-code=75',mod.LOCK,'/usr/bin/python3',str(mod.LIVE/'forecast_intel.py')]
    state={'ExecStart':command if bad!='command' else ['/usr/bin/python3','fixture.py'],'SuccessExitStatus':'75' if bad=='success' else ''}
    def properties(unit,keys):
        worker='forecast_intel.py' if unit=='forecast-json.service' else 'forecast_pre_dusk.py'
        wrapper=['/usr/bin/flock','--nonblock','--conflict-exit-code=75'] if unit=='forecast-json.service' else ['/usr/bin/flock','--wait','20','--conflict-exit-code=75']
        args=wrapper+[mod.LOCK,'/usr/bin/python3',str(mod.LIVE/worker)]+(['json'] if unit=='forecast-json.service' else [])
        if bad==('json_command' if unit=='forecast-json.service' else 'pre_dusk_command'):args=args[args.index('/usr/bin/python3'):]
        return {'ExecStart':args}
    checks=types.SimpleNamespace(argv=lambda raw:raw,properties=properties)
    monkeypatch.setattr(mod,'prepare',lambda:({}, {}, checks, state,b'profile'))
    with pytest.raises(ValueError):mod.execute(False)


def test_optimized_execution_refuses_before_any_preparation():
    result=subprocess.run([sys.executable,'-O',str(SCRIPT),'--help'],capture_output=True,text=True,timeout=10)
    assert result.returncode!=0,'optimized interpreter must not run assertion-based deployment guards'
