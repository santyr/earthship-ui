"""Standard-library I/O primitives shared by bounded OpenHAB workers."""
import fcntl
import os
from pathlib import Path
import stat
from time import monotonic,sleep
from urllib.request import HTTPRedirectHandler

BASES={'http://127.0.0.1:8080/rest','http://localhost:8080/rest','http://127.0.0.1:5190/rest'}


class ReadBudget:
    def __init__(self,seconds,*,clock=monotonic,max_requests=512,min_request_interval=1,sleeper=sleep,guard=None):
        if type(seconds) is not int or not 1<=seconds<=90 or type(max_requests) is not int or not 1<=max_requests<=512:
            raise ValueError('bounded read deadline and request count required')
        if type(min_request_interval) is not int or not 1<=min_request_interval<=5:
            raise ValueError('capture requests must be spaced by one to five seconds')
        if guard is not None and not callable(guard):raise ValueError('callable source guard required')
        self.guard=guard
        self.clock=clock;self.deadline=clock()+seconds;self.max_requests=max_requests;self.requests=0
        self.interval=min_request_interval;self.sleeper=sleeper;self.next_request=None
    def remaining(self):
        if self.guard is not None:self.guard()
        value=self.deadline-self.clock()
        if value<=0:raise ValueError('capture read deadline exceeded')
        return value
    def begin(self):
        remaining=self.remaining()
        if self.requests>=self.max_requests:raise ValueError('capture request count exceeded')
        if self.next_request is not None:
            delay=max(0,self.next_request-self.clock())
            if delay>=remaining:raise ValueError('capture request pacing exceeds deadline')
            if delay:self.sleeper(delay)
            remaining=self.remaining()
            if self.clock()<self.next_request:raise ValueError('capture request pacing interrupted')
        self.next_request=self.clock()+self.interval
        self.requests+=1
        return min(5,remaining)
    def call(self,operation,*args,**kwargs):
        self.begin();value=operation(*args,**kwargs);self.remaining();return value


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('capture redirects refused')


class SharedScoreLock:
    """Hold an existing owned private inode; never create or follow a lock."""
    def __init__(self,path):self.path=Path(path);self.fd=None
    def __enter__(self):
        from weather_source_files import _directory as _private_directory
        if not self.path.is_absolute() or self.path.resolve()!=self.path:
            raise ValueError('resolved absolute shared lock required')
        _private_directory(self.path.parent)
        self.fd=os.open(self.path,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        try:
            info=os.fstat(self.fd);self.identity=(info.st_dev,info.st_ino)
            self.verify()
            fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.verify();return self
        except BaseException:
            os.close(self.fd);self.fd=None;raise
    def verify(self):
        if self.fd is None:raise ValueError('shared lock not held')
        info=os.fstat(self.fd);current=self.path.lstat()
        for value in (info,current):
            if (not stat.S_ISREG(value.st_mode) or value.st_uid!=os.getuid() or
                    stat.S_IMODE(value.st_mode)!=0o600 or value.st_nlink!=1):
                raise ValueError('owned private single-link shared lock required')
        if (current.st_dev,current.st_ino)!=self.identity:
            raise ValueError('shared lock inode replaced')
    def __exit__(self,*args):
        if self.fd is not None:os.close(self.fd);self.fd=None
