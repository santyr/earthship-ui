"""Owned pauses must survive cancellation without restarting foreign state."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import pytest


def test_original_window_starvation_and_prepackage_drain():
    from datetime import datetime,timedelta,timezone
    from household_native_training import wait_for_handoff_window
    start=datetime(2026,10,25,0,51,1,tzinfo=timezone.utc);elapsed=[0]
    def clock():return start+timedelta(seconds=elapsed[0])
    def sleep(n):elapsed[0]+=n
    def pids():return ['0','7','0'] if clock().minute%5 in (1,2) else ['0']*3
    with pytest.raises(TimeoutError):
        wait_for_handoff_window(guard=lambda:None,read_pids=pids,clock=clock,monotonic=lambda:elapsed[0],sleep=sleep)
    from household_native_lifecycle import drain_score
    elapsed[0]=0
    drain_score(guard=lambda:None,read_pid=lambda:'7' if elapsed[0]<119 else '0',monotonic=lambda:elapsed[0],sleep=sleep)
    wait_for_handoff_window(guard=lambda:None,read_pids=lambda:['0']*3,clock=clock,monotonic=lambda:elapsed[0],sleep=sleep)
    assert elapsed[0]<=240+130


@pytest.mark.parametrize('signum',[signal.SIGTERM,signal.SIGINT])
def test_real_child_graceful_signal_runs_cleanup_and_ignores_second_signal(tmp_path,signum):
    script='''from household_native_lifecycle import cancellation_boundary
from pathlib import Path
import time,os,signal,sys
p=Path(sys.argv[1])
with cancellation_boundary():
 try:
  p.write_text('ready')
  while True: time.sleep(.01)
 finally:
  os.kill(os.getpid(),signal.SIGTERM)
  p.write_text('rolled_back')
'''
    path=tmp_path/'phase'
    child=subprocess.Popen([sys.executable,'-B','-c',script,str(path)])
    try:
        end=time.monotonic()+5
        while not path.exists() and child.poll() is None and time.monotonic()<end:time.sleep(.01)
        assert path.exists()
        child.send_signal(signum);child.wait(timeout=5)
        assert path.read_text()=='rolled_back'
    finally:
        if child.poll() is None:child.kill();child.wait()


def test_observable_timer_aba_and_enablement_change_refuse():
    from household_native_lifecycle import same_pause
    original={'ActiveState':'inactive','InactiveEnterTimestampMonotonic':'14','UnitFileState':'enabled'}
    assert same_pause(original,dict(original))
    assert not same_pause(original,dict(original,InactiveEnterTimestampMonotonic='16'))
    assert not same_pause(original,dict(original,UnitFileState='disabled'))


def test_pinned_runtime_qualification_uses_shared_collection_launcher(tmp_path,monkeypatch):
    import household_cycle_deploy as deploy
    from hashlib import sha256
    stage=tmp_path/'stage';stage.mkdir();(stage/'deployment.json').write_bytes(b'{}');pin=sha256(b'{}').hexdigest()
    monkeypatch.setattr(deploy,'verify_stage',lambda *a,**kw:{})
    monkeypatch.setattr(deploy,'_bytes',lambda *a,**kw:b'{}')
    import household_native_family as family
    interpreter={'path':'/retained/python3.12','sha256':'a'*64}
    monkeypatch.setattr(family,'_interpreter_reference',lambda ref:ref)
    commands=[]
    def call(command,**kwargs):
        commands.append(command)
        return ('{"status":"runtime_verified","deployment_sha256":"'+pin+'","automatic_actuation":false}').encode()
    monkeypatch.setattr(deploy.subprocess,'check_output',call)
    deploy._qualify(stage,deployment_sha256=pin,interpreter=interpreter)
    command=commands[0]
    assert '--collection' in command and command[command.index('--seconds')+1]=='45'
    assert '/retained/python3.12' in command and '--verify-runtime' in command


@pytest.mark.parametrize('position',[1,2,3,4,5])
@pytest.mark.parametrize('signum',[signal.SIGTERM,signal.SIGINT])
def test_actual_installer_signal_after_each_replacement_restores_old_family(tmp_path,position,signum):
    script='''import os,signal,sys
from pathlib import Path
import pytest
from test_household_native_install_composition import fixture
from household_native_lifecycle import cancellation_boundary
root=Path(sys.argv[1]);root.mkdir(mode=0o700)
mp=pytest.MonkeyPatch()
module,out,base,family,previous,calls,current=fixture(root,mp)
paths=[base/'thermal-provisional-forecast.service.d/zzzz-household-cycle.conf',base/'thermal-provisional-score.service.d/zzzz-household-score.conf']
original={p:p.read_bytes() for p in paths}
count=[0];replace=module.deploy._replace_owned;create=module._create
fired=[False]
def checkpoint():
 count[0]+=1
 if count[0]==int(sys.argv[2]) and not fired[0]:
  fired[0]=True;os.kill(os.getpid(),int(sys.argv[3]))
def wrapped_replace(*a,**kw):
 result=replace(*a,**kw);checkpoint();return result
def wrapped_create(*a,**kw):
 result=create(*a,**kw);checkpoint();return result
mp.setattr(module.deploy,'_replace_owned',wrapped_replace);mp.setattr(module,'_create',wrapped_create)
try:
 with cancellation_boundary():module._reload_handoff(out,guard=lambda:None)
except KeyboardInterrupt:pass
else:raise AssertionError('cancellation missed actual replacement')
assert all(p.read_bytes()==raw for p,raw in original.items())
assert not (base/'thermal-native-geometry-prepare.service').exists()
assert all(v=='active' for v in current.values())
print('coherent_rollback')
'''
    result=subprocess.run([sys.executable,'-B','-c',script,str(tmp_path/'files'),str(position),str(int(signum))],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert result.stdout.strip()=='coherent_rollback'


def manager_fixture(tmp_path,owner):
    from household_native_training import directory
    import household_native_lifecycle as life
    from household_native_handoff import FILES
    from hashlib import sha256
    root=directory(tmp_path/'manager');units=directory(root/'units');old=directory(root/'old'/'family');new=directory(root/'new'/'family')
    directory(root/'old'/'final');directory(units/'timers.target.wants')
    for parent in ('thermal-provisional-forecast.service.d','thermal-provisional-score.service.d','thermal-provisional-score.timer.d'):directory(units/parent)
    targets=['thermal-provisional-forecast.service.d/zzzz-household-cycle.conf','thermal-provisional-score.service.d/zzzz-household-score.conf',
        'thermal-provisional-score.timer.d/zzzz-household-native-timer.conf','thermal-native-geometry-prepare.service','thermal-native-geometry-prepare.timer']
    for i,(name,target) in enumerate(zip(FILES.values(),targets)):
        for path,raw in ((old/name,b'old-'+str(i).encode()),(new/name,b'new-'+str(i).encode()),(units/target,b'old-'+str(i).encode())):
            path.write_bytes(raw);path.chmod(0o600)
    for name in ('thermal-provisional-forecast.service','thermal-provisional-score.service',*life.TIMERS[:2]):
        (units/name).write_bytes(b'base');(units/name).chmod(0o600)
    for timer in life.TIMERS:(units/'timers.target.wants'/timer).symlink_to(units/timer)
    lock=root/'shared.lock';lock.write_bytes(b'');lock.chmod(0o600)
    life.save(root/'timers.json',{unit:{'ActiveState':'active','UnitFileState':'enabled','InactiveEnterTimestampMonotonic':'1'} for unit in life.TIMERS})
    reservation=directory(root/'reservation')
    life.save(reservation/'request.json',dict(nonce='reservation',owner=life.process_identity(owner.pid),run=str(root/'run'),
        previous={'stage':str(root/'old/final'),'deployment_sha256':'a'*64},root=str(units),shared_lock=str(lock),expires=time.monotonic()+60,
        phase='reserve',family=None,handoff_deadline=time.monotonic()+15,start_attempted=True,sources={str(Path(life.__file__)):life.fingerprint(Path(life.__file__))},source_sha256=sha256(Path(life.__file__).read_bytes()).hexdigest()))
    return root,targets


def wait_phase(root,phase):
    import household_native_lifecycle as life
    end=time.monotonic()+8
    while time.monotonic()<end:
        path=root/'reservation/status.json'
        if path.exists() and life.read(path)['phase']==phase:return life.read(path)
        time.sleep(.02)
    raise AssertionError('external owner missed phase '+phase)


@pytest.mark.parametrize('files',['old','new','mixed','absent'])
def test_hard_kill_external_recovery_accepts_only_complete_family(tmp_path,files):
    import household_native_lifecycle as life
    from household_native_handoff import FILES
    owner=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)'],start_new_session=True)
    manager=None
    try:
        root,targets=manager_fixture(tmp_path,owner)
        manager=subprocess.Popen([sys.executable,'-B','-m','test_native_activation_manager_fixture',str(root),'watch'],start_new_session=True)
        wait_phase(root,'reserved')
        request=life.read(root/'reservation/request.json');request.update(phase='handoff',family=str(root/'new/family'));life.save(root/'reservation/request.json',request)
        wait_phase(root,'quiesced')
        if files in ('new','mixed'):
            for i,(name,target) in enumerate(zip(FILES.values(),targets)):
                if files=='mixed' and i>0:break
                (root/'units'/target).write_bytes((root/'new/family'/name).read_bytes())
        if files=='absent':(root/'units'/targets[0]).unlink()
        os.killpg(owner.pid,signal.SIGKILL);owner.wait(timeout=5)
        # Independent manager survives the worker's entire killed process group.
        manager.wait(timeout=5)
        result=subprocess.run([sys.executable,'-B','-m','test_native_activation_manager_fixture',str(root),'recover'],capture_output=True,text=True,timeout=10)
        status=life.read(root/'reservation/status.json');timers=life.read(root/'timers.json')
        if files in ('old','new'):
            assert result.returncode==0,result.stderr
            assert status['phase']=='restored' and all(r['ActiveState']=='active' for r in timers.values())
        else:
            assert result.returncode!=0
            assert status['phase']=='reconciliation_required' and all(r['ActiveState']=='inactive' for r in timers.values())
    finally:
        for child in (owner,manager):
            if child is not None and child.poll() is None:child.kill();child.wait()


@pytest.mark.parametrize('change',['aba','link','source','owner_loss','file_aba'])
def test_recovery_preserves_operator_changes_and_owner_loss_as_reconciliation(tmp_path,change):
    import household_native_lifecycle as life
    owner=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)'],start_new_session=True)
    manager=None
    try:
        root,_=manager_fixture(tmp_path,owner)
        manager=subprocess.Popen([sys.executable,'-B','-m','test_native_activation_manager_fixture',str(root),'watch'],start_new_session=True)
        wait_phase(root,'reserved')
        # Kill only the external owner; manager's independent recovery attachment
        # is represented by a fresh recovery process, as with ExecStopPost.
        manager.kill();manager.wait(timeout=5)
        if change=='aba':
            rows=life.read(root/'timers.json');rows[life.SCORE]['InactiveEnterTimestampMonotonic']='999';life.save(root/'timers.json',rows)
        elif change=='link':
            path=root/'units/timers.target.wants'/life.SCORE;path.unlink();path.symlink_to(root/'foreign.timer')
        elif change=='file_aba':
            path=root/'units/thermal-provisional-forecast.service.d/zzzz-household-cycle.conf'
            raw=path.read_bytes();path.unlink();path.write_bytes(raw);path.chmod(0o600)
        elif change=='source':
            path=root/'reservation/status.json';record=life.read(path);record['request']['source_sha256']='0'*64;life.save(path,record)
        if change!='owner_loss':owner.kill();owner.wait(timeout=5)
        result=subprocess.run([sys.executable,'-B','-m','test_native_activation_manager_fixture',str(root),'recover'],capture_output=True,text=True,timeout=10)
        assert result.returncode!=0
        assert life.read(root/'reservation/status.json')['phase']=='reconciliation_required'
        assert life.read(root/'timers.json')[life.SCORE]['ActiveState']=='inactive'
    finally:
        for child in (owner,manager):
            if child is not None and child.poll() is None:child.kill();child.wait()


def test_existing_inactive_score_timer_is_not_started_on_recovery(tmp_path):
    import household_native_lifecycle as life
    owner=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)'],start_new_session=True)
    manager=None
    try:
        root,_=manager_fixture(tmp_path,owner)
        rows=life.read(root/'timers.json');rows[life.SCORE]['ActiveState']='inactive';life.save(root/'timers.json',rows)
        manager=subprocess.Popen([sys.executable,'-B','-m','test_native_activation_manager_fixture',str(root),'watch'],start_new_session=True)
        wait_phase(root,'reserved');owner.kill();owner.wait(timeout=5);manager.wait(timeout=5)
        result=subprocess.run([sys.executable,'-B','-m','test_native_activation_manager_fixture',str(root),'recover'],capture_output=True,text=True,timeout=10)
        assert result.returncode==0,result.stderr
        assert life.read(root/'timers.json')[life.SCORE]['ActiveState']=='inactive'
    finally:
        for child in (owner,manager):
            if child is not None and child.poll() is None:child.kill();child.wait()


def test_activation_child_timeout_is_reaped_before_caller_restores(tmp_path):
    import household_native_training as training
    from household_native_lifecycle import run_activation_child
    marker=tmp_path/'child-cleanup'
    code="from household_native_lifecycle import cancellation_boundary;from pathlib import Path;import time,sys\nwith cancellation_boundary():\n try:time.sleep(10)\n finally:Path(sys.argv[1]).write_text('graceful')"
    tmp_path.chmod(0o700)
    with training.daily_lock(tmp_path/'daily.lock') as lock:
        with pytest.raises(TimeoutError):run_activation_child([sys.executable,'-B','-c',code,str(marker)],environment=dict(os.environ),lock=lock,guard=lambda:None,seconds=.5)
    # At an exhausted original deadline a hard kill is allowed; either outcome
    # has been reaped before this call returns, never an orphaned live installer.
    assert not marker.exists() or marker.read_text()=='graceful'


def test_standalone_retry_uses_trusted_state_lock_and_inherited_child_keeps_exclusion(tmp_path,monkeypatch):
    import household_native_training as training
    import household_native_lifecycle as life
    tmp_path.chmod(0o700);run=tmp_path/'run';run.mkdir(mode=0o700)
    monkeypatch.delenv('EARTHSHIP_NATIVE_DAILY_LOCK_FD',raising=False)
    monkeypatch.setattr(life,'read',lambda path:{'state_directory':str(tmp_path)})
    with training.daily_lock(tmp_path/'daily.lock') as lock:
        with pytest.raises(BlockingIOError):
            with life.activation_lock(run):pass
        code="import os,sys;from pathlib import Path;import household_native_lifecycle as l;l.read=lambda path:{'state_directory':sys.argv[1]}\nwith l.activation_lock(Path(sys.argv[1])/'run'):print('held')"
        env=dict(os.environ,EARTHSHIP_NATIVE_DAILY_LOCK_FD=str(lock.fd))
        result=subprocess.run([sys.executable,'-B','-c',code,str(tmp_path)],env=env,pass_fds=(lock.fd,),capture_output=True,text=True,timeout=5)
        assert result.returncode==0,result.stderr
        assert result.stdout.strip()=='held'
        with pytest.raises(BlockingIOError):
            with training.daily_lock(tmp_path/'daily.lock'):pass
    with life.activation_lock(run):pass
    with pytest.raises(ValueError,match='trusted learner state'):
        with life.activation_lock(tmp_path/'foreign'/'run'):pass


def test_external_owner_start_is_charged_to_existing_shared_admission(monkeypatch,tmp_path):
    import household_native_lifecycle as life
    import household_job_pool as pool
    import household_job_launch as launch
    import household_cycle_deploy as deploy
    from household_job_budget import AdmissionDeferred
    from contextlib import contextmanager
    calls=[];available=[10*1024**3]
    @contextmanager
    def gate(path):
        calls.append('lock');yield lambda:calls.append('verified');calls.append('unlock')
    monkeypatch.setattr(launch,'admission_gate',gate)
    monkeypatch.setattr(pool,'available_memory',lambda:available[0])
    monkeypatch.setattr(pool,'check_host_pressure',lambda:None)
    monkeypatch.setattr(pool,'read_pool',lambda p:dict(pool_limit_bytes=6*1024**3,pool_used_bytes=0,jobs={}))
    monkeypatch.setattr(pool,'_counter',lambda p:0 if p.name=='memory.swap.max' else 256*1024**2)
    def systemctl(*args):
        if args[0]=='show':return f'/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/earthship.slice/earthship-work.slice'
        calls.append(args)
    monkeypatch.setattr(deploy,'_systemctl',systemctl)
    life.start_owner('private-owner.service',before_start=lambda:calls.append('dispatch'))
    assert calls==['lock','verified','dispatch',('start','private-owner.service'),'verified','unlock']
    calls.clear();available[0]=2*1024**3
    with pytest.raises(AdmissionDeferred):life.start_owner('private-owner.service',before_start=lambda:calls.append('dispatch'))
    assert 'dispatch' not in calls
    assert not any(isinstance(c,tuple) and c[0]=='start' for c in calls)


def test_real_child_cleanup_is_not_interrupted_by_parent_signal(tmp_path):
    script='''from pathlib import Path
import os,sys,signal,time
from household_native_training import daily_lock
from household_native_lifecycle import run_activation_child,cancellation_boundary
root=Path(sys.argv[1]);root.mkdir(mode=0o700)
child="from pathlib import Path;import os,sys,signal,time;signal.signal(signal.SIGTERM,lambda *args:None);Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(20)"
def guard():
 if (root/'pid').exists():
  os.kill(os.getpid(),signal.SIGTERM)
with daily_lock(root/'daily.lock') as lock:
 try:
  with cancellation_boundary():
   run_activation_child([sys.executable,'-B','-c',child,str(root/'pid')],environment=dict(os.environ),lock=lock,guard=guard,seconds=.8)
 except KeyboardInterrupt:pass
pid=int((root/'pid').read_text())
assert not Path('/proc',str(pid)).exists()
print('reaped')
'''
    result=subprocess.run([sys.executable,'-B','-c',script,str(tmp_path/'root')],capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='reaped'


def test_external_recovery_rejects_changed_imported_source_helper(tmp_path):
    import household_native_lifecycle as life
    from hashlib import sha256
    helper=tmp_path/'helper.py';helper.write_bytes(b'old helper');helper.chmod(0o600)
    data={'sources':{str(helper):life.fingerprint(helper)}}
    life.verify_sources(data)
    helper.write_bytes(b'new helper')
    with pytest.raises(ValueError,match='source closure'):life.verify_sources(data)


def reservation_constructor_fixture(tmp_path,monkeypatch):
    import household_native_lifecycle as life
    import household_native_training as training
    import household_cycle_deploy as deploy
    state=training.directory(tmp_path/'state');stage=training.directory(tmp_path/'old/final')
    config=tmp_path/'config.json';training.save(config,{'shared_lock':str(tmp_path/'shared.lock')});training.save(stage/'cycle.json',{'forecast_config':str(config)})
    previous={'stage':str(stage),'deployment_sha256':'a'*64}
    monkeypatch.setattr(life.subprocess,'check_output',lambda *a,**kw:b'')
    monkeypatch.setattr(training,'effective_selection',lambda:previous)
    monkeypatch.setattr(deploy,'verify_stage',lambda *a,**kw:{'service_file':str(tmp_path/'units/thermal-provisional-forecast.service')})
    monkeypatch.setattr(life,'source_snapshot',lambda repo:{str(Path(life.__file__)):life.fingerprint(Path(life.__file__))})
    monkeypatch.setattr(deploy,'_systemctl',lambda *a:'0')
    def started(unit,**kwargs):
        if 'before_start' in kwargs:kwargs['before_start']()
        nonce=unit.split('@')[1].removesuffix('.service')
        life.save(state/'activation-reservations'/nonce/'status.json',{'phase':'reserved','manager':life.process_identity(os.getpid())})
    return life,deploy,state,previous,started


@pytest.mark.parametrize('preflight',['stage','settings','source'])
def test_constructor_preflight_failure_creates_no_reservation_blocker(tmp_path,monkeypatch,preflight):
    life,deploy,state,previous,started=reservation_constructor_fixture(tmp_path,monkeypatch)
    def refuse(*a,**kw):raise ValueError('private preflight refusal')
    if preflight=='stage':monkeypatch.setattr(deploy,'verify_stage',refuse)
    elif preflight=='source':monkeypatch.setattr(life,'source_snapshot',refuse)
    else:(tmp_path/'config.json').unlink()
    monkeypatch.setattr(life,'start_owner',lambda *a,**kw:pytest.fail('preflight tried to start owner'))
    with pytest.raises((ValueError,OSError)):life.Reservation(state,tmp_path/'run',previous,guard=lambda:None)
    assert not (state/'activation-reservations').exists()


def test_prestart_admission_refusal_does_not_poison_later_constructor(tmp_path,monkeypatch):
    from household_job_budget import AdmissionDeferred
    life,deploy,state,previous,started=reservation_constructor_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(life,'start_owner',lambda *a,**kw:(_ for _ in ()).throw(AdmissionDeferred('headroom')))
    with pytest.raises(AdmissionDeferred):life.Reservation(state,tmp_path/'run',previous,guard=lambda:None)
    monkeypatch.setattr(life,'start_owner',started)
    reservation=life.Reservation(state,tmp_path/'run',previous,guard=lambda:None)
    assert life.read(reservation.status)['phase']=='reserved'


def test_ambiguous_systemctl_start_remains_blocking_without_creating_more_orphans(tmp_path,monkeypatch):
    life,deploy,state,previous,started=reservation_constructor_fixture(tmp_path,monkeypatch)
    def ambiguous(unit,**kwargs):
        if 'before_start' in kwargs:kwargs['before_start']()
        raise TimeoutError('start response lost')
    monkeypatch.setattr(life,'start_owner',ambiguous)
    with pytest.raises(TimeoutError):life.Reservation(state,tmp_path/'run',previous,guard=lambda:None)
    paths=list((state/'activation-reservations').iterdir());assert len(paths)==1
    assert not (paths[0]/'status.json').exists()
    monkeypatch.setattr(life,'start_owner',started)
    with pytest.raises(ValueError,match='reconciliation'):life.Reservation(state,tmp_path/'run',previous,guard=lambda:None)
    assert list((state/'activation-reservations').iterdir())==paths


def test_never_armed_marker_cannot_clear_changed_request_or_start_a_pause(tmp_path,monkeypatch):
    from household_job_budget import AdmissionDeferred
    life,deploy,state,previous,started=reservation_constructor_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(life,'start_owner',lambda *a,**kw:(_ for _ in ()).throw(AdmissionDeferred('headroom')))
    with pytest.raises(AdmissionDeferred):life.Reservation(state,tmp_path/'run',previous,guard=lambda:None)
    path=next((state/'activation-reservations').iterdir())
    assert life.read(path/'status.json')['phase']=='never_armed'
    assert life._finished_attempt(path)
    with pytest.raises(ValueError,match='dispatched original'):life.watch(path)
    request=life.read(path/'request.json');request['start_attempted']=True;life.save(path/'request.json',request)
    monkeypatch.setattr(life,'start_owner',started)
    with pytest.raises(ValueError,match='reconciliation'):life.Reservation(state,tmp_path/'run',previous,guard=lambda:None)
    assert list((state/'activation-reservations').iterdir())==[path]


@pytest.mark.parametrize('change',['release','owner_loss','expired','ack_expired','timer_edit'])
def test_long_family_verification_cannot_act_on_stale_handoff(tmp_path,change):
    import household_native_lifecycle as life
    owner=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)'])
    manager=None
    script='''from pathlib import Path
import sys,time
import household_native_lifecycle as life
import household_native_family as family
from test_native_activation_manager_fixture import configure
root=Path(sys.argv[1]);change=sys.argv[2];configure(root)
original=family.verify
def slow(family_path,guard):
 result=original(family_path,guard=guard)
 if Path(family_path)==root/'new/family':
  # Verification crossed the child's acknowledgement deadline; the child has
  # cancelled or its owner/deadline/observed timer state no longer permits pause.
  request=life.read(root/'reservation/request.json')
  if change=='release':request['phase']='release';life.save(root/'reservation/request.json',request)
  elif change=='owner_loss':life.process_identity=lambda pid:None
  elif change=='expired':life.time.monotonic=lambda:request['expires']+1
  elif change=='ack_expired':life.time.monotonic=lambda:request['handoff_deadline']+.1
  else:
   timers=life.read(root/'timers.json');timers[life.TIMERS[0]]['InactiveEnterTimestampMonotonic']='changed';life.save(root/'timers.json',timers)
 return result
family.verify=slow
try:life.watch(root/'reservation')
except ValueError:pass
'''
    try:
        root,_=manager_fixture(tmp_path,owner)
        manager=subprocess.Popen([sys.executable,'-B','-c',script,str(root),change])
        wait_phase(root,'reserved')
        request=life.read(root/'reservation/request.json');request.update(phase='handoff',family=str(root/'new/family'));life.save(root/'reservation/request.json',request)
        manager.wait(timeout=5)
        status=life.read(root/'reservation/status.json')
        assert set(status['paused'])=={life.SCORE}
        assert status['new_family'] is None
        assert life.read(root/'timers.json')[life.TIMERS[2]]['ActiveState']=='active'
    finally:
        for child in (owner,manager):
            if child is not None and child.poll() is None:child.kill();child.wait()


@pytest.mark.parametrize('change',['timer','target','lock'])
def test_recovery_rechecks_late_mutation_after_admitted_verification(tmp_path,change):
    import household_native_lifecycle as life
    owner=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)'])
    manager=None
    script='''from pathlib import Path
import sys
import household_native_lifecycle as life
import household_native_install as install
from test_native_activation_manager_fixture import configure
root=Path(sys.argv[1]);change=sys.argv[2];configure(root)
original=install._verify_effective_family
def verified(path,guard):
 result=original(path,guard=guard)
 if change=='timer':
  rows=life.read(root/'timers.json');rows[life.TIMERS[-1]]['InactiveEnterTimestampMonotonic']='foreign';life.save(root/'timers.json',rows)
 elif change=='target':
  status=life.read(root/'reservation/status.json');Path(next(iter(status['old_targets']))).write_bytes(b'foreign')
 else:
  path=root/'shared.lock';path.unlink();path.write_bytes(b'');path.chmod(0o600)
 return result
install._verify_effective_family=verified
life.recover(root/'reservation')
'''
    try:
        root,_=manager_fixture(tmp_path,owner)
        manager=subprocess.Popen([sys.executable,'-B','-m','test_native_activation_manager_fixture',str(root),'watch'])
        wait_phase(root,'reserved');request=life.read(root/'reservation/request.json')
        request.update(phase='handoff',family=str(root/'new/family'));life.save(root/'reservation/request.json',request)
        wait_phase(root,'quiesced');request['phase']='release';life.save(root/'reservation/request.json',request);manager.wait(timeout=5)
        result=subprocess.run([sys.executable,'-B','-c',script,str(root),change],capture_output=True,text=True,timeout=10)
        assert result.returncode!=0
        assert life.read(root/'reservation/status.json')['phase']=='reconciliation_required'
        assert all(row['ActiveState']=='inactive' for row in life.read(root/'timers.json').values())
    finally:
        for child in (owner,manager):
            if child is not None and child.poll() is None:child.kill();child.wait()
