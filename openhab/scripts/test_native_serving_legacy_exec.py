"""Legacy slots replace one process, preserving the unit's resource boundary."""
from pathlib import Path
from hashlib import sha256
import json
import pytest


def fixture(tmp_path,monkeypatch):
    import household_forecast_score as coordinator,household_cycle_deploy as deploy
    tmp_path.chmod(0o700);stage=tmp_path/'legacy';stage.mkdir(mode=0o700)
    config=stage/'forecast.json';config.write_bytes(b'{}');config.chmod(0o600)
    source='openhab/scripts/household_forecast_score.py';script=stage/'sources'/source
    script.parent.mkdir(parents=True);script.write_bytes(b'# synthetic retained worker\n');script.chmod(0o644)
    manifest=stage/'deployment.json';manifest.write_bytes(b'{}');manifest.chmod(0o600)
    selection={'stage':str(stage),'deployment_sha256':sha256(manifest.read_bytes()).hexdigest(),'config':str(config),'config_sha256':sha256(config.read_bytes()).hexdigest()}
    def verify(actual,*,expected_deployment_sha256):
        assert actual==stage and expected_deployment_sha256==selection['deployment_sha256']
        return {'schema':'earthship-household-cycle-deployment/v1','source_manifest':{source:sha256(script.read_bytes()).hexdigest()}}
    monkeypatch.setattr(deploy,'verify_stage',verify)
    return coordinator,selection,stage,config,script


def test_legacy_exec_uses_original_stage_and_preserves_existing_unit_environment(tmp_path,monkeypatch):
    coordinator,selection,stage,config,script=fixture(tmp_path,monkeypatch)
    import os
    seen=[]
    monkeypatch.setenv('OPENBLAS_NUM_THREADS','1')
    monkeypatch.setattr(os,'execve',lambda executable,argv,environment:seen.append((executable,argv,environment)))
    coordinator.execute_legacy_score(selection)
    executable,argv,environment=seen[0]
    assert executable=='/usr/bin/python3' and argv==[executable,'-P',str(Path(coordinator.__file__).resolve()),'--worker-script',str(script),'--worker-deployment-sha256',selection['deployment_sha256'],'--config',str(config),'--stage',str(stage)]
    assert environment['OPENBLAS_NUM_THREADS']=='1' and environment['PYTHONPATH'].startswith(str(stage/'sources/openhab/scripts')+':')


@pytest.mark.parametrize('damage',['manifest','config'])
def test_changed_retained_selection_cannot_execute(tmp_path,monkeypatch,damage):
    coordinator,selection,stage,config,script=fixture(tmp_path,monkeypatch)
    import os
    monkeypatch.setattr(os,'execve',lambda *a:pytest.fail('changed legacy selection executed'))
    (stage/'deployment.json' if damage=='manifest' else config).write_bytes(b'{ }')
    with pytest.raises(ValueError):coordinator.execute_legacy_score(selection)
