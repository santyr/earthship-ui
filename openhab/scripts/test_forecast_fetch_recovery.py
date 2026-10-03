from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
from urllib.error import HTTPError,URLError

import pytest
import forecast_fetch_recovery as m

NOW=datetime(2026,10,3,13,10,tzinfo=timezone.utc)
IDENTITY='a'*32


@pytest.mark.parametrize('value,enabled',[(None,False),('1',True),('0',False),('true',False),('1 ',False)])
def test_release_requires_exact_dedicated_service_setting(value,enabled):
    environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    environment.pop('EARTHSHIP_FORECAST_FETCH_RECOVERY_ENABLE',None)
    if value is not None:environment['EARTHSHIP_FORECAST_FETCH_RECOVERY_ENABLE']=value
    script='import forecast_fetch_recovery as m; print(m.RELEASE_READY)'
    result=subprocess.run([sys.executable,'-c',script],cwd=Path(m.__file__).parent,
        env=environment,capture_output=True,text=True,check=True,timeout=10)
    assert result.stdout.strip()==str(enabled)


def fixture():
    state={'predictions':{},'kalman':{'hi':{'b':2}},m.KEY:{'version':1,'phase':'weather_fetch',
        'day':'2026-10-03','timezone':'America/Denver','failed_at':(NOW-timedelta(minutes=15)).isoformat(),
        'invocation_id':IDENTITY,'failure_count':1,'retryable':True}}
    return state,{'LoadState':'loaded','ActiveState':'failed','InvocationID':IDENTITY}


def test_only_current_failed_fetch_invocation_is_eligible():
    state,service=fixture();before=deepcopy(state)
    assert m.eligible(state,NOW,service) is True and state==before


@pytest.mark.parametrize('fault',['early','late','yesterday','future','old','naive','bool_version',
    'bool_count','budget','unknown_field','unknown_phase','wrong_zone','wrong_date','no_failure',
    'bad_invocation','new_invocation','active','inactive','missing_unit','already_predicted','bad_state'])
def test_no_other_failure_or_time_window_authorizes_recovery(fault):
    state,service=fixture();now=NOW;marker=state[m.KEY]
    if fault=='early':now=NOW.replace(hour=12,minute=39)
    elif fault=='late':now=NOW.replace(hour=15,minute=0)
    elif fault=='yesterday':marker['failed_at']=(NOW-timedelta(days=1)).isoformat()
    elif fault=='future':marker['failed_at']=(NOW+timedelta(seconds=1)).isoformat()
    elif fault=='old':marker['failed_at']=(NOW-timedelta(seconds=1801)).isoformat()
    elif fault=='naive':marker['failed_at']='2026-10-03T06:55:00'
    elif fault=='bool_version':marker['version']=True
    elif fault=='bool_count':marker['failure_count']=True
    elif fault=='budget':marker['failure_count']=m.MAX_FAILURES
    elif fault=='unknown_field':marker['extra']='unreviewed'
    elif fault=='unknown_phase':marker['phase']='publication'
    elif fault=='wrong_zone':marker['timezone']='UTC'
    elif fault=='wrong_date':marker['day']='2026-10-02'
    elif fault=='no_failure':marker['retryable']=False
    elif fault=='bad_invocation':marker['invocation_id']='not-systemd'
    elif fault=='new_invocation':service['InvocationID']='b'*32
    elif fault=='active':service['ActiveState']='active'
    elif fault=='inactive':service['ActiveState']='inactive'
    elif fault=='missing_unit':service['LoadState']='not-found'
    elif fault=='already_predicted':state['predictions']['2026-10-03']=None
    else:state['predictions']=None
    assert m.eligible(state,now,service) is False


@pytest.mark.parametrize('error,allowed',[(URLError(socket.gaierror(-3,'private')),True),
    (URLError(TimeoutError('private')),True),(TimeoutError('private'),True),
    (HTTPError('private-url',503,'private',{},None),True),
    (HTTPError('private-url',401,'private',{},None),False),
    (URLError('unknown network problem'),False),(ValueError('private'),False)])
def test_failure_metadata_preserves_learning_and_rethrows_without_recording_secrets(error,allowed):
    state,service=fixture();saved=[]
    def fail():raise error
    with pytest.raises(type(error)) as raised:
        m.fetch_for_issue(fail,state,lambda value:saved.append(deepcopy(value)),
            now=lambda:NOW,invocation_id=IDENTITY,timezone_name='America/Denver')
    assert raised.value is error and len(saved)==1
    assert state['kalman']=={'hi':{'b':2}} and state['predictions']=={}
    assert state[m.KEY]['retryable'] is allowed and state[m.KEY]['failure_count']==2
    assert 'private' not in json.dumps(state)


