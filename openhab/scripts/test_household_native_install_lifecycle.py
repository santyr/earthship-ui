"""Timer lifecycle and effective-unit checks without live systemd mutations."""
from pathlib import Path
import pytest
import household_native_install as api
import household_cycle_deploy as deploy

TIMERS=('thermal-provisional-forecast.timer','thermal-provisional-score.timer')


def lifecycle(monkeypatch,states=('active','active')):
    calls=[];current=dict(zip(TIMERS,states))
    monkeypatch.setattr(api,'_timer_state',lambda unit:{'ActiveState':current[unit]})
    monkeypatch.setattr(api,'_services_inactive',lambda root:calls.append('inactive_checked'))
    def systemctl(*args):
        calls.append(args)
        if args[0] in ('start','stop'):current[args[1]]='active' if args[0]=='start' else 'inactive'
        return ''
    monkeypatch.setattr(deploy,'_systemctl',systemctl)
    return calls,current


def test_quiesces_only_owned_timers_and_restores_their_original_states(monkeypatch):
    calls,current=lifecycle(monkeypatch,('active','inactive'))
    with api._quiesce_timers(Path('/owned'),guard=lambda:None):
        assert current==dict(zip(TIMERS,('inactive','inactive')))
        calls.append('transaction')
    assert current==dict(zip(TIMERS,('active','inactive')))
    assert ('stop',TIMERS[0]) in calls and ('start',TIMERS[0]) in calls
    assert not any(isinstance(c,tuple) and c[-1]==TIMERS[1] for c in calls)
    assert not any(isinstance(c,tuple) and c[0]=='restart' for c in calls)


def test_failure_restores_both_existing_timer_schedules(monkeypatch):
    calls,current=lifecycle(monkeypatch)
    with pytest.raises(ValueError,match='transaction failed'):
        with api._quiesce_timers(Path('/owned'),guard=lambda:None):raise ValueError('transaction failed')
    assert all(current[t]=='active' for t in TIMERS)


def test_active_worker_refuses_before_any_timer_change(monkeypatch):
    calls,current=lifecycle(monkeypatch)
    def refuse(root):raise ValueError('worker active')
    monkeypatch.setattr(api,'_services_inactive',refuse)
    with pytest.raises(ValueError):
        with api._quiesce_timers(Path('/owned'),guard=lambda:None):pytest.fail('active worker admitted')
    assert calls==[]


def test_partial_stop_failure_restores_already_stopped_timer(monkeypatch):
    calls,current=lifecycle(monkeypatch);original=deploy._systemctl
    def fail(*args):
        if args==('stop',TIMERS[1]):raise ValueError('stop failed')
        return original(*args)
    monkeypatch.setattr(deploy,'_systemctl',fail)
    with pytest.raises(ValueError):
        with api._quiesce_timers(Path('/owned'),guard=lambda:None):pytest.fail('stop failure ignored')
    assert current[TIMERS[0]]=='active'


def test_unknown_timer_state_refuses_without_mutation(monkeypatch):
    calls,current=lifecycle(monkeypatch,('activating','active'))
    with pytest.raises(ValueError):
        with api._quiesce_timers(Path('/owned'),guard=lambda:None):pytest.fail('unknown state admitted')
    assert not any(isinstance(c,tuple) for c in calls)


def test_concurrent_timer_start_refuses_and_preserves_new_state(monkeypatch):
    calls,current=lifecycle(monkeypatch,('active','inactive'))
    def guard():
        if calls and calls[-1]==('stop',TIMERS[0]):current[TIMERS[1]]='active'
    with pytest.raises(ValueError):
        with api._quiesce_timers(Path('/owned'),guard=guard):pytest.fail('timer race admitted')
    assert current[TIMERS[1]]=='active'


def effective_fixture(tmp_path,monkeypatch):
    from test_household_native_install_files import setup
    module,out,base,family,previous=setup(tmp_path,monkeypatch);states={}
    for name,source,timeout,dropins in (
        ('thermal-provisional-forecast.service','forecast.conf','1min 30s',['zzzz-household-cycle.conf']),
        ('thermal-provisional-score.service','score.conf','1min',['zzzz-household-score.conf']),
        ('thermal-native-geometry-prepare.service','thermal-native-geometry-prepare.service','1min 30s',[])):
        raw=(family/source).read_text();command=[r[10:] for r in raw.splitlines() if r.startswith('ExecStart=') and r!='ExecStart='][0]
        states[name]=dict(deploy.EFFECTIVE_LIMITS,LoadState='loaded',ActiveState='inactive',MainPID='0',ExecStart=command,
            FragmentPath=str(base/name),DropInPaths=' '.join(str(base/(name+'.d')/f) for f in dropins),TimeoutStartUSec=timeout)
    for name,calendars,dropins in (
        ('thermal-provisional-forecast.timer',['*-*-* *:04/5:45 UTC'],[]),
        ('thermal-provisional-score.timer',['*-*-* *:01/5:00 UTC','*-*-* *:02/5:00 UTC'],['zzzz-household-native-timer.conf']),
        ('thermal-native-geometry-prepare.timer',['*-*-* *:03/5:05 UTC'],[])):
        states[name]=dict(LoadState='loaded',ActiveState='inactive',TimersCalendar=calendars,FragmentPath=str(base/name),
            DropInPaths=' '.join(str(base/(name+'.d')/f) for f in dropins),Unit=name.removesuffix('.timer')+'.service',
            AccuracyUSec='1s',RandomizedDelayUSec='0',Persistent='no')
    monkeypatch.setattr(module,'_effective_state',lambda unit:states[unit])
    return module,family,states


def test_effective_family_verifies_all_service_and_timer_definitions(tmp_path,monkeypatch):
    module,family,states=effective_fixture(tmp_path,monkeypatch)
    result=module._verify_effective_family(family,guard=lambda:None)
    assert result['status']=='native_effective_family_verified' and result['timers_inactive'] is True


@pytest.mark.parametrize('damage',['command','memory','timeout','active_worker','fragment','dropin','calendar','duplicate_calendar','timer_unit','accuracy','persistent','active_timer'])
def test_effective_family_refuses_unsafe_or_incoherent_definitions(tmp_path,monkeypatch,damage):
    module,family,states=effective_fixture(tmp_path,monkeypatch)
    service=states['thermal-provisional-score.service'];timer=states['thermal-provisional-score.timer']
    if damage=='command':service['ExecStart']='unowned command'
    elif damage=='memory':service['MemoryMax']='2147483648'
    elif damage=='timeout':service['TimeoutStartUSec']='5min'
    elif damage=='active_worker':service.update(ActiveState='activating',MainPID='42')
    elif damage=='fragment':service['FragmentPath']='/unowned.service'
    elif damage=='dropin':service['DropInPaths']+=' /unknown.conf'
    elif damage=='calendar':timer['TimersCalendar']=['*-*-* *:03/5:10 UTC']
    elif damage=='duplicate_calendar':timer['TimersCalendar'].append(timer['TimersCalendar'][0])
    elif damage=='timer_unit':timer['Unit']='unowned.service'
    elif damage=='accuracy':timer['AccuracyUSec']='1min'
    elif damage=='persistent':timer['Persistent']='yes'
    else:timer['ActiveState']='active'
    with pytest.raises(ValueError):module._verify_effective_family(family,guard=lambda:None)
