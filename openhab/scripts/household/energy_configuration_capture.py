"""Bounded fixed configuration acquisition; no writes, credentials or controls."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import os,stat,time
from .evidence import utc
from .energy_configuration import prepare_energy_configuration,SOURCES

FIXED_PATHS={'bank_source':Path('/home/sat/Solar_PV/analytics/config/system-epochs.json'),
             'load_topology_source':Path('/home/sat/Solar_PV/analytics/config/ac-evidence.json')}


def _metadata(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def _owned_text(path,maximum,check):
    check()
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('fixed resolved configuration path required')
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    except FileNotFoundError:return None,None
    except OSError:raise ValueError('configuration transport unavailable') from None
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_nlink!=1 or before.st_size>maximum:
            raise ValueError('bounded owned regular configuration required')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(maximum+1)
        after=os.fstat(fd);current=path.lstat();check()
        if len(raw)>maximum or _metadata(before)!=_metadata(after) or _metadata(before)!=_metadata(current):
            raise ValueError('configuration identity or content changed while reading')
        try:text=raw.decode('utf-8')
        except UnicodeError:raise ValueError('original configuration text unavailable') from None
        return text,_metadata(before)
    finally:os.close(fd)


def collect_configuration(*,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,remaining=None):
    started=utc(clock());deadline=monotonic()+15.
    def check():
        local=deadline-monotonic()
        if not 0.001<=local<=15.:raise ValueError('local configuration collection deadline elapsed')
        value=local if remaining is None else remaining()
        if type(value) not in (int,float) or not 0.001<=value<=15.:raise ValueError('configuration collection deadline elapsed')
        return min(local,value)
    if set(FIXED_PATHS)!=set(SOURCES):raise ValueError('fixed complete configuration sources required')
    check();originals={};available={}
    for key,path in FIXED_PATHS.items():
        originals[key]=_owned_text(path,SOURCES[key][1],check);available[key]=utc(clock())
    for key,path in FIXED_PATHS.items():
        if _owned_text(path,SOURCES[key][1],check)!=originals[key]:raise ValueError('configuration changed during collection')
    finished=utc(clock());check()
    if not started<=finished<=started+timedelta(seconds=15) or any(not started<=at<=finished for at in available.values()):
        raise ValueError('configuration collection clock changed')
    return prepare_energy_configuration(bank_config_raw=originals['bank_source'][0],ac_policy_raw=originals['load_topology_source'][0],
        bank_available_at=available['bank_source'],topology_available_at=available['load_topology_source'],as_of=finished,created_at=finished)
