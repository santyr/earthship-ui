"""An owned dispatch record is produced before the final stage digest exists."""
from hashlib import sha256
from pathlib import Path
import json
import pytest


def fixture(tmp_path,monkeypatch):
    import household_native_family as family,household_cycle_deploy as deploy
    writer=getattr(family,'prepare_score_dispatch',None)
    assert callable(writer),'family dispatch writer missing'
    tmp_path.chmod(0o700);stage=tmp_path/'legacy';stage.mkdir(mode=0o700)
    config=stage/'forecast.json';config.write_text(json.dumps({'schema':'earthship-provisional-thermal-live-config/v1'}));config.chmod(0o600)
    cycle=stage/'cycle.json';cycle.write_text(json.dumps({'forecast_config':str(config)}));cycle.chmod(0o600)
    manifest=stage/'deployment.json';manifest.write_bytes(b'{}');manifest.chmod(0o600)
    pin=sha256(manifest.read_bytes()).hexdigest()
    def verify(actual,*,expected_deployment_sha256=None):
        assert actual==stage and expected_deployment_sha256==pin;return {'schema':'earthship-household-cycle-deployment/v1'}
    monkeypatch.setattr(deploy,'verify_stage',verify)
    return writer,stage,pin,config,tmp_path/'score-dispatch.json'


def test_family_dispatch_retains_legacy_config_without_self_deployment_digest(tmp_path,monkeypatch):
    writer,stage,pin,config,output=fixture(tmp_path,monkeypatch)
    result=writer(legacy_stage=stage,legacy_deployment_sha256=pin,historical_selections=(),output=output,guard=lambda:None)
    body=json.loads(output.read_bytes())
    assert body=={'schema':'earthship-native-score-dispatch/v1','current':'current','legacy':{'stage':str(stage),'deployment_sha256':pin,'config':str(config),'config_sha256':sha256(config.read_bytes()).hexdigest()},'historical':[]}
    assert output.stat().st_mode & 0o777==0o600 and result['sha256']==sha256(output.read_bytes()).hexdigest()
    assert 'deployment_sha256' not in body and result['live_units_changed'] is False
    with pytest.raises(ValueError):writer(legacy_stage=stage,legacy_deployment_sha256=pin,historical_selections=(),output=output,guard=lambda:None)


def test_family_dispatch_refuses_changed_legacy_before_any_output(tmp_path,monkeypatch):
    writer,stage,pin,config,output=fixture(tmp_path,monkeypatch)
    (stage/'deployment.json').write_bytes(b'{ }')
    with pytest.raises(ValueError):writer(legacy_stage=stage,legacy_deployment_sha256=pin,historical_selections=(),output=output,guard=lambda:None)
    assert not output.exists()
