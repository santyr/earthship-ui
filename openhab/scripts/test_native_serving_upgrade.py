"""An owned receipt-family upgrade preserves schedules and retained queues."""
from hashlib import sha256
import json
from pathlib import Path
import pytest
from test_native_serving_handoff import fixture as initial
from test_household_cycle_deploy import write,encode

FILES={'forecast':'forecast.conf','score':'score.conf','score_timer':'score-timer.conf',
       'preparer_service':'thermal-native-geometry-prepare.service','preparer_timer':'thermal-native-geometry-prepare.timer'}


def fixture(tmp_path,monkeypatch):
    deploy,handoff,args,legacy,old_family,_,old_pin,*_=initial(tmp_path,monkeypatch)
    import household_native_family as family
    root=args['service_file'].parent
    targets={'forecast':root/'thermal-provisional-forecast.service.d/zzzz-household-cycle.conf',
             'score':root/'thermal-provisional-score.service.d/zzzz-household-score.conf',
             'score_timer':root/'thermal-provisional-score.timer.d/zzzz-household-native-timer.conf',
             'preparer_service':root/'thermal-native-geometry-prepare.service',
             'preparer_timer':root/'thermal-native-geometry-prepare.timer'}
    for role,target in targets.items():
        target.parent.mkdir(mode=0o700,exist_ok=True);write(target,(old_family/FILES[role]).read_bytes())
    old_stage=args['stage'];dispatch=json.loads(args['score_dispatch_path'].read_bytes())
    dispatch['historical'].append(dict(stage=str(old_stage),deployment_sha256=old_pin))
    dispatch_path=tmp_path/'new-dispatch.json';write(dispatch_path,encode(dispatch))
    new_args={**args,'stage':tmp_path/'new-stage','score_dispatch_path':dispatch_path,'score_dispatch_sha256':sha256(dispatch_path.read_bytes()).hexdigest()}
    deploy.stage_deployment(**new_args);pin=sha256((new_args['stage']/'deployment.json').read_bytes()).hexdigest()
    libraries=Path(json.loads((old_family/'family.json').read_bytes())['libraries_path'])
    new_family=tmp_path/'new-family';family.prepare(new_args['stage'],libraries,new_family,guard=lambda:None,deployment_sha256=pin)
    def state(path):
        role='forecast' if path.name=='thermal-provisional-forecast.service' else ('score' if path.name=='thermal-provisional-score.service' else 'preparer_service')
        raw=targets[role].read_text();command=[line[10:] for line in raw.splitlines() if line.startswith('ExecStart=') and line!='ExecStart='][0]
        return dict(deploy.EFFECTIVE_LIMITS,ExecStart=command,ActiveState='inactive',MainPID='0')
    monkeypatch.setattr(deploy,'_service_state',state)
    kwargs=dict(previous_forecast_stage=old_stage,previous_score_stage=old_stage,previous_family=old_family,
                previous_deployment_sha256=old_pin,output=tmp_path/'upgrade-handoff',guard=lambda:None)
    return deploy,handoff,new_family,kwargs,targets,old_family


def test_upgrade_binds_previous_effective_pin_and_all_five_owned_files(tmp_path,monkeypatch):
    deploy,handoff,family,kwargs,targets,old_family=fixture(tmp_path,monkeypatch)
    handoff.prepare(family,**kwargs);record=handoff.verify(kwargs['output'],guard=lambda:None)
    assert record['schema']=='earthship-native-thermal-handoff/v3'
    assert record['previous_family']['path']==str(old_family/'family.json')
    assert all(row['previous'] is not None for row in record['changes'].values())
    import household_native_install as install
    assert install._install_files(kwargs['output'],guard=lambda:None)['file_count']==5
    assert all(path.read_bytes()==(family/FILES[role]).read_bytes() for role,path in targets.items())


@pytest.mark.parametrize('damage',['pin','override','missing_history'])
def test_upgrade_refuses_changed_previous_selection(tmp_path,monkeypatch,damage):
    deploy,handoff,family,kwargs,targets,old_family=fixture(tmp_path,monkeypatch)
    if damage=='pin':kwargs['previous_deployment_sha256']='f'*64
    elif damage=='override':targets['preparer_service'].write_bytes(b'unowned replacement')
    else:
        # A valid new package that omits the previous backlog is not an upgrade.
        import household_forecast_score as scorer
        original=scorer.read_score_dispatch
        def dispatch(stage,**kw):
            value=original(stage,**kw)
            if str(stage)!=str(kwargs['previous_forecast_stage']):value['historical']=[]
            return value
        monkeypatch.setattr(scorer,'read_score_dispatch',dispatch)
    with pytest.raises(ValueError):handoff.prepare(family,**kwargs)
    assert not kwargs['output'].exists()


def test_upgrade_late_failure_restores_all_existing_files(tmp_path,monkeypatch):
    deploy,handoff,family,kwargs,targets,old_family=fixture(tmp_path,monkeypatch)
    handoff.prepare(family,**kwargs)
    import household_native_install as install
    original={path:path.read_bytes() for path in targets.values()}
    def guard():
        if targets['preparer_service'].read_bytes()!=original[targets['preparer_service']]:
            raise ValueError('late upgrade refusal')
    with pytest.raises(ValueError,match='late upgrade refusal'):install._install_files(kwargs['output'],guard=guard)
    assert all(path.read_bytes()==raw for path,raw in original.items())


@pytest.mark.parametrize('failure',[False,True])
def test_upgrade_activation_preserves_existing_preparer_schedule_and_enable_link(tmp_path,monkeypatch,failure):
    deploy,handoff,family,kwargs,targets,old_family=fixture(tmp_path,monkeypatch)
    handoff.prepare(family,**kwargs)
    import household_native_install as install
    root=targets['preparer_service'].parent
    parent=root/'timers.target.wants';parent.mkdir(mode=0o700)
    link=parent/install.PREPARER_TIMER;link.symlink_to(root/install.PREPARER_TIMER)
    identity=install._enable_link_identity(link)
    timers=(*install.TIMERS,install.PREPARER_TIMER);current={unit:'active' for unit in timers};calls=[]
    monkeypatch.setattr(install,'_timer_state',lambda unit:{'ActiveState':current[unit]})
    monkeypatch.setattr(install,'_services_inactive',lambda root:None)
    def systemctl(*args):
        calls.append(args)
        if args[0] in ('start','stop'):current[args[1]]='active' if args[0]=='start' else 'inactive'
        return ''
    monkeypatch.setattr(deploy,'_systemctl',systemctl)
    monkeypatch.setattr(install,'_enable_preparer',lambda *a,**kw:pytest.fail('existing timer must not be enabled again'))
    original={path:path.read_bytes() for path in targets.values()}
    def verify(family,guard):
        assert all(value=='inactive' for value in current.values())
        if failure:raise ValueError('new effective definition refused')
        return {'status':'native_effective_family_verified'}
    monkeypatch.setattr(install,'_verify_effective_family',verify)
    if failure:
        with pytest.raises(ValueError,match='new effective definition refused'):install._activate_handoff(kwargs['output'],guard=lambda:None)
        assert all(path.read_bytes()==raw for path,raw in original.items())
    else:
        result=install._activate_handoff(kwargs['output'],guard=lambda:None)
        assert result['new_preparer_timer_enabled'] is False
        assert result['existing_preparer_timer_preserved'] is True
    assert all(value=='active' for value in current.values())
    assert install._enable_link_identity(link)==identity
    assert ('stop',install.PREPARER_TIMER) in calls and ('start',install.PREPARER_TIMER) in calls
