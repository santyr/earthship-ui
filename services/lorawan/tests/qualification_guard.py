"""Run-specific sensor admission guardian. Never imported by production services.

The serialized service owns lifecycle operations for seven predeclared fixture
IDs. PID1 keeps the *same* admission flock OFD across guardian/controller death.
Ambiguous state retains exclusion; no error path calls LOCK_UN or removes a
stored descriptor. Actual system-manager/Docker qualification is separate from
this module's hermetic protocol tests.
"""
import array
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import struct
import tempfile
import signal
import threading
import time

SERVICES=('mqtt','postgres','ingest','openhab','redis','chirpstack','simulator')
WORKLOAD_PHASES=('python','retiring-chirpstack','chirpstack-retired','retiring-redis','redis-retired','retiring-simulator','browser-ready','browser')
PHASE_REQUESTS=('retire-chirpstack-for-browser','retire-redis-for-browser','retire-simulator-for-browser','enter-browser')


class Refused(RuntimeError):
    pass


def require(value,message='sensor admission protocol refused'):
    if not value:raise Refused(message)


class PhaseExpired(Refused):
    pass


@dataclass(frozen=True)
class PhaseDeadline:
    """Internal absolute authority; never a wire field or a renewable timeout."""
    end: float

    def __post_init__(self):
        require(type(self.end) in (int,float) and math.isfinite(self.end))

    def check(self):
        if time.monotonic()>=self.end:raise PhaseExpired('phase request expired')

    def timeout(self,ceiling):
        remaining=self.end-time.monotonic()
        if remaining<=0:raise PhaseExpired('phase request expired')
        require(ceiling>0)
        return min(ceiling,remaining)


def check_deadline(deadline):
    if deadline is not None:
        require(isinstance(deadline,PhaseDeadline),'internal phase deadline required');deadline.check()


_phase_deadline=None


@contextmanager
def phase_scope(deadline):
    """One main-thread wall timer, removed before independent owned cleanup."""
    global _phase_deadline
    if deadline is None:
        yield;return
    check_deadline(deadline)
    require(threading.current_thread() is threading.main_thread(),'phase timer requires the main thread')
    if _phase_deadline is not None:
        require(_phase_deadline is deadline,'phase deadline cannot be replaced')
        yield;deadline.check();return
    previous_mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM})
    previous_handler=signal.getsignal(signal.SIGALRM);owned=False
    def expired(*_):raise PhaseExpired('phase wall deadline expired')
    try:
        require(signal.SIGALRM not in previous_mask and signal.getitimer(signal.ITIMER_REAL)==(0.,0.)
                and signal.SIGALRM not in signal.sigpending(),'phase timer already owned or blocked')
        signal.signal(signal.SIGALRM,expired);owned=True;_phase_deadline=deadline
        signal.setitimer(signal.ITIMER_REAL,deadline.timeout(30))
        signal.pthread_sigmask(signal.SIG_SETMASK,previous_mask)
        yield
        deadline.check()
    finally:
        if owned:
            signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM})
            signal.setitimer(signal.ITIMER_REAL,0.)
            # A timer that expired while blocked must not reach the restored
            # handler (possibly SIG_DFL) during diagnostic I/O or cleanup.
            while signal.SIGALRM in signal.sigpending():signal.sigtimedwait({signal.SIGALRM},0)
            _phase_deadline=None
            signal.signal(signal.SIGALRM,previous_handler)
        signal.pthread_sigmask(signal.SIG_SETMASK,previous_mask)


def decode(raw,*,limit=65536):
    def pairs(values):
        result={}
        for k,v in values:
            require(k not in result,'duplicate receipt key');result[k]=v
        return result
    try:
        require(type(limit) is int and 1<=limit<=1048576 and len(raw)<=limit)
        return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(Refused('nonfinite JSON')))
    except (ValueError,TypeError,UnicodeError) as error:raise Refused('invalid bounded JSON') from error


def read_private(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1)
        return decode(os.read(fd,65537))
    finally:os.close(fd)


def persist(path,value,*,limit=65536,deadline=None):
    check_deadline(deadline)
    path=Path(path)
    fd,name=tempfile.mkstemp(prefix=path.name+'.pending-',dir=path.parent)
    temporary=Path(name)
    try:
        raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode();require(type(limit) is int and 1<=limit<=1048576 and len(raw)<=limit)
        with os.fdopen(fd,'wb') as output:output.write(raw);output.flush();os.fsync(output.fileno())
        check_deadline(deadline)
        os.replace(temporary,path)
        check_deadline(deadline)
        directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
        check_deadline(deadline)
    except BaseException:
        # Interrupted temporary bytes cannot replace the last durable receipt.
        # Never delete an unknown replacement as an error-recovery shortcut.
        raise


