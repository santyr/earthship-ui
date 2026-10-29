"""One nonrenewable score-timer pause with manager-owned external cleanup.

The installed template runs outside the learner's work scope. Unknown or mixed
files remain quiescent and require reconciliation; this is not an undo journal.
A redundant no-op operator stop cannot be distinguished from the owned pause.
"""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import json
import os
import signal
import stat
import subprocess
import time
from uuid import uuid4

TIMERS=('thermal-provisional-forecast.timer','thermal-provisional-score.timer','thermal-native-geometry-prepare.timer')
SCORE=TIMERS[1]
TRANSITIONS=('ActiveEnterTimestampMonotonic','ActiveExitTimestampMonotonic','InactiveEnterTimestampMonotonic','InactiveExitTimestampMonotonic','InvocationID')


@contextmanager
def cancellation_boundary():
    previous={s:signal.getsignal(s) for s in (signal.SIGINT,signal.SIGTERM)}
    def cancel(signum,frame):
        # Subsequent cancellation must not interrupt coherent rollback.
        for sig in previous:signal.signal(sig,signal.SIG_IGN)
        raise KeyboardInterrupt('native activation cancelled')
    try:
        for sig in previous:signal.signal(sig,cancel)
        yield
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)


@contextmanager
def cleanup_boundary():
    """Do not let another cancellation orphan a child during bounded reap."""
    previous={sig:signal.getsignal(sig) for sig in (signal.SIGINT,signal.SIGTERM)}
    try:
        for sig in previous:signal.signal(sig,signal.SIG_IGN)
        yield
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)


def drain_score(*,guard,read_pid,monotonic=time.monotonic,sleep=time.sleep):
    end=monotonic()+130
    original=None
    while True:
        guard();pid=read_pid()
        if not isinstance(pid,str) or not pid.isdecimal():raise ValueError('explicit scorer identity required')
        if pid=='0':return
        if original is None:original=pid
        if original!=pid:raise ValueError('scorer identity changed during owned drain')
        if monotonic()>=end:raise TimeoutError('original scorer did not drain within130 seconds')
        sleep(1)


def process_identity(pid):
    try:
        raw=Path('/proc')/str(pid)/'stat';tail=raw.read_text().rsplit(')',1)[1].split()
        if tail[0]=='Z':return None
        return [int(pid),tail[19],Path('/proc/sys/kernel/random/boot_id').read_text().strip()]
    except (FileNotFoundError,ProcessLookupError):return None


def same_pause(before,after):
    keys=('ActiveState','UnitFileState','FragmentPath','DropInPaths',*TRANSITIONS)
    return all(before.get(k)==after.get(k) for k in keys) and after.get('ActiveState')=='inactive'


def save(path,value):
    from household_native_training import save as write
    write(path,value)
    fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def read(path):
    from household_native_training import read as load
    return load(path,2097152)


def _timer(unit):
    from household_native_install import _effective_state
    from household_cycle_deploy import _systemctl
    result=_effective_state(unit)
    extra=_systemctl('show',unit,*['--property='+key for key in TRANSITIONS])
    result.update(dict(row.split('=',1) for row in extra.splitlines() if '=' in row))
    if any(key not in result for key in TRANSITIONS):raise ValueError('explicit timer transition identities required')
    # next_elapse is deliberately omitted by _effective_state; it is not an ownership identity.
    return result


def fingerprint(path,*,link=False):
    path=Path(path);info=path.lstat()
    if info.st_uid!=os.getuid() or info.st_mode&0o022 and not stat.S_ISLNK(info.st_mode):raise ValueError('owned lifecycle path required')
    result=[info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_mtime_ns,info.st_ctime_ns]
    if link:
        if not stat.S_ISLNK(info.st_mode):raise ValueError('exact timer enablement link required')
        return result+[str(path.readlink())]
    from household_cycle_deploy import _bytes,_path,MAX_BYTES
    if path.name!='thermal-native-activation-owner@.service':
        return result+[sha256(_bytes(path)).hexdigest()]
    # Only this installed manager template needs '@'. Deployment/source readers
    # retain their closed path contract; the parent still uses that contract.
    if not path.is_absolute() or _path(path.parent)!=path.parent or path.resolve()!=path:
        raise ValueError('canonical activation template required')
    metadata=lambda row:(row.st_dev,row.st_ino,row.st_mode,row.st_uid,row.st_nlink,row.st_size,row.st_mtime_ns,row.st_ctime_ns)
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except OSError:raise ValueError('owned activation template unavailable') from None
    try:
        opened=os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid!=os.getuid() or opened.st_mode&0o022 or
            opened.st_nlink!=1 or opened.st_size>MAX_BYTES or metadata(info)!=metadata(opened)):
            raise ValueError('bounded owned activation template required')
        raw=os.read(fd,MAX_BYTES+1)
        if (len(raw)!=opened.st_size or len(raw)>MAX_BYTES or metadata(opened)!=metadata(os.fstat(fd)) or
            metadata(opened)!=metadata(path.lstat()) or path.resolve()!=path):
            raise ValueError('activation template changed while reading')
        return result+[sha256(raw).hexdigest()]
    finally:os.close(fd)


