"""Live publication caps using kernel metadata, outside the fitted runtime.

The idle-IO fallback reads this process's priority directly. It neither changes
priority nor launches a child for each original-source access.
"""
import ctypes,math,os,stat
from contextlib import contextmanager
from pathlib import Path,PurePosixPath
from thermal_model.capture_guard import _small_text


def current_ioprio():
    # Verified against the installed x86_64 Linux syscall ABI, not guessed for
    # other architectures. Unknown hosts must not weaken this check.
    if (os.uname().sysname!='Linux' or os.uname().machine!='x86_64' or
            ctypes.sizeof(ctypes.c_void_p)!=8 or ctypes.sizeof(ctypes.c_long)!=8):
        raise ValueError('known publication IO-priority ABI required')
    libc=ctypes.CDLL(None,use_errno=True)
    syscall=libc.syscall;syscall.restype=ctypes.c_long
    value=syscall(ctypes.c_long(252),ctypes.c_int(1),ctypes.c_int(os.getpid()))
    if value<0:raise ValueError('publication kernel IO priority unavailable')
    return int(value)


_parsed_leaf=None
_cap_paths=None


def _leaf():
    global _parsed_leaf
    row=_small_text('/proc/self/cgroup')
    parsed=_parsed_leaf
    if parsed is None or parsed[0]!=row:
        if len(row.splitlines())!=1 or not row.startswith('0::/'):
            raise ValueError('unified publication cgroup required')
        path=PurePosixPath(row[3:]);original_root=Path('/sys/fs/cgroup');root=original_root.resolve()
        if path.root!='/' or '..' in path.parts or str(path)!=row[3:]:
            raise ValueError('normalized publication cgroup required')
        leaf=root.joinpath(*path.parts[1:])
        if leaf.resolve()!=leaf or not leaf.is_relative_to(root):raise ValueError('contained publication cgroup required')
        parsed=(row,leaf,tuple(reversed(leaf.parents))+(leaf,))
        _parsed_leaf=parsed if original_root==root else None
    _,leaf,components=parsed
    for component in components:
        if not stat.S_ISDIR(component.lstat().st_mode):
            raise ValueError('publication cgroup path is no longer a real directory')
    return leaf


def _resource_text(path):
    # Read fresh bytes with the same bound/encoding as the fitted helper.
    with open(path,'rb') as stream:data=stream.read(4097)
    if len(data)>4096:raise ValueError('bounded resource metadata required')
    return data.decode('ascii').strip()


def _paths(leaf):
    global _cap_paths
    if _cap_paths is None or _cap_paths[0]!=leaf:
        _cap_paths=(leaf,{name:leaf/name for name in ('cpu.max','memory.max','memory.swap.max','pids.max','io.weight')})
    return _cap_paths[1]


SHARED_PRODUCTION_POOL = True
SHARED_CGROUP_ROOT = Path('/sys/fs/cgroup')


def _shared_pool_limit(leaf):
    """Recognize only the owned pool, with fresh parent kernel limits.

    Kept self-contained so pinned current admission also works when numerical
    code is loaded from an archive predating the shared launcher.
    """
    if leaf.parent.name != 'earthship-work.slice':
        return None
    uid=os.getuid()
    expected=SHARED_CGROUP_ROOT/f'user.slice/user-{uid}.slice/user@{uid}.service/earthship.slice/earthship-work.slice'
    name=leaf.name
    if (leaf.parent!=expected or leaf.resolve()!=leaf or
            not name.startswith('earthship-job-') or not name.endswith('.scope') or
            len(name)!=52 or any(c not in '0123456789abcdef' for c in name[14:-6])):
        raise ValueError('owned shared worker ancestry required')
    parent=leaf.parent
    quota,period=map(int,_resource_text(parent/'cpu.max').split())
    memory=int(_resource_text(parent/'memory.max'))
    high=int(_resource_text(parent/'memory.high'))
    swap=int(_resource_text(parent/'memory.swap.max'))
    tasks=int(_resource_text(parent/'pids.max'))
    if not (0<quota<=8*period and period>0 and 0<high<=memory<=6*1024**3 and swap==0 and 0<tasks<=256):
        raise ValueError('verified shared parent budget required')
    return memory


