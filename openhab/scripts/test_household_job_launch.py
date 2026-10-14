"""Concurrent launch admission remains serialized until a unit exists."""
import threading
from pathlib import Path
from household_job_budget import GiB,MiB,AdmissionDeferred
from test_household_job_pool import pool


def test_second_launcher_counts_first_scope_before_allocating(tmp_path):
    from household_job_launch import launch_job
    root,child=pool(tmp_path)
    for p in child.iterdir():p.unlink()
    child.rmdir();(root/'memory.current').write_text('0')
    spawned=threading.Event();finish=threading.Event();failures=[]
    class Process:
        def cancel(self):pass
        def authorize(self):pass
        def poll(self):return 0 if finish.is_set() else None
        def wait(self):return 0
    def spawn(command,*,unit,memory_bytes,production,tasks,seconds):
        target=root/unit;target.mkdir()
        (target/'memory.max').write_text(str(memory_bytes));(target/'memory.swap.max').write_text('0')
        (target/'memory.current').write_text('0');spawned.set()
        return Process()
    kwargs=dict(pool_path=root,lock_path=tmp_path/'admission.lock',minimum_bytes=256*MiB,
        preferred_bytes=GiB,reserve_bytes=3*GiB,available=lambda:4*GiB,spawn=spawn,health=lambda:None)
    def first():
        try:assert launch_job(['/usr/bin/true'],**kwargs)==0
        except Exception as error:failures.append(error)
    thread=threading.Thread(target=first);thread.start()
    try:
        assert spawned.wait(3)
        try:launch_job(['/usr/bin/true'],**kwargs)
        except AdmissionDeferred:pass
        else:raise AssertionError('both launchers promised the same RAM')
        assert len([p for p in root.iterdir() if p.is_dir()])==1
    finally:finish.set();thread.join(5)
    assert not thread.is_alive() and failures==[]


def test_finished_command_status_is_returned_without_waiting_for_vanished_scope(tmp_path):
    from household_job_launch import launch_job
    root,_=pool(tmp_path)
    class Process:
        def cancel(self):pass
        def authorize(self):pass
        def poll(self):return 7
        def wait(self):return 7
    assert launch_job(['/usr/bin/false'],pool_path=root,lock_path=tmp_path/'gate.lock',
        minimum_bytes=256*MiB,preferred_bytes=512*MiB,reserve_bytes=3*GiB,
        available=lambda:8*GiB,spawn=lambda *a,**kw:Process())==7


def test_spawning_failure_releases_admission_lock(tmp_path):
    import pytest
    from household_job_launch import launch_job,admission_gate
    root,_=pool(tmp_path)
    def failed(*a,**kw):raise OSError('cannot start scope')
    path=tmp_path/'gate.lock'
    with pytest.raises(OSError):
        launch_job(['/usr/bin/true'],pool_path=root,lock_path=path,
            minimum_bytes=256*MiB,preferred_bytes=512*MiB,reserve_bytes=3*GiB,
            available=lambda:8*GiB,spawn=failed)
    with admission_gate(path,seconds=.1):pass


def test_pressure_refusal_stops_only_the_scope_created_by_this_launcher(tmp_path):
    import pytest
    from household_job_launch import launch_job
    root,other=pool(tmp_path);owned=[];stopped=[];checks=[]
    class Process:
        def cancel(self):pass
        def authorize(self):pass
        def poll(self):return None
        def wait(self):return 0
    def spawn(command,*,unit,memory_bytes,**kw):
        leaf=root/unit;leaf.mkdir();(leaf/'memory.max').write_text(str(memory_bytes))
        (leaf/'memory.swap.max').write_text('0');owned.append(unit);return Process()
    def health():
        checks.append(1)
        if len(checks)>1:raise AdmissionDeferred('sustained pressure')
    with pytest.raises(AdmissionDeferred):
        launch_job(['/usr/bin/true'],pool_path=root,lock_path=tmp_path/'gate.lock',
            minimum_bytes=256*MiB,preferred_bytes=512*MiB,reserve_bytes=3*GiB,
            available=lambda:8*GiB,spawn=spawn,health=health,stop=stopped.append)
    assert stopped==owned and len(stopped)==1
    assert other.name not in stopped and other.exists()


def test_unconfirmed_scope_is_stopped_before_gate_can_be_reused(tmp_path,monkeypatch):
    import pytest
    import household_job_launch as launch
    root,_=pool(tmp_path);stopped=[];ticks=[0]
    class Clock:
        @staticmethod
        def monotonic():ticks[0]+=20;return ticks[0]
        @staticmethod
        def sleep(seconds):pass
    class Process:
        def cancel(self):pass
        def authorize(self):pass
        def poll(self):return None
        def wait(self):return 0
    monkeypatch.setattr(launch,'time',Clock)
    gate=tmp_path/'gate.lock'
    with pytest.raises(TimeoutError):
        launch.launch_job(['/usr/bin/true'],pool_path=root,lock_path=gate,
            minimum_bytes=256*MiB,preferred_bytes=512*MiB,reserve_bytes=3*GiB,
            available=lambda:8*GiB,spawn=lambda *a,**kw:Process(),health=lambda:None,stop=stopped.append)
    assert len(stopped)==1 and stopped[0].startswith('earthship-job-')
    with launch.admission_gate(gate):pass


