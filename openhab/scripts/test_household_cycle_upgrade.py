"""Owned observer upgrades preserve originals and never restart services."""
import pytest
from test_household_cycle_deploy import api,fixture


def upgrade_fixture(tmp_path,monkeypatch):
    args,_=fixture(tmp_path);old=args['stage'];new=tmp_path/'new-stage'
    api().stage_deployment(**args);api().stage_deployment(**{**args,'stage':new})
    folder=args['service_file'].parent/(args['service_file'].name+'.d');folder.mkdir(mode=0o700)
    target=folder/'zzzz-household-cycle.conf';target.write_bytes((old/'service.conf').read_bytes());target.chmod(0o600)
    calls=[]
    def state(service):
        command=next(line[10:] for line in target.read_text().splitlines() if line.startswith('ExecStart=') and len(line)>10)
        return dict(ActiveState='inactive',MainPID='0',ExecStart=command,**api().EFFECTIVE_LIMITS)
    monkeypatch.setattr(api(),'_service_state',state)
    monkeypatch.setattr(api(),'_qualify',lambda stage:calls.append('qualified'))
    monkeypatch.setattr(api(),'_systemctl',lambda *args:calls.append(args))
    return args,old,new,target,calls


def test_owned_stage_upgrade_only_reloads_and_preserves_base_service(tmp_path,monkeypatch):
    args,old,new,target,calls=upgrade_fixture(tmp_path,monkeypatch);base=args['service_file'].read_bytes()
    result=api().upgrade_stage(new,previous_stage=old)
    assert result['status']=='deployment_upgraded' and result['service_restarted'] is False
    assert target.read_bytes()==(new/'service.conf').read_bytes()
    assert args['service_file'].read_bytes()==base
    assert calls==['qualified',('daemon-reload',)]


@pytest.mark.parametrize('damage',['override','old_source','active','cache'])
def test_upgrade_refuses_unowned_drift_active_worker_or_different_cache(damage,tmp_path,monkeypatch):
    args,old,new,target,calls=upgrade_fixture(tmp_path,monkeypatch)
    if damage=='override':target.write_bytes(b'[Service]\nExecStart=/unknown\n')
    elif damage=='old_source':(old/'sources/openhab/scripts/household_cycle.py').write_bytes(b'drift')
    elif damage=='active':
        state=api()._service_state
        monkeypatch.setattr(api(),'_service_state',lambda service:{**state(service),'ActiveState':'activating','MainPID':'123'})
    else:
        import json
        p=new/'cycle.json';v=json.loads(p.read_bytes());v['observation_cache']=str(tmp_path/'other-cache');p.write_bytes(api()._encode(v))
        p=new/'deployment.json';v=json.loads(p.read_bytes())
        from hashlib import sha256
        v['cycle_sha256']=sha256((new/'cycle.json').read_bytes()).hexdigest();p.write_bytes(api()._encode(v))
    before=target.read_bytes()
    with pytest.raises(ValueError):api().upgrade_stage(new,previous_stage=old)
    assert target.read_bytes()==before and calls==[]


@pytest.mark.parametrize('damage',['refused','override','active'])
def test_qualification_failure_or_concurrent_change_prevents_upgrade(damage,tmp_path,monkeypatch):
    args,old,new,target,calls=upgrade_fixture(tmp_path,monkeypatch);original=target.read_bytes()
    def qualify(stage):
        if damage=='refused':raise ValueError('qualification refused')
        if damage=='override':target.write_bytes(b'concurrent edit')
        else:
            state=api()._service_state
            monkeypatch.setattr(api(),'_service_state',lambda service:{**state(service),'ActiveState':'activating','MainPID':'123'})
    monkeypatch.setattr(api(),'_qualify',qualify)
    with pytest.raises(ValueError):api().upgrade_stage(new,previous_stage=old)
    assert target.read_bytes()==(b'concurrent edit' if damage=='override' else original)
    assert calls==[]


@pytest.mark.parametrize('concurrent',[False,True])
def test_failed_reload_restores_only_exact_owned_replacement(concurrent,tmp_path,monkeypatch):
    args,old,new,target,calls=upgrade_fixture(tmp_path,monkeypatch);original=target.read_bytes()
    def reload(*args):
        calls.append(args)
        if len(calls)==2:
            if concurrent:target.write_bytes(b'concurrent edit')
            raise ValueError('reload failed')
    monkeypatch.setattr(api(),'_systemctl',reload)
    with pytest.raises(ValueError):api().upgrade_stage(new,previous_stage=old)
    assert target.read_bytes()==(b'concurrent edit' if concurrent else original)
    assert len(calls)==(2 if concurrent else 3)