def source_snapshot(repo):
    names=subprocess.check_output(['git','-C',str(repo),'ls-files','-z','openhab/scripts','scripts/run-household-job.py'],timeout=10).decode().split('\0')
    paths=[repo/name for name in names if name.endswith('.py') and not Path(name).name.startswith('test_')]
    if not 1<=len(paths)<=1024:raise ValueError('bounded committed owner source closure required')
    return {str(path):fingerprint(path) for path in paths}


def verify_sources(data,*,full=True):
    sources=data['sources']
    if not isinstance(sources,dict) or not 1<=len(sources)<=1024:raise ValueError('bounded owner source closure required')
    for path,expected in sources.items():
        if full:actual=fingerprint(path)
        else:
            info=Path(path).lstat();actual=[info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_mtime_ns,info.st_ctime_ns]
            if Path(path).resolve()!=Path(path):raise ValueError('owner source closure path changed')
            expected=expected[:-1]
        if actual!=expected:raise ValueError('owner source closure changed')


def _dependencies(root):
    """Fixed base definitions, enable links, and target-parent identities."""
    paths={}
    for timer in TIMERS:
        link=root/'timers.target.wants'/timer
        paths[str(link)]=fingerprint(link,link=True) if link.exists() or link.is_symlink() else None
    for name in ('thermal-provisional-forecast.service','thermal-provisional-score.service',*TIMERS[:2]):
        paths[str(root/name)]=fingerprint(root/name)
    for parent in (root,root/'timers.target.wants',root/'thermal-provisional-forecast.service.d',root/'thermal-provisional-score.service.d',root/'thermal-provisional-score.timer.d'):
        info=parent.lstat()
        if parent.resolve()!=parent or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o022:raise ValueError('owned unit parent required')
        paths[str(parent)]=[info.st_dev,info.st_ino,info.st_mode,info.st_uid]
    return paths


def _targets(root,family):
    from household_native_handoff import FILES
    targets={
        'forecast':root/'thermal-provisional-forecast.service.d/zzzz-household-cycle.conf',
        'score':root/'thermal-provisional-score.service.d/zzzz-household-score.conf',
        'score_timer':root/'thermal-provisional-score.timer.d/zzzz-household-native-timer.conf',
        'preparer_service':root/'thermal-native-geometry-prepare.service',
        'preparer_timer':root/'thermal-native-geometry-prepare.timer'}
    from household_cycle_deploy import _bytes
    return {str(path):sha256(_bytes(Path(family)/FILES[role],private=True)).hexdigest() for role,path in targets.items()}


def _matches(targets):
    from household_cycle_deploy import _bytes
    try:return all(sha256(_bytes(path,private=True)).hexdigest()==pin for path,pin in targets.items())
    except (OSError,ValueError):return False


def start_owner(unit,*,before_start=lambda:None):
    """Charge the finite recovery service to the unchanged shared admission gate."""
    from household_job_launch import admission_gate
    from household_job_budget import admit_memory
    from household_job_pool import POOL_NAME,HOST_RESERVE,available_memory,read_pool,_counter,check_host_pressure
    from household_cycle_deploy import _systemctl
    relative=_systemctl('show',POOL_NAME,'--value','-p','ControlGroup')
    expected=f'/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/earthship.slice/'+POOL_NAME
    if relative!=expected:raise ValueError('original shared work pool required')
    pool=Path('/sys/fs/cgroup')/relative.lstrip('/')
    with admission_gate(Path('/run/user')/str(os.getuid())/'earthship-job-admission.lock') as verify:
        check_host_pressure()
        memory=admit_memory(available_bytes=available_memory(),**read_pool(pool),
            minimum_bytes=256*1024**2,preferred_bytes=256*1024**2,reserve_bytes=HOST_RESERVE)
        verify();before_start();_systemctl('start',unit)
        if _counter(pool/unit/'memory.max')!=memory or _counter(pool/unit/'memory.swap.max')!=0:
            raise ValueError('external recovery service commitment differs')
        verify()