def test_admission_remains_locked_during_failed_start_cleanup(tmp_path,monkeypatch):
    import pytest
    import household_job_launch as launch
    root,_=pool(tmp_path);gate=tmp_path/'gate.lock';events=[]
    class Process:
        def cancel(self):pass
        def authorize(self):pass
        def poll(self):return None
        def wait(self):return 0
        def cancel(self):events.append('cancel')
        def authorize(self):events.append('authorize')
    def spawn(command,*,unit,**kw):
        leaf=root/unit;leaf.mkdir()
        # Wrong cap forces an unconfirmed start failure.
        (leaf/'memory.max').write_text('1')
        return Process()
    def stop(unit):
        events.append('stop')
        with pytest.raises(AdmissionDeferred):
            with launch.admission_gate(gate,seconds=.05):pass
    with pytest.raises(ValueError,match='differs'):
        launch.launch_job(['/usr/bin/true'],pool_path=root,lock_path=gate,
            minimum_bytes=256*MiB,preferred_bytes=512*MiB,
            available=lambda:8*GiB,spawn=spawn,health=lambda:None,stop=stop)
    assert events==['cancel','stop']


def test_pending_command_requires_explicit_start_permission(tmp_path, tmp_path_factory):
    import subprocess,sys
    from household_job_launch import StartupPermission
    shim=Path(__file__).with_name('household_job_start.py')
    marker=tmp_path/'executed'
    command=[sys.executable,str(shim),'--socket',None,'--',sys.executable,
        '-c','from pathlib import Path; Path('+repr(str(marker))+').touch()']
    with StartupPermission(tmp_path_factory.mktemp('permit')) as permit:
        command[3]=str(permit.path)
        child=subprocess.Popen(command)
        connection,_=permit.listener.accept()
        assert not marker.exists()
        connection.close() # Parent disappears without granting admission.
        assert child.wait(timeout=3)!=0
    assert not marker.exists()
    with StartupPermission(tmp_path_factory.mktemp('permit')) as permit:
        command[3]=str(permit.path)
        child=subprocess.Popen(command)
        permit.authorize()
        assert child.wait(timeout=3)==0
    assert marker.exists()


def test_delayed_shim_after_cancellation_never_executes(tmp_path, tmp_path_factory):
    import subprocess,sys
    from household_job_launch import StartupPermission
    marker=tmp_path/'late-command'
    with StartupPermission(tmp_path_factory.mktemp('late')) as permit:
        address=str(permit.path)
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('household_job_start.py')),
        '--socket',address,'--',sys.executable,'-c',
        'from pathlib import Path; Path('+repr(str(marker))+').touch()'],timeout=3)
    assert result.returncode==75 and not marker.exists()


def test_permitted_shim_preserves_arguments_and_exit_status(tmp_path_factory):
    import subprocess,sys
    from household_job_launch import StartupPermission
    argument='spaces ; $HOME `literal`'
    with StartupPermission(tmp_path_factory.mktemp('argv')) as permit:
        child=subprocess.Popen([sys.executable,str(Path(__file__).with_name('household_job_start.py')),
            '--socket',str(permit.path),'--',sys.executable,'-c',
            'import sys; print(sys.argv[1]); sys.exit(7)',argument],stdout=subprocess.PIPE,text=True)
        permit.authorize()
        output,_=child.communicate(timeout=3)
    assert child.returncode==7 and output.strip()==argument


def test_collection_profile_cannot_expand_its_original_leaf_budget(tmp_path):
    import pytest
    from household_job_launch import launch_job
    root,_=pool(tmp_path)
    with pytest.raises(ValueError,match='collection'):
        launch_job(['/usr/bin/true'],pool_path=root,lock_path=tmp_path/'gate.lock',
            minimum_bytes=256*MiB,preferred_bytes=512*MiB,tasks=24,seconds=90,
            collection=True,available=lambda:8*GiB,health=lambda:None)


def test_collection_scope_keeps_strict_cpu_memory_tasks_and_io(monkeypatch):
    import household_job_launch as launch
    calls=[]
    class Permit:
        path=Path('/fixture/permission')
        def __init__(self,*args):pass
        def close(self):pass
    monkeypatch.setattr(launch,'StartupPermission',Permit)
    monkeypatch.setattr(launch.subprocess,'Popen',lambda argv,**kw:calls.append(argv))
    launch.start_scope(['/usr/bin/true'],unit='earthship-job-test.scope',memory_bytes=256*MiB,
        production=True,tasks=24,seconds=90,collection=True)
    argv=calls[0]
    for setting in ('CPUQuota=20%','MemoryMax=268435456','MemorySwapMax=0','TasksMax=24','IOWeight=10'):
        assert setting in argv
