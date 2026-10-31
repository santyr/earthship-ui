"""Hermetic protocol regressions; not PID1/Docker lifecycle qualification."""
import array
import fcntl
import json
import os
from pathlib import Path
import socket
import pytest
from services.lorawan.tests import qualification_guard as guard


def lock(tmp_path):
    path=tmp_path/'admission.lock';fd=os.open(path,os.O_RDWR|os.O_CREAT,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    return path,fd


def test_handoff_keeps_original_open_file_description(tmp_path):
    path,fd=lock(tmp_path);left,right=socket.socketpair()
    try:
        guard.send_descriptor(left,fd,{'nonce':'a'*32})
        body,received=guard.receive_descriptor(right,uid=os.getuid(),pid=os.getpid())
        assert body=={'nonce':'a'*32}
        guard.verify_lock(path,received,uid=os.getuid(),identity=(path.stat().st_dev,path.stat().st_ino))
        os.close(fd);fd=None
        other=os.open(path,os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
            os.close(received)
            fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:os.close(other)
    finally:
        if fd is not None:os.close(fd)
        left.close();right.close()


def test_second_descriptor_is_not_an_admission_handoff(tmp_path):
    path,fd=lock(tmp_path);second=os.open(path,os.O_RDWR)
    try:
        with pytest.raises(guard.Refused):guard.verify_lock(path,second,uid=os.getuid(),identity=(path.stat().st_dev,path.stat().st_ino))
    finally:os.close(fd);os.close(second)


@pytest.mark.parametrize('change',['inode','mode','owner','peer','no_fd','two_fds'])
def test_bad_handoff_cannot_authorize_start(tmp_path,change):
    path,fd=lock(tmp_path);left,right=socket.socketpair()
    try:
        if change in ('peer','no_fd','two_fds'):
            anc=[] if change=='no_fd' else [(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]*(2 if change=='two_fds' else 1)))]
            left.sendmsg([b'{"nonce":"a"}'],anc)
            with pytest.raises(guard.Refused):guard.receive_descriptor(right,uid=os.getuid(),pid=os.getpid()+1 if change=='peer' else os.getpid())
        else:
            original=(path.stat().st_dev,path.stat().st_ino)
            if change=='inode':path.unlink();path.write_text('replacement');path.chmod(0o600)
            if change=='mode':path.chmod(0o644)
            with pytest.raises(guard.Refused):guard.verify_lock(path,fd,uid=os.getuid()+1 if change=='owner' else os.getuid(),identity=original)
    finally:os.close(fd);left.close();right.close()


class Docker:
    def __init__(self):self.calls=[];self.fail=False;self.ids={name:f'{i:064x}' for i,name in enumerate(guard.SERVICES,1)}
    def validate(self,ids,*,running=False,cleanup=False):
        assert ids==self.ids
        if self.fail:raise guard.Refused('identity changed')
    def action(self,action,identity):
        self.calls.append((action,identity))
    def absent(self,ids):return True


def engine(tmp_path):
    docker=Docker();events=[];receipt=tmp_path/'receipt.json'
    g=guard.GuardianState(receipt,manifest_digest='a'*64,docker=docker,quiesce=lambda:events.append('quiesce'),release=lambda:events.append('release'))
    g.register(docker.ids)
    return g,docker,events,receipt


def test_only_closed_services_and_actions_can_be_executed(tmp_path):
    g,docker,events,_=engine(tmp_path)
    for action,service in [('start','production'),('exec','mqtt'),('delete','postgres'),('restart','simulator')]:
        with pytest.raises(guard.Refused):g.action(action,service)
    assert docker.calls==[] and events==[]
    g.action('start','mqtt')
    assert docker.calls==[('start',docker.ids['mqtt'])]


def test_cleanup_quiesces_controller_then_revalidates_removes_ids_then_releases(tmp_path):
    g,docker,events,receipt=engine(tmp_path)
    def action(action,identity):
        assert events==['quiesce']
        assert json.loads(receipt.read_text())['phase']=='cleanup'
        docker.calls.append((action,identity))
    docker.action=action
    g.cleanup()
    assert docker.calls==[('remove',identity) for identity in docker.ids.values()]
    assert events==['quiesce','release']
    assert json.loads(receipt.read_text())['phase']=='terminal'
    with pytest.raises(guard.Refused):g.action('start','mqtt')


