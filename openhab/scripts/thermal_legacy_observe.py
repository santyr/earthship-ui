#!/usr/bin/env python3
"""Verify private legacy sources or explicitly run the original shadow cycle.

Default execution imports no legacy or numerical code. Explicit observation
runs only the compatible original shadow command, with optional diagnostics.
"""
import argparse
from hashlib import sha256
import fcntl,importlib,json,math,os,re,stat,subprocess,sys
from pathlib import Path,PurePosixPath

SCHEMA='earthship-thermal-legacy-observe-config/v1'
FIELDS={'schema','legacy_root','source_sha256','archive','shared_lock'}
REQUIRED={'thermal_intel.py','thermal_temperature_runtime.py','thermal_legacy_origin.py',
    'thermal_legacy_observe.py','thermal_model/artifacts.py','thermal_model/forcing_capture.py'}


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate private key')
        result[key]=value
    return result


def _nonfinite(_):raise ValueError('nonfinite private value')


def _directory(path):
    path=Path(path);info=path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid()
            or stat.S_IMODE(info.st_mode)!=0o700 or path.resolve(strict=True)!=path):
        raise ValueError('owned private resolved directory required')
    return path


def _read(path,maximum):
    path=Path(path);before=path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid()
            or stat.S_IMODE(before.st_mode)!=0o600 or before.st_nlink!=1
            or before.st_size>maximum or path.resolve(strict=True)!=path):
        raise ValueError('owned private original file required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as handle:
        opened=os.fstat(handle.fileno());raw=handle.read(maximum+1);after=os.fstat(handle.fileno())
    if (len(raw)!=before.st_size or len(raw)>maximum
            or (before.st_dev,before.st_ino)!=(opened.st_dev,opened.st_ino)
            or (opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
        raise ValueError('original file changed during read')
    return raw


def load_settings(path):
    path=Path(path);_directory(path.parent)
    value=json.loads(_read(path,16384),object_pairs_hook=_object,parse_constant=_nonfinite)
    if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA:
        raise ValueError('closed private legacy configuration required')
    for key in ('legacy_root','archive','shared_lock'):
        name=value[key]
        if not isinstance(name,str) or not 1<=len(name)<=1024 or not Path(name).is_absolute():
            raise ValueError('bounded absolute private path required')
    root=_directory(value['legacy_root']);archive=_directory(value['archive'])
    if root==archive or root.is_relative_to(archive) or archive.is_relative_to(root):
        raise ValueError('separate original code and diagnostic archive required')
    lock=Path(value['shared_lock']);_directory(lock.parent);_read(lock,8192)
    sources=value['source_sha256']
    if not isinstance(sources,dict) or not 2<=len(sources)<=64 or not REQUIRED<=set(sources):
        raise ValueError('complete bounded declared legacy sources required')
    for name,digest in sources.items():
        if not isinstance(name,str) or not 1<=len(name)<=256:raise ValueError('bounded original source name required')
        relative=PurePosixPath(name)
        if (relative.is_absolute() or str(relative)!=name or not name.endswith('.py')
                or any(part in ('.','..') for part in relative.parts)
                or not isinstance(digest,str) or re.fullmatch('[0-9a-f]{64}',digest) is None):
            raise ValueError('relative source and full original digest required')
    found=set();pending=[root];count=0;total=0
    while pending:
        directory=pending.pop();_directory(directory)
        for p in directory.iterdir():
            count+=1
            if count>256:raise ValueError('bounded legacy source inventory required')
            info=p.lstat()
            if stat.S_ISDIR(info.st_mode):pending.append(p);continue
            name=str(p.relative_to(root))
            if name not in sources:raise ValueError('unverified source inventory member')
            raw=_read(p,2000000);total+=len(raw)
            if total>2000000 or sha256(raw).hexdigest()!=sources[name]:
                raise ValueError('original source bytes differ')
            found.add(name)
    if found!=set(sources):raise ValueError('original source inventory incomplete')
    return value


def _small(path):
    with Path(path).open('rb') as handle:raw=handle.read(4097)
    if len(raw)>4096:raise ValueError('bounded resource metadata required')
    return raw.decode('ascii').strip()


def _resource_preflight(*,cgroup_root=Path('/sys/fs/cgroup'),proc_root=Path('/proc')):
    row=_small(proc_root/'self/cgroup')
    if not row.startswith('0::/') or '\n' in row:raise ValueError('unified cgroup required')
    relative=PurePosixPath(row[3:]);root=Path(cgroup_root).resolve()
    leaf=root.joinpath(*relative.parts[1:])
    if '..' in relative.parts or str(relative)!=row[3:] or leaf.resolve()!=leaf or not leaf.is_relative_to(root):
        raise ValueError('contained original cgroup required')
    quota,period=map(int,_small(leaf/'cpu.max').split())
    memory=int(_small(leaf/'memory.max'));swap=int(_small(leaf/'memory.swap.max'));tasks=int(_small(leaf/'pids.max'))
    if not (0<quota and 0<period and quota*5<=period and 0<memory<=268435456 and swap==0 and 0<tasks<=24):
        raise ValueError('strict shadow resource caps required')
    try:weight=_small(leaf/'io.weight').split()
    except FileNotFoundError:
        priority=subprocess.check_output(['/usr/bin/ionice','-p',str(os.getpid())],stderr=subprocess.DEVNULL,timeout=1,env={'LC_ALL':'C'})
        if priority.strip()!=b'idle':raise ValueError('idle IO priority required')
    else:
        if len(weight)!=2 or weight[0]!='default' or not 0<int(weight[1])<=10:
            raise ValueError('strict original IO weight required')
    if os.getpriority(os.PRIO_PROCESS,0)<15:raise ValueError('lowered shadow priority required')
    if any(os.environ.get(key)!='1' for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','PYTHONDONTWRITEBYTECODE')):
        raise ValueError('one numerical thread and no source bytecode writes required')
    available=[row.split() for row in _small(proc_root/'meminfo').splitlines() if row.startswith('MemAvailable:')]
    if len(available)!=1 or len(available[0])!=3 or available[0][2]!='kB' or int(available[0][1])<1572864:
        raise ValueError('shadow memory headroom unavailable')
    pressure=_small(proc_root/'pressure/memory').splitlines();seen=set()
    for line in pressure:
        cells=line.split();kind=cells[0];values=dict(cell.split('=',1) for cell in cells[1:]);avg=float(values['avg10'])
        if kind not in ('some','full') or kind in seen or not math.isfinite(avg) or not 0<=avg<=.5:
            raise ValueError('shadow memory pressure unavailable')
        seen.add(kind)
    if seen!={'some','full'}:raise ValueError('complete memory pressure required')


def _verify_loaded(settings):
    root=Path(settings['legacy_root']);prefixes={Path(name).parts[0].removesuffix('.py') for name in settings['source_sha256']}
    for name,module in list(sys.modules.items()):
        if name.split('.')[0] not in prefixes and name!='__main__':continue
        file=getattr(module,'__file__',None)
        if not file:continue
        p=Path(file).resolve()
        if not p.is_relative_to(root):raise ValueError('unrelated original module already loaded')
        relative=str(p.relative_to(root))
        if relative not in settings['source_sha256']:raise ValueError('undeclared original module loaded')
        if sha256(_read(p,2000000)).hexdigest()!=settings['source_sha256'][relative]:
            raise ValueError('loaded original module source differs')


def _observe(path,settings,lock_identity):
    root=Path(settings['legacy_root'])
    if Path(__file__).resolve()!=root/'thermal_legacy_observe.py':
        raise ValueError('executing entrypoint must be the pinned private source')
    prefixes={Path(name).parts[0].removesuffix('.py') for name in settings['source_sha256']}-{'thermal_legacy_observe'}
    if any(name.split('.')[0] in prefixes for name in sys.modules):
        raise ValueError('fresh original module namespace required')
    config_sha=sha256(_read(Path(path),16384)).hexdigest()
    def verify():
        if load_settings(path)!=settings or sha256(_read(Path(path),16384)).hexdigest()!=config_sha:
            raise ValueError('original settings changed')
        lock=Path(settings['shared_lock']).lstat()
        if (lock.st_dev,lock.st_ino)!=lock_identity:raise ValueError('original shared lock replaced')
        _verify_loaded(settings)
    # Reconcile after resource checks and lock acquisition, before importing
    # any protected original code. Later checks cannot undo import side effects.
    verify()
    sys.path.insert(0,str(root))
    legacy=importlib.import_module('thermal_intel')
    native=importlib.import_module('thermal_temperature_runtime')
    helper=importlib.import_module('thermal_legacy_origin')
    artifacts=importlib.import_module('thermal_model.artifacts')
    if artifacts.MODEL_SCHEMA!='earthship-thermal-model/v4':raise ValueError('compatible legacy v4 reader required')
    verify()
    def runtime():
        verify();r=helper.bind_legacy_runtime(root,sorted(settings['source_sha256']))
        if r['source_sha256']!=settings['source_sha256']:raise ValueError('actual original closure differs')
        return r
    observer=helper.LegacyOriginObserver(settings['archive'],runtime_provider=runtime,
        on_gap=lambda status:print(json.dumps(dict(status=status,release_authority=False)),file=sys.stderr))
    native.configured_shadow_temperatures=observer.wrap_native(native.configured_shadow_temperatures)
    legacy.capture_shadow_inputs=observer.wrap_capture(legacy.capture_shadow_inputs)
    # Literal existing shadow command: no training, release override or action.
    return legacy.main(['shadow','--publish'])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--observe',action='store_true')
    args=parser.parse_args(argv)
    base=dict(live_execution_requested=args.observe,release_authority=False,publication_delivery_verified=False)
    try:
        settings=load_settings(args.config)
        if not args.observe:
            print(json.dumps(dict(base,status='configuration_verified')));return 0
        _resource_preflight()
        os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        fd=os.open(settings['shared_lock'],os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        try:
            info=os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
                    or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):
                raise ValueError('owned original shared lock required')
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:print(json.dumps(dict(base,status='busy')));return 75
            status=_observe(args.config,settings,(info.st_dev,info.st_ino))
        finally:os.close(fd)
        print(json.dumps(dict(base,status='original_shadow_cycle_completed',original_exit_status=status)))
        return status
    except Exception:
        print(json.dumps(dict(base,status='unverified_failure')));return 1


if __name__=='__main__':raise SystemExit(main())
