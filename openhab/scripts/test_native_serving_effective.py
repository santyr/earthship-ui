"""Effective v3 unit definitions must preserve pins, limits and all score slots."""
from pathlib import Path
import pytest
from test_native_serving_handoff import fixture as handoff_fixture


def fixture(tmp_path,monkeypatch):
    deploy,handoff,args,previous,family,output,pin,old_forecast,old_score=handoff_fixture(tmp_path,monkeypatch)
    import household_native_install as install
    root=args['service_file'].parent;states={}
    for name,source,timeout,dropins in (
        ('thermal-provisional-forecast.service','forecast.conf','1min 30s',['zzzz-household-cycle.conf']),
        ('thermal-provisional-score.service','score.conf','1min',['zzzz-household-score.conf']),
        ('thermal-native-geometry-prepare.service','thermal-native-geometry-prepare.service','1min 30s',[])):
        command=[line[10:] for line in (family/source).read_text().splitlines() if line.startswith('ExecStart=') and line!='ExecStart='][0]
        states[name]=dict(deploy.EFFECTIVE_LIMITS,LoadState='loaded',ActiveState='inactive',MainPID='0',ExecStart=command,
            FragmentPath=str(root/name),DropInPaths=' '.join(str(root/(name+'.d')/v) for v in dropins),TimeoutStartUSec=timeout)
    for name,calendars,dropins in (
        ('thermal-provisional-forecast.timer',['*-*-* *:04/5:45 UTC'],[]),
        ('thermal-provisional-score.timer',['*-*-* *:'+v+'/5:10 UTC' for v in ('00','01','02','03')],['zzzz-household-native-timer.conf']),
        ('thermal-native-geometry-prepare.timer',['*-*-* *:03/5:05 UTC'],[])):
        states[name]=dict(LoadState='loaded',ActiveState='inactive',TimersCalendar=calendars,FragmentPath=str(root/name),
            DropInPaths=' '.join(str(root/(name+'.d')/v) for v in dropins),Unit=name.removesuffix('.timer')+'.service',
            AccuracyUSec='1s',RandomizedDelayUSec='0',Persistent='no')
    monkeypatch.setattr(install,'_effective_state',lambda unit:states[unit])
    return install,family,pin,states


def test_effective_receipt_family_accepts_exact_pins_caps_and_both_score_selections(tmp_path,monkeypatch):
    install,family,pin,states=fixture(tmp_path,monkeypatch)
    result=install._verify_effective_family(family,guard=lambda:None)
    assert result['deployment_sha256']==pin and result['services_inactive'] is True and result['timers_inactive'] is True


@pytest.mark.parametrize('damage',['forecast_pin','score_pin','preparer_pin','legacy_slots','memory','active_timer'])
def test_effective_receipt_family_refuses_changed_selection_or_limits(tmp_path,monkeypatch,damage):
    install,family,pin,states=fixture(tmp_path,monkeypatch)
    if damage.endswith('_pin'):
        unit={'forecast_pin':'thermal-provisional-forecast.service','score_pin':'thermal-provisional-score.service','preparer_pin':'thermal-native-geometry-prepare.service'}[damage]
        states[unit]['ExecStart']=states[unit]['ExecStart'].replace(pin,'f'*64)
    elif damage=='legacy_slots':states['thermal-provisional-score.timer']['TimersCalendar']=['*-*-* *:00/5:10 UTC','*-*-* *:02/5:10 UTC']
    elif damage=='memory':states['thermal-provisional-score.service']['MemoryMax']='536870912'
    else:states['thermal-provisional-score.timer']['ActiveState']='active'
    with pytest.raises(ValueError):install._verify_effective_family(family,guard=lambda:None)


@pytest.mark.parametrize('unit', ['thermal-provisional-score.service', 'thermal-native-geometry-prepare.service'])
def test_other_roles_do_not_inherit_forecast_cpu_budget(tmp_path, monkeypatch, unit):
    install, family, pin, states = fixture(tmp_path, monkeypatch)
    states[unit]['CPUQuotaPerSecUSec'] = '1s'
    with pytest.raises(ValueError, match='role CPU budget'):
        install._verify_effective_family(family, guard=lambda: None)


def test_shared_effective_family_requires_pool_readback(tmp_path,monkeypatch):
    import household_native_family as family_api
    import household_native_install as install
    monkeypatch.setattr(family_api,'_shared_job_pool',lambda stage:True)
    calls=[]
    monkeypatch.setattr(install,'_verify_shared_pool',lambda:calls.append('pool'),raising=False)
    _,family,pin,states=fixture(tmp_path,monkeypatch)
    assert install._verify_effective_family(family,guard=lambda:None)['deployment_sha256']==pin
    assert calls==['pool']
    def refused():raise ValueError('shared pool unavailable')
    monkeypatch.setattr(install,'_verify_shared_pool',refused)
    with pytest.raises(ValueError,match='pool unavailable'):
        install._verify_effective_family(family,guard=lambda:None)