def test_identity_change_or_incomplete_cgroup_cleanup_keeps_admission(tmp_path):
    g,docker,events,_=engine(tmp_path);docker.fail=True
    with pytest.raises(guard.Refused):g.cleanup()
    assert docker.calls==[] and events==['quiesce']
    docker.fail=False;docker.absent=lambda ids:False
    with pytest.raises(guard.Refused):g.cleanup()
    assert 'release' not in events


def test_restart_with_unacknowledged_lifecycle_request_cleans_without_replay(tmp_path):
    g,docker,events,receipt=engine(tmp_path)
    def failed(action,identity):
        assert json.loads(receipt.read_text())['pending']=={'action':'start','service':'mqtt'}
        raise TimeoutError('daemon reply lost')
    docker.action=failed
    with pytest.raises(TimeoutError):g.action('start','mqtt')
    assert events==[]
    docker.action=lambda action,identity:docker.calls.append((action,identity))
    recovered=guard.GuardianState(receipt,manifest_digest='a'*64,docker=docker,quiesce=lambda:events.append('quiesce'),release=lambda:events.append('release'))
    with pytest.raises(guard.Refused):recovered.action('start','mqtt')
    recovered.cleanup()
    assert all(action=='remove' for action,_ in docker.calls)
    assert events==['quiesce','release']


def test_missing_or_tampered_receipt_never_releases_a_recovered_lock(tmp_path):
    docker=Docker();events=[];receipt=tmp_path/'receipt.json'
    for raw in ['{}','{"phase":"terminal","ids":{},"pending":null}','not json']:
        receipt.write_text(raw);receipt.chmod(0o600)
        with pytest.raises(guard.Refused):guard.GuardianState(receipt,manifest_digest='a'*64,docker=docker,quiesce=lambda:None,release=lambda:events.append('release'))
    assert events==[]


def test_fdstore_release_requires_acknowledged_count_transition():
    events=[];counts=iter([1,0])
    store=guard.FdStore(notify=lambda message,fd=None:events.append((message,fd)),
                        barrier=lambda:events.append(('barrier',None)),count=lambda:next(counts))
    store.pin(17)
    store.release()
    assert events==[('FDSTORE=1\nFDNAME=admission\nFDPOLL=0',17),('barrier',None),
                    ('FDSTOREREMOVE=1\nFDNAME=admission',None),('barrier',None)]


def test_unacknowledged_fdstore_cannot_grant_fixture_start():
    events=[]
    store=guard.FdStore(notify=lambda *a:events.append(a),barrier=lambda:None,count=lambda:0)
    with pytest.raises(guard.Refused):store.pin(17)
    assert events==[('FDSTORE=1\nFDNAME=admission\nFDPOLL=0',17)]


def test_recovery_accepts_only_named_original_fd_and_matching_receipt(tmp_path,monkeypatch):
    path,fd=lock(tmp_path)
    try:
        for env in ({'LISTEN_PID':str(os.getpid()),'LISTEN_FDS':'1','LISTEN_FDNAMES':'other'},
                    {'LISTEN_PID':str(os.getpid()+1),'LISTEN_FDS':'1','LISTEN_FDNAMES':'admission'},
                    {'LISTEN_PID':str(os.getpid()),'LISTEN_FDS':'2','LISTEN_FDNAMES':'admission:other'}):
            with pytest.raises(guard.Refused):guard.inherited_descriptor(env)
        assert guard.inherited_descriptor({}) is None
        assert guard.inherited_descriptor({'LISTEN_PID':str(os.getpid()),'LISTEN_FDS':'1','LISTEN_FDNAMES':'admission'})==3
    finally:os.close(fd)


