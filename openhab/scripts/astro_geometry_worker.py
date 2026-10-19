"""Bounded native-library batch acquisition, with no OpenHAB/provider writes.

The caller captures configured source metadata and holds the shared ML lock.
The worker pins original request/code/library bytes and delegates process-group
supervision to the existing pressure worker. Cache replay needs no JVM.
"""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import os,stat,pwd
import astro_geometry as geometry
from thermal_model.training_pressure_guard import run_training_worker
from thermal_model.serial_publication_caps import _resource_preflight

ROOT=Path(__file__).resolve().parents[2]
JAVA_SOURCE=ROOT/'scripts/java/NativeSolarGeometry.java'
ROLES={'astro_binding','openhab_core','unit_api','indriya','pax_logging_api','osgi_core'}
NATIVE_ROOTS=(Path('/var/lib/openhab/tmp/kar'),Path('/usr/share/openhab/runtime'))
MAX_BATCH_POINTS=128 # Native result must fit the original worker's 16 KiB pipe.
CODE_FILES=('openhab/scripts/astro_geometry_worker.py','openhab/scripts/astro_geometry.py',
            'openhab/scripts/astro_forecast_context.py','scripts/java/NativeSolarGeometry.java',
            'openhab/scripts/thermal_model/training_pressure_guard.py','openhab/scripts/thermal_model/serial_publication_caps.py')


def _read(path,*,maximum,guard,trusted_owners=None):
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path:
        raise ValueError('resolved native input path required')
    guard();fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        owners=(0,os.getuid()) if trusted_owners is None else trusted_owners
        if (not stat.S_ISREG(before.st_mode) or before.st_uid not in owners or
                before.st_mode & 0o022 or not 0<before.st_size<=maximum):
            raise ValueError('bounded trusted native input required')
        raw=bytearray()
        while True:
            guard();part=os.read(fd,min(262144,maximum+1-len(raw)))
            if not part:break
            raw.extend(part)
            if len(raw)>maximum:raise ValueError('native input exceeds bound')
        after=os.fstat(fd);fields=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if fields(before)!=fields(after):raise ValueError('native input changed while reading')
        return bytes(raw)
    finally:os.close(fd)


def collector_identity(*,guard):
    hashes={name:sha256(_read(ROOT/name,maximum=2097152,guard=guard)).hexdigest() for name in CODE_FILES}
    return sha256(geometry._canonical(hashes)).hexdigest()


def _openhab_uid():
    try:return pwd.getpwnam('openhab').pw_uid
    except KeyError:return None


def runtime_identity(library_paths,*,binding_version,guard):
    if not isinstance(library_paths,dict) or set(library_paths)!=ROLES:
        raise ValueError('exact native calculation library roles required')
    identities={}
    for role in sorted(ROLES):
        path=Path(library_paths[role]);owners=(0,os.getuid())
        if any(path.is_relative_to(root) for root in NATIVE_ROOTS):
            service_owner=_openhab_uid()
            if service_owner is not None:owners+= (service_owner,)
        identities[role]=sha256(_read(path,maximum=16777216,guard=guard,trusted_owners=owners)).hexdigest()
    return geometry._runtime(dict(binding_version=binding_version,libraries=identities,
                                  collector_sha256=collector_identity(guard=guard)))


def capture_batch(request,source,*,library_paths,scratch,guard,java_path=Path('/usr/bin/java'),
                  clock=lambda:datetime.now(timezone.utc)):
    _resource_preflight();guard();request=geometry._request(request);source=geometry._source(source,request)
    if len(request['instants'])>MAX_BATCH_POINTS:
        raise ValueError('native worker batch exceeds bounded result budget')
    directory=Path(scratch)
    info=directory.lstat()
    if (not directory.is_absolute() or directory.resolve()!=directory or
            not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700):
        raise ValueError('owned private native scratch directory required')
    java=Path(java_path).resolve();java_raw=_read(java,maximum=2097152,guard=guard)
    if not os.access(java,os.X_OK):raise ValueError('native Java launcher unavailable')
    runtime=runtime_identity(library_paths,binding_version=source['native_runtime']['binding_version'],guard=guard)
    if runtime!=source['native_runtime']:raise ValueError('original native runtime changed')
    site=request['site'];body=('\n'.join([request['requested_at'],str(site['latitude'])+'\t'+str(site['longitude']),*request['instants']])+'\n').encode('ascii')
    if len(body)>16384:raise ValueError('bounded native request file required')
    path=directory/(uuid4().hex+'.native-geometry-request.txt')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
    def unchanged():
        guard()
        if _read(path,maximum=16384,guard=guard)!=body:raise ValueError('original native request changed')
    try:
        unchanged()
        env=dict(os.environ)
        for key in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS','CLASSPATH'):env.pop(key,None)
        env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
                   EARTHSHIP_QUALIFICATION_FIT='0',EARTHSHIP_REMOTE_QUALIFICATION_FIT='0')
        argv=[str(java),'-XX:ActiveProcessorCount=1','-XX:+UseSerialGC','-Xms16m','-Xmx64m',
              '-XX:MaxMetaspaceSize=64m','-XX:ReservedCodeCacheSize=32m','--class-path',
              os.pathsep.join(str(Path(library_paths[role])) for role in sorted(ROLES)),str(JAVA_SOURCE),str(path)]
        status,raw=run_training_worker(argv,check=unchanged,seconds=25,env=env)
        if status!=0:raise ValueError('native geometry worker refused or incomplete')
        unchanged()
        if (runtime_identity(library_paths,binding_version=runtime['binding_version'],guard=guard)!=runtime or
                _read(java,maximum=2097152,guard=guard)!=java_raw):
            raise ValueError('original native calculation inputs changed')
        result=geometry.build_cache(request,source,native_output=raw,computed_at=clock());guard()
        return result
    finally:
        # Delete only the exact temporary request this worker created.
        try:
            if _read(path,maximum=16384,guard=guard)==body:path.unlink()
        except (OSError,ValueError):pass
