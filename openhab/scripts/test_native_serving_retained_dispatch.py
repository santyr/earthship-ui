"""A source revision must score in its retained interpreter/source archive."""
from datetime import datetime,timezone
from pathlib import Path
from hashlib import sha256
import pytest


def test_native_opportunities_preserve_current_and_rotate_explicit_retained_stages():
    import household_forecast_score as coordinator
    choose=getattr(coordinator,'native_score_selection',None)
    assert callable(choose),'retained native scheduling is missing'
    historical=[{'stage':'/private/old-a','deployment_sha256':'a'*64},{'stage':'/private/old-b','deployment_sha256':'b'*64}]
    dispatch={'current':'current','historical':historical}
    assert choose(dispatch,datetime(2026,10,13,18,0,10,tzinfo=timezone.utc))=='current'
    targets=[choose(dispatch,datetime(2026,10,13,18,minute,10,tzinfo=timezone.utc)) for minute in (2,7)]
    assert {t['stage'] for t in targets}=={h['stage'] for h in historical}
    assert choose({'current':'current','historical':[]},datetime(2026,10,13,18,2,10,tzinfo=timezone.utc))=='current'
    with pytest.raises(ValueError):choose(dispatch,datetime(2026,10,13,18,1,10,tzinfo=timezone.utc))


def test_retained_native_exec_uses_its_own_external_pin_and_source_closure(tmp_path,monkeypatch):
    import household_forecast_score as coordinator,household_cycle_deploy as deploy
    execute=getattr(coordinator,'execute_retained_native_score',None)
    assert callable(execute),'retained native source execution is missing'
    import os,json
    tmp_path.chmod(0o700);stage=tmp_path/'old';stage.mkdir(mode=0o700)
    script=stage/'sources/openhab/scripts/household_forecast_score.py';script.parent.mkdir(parents=True);script.write_bytes(b'# synthetic retained coordinator\n')
    config=stage/'forecast.json';config.write_bytes(b'{}');config.chmod(0o600)
    cycle=stage/'cycle.json';cycle.write_text(json.dumps({'forecast_config':str(config)}));cycle.chmod(0o600)
    manifest=stage/'deployment.json';manifest.write_bytes(b'{}');manifest.chmod(0o600)
    selection={'stage':str(stage),'deployment_sha256':sha256(manifest.read_bytes()).hexdigest()}
    def verify(actual,*,expected_deployment_sha256):
        assert actual==stage and expected_deployment_sha256==selection['deployment_sha256']
        return {'schema':'earthship-household-cycle-deployment/v3','source_manifest':{'openhab/scripts/household_forecast_score.py':sha256(script.read_bytes()).hexdigest()}}
    monkeypatch.setattr(deploy,'verify_stage',verify);seen=[]
    monkeypatch.setattr(os,'execve',lambda executable,args,environment:seen.append((executable,args,environment)))
    execute(selection)
    executable,args,environment=seen[0]
    assert args==[executable,str(script),'--config',str(config),'--stage',str(stage),'--deployment-sha256',selection['deployment_sha256'],'--retained-native']
    assert environment['PYTHONPATH'].startswith(str(stage/'sources/openhab/scripts')+':')
    manifest.write_bytes(b'{ }')
    with pytest.raises(ValueError):execute(selection)
