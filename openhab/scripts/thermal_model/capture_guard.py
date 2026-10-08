"""Require capped Linux capture execution and bound its worker lifetime.

This helper creates no scope, performs no source reads and confers no release
or fitting authority. A trusted capture command must supply its fixed worker.
"""
import os
from pathlib import Path,PurePosixPath
import signal
import subprocess
from time import monotonic,sleep


def _small_text(path):
    with Path(path).open('rb') as stream:
        data=stream.read(4097)
    if len(data)>4096:raise ValueError('bounded resource metadata required')
    return data.decode('ascii').strip()


def verify_resource_limits(*,cgroup_root=Path('/sys/fs/cgroup'),proc_cgroup=Path('/proc/self/cgroup')):
    try:
        rows=_small_text(proc_cgroup).splitlines()
        if len(rows)!=1 or not rows[0].startswith('0::/'):raise ValueError('unified capture cgroup required')
        path=PurePosixPath(rows[0][3:])
        if '..' in path.parts or str(path)!=rows[0][3:]:raise ValueError('normalized capture cgroup required')
        root=Path(cgroup_root).resolve();leaf=root.joinpath(*path.parts[1:])
        if leaf.resolve()!=leaf or not leaf.is_relative_to(root):raise ValueError('contained capture cgroup required')
        quota,period=map(int,_small_text(leaf/'cpu.max').split())
        memory=int(_small_text(leaf/'memory.max'));swap=int(_small_text(leaf/'memory.swap.max'))
        tasks=int(_small_text(leaf/'pids.max'))
        try:weight=_small_text(leaf/'io.weight').splitlines()
        except FileNotFoundError:
            priority=subprocess.check_output(['/usr/bin/ionice','-p',str(os.getpid())],stderr=subprocess.DEVNULL,timeout=1,env={'LC_ALL':'C'})
            if priority.strip()!=b'idle':raise ValueError('verified idle IO priority required without IO controller')
        else:
            # Refuse device-specific overrides as well as a relaxed default.
            if len(weight)!=1 or len(weight[0].split())!=2 or weight[0].split()[0]!='default':raise ValueError('bounded capture IO weight required')
            io=int(weight[0].split()[1])
            if not 0<io<=10:raise ValueError('bounded capture IO weight required')
        if not (0<quota and 0<period and quota*4<=period and 0<memory<=805306368 and swap==0 and 0<tasks<=48):
            raise ValueError('capture resource limits exceed approved caps')
    except (OSError,UnicodeError,IndexError,TypeError,ValueError,subprocess.SubprocessError):
        raise ValueError('verified CPU memory swap task and IO capture caps required') from None


def run_guarded_capture(argv,*,seconds=90):
    if (type(seconds) is not int or not 1<=seconds<=90 or not isinstance(argv,(tuple,list)) or not 1<=len(argv)<=64 or
            any(not isinstance(arg,str) or not arg or '\0' in arg or len(arg)>8192 for arg in argv) or
            sum(len(arg) for arg in argv)>32768 or not Path(argv[0]).is_absolute()):
        raise ValueError('bounded explicit capture worker and deadline required')
    verify_resource_limits()
    if os.getpriority(os.PRIO_PROCESS,0)<15:raise ValueError('capture requires lowered scheduling priority')
    env=dict(os.environ,EARTHSHIP_GUARDED_CAPTURE_WORKER='1',EARTHSHIP_REMOTE_QUALIFICATION_FIT='0',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    deadline=monotonic()+seconds
    worker=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                            env=env,start_new_session=True,close_fds=True)
    try:
        while True:
            remaining=deadline-monotonic()
            if remaining<=0:raise ValueError('capture worker deadline exceeded')
            # Keep the leader unreaped until group cleanup so its PID cannot be reused.
            result=os.waitid(os.P_PID,worker.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            if result is not None:
                return result.si_status if result.si_code==os.CLD_EXITED else -result.si_status
            sleep(min(.05,remaining))
    finally:
        # The worker owns this fresh process group; signal only that group.
        try:os.killpg(worker.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        worker.wait(timeout=2)