def publication_resource_preflight(*,leaf=None,meminfo=Path('/proc/meminfo'),pressure=Path('/proc/pressure/memory'),
        get_nice=lambda:os.getpriority(os.PRIO_PROCESS,0),get_ioprio=current_ioprio,environ=None):
    try:
        leaf=_leaf() if leaf is None else Path(leaf)
        paths=_paths(leaf)
        shared_limit=_shared_pool_limit(leaf)
        quota_text,period_text=_resource_text(paths['cpu.max']).split()
        period=int(period_text)
        quota=None if quota_text=='max' else int(quota_text)
        memory=int(_resource_text(paths['memory.max']));swap=int(_resource_text(paths['memory.swap.max']))
        tasks=int(_resource_text(paths['pids.max']))
        if shared_limit is None:
            valid=quota is not None and 0<quota<=period and 0<period and 0<memory<=268435456 and swap==0 and 0<tasks<=24
        else:
            valid=period>0 and (quota is None or 0<quota<=8*period) and 0<memory<=shared_limit and swap==0 and 0<tasks<=128
        if not valid:raise ValueError('publication caps exceed approved limits')
        try:weight=_resource_text(paths['io.weight']).splitlines()
        except FileNotFoundError:
            priority=get_ioprio()
            if type(priority) is not int or not 0<=priority<=65535 or priority>>13!=3:
                raise ValueError('verified idle publication IO required')
        else:
            if len(weight)!=1 or len(weight[0].split())!=2 or weight[0].split()[0]!='default' or not 0<int(weight[0].split()[1])<=(100 if shared_limit is not None else 10):
                raise ValueError('bounded publication IO weight required')
        nice=get_nice()
        if type(nice) is not int or nice<15:raise ValueError('lowered publication scheduling priority required')
        available=[]
        for line in _resource_text(meminfo).splitlines():
            cells=line.split()
            if cells and cells[0]=='MemAvailable:':
                if len(cells)!=3 or not cells[1].isascii() or not cells[1].isdecimal() or cells[2]!='kB':
                    raise ValueError('publication memory metadata unavailable')
                available.append(int(cells[1]))
        if len(available)!=1 or available[0]<1572864:raise ValueError('publication memory headroom unavailable')
        seen=set()
        for line in _resource_text(pressure).splitlines():
            cells=line.split()
            if not cells or cells[0] not in {'some','full'} or cells[0] in seen:raise ValueError('publication PSI metadata unavailable')
            seen.add(cells[0]);values={}
            for part in cells[1:]:
                key,value=part.split('=',1)
                if key in values:raise ValueError('publication PSI metadata unavailable')
                values[key]=value
            average=float(values['avg10'])
            threshold=(5. if cells[0]=='some' else 1.) if shared_limit is not None else .5
            if not math.isfinite(average) or not 0<=average<=threshold:raise ValueError('publication memory pressure unavailable')
        if seen!={'some','full'}:raise ValueError('complete publication PSI metadata required')
        environment=os.environ if environ is None else environ
        if any(environment.get(key)!='1' for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):
            raise ValueError('one numerical thread required')
    except (OSError,UnicodeError,ValueError,TypeError,KeyError,IndexError):
        raise ValueError('verified publication resources required') from None


@contextmanager
def publication_geometry_policy():
    """Use current operational admission around original native calculations."""
    import astro_geometry_worker as worker
    publication_resource_preflight()
    previous=worker._resource_preflight
    worker._resource_preflight=publication_resource_preflight
    try:
        yield
    finally:
        worker._resource_preflight=previous


@contextmanager
def publication_native_policy():
    """Retain fitted adapter bytes while selecting current operational limits."""
    import native_thermal_live as native
    publication_resource_preflight()
    previous=native._resource_preflight
    native._resource_preflight=publication_resource_preflight
    try:
        yield
    finally:
        native._resource_preflight=previous