def send_descriptor(connection,fd,value):
    raw=json.dumps(value,separators=(',',':')).encode();require(len(raw)<=8192)
    require(connection.sendmsg([raw],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]))])==len(raw))


def receive_descriptor(connection,*,uid,pid):
    received=[]
    try:
        peer=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        raw,ancillary,flags,_=connection.recvmsg(8193,socket.CMSG_SPACE(8),socket.MSG_CMSG_CLOEXEC)
        for level,kind,data in ancillary:
            require(level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS)
            descriptors=array.array('i');descriptors.frombytes(data[:len(data)-len(data)%descriptors.itemsize]);received.extend(descriptors)
        require(peer[:2]==(pid,uid) and not flags & (socket.MSG_TRUNC|socket.MSG_CTRUNC) and len(raw)<=8192 and len(received)==1)
        return decode(raw),received.pop()
    finally:
        for fd in received:os.close(fd)


def verify_lock(path,fd,*,uid,identity):
    path=Path(path);info=path.lstat();opened=os.fstat(fd);directory=path.parent.stat()
    require(path.parent.resolve()==path.parent.absolute() and directory.st_uid==uid and stat.S_IMODE(directory.st_mode)==0o700)
    for value in (info,opened):
        require(stat.S_ISREG(value.st_mode) and value.st_uid==uid and value.st_nlink==1 and stat.S_IMODE(value.st_mode)==0o600
                and (value.st_dev,value.st_ino)==tuple(identity),'admission lock inode or permissions changed')
    # Linux fdinfo reports flock ownership on this OFD, not just another open
    # descriptor to the same inode. Never reacquire/unlock the transferred FD.
    locks=[line for line in Path(f'/proc/self/fdinfo/{fd}').read_text().splitlines() if line.startswith('lock:')]
    require(len(locks)==1 and ' FLOCK ' in locks[0] and ' WRITE ' in locks[0], 'original locked open file description required')


def validate_ids(ids):
    require(type(ids) is dict and set(ids)==set(SERVICES) and len(set(ids.values()))==len(SERVICES))
    require(all(isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) for value in ids.values()))


