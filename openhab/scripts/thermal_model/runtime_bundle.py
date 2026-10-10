"""Retain original declared publication sources and interpreter; never execute them.

The archive is private observational evidence. Dependency versions are retained;
replay/rollback still requires a separately retained compatible environment.
"""
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import stat
import sys
from uuid import uuid4

from .forcing_capture import _canonical,_private_directory
from .origin_capture import (_runtime,_source_bytes,_private_file,_object,build_runtime_binding)

SCHEMA='earthship-thermal-runtime-bundle/v1'
FIELDS={'schema','runtime','revision_paths','release_authorized','bundle_sha256'}
MAX_TOTAL_BYTES=128000000


def _digest(value):return sha256(_canonical(value)).hexdigest()


def _path(name):
    if not isinstance(name,str):raise ValueError('relative runtime source path required')
    path=PurePosixPath(name)
    if (path.is_absolute() or str(path)!=name or any(part in ('.','..') for part in path.parts) or
            len(name.encode())>256 or len(path.parts)>7 or not name.endswith('.py')):
        raise ValueError('relative bounded runtime source path invalid')
    return name


def _revision(paths,sources):
    if (not isinstance(paths,list) or not 1<=len(paths)<=64 or
            any(not isinstance(name,str) for name in paths) or len(set(paths))!=len(paths) or
            'thermal_intel.py' not in paths or (len(paths)==64 and 'thermal_model/origin_capture.py' not in paths)):raise ValueError('original ordered prediction closure required')
    digest=sha256()
    for name in paths:
        _path(name);raw=sources[name];encoded=name.encode()
        digest.update(len(encoded).to_bytes(4,'big'));digest.update(encoded)
        digest.update(len(raw).to_bytes(8,'big'));digest.update(raw)
    return digest.hexdigest()


def _owned_bytes(path,maximum):
    try:info=path.lstat()
    except OSError:raise ValueError('archived runtime file unavailable') from None
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or
            stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):
        raise ValueError('owned private runtime file required')
    return _source_bytes(path,maximum=maximum)


def _members(directory):
    found=set();pending=[directory];count=0
    while pending:
        current=pending.pop();_private_directory(current)
        for path in current.iterdir():
            count+=1
            if count>600:raise ValueError('runtime bundle tree exceeds bound')
            info=path.lstat()
            if stat.S_ISDIR(info.st_mode):pending.append(path)
            elif stat.S_ISREG(info.st_mode):found.add(str(path.relative_to(directory)))
            else:raise ValueError('runtime bundle contains unsupported entry')
    return found


def _verify(directory,*,address_required):
    _private_directory(directory)
    def reject(_):raise ValueError('nonfinite runtime bundle manifest')
    try:record=json.loads(_private_file(directory/'manifest.json'),object_pairs_hook=_object,parse_constant=reject)
    except (OSError,UnicodeDecodeError,json.JSONDecodeError):raise ValueError('runtime bundle manifest unavailable') from None
    if (not isinstance(record,dict) or set(record)!=FIELDS or record['schema']!=SCHEMA or
            record['release_authorized'] is not False):raise ValueError('closed runtime bundle contract required')
    body={key:value for key,value in record.items() if key!='bundle_sha256'}
    if _digest(body)!=record['bundle_sha256']:raise ValueError('runtime bundle manifest changed')
    runtime=record['runtime'];_runtime(runtime)
    if address_required and directory.name!=_digest(runtime):raise ValueError('runtime bundle address differs')
    names={_path(name) for name in runtime['source_manifest']}
    paths=record['revision_paths']
    if (not isinstance(paths,list) or any(not isinstance(name,str) for name in paths) or
            set(paths)|{'thermal_model/origin_capture.py'}!=names):
        raise ValueError('archive differs from declared prediction/observer closure')
    expected={'manifest.json','interpreter.bin'}|{'sources/'+name for name in names}
    if _members(directory)!=expected:raise ValueError('runtime bundle has missing or extra files')
    sources={};total=0
    for name in names:
        raw=_owned_bytes(directory/'sources'/name,2000000);total+=len(raw)
        if total>MAX_TOTAL_BYTES:raise ValueError('runtime source bytes exceed bound')
        if sha256(raw).hexdigest()!=runtime['source_manifest'][name]:raise ValueError('archived runtime source changed')
        sources[name]=raw
    if _revision(paths,sources)!=runtime['code_revision']:raise ValueError('ordered runtime revision differs')
    executable=_owned_bytes(directory/'interpreter.bin',64000000);total+=len(executable)
    if total>MAX_TOTAL_BYTES or sha256(executable).hexdigest()!=runtime['interpreter_sha256']:
        raise ValueError('archived interpreter differs or exceeds total bound')
    return record