def test_cleanup_recovery_allows_already_removed_ids_but_never_replacements(tmp_path):
    g,docker,events,receipt=engine(tmp_path)
    removed=[]
    def action(action,identity):
        if len(removed)==2:raise TimeoutError('daemon unavailable')
        removed.append(identity)
    docker.action=action
    with pytest.raises(TimeoutError):g.cleanup()
    assert events==['quiesce']
    docker.action=lambda action,identity:None
    recovered=guard.GuardianState(receipt,manifest_digest='a'*64,docker=docker,quiesce=lambda:None,release=lambda:events.append('release'))
    recovered.cleanup()
    assert events==['quiesce','release']


def test_receipt_cannot_be_recovered_under_a_different_immutable_manifest(tmp_path):
    docker=Docker();receipt=tmp_path/'receipt.json'
    state=guard.GuardianState(receipt,manifest_digest='a'*64,docker=docker,quiesce=lambda:None,release=lambda:None)
    state.register(docker.ids)
    with pytest.raises(guard.Refused):guard.GuardianState(receipt,manifest_digest='b'*64,docker=docker,quiesce=lambda:None,release=lambda:None)


def test_interrupted_atomic_receipt_write_preserves_last_state_and_can_retry(tmp_path,monkeypatch):
    receipt=tmp_path/'receipt.json';guard.persist(receipt,{'phase':'armed'})
    original=guard.os.replace
    monkeypatch.setattr(guard.os,'replace',lambda *args:(_ for _ in ()).throw(OSError('interrupted before rename')))
    with pytest.raises(OSError):guard.persist(receipt,{'phase':'cleanup'})
    assert json.loads(receipt.read_text())=={'phase':'armed'}
    monkeypatch.setattr(guard.os,'replace',original)
    guard.persist(receipt,{'phase':'cleanup'})
    assert json.loads(receipt.read_text())=={'phase':'cleanup'}


def test_large_immutable_manifest_has_explicit_bound_without_widening_protocol():
    raw=json.dumps({'environment_metadata':'x'*70000}).encode()
    with pytest.raises(guard.Refused):guard.decode(raw)
    assert guard.decode(raw,limit=1048576)['environment_metadata']=='x'*70000
    with pytest.raises(guard.Refused):guard.decode(b' '*1048577,limit=1048576)
    with pytest.raises(guard.Refused):guard.decode(b'{}',limit=1048577)


def test_lifecycle_proof_keeps_original_receipt_schema_without_phase_authority(tmp_path):
    docker=Docker();docker.mode='lifecycle-proof';events=[];receipt=tmp_path/'proof-receipt.json'
    state=guard.GuardianState(receipt,manifest_digest='a'*64,docker=docker,quiesce=lambda:events.append('quiesce'),release=lambda:events.append('release'))
    state.register(docker.ids)
    assert set(guard.read_private(receipt))=={'phase','ids','pending','manifest_sha256'}
    for operation in ('retire-chirpstack-for-browser','retire-redis-for-browser','enter-browser'):
        with pytest.raises(guard.Refused):state.transition(operation)
    assert not docker.calls and not events
    state.cleanup()
    assert events==['quiesce','release'] and docker.calls==[('remove',identity) for identity in docker.ids.values()]


def deadline(end):
    assert hasattr(guard,'PhaseDeadline'),'phase operations need an absolute shared deadline'
    return guard.PhaseDeadline(end)


@pytest.mark.parametrize('now',[30.,31.])
def test_deadline_equality_and_negative_remaining_refuse_io(monkeypatch,now):
    import time
    clock=[0.];monkeypatch.setattr(time,'monotonic',lambda:clock[0]);value=deadline(30.)
    assert value.timeout(35)==30. and value.timeout(5)==5.
    clock[0]=29.;assert value.timeout(35)==1.
    clock[0]=now
    with pytest.raises(guard.Refused):value.check()
    with pytest.raises(guard.Refused):value.timeout(35)


def test_expiry_during_flush_preserves_previous_atomic_receipt(tmp_path,monkeypatch):
    import time
    path=tmp_path/'bounded-receipt.json';guard.persist(path,{'phase':'armed'});clock=[0.]
    monkeypatch.setattr(time,'monotonic',lambda:clock[0]);value=deadline(30.);fsync=os.fsync
    def delayed(fd):fsync(fd);clock[0]=30.
    monkeypatch.setattr(os,'fsync',delayed)
    with pytest.raises(guard.Refused):guard.persist(path,{'phase':'next'},deadline=value)
    assert guard.read_private(path)=={'phase':'armed'}