def _request_pin(data):
    return sha256(json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _finished_attempt(path):
    """Only durable completed recovery or proven never-dispatched starts clear."""
    status=path/'status.json'
    if not status.exists():return False
    record=read(status)
    if record.get('phase')=='restored':return True
    if (set(record)!={'schema','phase','nonce','request_sha256'} or
        record['schema']!='earthship-native-activation-never-armed/v1' or
        record['phase']!='never_armed' or record['nonce']!=path.name):return False
    request=read(path/'request.json')
    return (request.get('nonce')==path.name and request.get('phase')=='never_armed' and
        request.get('start_attempted') is False and _request_pin(request)==record['request_sha256'])


class Reservation:
    def __init__(self,state,run,previous,*,guard):
        from household_native_training import directory
        from household_cycle_deploy import verify_stage,_systemctl
        repo=Path(__file__).resolve().parents[2]
        if subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],timeout=10).strip():raise ValueError('clean Git-backed repaired release required')
        from household_native_training import effective_selection
        if effective_selection()!={k:previous[k] for k in ('stage','deployment_sha256')}:raise ValueError('selected model changed before reservation')
        from thermal_model.forcing_capture import _private_directory
        root=_private_directory(Path(state))/'activation-reservations'
        if root.exists() or root.is_symlink():
            _private_directory(root)
            for path in root.iterdir():
                _private_directory(path)
                if not _finished_attempt(path):raise ValueError('previous reservation requires reconciliation')
        guard()
        self.guard=guard;self.nonce=uuid4().hex;self.directory=root/self.nonce
        self.request=self.directory/'request.json';self.status=self.directory/'status.json'
        self.unit='thermal-native-activation-owner@'+self.nonce+'.service'
        stage=Path(previous['stage']);record=verify_stage(stage,expected_deployment_sha256=previous['deployment_sha256'])
        settings=read(read(stage/'cycle.json')['forecast_config'])
        self.data=dict(nonce=self.nonce,owner=process_identity(os.getpid()),run=str(run),previous=previous,
            root=str(Path(record['service_file']).parent),shared_lock=settings['shared_lock'],
            expires=time.monotonic()+min(600,max(0,getattr(guard,'deadline',time.monotonic()+600)-time.monotonic())),
            phase='reserve',family=None,handoff_deadline=None,start_attempted=False,sources=source_snapshot(repo),source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
        # All source/selection/settings/prior-attempt preflight precedes publication.
        guard();directory(root);directory(self.directory)
        dispatched=False
        def before_start():
            nonlocal dispatched
            # Mark ambiguous BEFORE sending the manager command, never afterward.
            dispatched=True;self.data['start_attempted']=True;save(self.request,self.data)
        try:
            save(self.request,self.data)
            start_owner(self.unit,before_start=before_start)
            self.wait('reserved')
            drain_score(guard=self.check,read_pid=lambda:_systemctl('show','thermal-provisional-score.service','-p','MainPID','--value'))
        except BaseException as error:
            if not dispatched:
                self.data['phase']='never_armed';save(self.request,self.data)
                save(self.status,dict(schema='earthship-native-activation-never-armed/v1',phase='never_armed',
                    nonce=self.nonce,request_sha256=_request_pin(self.data)))
                raise
            self.data['phase']='release';save(self.request,self.data)
            if self.status.exists():
                try:self.close()
                except BaseException as cleanup:error.add_note('external pause reconciliation required: '+type(cleanup).__name__)
            raise
    def wait(self,phase):
        end=min(self.data['expires'],time.monotonic()+15)
        if phase=='quiesced':end=min(end,self.data['handoff_deadline'])
        while time.monotonic()<end:
            self.guard()
            if self.status.exists():
                value=read(self.status)
                if value.get('phase')==phase:return value
                if value.get('phase')=='reconciliation_required':raise ValueError('activation reservation requires reconciliation: '+value.get('reason',''))
            time.sleep(.1)
        raise TimeoutError('external activation owner acknowledgment missing')
    def check(self):
        self.guard()
        if time.monotonic()>=self.data['expires']:raise TimeoutError('activation reservation expired')
        value=read(self.status)
        if value['phase'] not in ('reserved','stopping','quiesced') or process_identity(value['manager'][0])!=value['manager']:raise ValueError('external activation owner lost')
    def quiesce(self,family):
        self.check();self.data.update(phase='handoff',family=str(family),handoff_deadline=min(self.data['expires'],time.monotonic()+15));save(self.request,self.data);self.wait('quiesced')
    def close(self):
        self.data['phase']='release';save(self.request,self.data)
        end=time.monotonic()+30
        while time.monotonic()<end:
            value=read(self.status)
            if value['phase']=='restored':return
            if value['phase']=='reconciliation_required':raise ValueError('external cleanup requires reconciliation: '+value.get('reason',''))
            time.sleep(.1)
        raise TimeoutError('external cleanup acknowledgment missing')


def attach(directory,*,guard):
    """Same nonce in staged child; external owner remains sole schedule authority."""
    result=Reservation.__new__(Reservation);result.directory=Path(directory);result.request=result.directory/'request.json';result.status=result.directory/'status.json';result.data=read(result.request);result.guard=guard
    result.nonce=result.data['nonce'];result.unit='thermal-native-activation-owner@'+result.nonce+'.service';result.check();return result


def verify_manager_domain(data):
    """Refuse an attachment inside the worker's kill domain or wrong manager epoch."""
    from household_cycle_deploy import _systemctl
    unit='thermal-native-activation-owner@'+data['nonce']+'.service'
    own=Path('/proc/self/cgroup').read_text().strip()
    parent=Path('/proc')/str(data['owner'][0])/'cgroup'
    if parent.exists():
        owner=parent.read_text().strip()
        if own==owner or own.startswith(owner+'/'):raise ValueError('external recovery shares worker kill domain')
    expected=f'0::/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/earthship.slice/earthship-work.slice/'+unit
    if own!=expected:raise ValueError('manager-owned activation recovery service required')
    keys=('InvocationID','ControlGroup','ExecStart','ExecStopPost','FragmentPath','DropInPaths','MemoryMax','MemorySwapMax','TasksMax','KillMode','CPUQuotaPerSecUSec')
    state=dict(row.split('=',1) for row in _systemctl('show',unit,*['--property='+k for k in keys]).splitlines() if '=' in row)
    if (state.get('InvocationID')!=os.environ.get('INVOCATION_ID') or not state.get('InvocationID') or
        state.get('MemoryMax')!='268435456' or state.get('MemorySwapMax')!='0' or state.get('TasksMax')!='24' or
        state.get('CPUQuotaPerSecUSec')!='200ms' or state.get('KillMode')!='control-group' or
        'household_native_lifecycle' not in state.get('ExecStart','') or '--recover' not in state.get('ExecStopPost','') or
        state.get('DropInPaths') or own!='0::'+state.get('ControlGroup','')):
        raise ValueError('pinned capped external recovery topology required')
    return dict(invocation=state['InvocationID'],fragment=state['FragmentPath'],definition=fingerprint(state['FragmentPath']))


def _verification_worker(request,pin,family,output,*,effective=False):
    """Read-only admitted leaf: run the existing complete validators unchanged."""
    data=read(request)
    if (_request_pin(data)!=pin or request.resolve()!=request or output.parent!=request.parent or
        output.exists() or output.is_symlink() or not output.name.startswith('verification-') or
        data['source_sha256']!=sha256(Path(__file__).read_bytes()).hexdigest()):
        raise ValueError('pinned private family verification required')
    if family not in (Path(data['previous']['stage']).parent/'family',Path(data['run'])/'family'):
        raise ValueError('original or candidate family required')
    verify_sources(data)
    end=time.monotonic()+8
    def guard():
        if time.monotonic()>=end:raise TimeoutError('bounded family verification expired')
    if effective:
        from household_native_install import _verify_effective_family
        result=_verify_effective_family(family,guard=guard)
    else:
        from household_native_family import verify
        result=verify(family,guard=guard)
    guard();verify_sources(data)
    if _request_pin(read(request))!=pin:raise ValueError('verification request changed')
    save(output,dict(schema='earthship-native-family-check/v1',request_sha256=pin,
        family=str(family),effective=effective,result=result))


def _verify_family(directory,family,*,effective=False):
    """Keep full verification off the CPU20% pause owner's control path.

    A separately charged 256MiB/24-task, ten-second shared leaf is read-only.
    The original launcher revokes/kills its owned scope on cancellation/failure;
    the kernel runtime bound also applies if the external owner itself is lost.
    """
    import sys
    from household_job_launch import launch_job
    from household_job_pool import POOL_NAME,check_host_pressure
    from household_cycle_deploy import _systemctl
    directory=Path(directory);family=Path(family);request=directory/'request.json'
    data=read(request);pin=_request_pin(data)
    output=directory/('verification-'+uuid4().hex+'.json')
    relative=_systemctl('show',POOL_NAME,'--value','-p','ControlGroup')
    expected=f'/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/earthship.slice/'+POOL_NAME
    if relative!=expected:raise ValueError('original shared work pool required')
    end=time.monotonic()+10
    def checked():
        check_host_pressure()
        if time.monotonic()>=end:raise TimeoutError('bounded family verification expired')
        verify_sources(data,full=False)
    command=[sys.executable,'-B',str(Path(__file__)),
        '--verify-family',str(family),'--verification-request',str(request),
        '--verification-pin',pin,'--verification-output',str(output)]
    if effective:command+=['--verify-effective']
    result=launch_job(command,pool_path=Path('/sys/fs/cgroup')/relative.lstrip('/'),
        lock_path=Path('/run/user')/str(os.getuid())/'earthship-job-admission.lock',
        minimum_bytes=256*1024**2,preferred_bytes=256*1024**2,production=True,tasks=24,seconds=10,health=checked)
    checked();verify_sources(data)
    if result:raise ValueError('external family verification failed')
    value=read(output)
    if (set(value)!={'schema','request_sha256','family','effective','result'} or
        value['schema']!='earthship-native-family-check/v1' or value['request_sha256']!=pin or
        value['family']!=str(family) or value['effective'] is not effective or _request_pin(read(request))!=pin):
        raise ValueError('family verification result binding changed')
    return value['result']


def _current_request(request,data):
    current=read(request)
    if {k:v for k,v in current.items() if k not in ('phase','family','handoff_deadline')}!={k:v for k,v in data.items() if k not in ('phase','family','handoff_deadline')}:
        raise ValueError('reservation owner record changed')
    if current['phase']=='handoff' and (type(current.get('handoff_deadline')) not in (float,int) or
        not 0<current['handoff_deadline']<=min(data['expires'],time.monotonic()+15)):raise ValueError('bounded handoff acknowledgement deadline required')
    return current


def watch(directory):
    from household_cycle_deploy import _systemctl
    directory=Path(directory);request=directory/'request.json';status=directory/'status.json';data=read(request)
    if data.get('start_attempted') is not True or data.get('phase')!='reserve':raise ValueError('dispatched original reservation required')
    if data['nonce']!=directory.name or data['source_sha256']!=sha256(Path(__file__).read_bytes()).hexdigest():raise ValueError('pinned external owner required')
    verify_sources(data)
    manager_binding=verify_manager_domain(data)
    old=Path(data['previous']['stage']).parent/'family';selected=_verify_family(directory,old)
    if selected['deployment_sha256']!=data['previous']['deployment_sha256']:raise ValueError('previous family pin differs')
    if (_current_request(request,data)['phase']!='reserve' or process_identity(data['owner'][0])!=data['owner'] or
        time.monotonic()>=data['expires']):return
    verify_sources(data)
    if verify_manager_domain(data)!=manager_binding:raise ValueError('external manager binding changed')
    root=Path(data['root']);baseline=_dependencies(root);timers={unit:_timer(unit) for unit in TIMERS}
    if any(v.get('ActiveState') not in ('active','inactive') for v in timers.values()):raise ValueError('stable original timer activity required')
    info=Path(data['shared_lock']).lstat();lock_identity=[info.st_dev,info.st_ino]
    record=dict(phase='armed',manager=process_identity(os.getpid()),manager_binding=manager_binding,original=timers,paused={},dependencies=baseline,
        lock_identity=lock_identity,old_family=str(old),old_targets=_targets(root,old),new_family=None,new_targets=None,request=data)
    if not _matches(record['old_targets']):raise ValueError('original family files changed')
    record['original_target_identities']={path:fingerprint(path) for path in record['old_targets']}
    save(status,record)
    def pause(unit):
        if unit!=SCORE:
            current=_current_request(request,data)
            if (current['phase']!='handoff' or current['family']!=record['new_family'] or
                process_identity(data['owner'][0])!=data['owner'] or time.monotonic()>=current['handoff_deadline']):
                raise ValueError('handoff authorization elapsed before pause')
        # Persist intention BEFORE a possible stop. A kill before its readback is ambiguous.
        record['phase']='stopping';record['stopping']=unit;save(status,record)
        if _timer(unit)!=timers[unit]:raise ValueError('timer changed before owned stop')
        if timers[unit]['ActiveState']=='active':_systemctl('stop',unit)
        stopped=_timer(unit)
        if stopped['ActiveState']!='inactive':raise ValueError('timer did not stop')
        record['paused'][unit]=stopped;record.pop('stopping',None);save(status,record)
    pause(SCORE);record['phase']='reserved';save(status,record)
    while True:
        current=_current_request(request,data)
        verify_sources(data,full=False)
        if verify_manager_domain(data)!=manager_binding:raise ValueError('external manager binding changed')
        if data['source_sha256']!=sha256(Path(__file__).read_bytes()).hexdigest():raise ValueError('owner source changed')
        if _dependencies(root)!=baseline:raise ValueError('reservation definitions or enablement changed')
        if any(not same_pause(v,_timer(u)) for u,v in record['paused'].items()):raise ValueError('observable timer ownership changed')
        if record['new_family'] is None and any(fingerprint(path)!=saved for path,saved in record['original_target_identities'].items()):
            raise ValueError('original unit file identity changed before handoff')
        if current['phase']=='release':return
        if process_identity(data['owner'][0])!=data['owner'] or time.monotonic()>=data['expires']:return
        if current['phase']=='handoff' and record['phase']=='reserved':
            family=Path(current['family']);_verify_family(directory,family)
            # A late verifier must never pause on a cancelled, expired or changed
            # request. Recheck every ownership input after the admitted work.
            latest=_current_request(request,data)
            if latest['phase']=='release' or process_identity(data['owner'][0])!=data['owner']:return
            if latest!=current:raise ValueError('handoff request changed during verification')
            if time.monotonic()>=min(data['expires'],latest['handoff_deadline']):return
            verify_sources(data)
            if verify_manager_domain(data)!=manager_binding or _dependencies(root)!=baseline:
                raise ValueError('handoff ownership changed during verification')
            if any((_timer(u)!=timers[u] if u not in record['paused'] else not same_pause(record['paused'][u],_timer(u))) for u in TIMERS):
                raise ValueError('timer ownership changed during verification')
            if any(fingerprint(path)!=saved for path,saved in record['original_target_identities'].items()):
                raise ValueError('original files changed during verification')
            record.update(new_family=str(family),new_targets=_targets(root,family));save(status,record)
            for unit in TIMERS:
                if unit!=SCORE:pause(unit)
            record['phase']='quiesced';save(status,record)
        time.sleep(.25)


def recover(directory):
    """ExecStopPost; outside learner kill domain, conservative on any unknown."""
    from household_cycle_deploy import _systemctl
    from thermal_model.capture_guard import SharedScoreLock
    directory=Path(directory);path=directory/'status.json'
    if not path.exists():return
    record=read(path)
    if record['phase']=='restored':return
    data=record['request'];root=Path(data['root'])
    try:
        current=_current_request(directory/'request.json',data)
        verify_sources(data)
        if verify_manager_domain(data)!=record['manager_binding']:raise ValueError('external manager identity changed')
        if data['source_sha256']!=sha256(Path(__file__).read_bytes()).hexdigest():raise ValueError('recovery source changed')
        if current['phase']!='release' and process_identity(data['owner'][0])==data['owner']:raise ValueError('live mutation owner requires reconciliation')
        if record['new_family'] is None and any(fingerprint(path)!=saved for path,saved in record['original_target_identities'].items()):
            raise ValueError('original unit file identity changed before handoff')
        if record.get('stopping') or _dependencies(root)!=record['dependencies']:raise ValueError('uncertain stop or changed unit dependencies')
        if any(not same_pause(v,_timer(u)) for u,v in record['paused'].items()):raise ValueError('timer ownership changed')
        info=Path(data['shared_lock']).lstat()
        if [info.st_dev,info.st_ino]!=record['lock_identity']:raise ValueError('original serving lock replaced')
        with SharedScoreLock(data['shared_lock']) as lock:
            family=record['old_family'] if _matches(record['old_targets']) else record['new_family'] if record['new_targets'] and _matches(record['new_targets']) else None
            if family is None:raise ValueError('mixed or absent family files require reconciliation')
            if record['new_family'] is not None:
                _systemctl('daemon-reload');_verify_family(directory,Path(family),effective=True)
                lock.verify();verify_sources(data)
                latest=_current_request(directory/'request.json',data)
                if latest!=current or verify_manager_domain(data)!=record['manager_binding'] or _dependencies(root)!=record['dependencies']:
                    raise ValueError('recovery ownership changed during verification')
                targets=record['old_targets'] if family==record['old_family'] else record['new_targets']
                if not _matches(targets):raise ValueError('family files changed during recovery verification')
            elif family!=record['old_family']:raise ValueError('unknown pre-handoff family')
            if any(not same_pause(paused,_timer(unit)) for unit,paused in record['paused'].items()):
                raise ValueError('timer ownership changed during recovery verification')
            for unit,paused in record['paused'].items():
                if not same_pause(paused,_timer(unit)):raise ValueError('timer ownership changed during recovery')
                if record['original'][unit]['ActiveState']=='active':_systemctl('start',unit)
            record['phase']='restored';record['restored_family']=family;save(path,record)
    except BaseException as error:
        record.update(phase='reconciliation_required',reason=str(error));save(path,record);raise


def main():
    import argparse,sys
    if '--verify-family' in sys.argv[1:]:
        parser=argparse.ArgumentParser()
        parser.add_argument('--verify-family',type=Path,required=True)
        parser.add_argument('--verification-request',type=Path,required=True)
        parser.add_argument('--verification-pin',required=True)
        parser.add_argument('--verification-output',type=Path,required=True)
        parser.add_argument('--verify-effective',action='store_true');args=parser.parse_args()
        try:_verification_worker(args.verification_request,args.verification_pin,args.verify_family,args.verification_output,effective=args.verify_effective)
        except Exception:raise SystemExit(1) from None
        return
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True);parser.add_argument('--nonce',required=True);parser.add_argument('--recover',action='store_true');args=parser.parse_args()
    if len(args.nonce)!=32 or any(c not in '0123456789abcdef' for c in args.nonce):raise ValueError('owned reservation nonce required')
    directory=Path(read(args.config)['state_directory'])/'activation-reservations'/args.nonce
    if args.recover:recover(directory)
    else:
        with cancellation_boundary():watch(directory)