class GuardianState:
    """Single-threaded lifecycle state; the transport supplies authenticated peers."""
    def __init__(self,receipt,*,manifest_digest,docker,quiesce,release):
        require(isinstance(manifest_digest,str) and re.fullmatch('[a-f0-9]{64}',manifest_digest))
        self.receipt=Path(receipt);self.docker=docker;self.quiesce=quiesce;self.release=release
        self.mode=getattr(docker,'mode','lifecycle-proof');require(self.mode in ('qualification','lifecycle-proof'))
        self.recovered=self.receipt.exists()
        self.state=read_private(self.receipt) if self.recovered else {'phase':'new','ids':None,'pending':None,'manifest_sha256':manifest_digest}
        if self.mode=='qualification' and not self.recovered:self.state['workload_phase']='python'
        keys={'phase','ids','pending','manifest_sha256'}|({'workload_phase'} if self.mode=='qualification' else set())
        require(set(self.state)==keys and self.state['manifest_sha256']==manifest_digest and self.state['phase'] in ('new','armed','cleanup','terminal'))
        if self.state['ids'] is not None:validate_ids(self.state['ids'])
        require(self.state['phase']=='new' or self.state['ids'] is not None)
        pending=self.state['pending']
        require(pending is None or type(pending) is dict and set(pending)=={'action','service'}
                and pending['action'] in ('start','stop','restart') and pending['service'] in SERVICES)
        if self.mode=='qualification':
            phase=self.state['workload_phase'];require(phase in WORKLOAD_PHASES)
            require(self.state['phase']!='new' or phase=='python')
            if self.state['phase']=='armed' and phase not in ('python','browser'):
                expected={'action':'stop','service':phase.removeprefix('retiring-')} if phase.startswith('retiring-') else None
                require(pending==expected)
            if phase=='browser' and pending is not None:
                require(pending['service'] not in ('chirpstack','redis','simulator'))

    def write(self,*,deadline=None):persist(self.receipt,self.state,deadline=deadline)

    def register(self,ids):
        require(not self.recovered and self.state['phase']=='new')
        validate_ids(ids);self.docker.validate(ids,running=False)
        self.state.update(phase='armed',ids=dict(ids));self.write()

    def action(self,action,service):
        require(not self.recovered and self.state['phase']=='armed' and self.state['pending'] is None)
        require(service in SERVICES and action in ('start','stop','restart') and not (service=='simulator' and action!='start'))
        if self.mode=='qualification':
            phase=self.state['workload_phase']
            require(phase=='python' or phase=='browser' and service not in ('chirpstack','redis','simulator'),'retirement revokes lifecycle authority')
        self.docker.validate(self.state['ids'],running=False)
        self.state['pending']={'action':action,'service':service};self.write()
        # No parallel handler: a cleanup request cannot overtake this call.
        self.docker.action(action,self.state['ids'][service])
        self.state['pending']=None;self.write()

    def transition(self,operation,*,deadline=None):
        """One irreversible exact stop per request; recovery never calls this."""
        require(self.mode=='qualification' and not self.recovered and self.state['phase']=='armed' and self.state['pending'] is None)
        require(operation in PHASE_REQUESTS)
        require(isinstance(deadline,PhaseDeadline),'phase transition requires its original deadline');deadline.check()
        phase=self.state['workload_phase']
        if operation=='enter-browser':
            require(phase=='browser-ready')
            self.docker.browser_ready(deadline=deadline);deadline.check()
            self.state['workload_phase']='browser';self.write(deadline=deadline)
        else:
            steps={
                'retire-chirpstack-for-browser':('chirpstack','python','chirpstack-retired',('chirpstack',)),
                'retire-redis-for-browser':('redis','chirpstack-retired','redis-retired',('chirpstack','redis')),
                'retire-simulator-for-browser':('simulator','redis-retired','browser-ready',('chirpstack','redis','simulator')),
            }
            service,previous,following,retired=steps[operation]
            require(phase==previous)
            self.docker.validate(self.state['ids'],running=False,deadline=deadline);deadline.check()
            if retired[:-1]:self.docker.retired(retired[:-1],deadline=deadline);deadline.check()
            # All retired members lose start/restart authority before any stop.
            self.state.update(workload_phase='retiring-'+service,pending={'action':'stop','service':service});self.write(deadline=deadline)
            deadline.check()
            self.docker.action('stop',self.state['ids'][service],deadline=deadline);deadline.check()
            self.docker.retired(retired,deadline=deadline);deadline.check()
            self.state.update(workload_phase=following,pending=None);self.write(deadline=deadline)
        deadline.check()
        return {'workload_phase':self.state['workload_phase']}

    def check_retired(self,*,deadline=None):
        if self.mode!='qualification':return
        check_deadline(deadline)
        phase=self.state['workload_phase'];require(phase in WORKLOAD_PHASES)
        if phase in ('chirpstack-retired','retiring-redis'):self.docker.retired(('chirpstack',),deadline=deadline)
        elif phase in ('redis-retired','retiring-simulator'):self.docker.retired(('chirpstack','redis'),deadline=deadline)
        elif phase in ('browser-ready','browser'):self.docker.retired(('chirpstack','redis','simulator'),deadline=deadline)
        check_deadline(deadline)

    def cleanup(self):
        # Even a terminal restart must re-establish quiescence/absence before
        # removing PID1's descriptor. Missing IDs never authorize broad cleanup.
        require(self.state['ids'] is not None,'unacknowledged create requires reconciliation')
        self.state['phase']='cleanup';self.write()
        self.quiesce()
        self.docker.validate(self.state['ids'],running=False,cleanup=True)
        for identity in self.state['ids'].values():self.docker.action('remove',identity)
        require(self.docker.absent(self.state['ids']),'owned IDs or cgroups remain')
        self.state.update(phase='terminal',pending=None);self.write()
        self.release()


class FdStore:
    """Store/removal must be acknowledged before start/release respectively."""
    def __init__(self,*,notify,barrier,count):
        self.notify=notify;self.barrier=barrier;self.count=count

    def pin(self,fd):
        self.notify('FDSTORE=1\nFDNAME=admission\nFDPOLL=0',fd)
        self.barrier()
        require(self.count()==1,'PID1 did not acknowledge the admission descriptor')

    def release(self):
        self.notify('FDSTOREREMOVE=1\nFDNAME=admission')
        self.barrier()
        require(self.count()==0,'PID1 did not acknowledge descriptor removal')


def inherited_descriptor(environment):
    keys=('LISTEN_PID','LISTEN_FDS','LISTEN_FDNAMES')
    if not any(key in environment for key in keys):return None
    require(environment.get('LISTEN_PID')==str(os.getpid()) and environment.get('LISTEN_FDS')=='1'
            and environment.get('LISTEN_FDNAMES')=='admission','exact named PID1 descriptor required')
    return 3
