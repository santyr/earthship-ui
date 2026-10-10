"""Scoped shared replay time; inactive callers retain their existing limits."""
from contextlib import contextmanager
from contextvars import ContextVar
import math

_remaining=ContextVar('earthship_shared_replay_remaining',default=None)


def _seconds(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
        raise ValueError('shared replay deadline elapsed or invalid')
    return float(value)


def remaining_budget(maximum):
    maximum=_seconds(maximum);remaining=_remaining.get()
    return maximum if remaining is None else min(maximum,_seconds(remaining()))


def check_shared_budget():
    remaining=_remaining.get()
    if remaining is not None:_seconds(remaining())


@contextmanager
def shared_replay_budget(remaining):
    if not callable(remaining):raise ValueError('remaining replay budget callback required')
    parent=_remaining.get()
    def bounded():
        value=_seconds(remaining())
        return value if parent is None else min(value,_seconds(parent()))
    token=_remaining.set(bounded)
    try:
        check_shared_budget();yield
    finally:_remaining.reset(token)


# This bounds observation metadata; every original reader retains its own bounds.
MAX_OBSERVED_FILES=32768
MAX_OBSERVED_BYTES=1024*1024*1024
_source_reads=ContextVar('earthship_qualification_source_reads',default=None)


def observe_source_bytes(path,raw):
    observer=_source_reads.get()
    if observer is not None:observer.record(path,raw)


class OriginalSourceInventory:
    """Invocation-local digests of originals, with streaming final verification."""
    def __init__(self):self.records={};self.total_bytes=0
    @property
    def file_count(self):return len(self.records)
    def _stat(self,path):
        import os,stat
        try:info=path.lstat()
        except OSError:raise ValueError('original qualification source unavailable') from None
        if (not path.is_absolute() or path.resolve()!=path or not stat.S_ISREG(info.st_mode) or
                info.st_uid not in (0,os.getuid()) or info.st_mode&0o022 or info.st_nlink!=1):
            raise ValueError('original qualification source identity invalid')
        return info
    def record(self,path,raw):
        from pathlib import Path
        from hashlib import sha256
        path=Path(path);info=self._stat(path)
        if len(str(path))>1024 or info.st_size!=len(raw):raise ValueError('original qualification source changed during observation')
        record=(sha256(raw).hexdigest(),len(raw),info.st_mode,info.st_uid,info.st_gid,info.st_nlink)
        previous=self.records.get(path)
        if previous is not None:
            if previous!=record:raise ValueError('original qualification source changed during replay')
        else:
            if len(self.records)>=MAX_OBSERVED_FILES or self.total_bytes+len(raw)>MAX_OBSERVED_BYTES:
                raise ValueError('qualification source observation inventory exceeded')
            self.records[path]=record;self.total_bytes+=len(raw)
    def verify(self):
        import os
        from hashlib import sha256
        if not self.records:raise ValueError('original qualification source inventory missing')
        check_shared_budget();verified={}
        def identity(info):return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_mode,info.st_uid,info.st_gid,info.st_nlink)
        for path,(expected,size,mode,owner,group,links) in self.records.items():
            check_shared_budget();info=self._stat(path)
            if (info.st_size,info.st_mode,info.st_uid,info.st_gid,info.st_nlink)!=(size,mode,owner,group,links):
                raise ValueError('original qualification source metadata changed')
            try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
            except OSError:raise ValueError('original qualification source unavailable') from None
            try:
                opened=os.fstat(fd)
                if (opened.st_dev,opened.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('original qualification source replaced')
                digest=sha256();count=0
                while True:
                    check_shared_budget();part=os.read(fd,min(65536,size-count+1))
                    if not part:break
                    count+=len(part)
                    if count>size:raise ValueError('original qualification source grew')
                    digest.update(part)
                finished=os.fstat(fd)
                if ((opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns)!=(finished.st_size,finished.st_mtime_ns,finished.st_ctime_ns) or
                        count!=size or digest.hexdigest()!=expected):raise ValueError('original qualification source bytes changed')
            finally:os.close(fd)
            latest=self._stat(path)
            if identity(latest)!=identity(finished):raise ValueError('original qualification source changed after read')
            verified[path]=identity(latest)
        # Refuse changes to earlier files while later originals were streamed.
        for path,expected in verified.items():
            check_shared_budget()
            if identity(self._stat(path))!=expected:raise ValueError('original qualification source changed across inventory verification')
        check_shared_budget()


@contextmanager
def capture_source_reads():
    inventory=OriginalSourceInventory();token=_source_reads.set(inventory)
    try:yield inventory
    finally:_source_reads.reset(token)