@contextmanager
def activation_lock(run):
    """Trusted installed config selects exclusion; run path cannot select a lock."""
    from household_native_training import daily_lock
    import fcntl
    config=Path('/home/sat/.local/state/earthship-weather/audit-rollout-8f3747-20261020-native/native-config.json')
    state=Path(read(config)['state_directory']);run=Path(run)
    if run.resolve()!=run or run.parent!=state:raise ValueError('activation run outside trusted learner state')
    path=state/'daily.lock';descriptor=os.environ.get('EARTHSHIP_NATIVE_DAILY_LOCK_FD')
    if descriptor is None:
        with daily_lock(path) as lock:yield lock
    else:
        from openhab_runtime_io import SharedScoreLock
        lock=SharedScoreLock(path);lock.fd=int(descriptor)
        info=os.fstat(lock.fd);lock.identity=(info.st_dev,info.st_ino);lock.verify()
        # Same inherited open-file-description owns the parent's exclusion.
        # An unlocked or unrelated descriptor never bypasses this kernel check.
        fcntl.flock(lock.fd,fcntl.LOCK_EX|fcntl.LOCK_NB);lock.verify()
        yield lock


def run_activation_child(command,*,environment,lock,guard,seconds=600):
    """Graceful cancellation first, reap before external schedule restoration."""
    if not 0<seconds<=600:raise ValueError('original activation child bound required')
    child=subprocess.Popen(command,env=environment,pass_fds=(lock.fd,))
    deadline=time.monotonic()+seconds
    try:
        while child.poll() is None:
            lock.verify();guard()
            if time.monotonic()>=deadline:raise TimeoutError('activation child deadline exceeded')
            time.sleep(.1)
        if child.returncode:raise subprocess.CalledProcessError(child.returncode,command)
    except BaseException:
        with cleanup_boundary():
            if child.poll() is None:child.terminate()
            try:child.wait(timeout=min(15,max(.01,deadline-time.monotonic())))
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
        raise

if __name__=='__main__':main()