def read_runtime_bundle(directory):
    """Validate complete immutable bytes independently of the current installation."""
    return _verify(Path(directory),address_required=True)


def _write_private(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


def _sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def capture_runtime_bundle(directory,runtime_root,revision_paths,*,expected_binding=None):
    """Copy stable original bytes into a content-addressed observational archive."""
    root=_private_directory(Path(directory));source_root=Path(runtime_root).resolve(strict=True)
    binding=build_runtime_binding(source_root,revision_paths)
    if expected_binding is not None and _canonical(binding)!=_canonical(expected_binding):
        raise ValueError('publication runtime differs from original binding')
    paths=list(revision_paths);sources={};total=0
    for name,expected in binding['source_manifest'].items():
        _path(name);raw=_source_bytes(source_root/name,maximum=2000000);total+=len(raw)
        if sha256(raw).hexdigest()!=expected or total>MAX_TOTAL_BYTES:raise ValueError('runtime source changed or exceeded bound')
        sources[name]=raw
    executable=_source_bytes(Path(sys.executable).resolve(strict=True),maximum=64000000);total+=len(executable)
    if total>MAX_TOTAL_BYTES or sha256(executable).hexdigest()!=binding['interpreter_sha256']:
        raise ValueError('runtime interpreter changed or exceeded bound')
    if _revision(paths,sources)!=binding['code_revision']:raise ValueError('runtime source order differs')
    body=dict(schema=SCHEMA,runtime=binding,revision_paths=paths,release_authorized=False)
    body['bundle_sha256']=_digest(body);encoded=_canonical(body)
    if len(encoded)>256000:raise ValueError('runtime bundle manifest exceeds bound')
    target=root/_digest(binding);stage=root/('.runtime-'+uuid4().hex)
    lock=os.open(root/'.runtime-bundle.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        info=os.fstat(lock)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or
                stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):raise ValueError('private runtime archive lock required')
        fcntl.flock(lock,fcntl.LOCK_EX)
        if target.exists():
            if read_runtime_bundle(target)!=body:raise ValueError('existing runtime archive has different content')
            return target
        stage.mkdir(mode=0o700);(stage/'sources').mkdir(mode=0o700)
        for name,raw in sources.items():
            parent=stage/'sources'
            for part in PurePosixPath(name).parts[:-1]:
                parent=parent/part
                try:parent.mkdir(mode=0o700)
                except FileExistsError:pass
                _private_directory(parent)
            _write_private(stage/'sources'/name,raw)
        _write_private(stage/'interpreter.bin',executable)
        _write_private(stage/'manifest.json',encoded)
        _verify(stage,address_required=False)
        if _canonical(build_runtime_binding(source_root,revision_paths))!=_canonical(binding):
            raise ValueError('runtime source changed during archive collection')
        # Flush every private directory before publishing the complete generation.
        directories=[stage/'sources',stage]
        directories.extend(path for path in (stage/'sources').rglob('*') if path.is_dir())
        for path in sorted(directories,key=lambda value:len(value.parts),reverse=True):_sync_directory(path)
        os.rename(stage,target);_sync_directory(root)
        return target
    finally:
        if stage.exists():shutil.rmtree(stage)
        os.close(lock)