def test_success_revokes_cookie_before_later_stages_without_extra_normal_writes():
    state,_=fixture();saved=[]
    result=object()
    assert m.fetch_for_issue(lambda:result,state,lambda value:saved.append(deepcopy(value)),
        now=lambda:NOW,invocation_id=IDENTITY,timezone_name=m.ZONE.key) is result
    assert m.KEY not in state and len(saved)==1
    m.fetch_for_issue(lambda:result,state,lambda _:pytest.fail('unnecessary state write'),
        now=lambda:NOW,invocation_id=IDENTITY,timezone_name=m.ZONE.key)


def test_run_interface_refuses_before_state_or_systemd_reads(monkeypatch):
    monkeypatch.setattr(m,'run',lambda *_:pytest.fail('systemd request'))
    monkeypatch.setattr(m,'read_state',lambda:pytest.fail('state read'))
    with pytest.raises(ValueError):m.command(['--run'])
    with pytest.raises(ValueError):m.command(['--target','other'])


@pytest.mark.parametrize('fault',[None,'changed_invocation','changed_state','new_prediction'])
def test_same_original_unit_only_and_failed_context_rechecked(monkeypatch,fault):
    state,service=fixture();calls=[]
    monkeypatch.setattr(m,'RELEASE_READY',True)
    reads=[]
    def read():
        reads.append(True)
        if fault=='new_prediction' and len(reads)>1:
            state['predictions']['2026-10-03']={}
        return state
    monkeypatch.setattr(m,'read_state',read)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return cls.fromtimestamp(NOW.timestamp(),tz)
    monkeypatch.setattr(m,'datetime',Clock)
    def run(command):
        calls.append(command)
        if 'LoadState' in command:return 'InvocationID='+IDENTITY+'\nLoadState=loaded\nActiveState=failed\n'
        if 'show' in command:
            return ('InvocationID='+('b'*32 if fault=='changed_invocation' else IDENTITY)+
                '\nActiveState='+('active' if fault=='changed_state' else 'failed')+'\n')
        assert command==['systemctl','--user','start','--no-block',m.UNIT]
        return ''
    monkeypatch.setattr(m,'run',run)
    if fault:
        with pytest.raises(ValueError):m.command(['--run'])
        assert len(calls)==2
    else:
        assert m.command(['--run'])['start_requested'] is True
        assert len(calls)==3


def test_owned_state_read_never_repairs_corruption_or_follows_symlink(tmp_path,monkeypatch):
    tmp_path.chmod(0o700);path=tmp_path/'state.json';path.write_text('{broken')
    monkeypatch.setattr(m,'STATE',path)
    with pytest.raises(ValueError):m.read_state()
    assert path.read_text()=='{broken' and len(list(tmp_path.iterdir()))==1
    path.unlink();path.symlink_to(tmp_path/'missing')
    with pytest.raises(OSError):m.read_state()


@pytest.mark.parametrize('fault',[None,'other_primary_member','other_explicit_member',
    'foreign_group','acl','world_write'])
def test_legacy_group_write_only_when_exclusive_to_owner(tmp_path,monkeypatch,fault):
    path=tmp_path/'state.json';path.write_text('{"predictions":{}}')
    tmp_path.chmod(0o775);path.chmod(0o664)
    uid=os.getuid();gid=path.stat().st_gid
    owner=SimpleNamespace(pw_name='owner',pw_gid=gid)
    monkeypatch.setattr(m.pwd,'getpwuid',lambda _:owner)
    monkeypatch.setattr(m.pwd,'getpwall',lambda:[owner]+(
        [SimpleNamespace(pw_name='other',pw_gid=gid)] if fault=='other_primary_member' else []))
    monkeypatch.setattr(m.grp,'getgrgid',lambda _:SimpleNamespace(
        gr_mem=['other'] if fault=='other_explicit_member' else []))
    monkeypatch.setattr(m.os,'listxattr',lambda *a,**k:
        ['system.posix_acl_access'] if fault=='acl' else [])
    monkeypatch.setattr(m,'STATE',path)
    if fault=='foreign_group':owner.pw_gid=gid+1
    if fault=='world_write':path.chmod(0o666)
    if fault:
        with pytest.raises(ValueError):m.read_state()
    else:assert m.read_state()=={'predictions':{}}
    assert tmp_path.stat().st_mode & 0o777 == 0o775
    assert path.stat().st_mode & 0o777 == (0o666 if fault=='world_write' else 0o664)
