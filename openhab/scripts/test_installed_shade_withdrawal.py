"""Explicit withdrawal needs no candidate and never claims HTTP-only delivery."""
import importlib,json,subprocess,sys
from pathlib import Path
import pytest
from thermal_model.forcing_capture import _canonical


def module():
    from thermal_model import installed_shade_live as live
    assert hasattr(live,'withdraw_live_publication'),'missing explicit withdrawal'
    return live


class Backend:
    def __init__(self,fail=False):self.fail=fail;self.states=[]
    def verify_unchanged(self):pass
    def put(self,item,state,*,preflight=None):
        if preflight:preflight()
        self.states.append((item,state))
    def persisted(self,item,state,*,since):
        if self.fail:raise ValueError('synthetic missing receipt')
        return dict(item=item,time=int(since.timestamp()*1000),state=state)


def test_explicit_withdrawal_retains_reason_and_actual_unavailable_receipt(tmp_path):
    tmp_path.chmod(0o700);backend=Backend();result=module().withdraw_live_publication(archive=tmp_path,backend=backend,reason='baseline regression')
    assert result['status']=='withdrawn' and result['delivery_verified'] is True
    assert len(backend.states)==1 and backend.states[0][0]=='Thermal_Model_JSON'
    output=json.loads(backend.states[0][1]);assert output['status']=='unavailable' and output['forecast'] is None
    record=json.loads(Path(result['receipt_path']).read_text())
    assert record['reason']=='baseline regression' and record['publication']['state']==backend.states[0][1]


def test_withdrawal_cannot_claim_delivery_without_matching_jdbc_receipt(tmp_path):
    tmp_path.chmod(0o700);result=module().withdraw_live_publication(archive=tmp_path,backend=Backend(True),reason='source failure')
    assert result['status']=='unverified_failure' and result['delivery_verified'] is False
    assert not list(tmp_path.glob('*.installed-shade-withdrawal-v1.json'))


def test_withdrawal_shares_existing_publication_lock(tmp_path):
    import os,fcntl
    tmp_path.chmod(0o700);fd=os.open(tmp_path/'.installed-shade-live.lock',os.O_RDWR|os.O_CREAT,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);backend=Backend()
        assert module().withdraw_live_publication(archive=tmp_path,backend=backend,reason='operator')['status']=='busy'
        assert backend.states==[]
    finally:os.close(fd)


def test_minimal_withdraw_settings_require_no_model_or_database_files(tmp_path):
    from thermal_model import installed_shade_live_inputs as inputs
    assert hasattr(inputs,'load_withdraw_settings'),'missing withdrawal-only settings'
    tmp_path.chmod(0o700);token=tmp_path/'token';token.write_text('fixture');token.chmod(0o600)
    settings=dict(schema='earthship-installed-shade-withdraw-config/v1',openhab_base='http://127.0.0.1:8080/rest',token_file=str(token),evidence_directory=str(tmp_path))
    p=tmp_path/'settings.json';p.write_text(json.dumps(settings));p.chmod(0o600)
    assert inputs.load_withdraw_settings(p)==settings
    p.write_text(json.dumps({**settings,'active':True}))
    with pytest.raises(ValueError):inputs.load_withdraw_settings(p)


def test_withdrawal_backend_refuses_changed_credentials_before_transport(tmp_path):
    from thermal_model.installed_shade_live_inputs import WithdrawalBackend
    tmp_path.chmod(0o700);token=tmp_path/'token';token.write_text('fixture');token.chmod(0o600)
    backend=WithdrawalBackend(dict(openhab_base='http://127.0.0.1:8080/rest',token_file=str(token)))
    calls=[]
    class Transport:
        def put(self,*args,**kwargs):calls.append(args)
    backend.transport=Transport();token.write_text('changed fixture')
    with pytest.raises(ValueError,match='credential changed'):backend.put('Thermal_Model_JSON','{}')
    assert calls==[]


def test_withdrawal_backend_rechecks_credentials_at_transport_preflight(tmp_path):
    from thermal_model.installed_shade_live_inputs import WithdrawalBackend
    tmp_path.chmod(0o700);token=tmp_path/'token';token.write_text('fixture');token.chmod(0o600)
    backend=WithdrawalBackend(dict(openhab_base='http://127.0.0.1:8080/rest',token_file=str(token)))
    writes=[]
    class Transport:
        def put(self,item,state,*,preflight):
            token.write_text('changed fixture');preflight();writes.append((item,state))
    backend.transport=Transport()
    with pytest.raises(ValueError,match='credential changed'):backend.put('Thermal_Model_JSON','{}')
    assert writes==[]


def test_withdrawal_refuses_lock_replacement_during_source_verification(tmp_path):
    tmp_path.chmod(0o700)
    class ReplacingBackend(Backend):
        def verify_unchanged(self):
            lock=tmp_path/'.installed-shade-live.lock'
            if lock.exists():lock.unlink();lock.touch(mode=0o600)
    backend=ReplacingBackend()
    result=module().withdraw_live_publication(archive=tmp_path,backend=backend,reason='operator')
    assert result['status']=='unverified_failure'
    assert backend.states==[]


def test_cli_withdrawal_resource_refusal_precedes_configuration_and_transport(monkeypatch,capsys):
    import thermal_installed_intel as cli
    from thermal_model import installed_shade_live_inputs as inputs
    def refuse():raise ValueError('synthetic headroom refusal')
    monkeypatch.setattr(cli,'_resource_preflight',refuse)
    def forbidden(*args):pytest.fail('configuration or transport reached after resource refusal')
    monkeypatch.setattr(inputs,'load_withdraw_settings',forbidden)
    monkeypatch.setattr(inputs,'WithdrawalBackend',forbidden)
    assert cli.main(['--config','/missing/private/config','--withdraw','--reason','operator'])==1
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='unverified_failure' and result['publication_executed'] is False


@pytest.mark.parametrize('args',[
    ['--withdraw'],['--publish','--withdraw','--reason','operator'],
    ['--check-only','--reason','operator']])
def test_cli_refuses_ambiguous_or_reasonless_intents_before_resources(monkeypatch,args):
    import thermal_installed_intel as cli
    monkeypatch.setattr(cli,'_resource_preflight',lambda:pytest.fail('invalid intent reached resources'))
    with pytest.raises(SystemExit) as error:cli.main(['--config','/missing/private/config',*args])
    assert error.value.code==2