def test_nested_scope_arms_once_and_restores_alarm_handler():
    import signal,time
    value=deadline(time.monotonic()+.25);prior=signal.getsignal(signal.SIGALRM)
    with guard.phase_scope(value):
        first=signal.getitimer(signal.ITIMER_REAL)[0]
        with guard.phase_scope(value):
            assert guard._phase_deadline is value
            assert 0<signal.getitimer(signal.ITIMER_REAL)[0]<=first
        assert guard._phase_deadline is value
    assert guard._phase_deadline is None and signal.getitimer(signal.ITIMER_REAL)==(0.,0.)
    assert signal.getsignal(signal.SIGALRM)==prior


def test_scope_refuses_unrelated_active_timer_without_overwriting_it():
    import signal,time
    value=deadline(time.monotonic()+1.);prior=signal.getsignal(signal.SIGALRM)
    signal.setitimer(signal.ITIMER_REAL,2.)
    try:
        with pytest.raises(guard.Refused):
            with guard.phase_scope(value):pytest.fail('cannot steal another timer')
        assert 1.<signal.getitimer(signal.ITIMER_REAL)[0]<=2.
        assert signal.getsignal(signal.SIGALRM)==prior and guard._phase_deadline is None
    finally:signal.setitimer(signal.ITIMER_REAL,0.)


def test_owned_pending_alarm_is_drained_before_cleanup_handler_restored():
    import signal,time
    value=deadline(time.monotonic()+.04);prior=signal.getsignal(signal.SIGALRM);mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
    try:
        with pytest.raises(guard.Refused):
            with guard.phase_scope(value):
                signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM});time.sleep(.07)
                assert signal.SIGALRM in signal.sigpending()
                raise guard.Refused('operation expired with owned signal pending')
        assert signal.SIGALRM not in signal.sigpending() and signal.getitimer(signal.ITIMER_REAL)==(0.,0.)
        assert signal.getsignal(signal.SIGALRM)==prior and guard._phase_deadline is None
        assert signal.pthread_sigmask(signal.SIG_BLOCK,set())==mask
    finally:signal.pthread_sigmask(signal.SIG_SETMASK,mask)


def test_phase_wall_timer_fails_closed_off_main_thread():
    import threading,time
    value=deadline(time.monotonic()+1.);result=[]
    def run():
        try:
            with guard.phase_scope(value):result.append('unbounded')
        except guard.Refused:result.append('refused')
    worker=threading.Thread(target=run);worker.start();worker.join(1)
    assert not worker.is_alive() and result==['refused']


def test_timer_installation_failure_clears_context_and_restores_handler(monkeypatch):
    import signal,time
    value=deadline(time.monotonic()+1.);previous=signal.getsignal(signal.SIGALRM);setitimer=signal.setitimer
    def fail(which,delay,*args):
        if delay:raise OSError('timer unavailable')
        return setitimer(which,delay,*args)
    monkeypatch.setattr(signal,'setitimer',fail)
    with pytest.raises(OSError,match='timer unavailable'):
        with guard.phase_scope(value):pytest.fail('an unbounded phase cannot run')
    assert guard._phase_deadline is None and signal.getsignal(signal.SIGALRM)==previous
    assert signal.getitimer(signal.ITIMER_REAL)==(0.,0.)


def test_blocked_unowned_alarm_mask_is_not_overwritten():
    import signal,time
    value=deadline(time.monotonic()+1.);previous=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM})
    try:
        with pytest.raises(guard.Refused):
            with guard.phase_scope(value):pytest.fail('a blocked phase timer cannot bound work')
        assert signal.SIGALRM in signal.pthread_sigmask(signal.SIG_BLOCK,set())
        assert guard._phase_deadline is None and signal.getitimer(signal.ITIMER_REAL)==(0.,0.)
    finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)
