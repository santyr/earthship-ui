"""Capture resource preflight and bounded worker lifetime; no household I/O."""
import os
from pathlib import Path
import sys
import pytest


@pytest.fixture(autouse=True)
def synthetic_host_headroom(monkeypatch):
    # Resource/lifecycle tests use synthetic cgroups; host capacity is covered
    # independently in test_thermal_capture_headroom.py.
    from thermal_model import capture_guard
    monkeypatch.setattr(capture_guard,'verify_host_headroom',lambda:None)


def module():
    from thermal_model import capture_guard
    return capture_guard


def fixture_limits(tmp_path):
    root=tmp_path/'cgroup';leaf=root/'synthetic.scope';leaf.mkdir(parents=True)
    values={'cpu.max':'25000 100000','memory.max':'805306368','memory.swap.max':'0','pids.max':'48','io.weight':'default 10'}
    for name,value in values.items():(leaf/name).write_text(value)
    proc=tmp_path/'proc-cgroup';proc.write_text('0::/synthetic.scope\n')
    return root,leaf,proc


def test_resource_preflight_accepts_declared_caps(tmp_path):
    root,leaf,proc=fixture_limits(tmp_path)
    module().verify_resource_limits(cgroup_root=root,proc_cgroup=proc)


@pytest.mark.parametrize('name,value',[('cpu.max','max 100000'),('cpu.max','26000 100000'),('memory.max','max'),('memory.swap.max','1'),('pids.max','49'),('io.weight','default 100'),('io.weight','default 10\n8:0 100')])
def test_resource_preflight_refuses_relaxed_caps(tmp_path,name,value):
    root,leaf,proc=fixture_limits(tmp_path);(leaf/name).write_text(value)
    with pytest.raises(ValueError):module().verify_resource_limits(cgroup_root=root,proc_cgroup=proc)


def test_resource_preflight_refuses_unified_path_escape(tmp_path):
    root,leaf,proc=fixture_limits(tmp_path);proc.write_text('0::/../outside\n')
    with pytest.raises(ValueError):module().verify_resource_limits(cgroup_root=root,proc_cgroup=proc)


def test_capture_guard_refuses_before_worker_without_caps(monkeypatch):
    source=module()
    def refuse():raise ValueError('missing caps')
    monkeypatch.setattr(source,'verify_resource_limits',refuse)
    monkeypatch.setattr(source.subprocess,'Popen',lambda *args,**kwargs:pytest.fail('uncapped worker launched'))
    with pytest.raises(ValueError):source.run_guarded_capture([sys.executable,'-c','pass'],seconds=1)


def test_capture_guard_runs_small_worker(tmp_path,monkeypatch):
    source=module();root,leaf,proc=fixture_limits(tmp_path)
    original=source.verify_resource_limits
    monkeypatch.setattr(source,'verify_resource_limits',lambda:original(cgroup_root=root,proc_cgroup=proc))
    monkeypatch.setattr(source.os,'getpriority',lambda *args:15)
    assert module().run_guarded_capture([sys.executable,'-c',"import os; assert os.getenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT')=='0'; assert os.getenv('OMP_NUM_THREADS')=='1'"],seconds=5)==0


def test_capture_guard_terminates_blocking_worker(tmp_path,monkeypatch):
    source=module();root,leaf,proc=fixture_limits(tmp_path)
    original=source.verify_resource_limits
    monkeypatch.setattr(source,'verify_resource_limits',lambda:original(cgroup_root=root,proc_cgroup=proc))
    monkeypatch.setattr(source.os,'getpriority',lambda *args:15)
    import time
    start=time.monotonic()
    with pytest.raises(ValueError,match='deadline'):
        module().run_guarded_capture([sys.executable,'-c','import time; time.sleep(20)'],seconds=1)
    assert time.monotonic()-start<4


@pytest.mark.parametrize('priority',[b'idle\n',b'none: prio 0\n'])
def test_missing_io_controller_requires_verified_idle_priority(tmp_path,monkeypatch,priority):
    source=module();root,leaf,proc=fixture_limits(tmp_path);(leaf/'io.weight').unlink()
    calls=[]
    def probe(argv,**kwargs):calls.append((argv,kwargs));return priority
    monkeypatch.setattr(source.subprocess,'check_output',probe)
    if priority.startswith(b'idle'):source.verify_resource_limits(cgroup_root=root,proc_cgroup=proc)
    else:
        with pytest.raises(ValueError):source.verify_resource_limits(cgroup_root=root,proc_cgroup=proc)
    assert calls[0][0]==['/usr/bin/ionice','-p',str(os.getpid())] and calls[0][1]['timeout']==1


@pytest.mark.parametrize('mode',['success','timeout'])
def test_cleanup_kills_inherited_worker_descendant(tmp_path,monkeypatch,mode):
    source=module();root,leaf,proc=fixture_limits(tmp_path);original=source.verify_resource_limits
    monkeypatch.setattr(source,'verify_resource_limits',lambda:original(cgroup_root=root,proc_cgroup=proc))
    monkeypatch.setattr(source.os,'getpriority',lambda *args:15)
    pin=tmp_path/'child.pid'
    code="import os,time; from pathlib import Path; child=os.fork(); Path(os.environ['CHILD_PIN']).write_text(str(child)) if child else time.sleep(20)"
    monkeypatch.setenv('CHILD_PIN',str(pin))
    if mode=='timeout':
        code+='; time.sleep(20)'
        with pytest.raises(ValueError,match='deadline'):source.run_guarded_capture([sys.executable,'-c',code],seconds=1)
    else:assert source.run_guarded_capture([sys.executable,'-c',code],seconds=5)==0
    child=int(pin.read_text());status=Path('/proc')/str(child)/'stat'
    # The killed orphan may briefly remain a zombie until init reaps it.
    from time import monotonic,sleep
    deadline=monotonic()+1
    while True:
        try:state=status.read_text().rsplit(')',1)[1].split()[0]
        except FileNotFoundError:break
        if state=='Z':break
        assert monotonic()<deadline,'worker descendant remained alive after cleanup'
        sleep(.01)


def test_guard_refuses_normal_scheduler_priority_before_worker(tmp_path,monkeypatch):
    source=module();root,leaf,proc=fixture_limits(tmp_path);original=source.verify_resource_limits
    monkeypatch.setattr(source,'verify_resource_limits',lambda:original(cgroup_root=root,proc_cgroup=proc))
    monkeypatch.setattr(source.os,'getpriority',lambda *args:0)
    monkeypatch.setattr(source.subprocess,'Popen',lambda *args,**kwargs:pytest.fail('normal priority worker launched'))
    with pytest.raises(ValueError):source.run_guarded_capture([sys.executable,'-c','pass'],seconds=1)


def test_signaled_worker_status_propagates(tmp_path,monkeypatch):
    source=module();root,leaf,proc=fixture_limits(tmp_path);original=source.verify_resource_limits
    monkeypatch.setattr(source,'verify_resource_limits',lambda:original(cgroup_root=root,proc_cgroup=proc))
    monkeypatch.setattr(source.os,'getpriority',lambda *args:15)
    assert source.run_guarded_capture([sys.executable,'-c','import os,signal; os.kill(os.getpid(),signal.SIGTERM)'],seconds=5)==-15
