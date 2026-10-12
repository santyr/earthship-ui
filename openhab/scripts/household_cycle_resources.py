"""Live publication caps using kernel metadata, outside the fitted runtime.

The idle-IO fallback reads this process's priority directly. It neither changes
priority nor launches a child for each original-source access.
"""
import ctypes,math,os
from pathlib import Path,PurePosixPath
from thermal_model.capture_guard import _small_text


def current_ioprio():
    # Verified against the installed x86_64 Linux syscall ABI, not guessed for
    # other architectures. Unknown hosts must not weaken this check.
    if os.uname().sysname!='Linux' or os.uname().machine!='x86_64':
        raise ValueError('known publication IO-priority ABI required')
    libc=ctypes.CDLL(None,use_errno=True)
    syscall=libc.syscall;syscall.restype=ctypes.c_long
    value=syscall(ctypes.c_long(252),ctypes.c_int(1),ctypes.c_int(os.getpid()))
    if value<0:raise ValueError('publication kernel IO priority unavailable')
    return int(value)


def _leaf():
    row=_small_text('/proc/self/cgroup')
    if len(row.splitlines())!=1 or not row.startswith('0::/'):
        raise ValueError('unified publication cgroup required')
    path=PurePosixPath(row[3:]);root=Path('/sys/fs/cgroup').resolve()
    if path.root!='/' or '..' in path.parts or str(path)!=row[3:]:
        raise ValueError('normalized publication cgroup required')
    leaf=root.joinpath(*path.parts[1:])
    if leaf.resolve()!=leaf or not leaf.is_relative_to(root):raise ValueError('contained publication cgroup required')
    return leaf


def publication_resource_preflight(*,leaf=None,meminfo=Path('/proc/meminfo'),pressure=Path('/proc/pressure/memory'),
        get_nice=lambda:os.getpriority(os.PRIO_PROCESS,0),get_ioprio=current_ioprio,environ=None):
    try:
        leaf=_leaf() if leaf is None else Path(leaf)
        quota,period=map(int,_small_text(leaf/'cpu.max').split())
        memory=int(_small_text(leaf/'memory.max'));swap=int(_small_text(leaf/'memory.swap.max'))
        tasks=int(_small_text(leaf/'pids.max'))
        if not (0<quota and 0<period and quota*5<=period and 0<memory<=268435456 and swap==0 and 0<tasks<=24):
            raise ValueError('publication caps exceed approved limits')
        try:weight=_small_text(leaf/'io.weight').splitlines()
        except FileNotFoundError:
            priority=get_ioprio()
            if type(priority) is not int or not 0<=priority<=65535 or priority>>13!=3:
                raise ValueError('verified idle publication IO required')
        else:
            if len(weight)!=1 or len(weight[0].split())!=2 or weight[0].split()[0]!='default' or not 0<int(weight[0].split()[1])<=10:
                raise ValueError('bounded publication IO weight required')
        nice=get_nice()
        if type(nice) is not int or nice<15:raise ValueError('lowered publication scheduling priority required')
        available=[]
        for line in _small_text(meminfo).splitlines():
            cells=line.split()
            if cells and cells[0]=='MemAvailable:':
                if len(cells)!=3 or not cells[1].isascii() or not cells[1].isdecimal() or cells[2]!='kB':
                    raise ValueError('publication memory metadata unavailable')
                available.append(int(cells[1]))
        if len(available)!=1 or available[0]<1572864:raise ValueError('publication memory headroom unavailable')
        seen=set()
        for line in _small_text(pressure).splitlines():
            cells=line.split()
            if not cells or cells[0] not in {'some','full'} or cells[0] in seen:raise ValueError('publication PSI metadata unavailable')
            seen.add(cells[0]);values={}
            for part in cells[1:]:
                key,value=part.split('=',1)
                if key in values:raise ValueError('publication PSI metadata unavailable')
                values[key]=value
            average=float(values['avg10'])
            if not math.isfinite(average) or not 0<=average<=.5:raise ValueError('publication memory pressure unavailable')
        if seen!={'some','full'}:raise ValueError('complete publication PSI metadata required')
        environment=os.environ if environ is None else environ
        if any(environment.get(key)!='1' for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):
            raise ValueError('one numerical thread required')
    except (OSError,UnicodeError,ValueError,TypeError,KeyError,IndexError):
        raise ValueError('verified publication resources required') from None
