#!/usr/bin/env python3
"""Bounded, default-off recovery of failed morning weather fetches only.

Never execute the forecast under this unit's environment. Start the existing
forecast-intel.service so all its source/learning policies remain in effect.
"""
from datetime import datetime, time, timezone
import grp
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import subprocess
import sys
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

RELEASE_READY = os.environ.get('EARTHSHIP_FORECAST_FETCH_RECOVERY_ENABLE') == '1'
KEY = 'forecast_fetch_failure'
FIELDS = {'version','phase','day','timezone','failed_at','invocation_id','failure_count','retryable'}
ZONE = ZoneInfo('America/Denver')
UNIT = 'forecast-intel.service'
STATE = Path('/home/sat/.local/state/forecast-intel/state.json')
MAX_FAILURES = 8


def invocation(value):
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{32}',value) is not None


def transient(error):
    if isinstance(error,HTTPError):
        return 500 <= error.code < 600
    reason = error.reason if isinstance(error,URLError) else error
    return isinstance(reason,(TimeoutError,socket.gaierror))


def fetch_for_issue(fetch,state,persist,*,now,invocation_id,timezone_name):
    """Retain only typed failure metadata, never an exception URL/message."""
    try:
        snapshot = fetch()
    except Exception as error:
        at = now()
        day = at.astimezone(ZONE).date().isoformat()
        old = state.get(KEY)
        count = 0
        if isinstance(old,dict) and old.get('day') == day:
            previous = old.get('failure_count')
            count = previous if type(previous) is int and 0 <= previous <= MAX_FAILURES else MAX_FAILURES
        state[KEY] = {'version':1,'phase':'weather_fetch','day':day,'timezone':timezone_name,
            'failed_at':at.astimezone(timezone.utc).isoformat(),
            'invocation_id':invocation_id if invocation(invocation_id) else '',
            'failure_count':min(MAX_FAILURES,count+1),'retryable':transient(error)}
        persist(state)
        raise
    if KEY in state:
        state.pop(KEY)
        persist(state)  # Clear authority before any later, unrelated failure.
    return snapshot


def eligible(state,now,service):
    if not isinstance(now,datetime) or now.utcoffset() is None or not isinstance(state,dict):
        return False
    local = now.astimezone(ZONE)
    if not time(6,40) <= local.time() < time(9):
        return False
    predictions = state.get('predictions')
    marker = state.get(KEY)
    if (not isinstance(predictions,dict) or local.date().isoformat() in predictions
            or not isinstance(marker,dict) or set(marker) != FIELDS
            or type(marker['version']) is not int or marker['version'] != 1
            or marker['phase'] != 'weather_fetch' or marker['timezone'] != ZONE.key
            or marker['day'] != local.date().isoformat() or marker['retryable'] is not True
            or type(marker['failure_count']) is not int or not 1 <= marker['failure_count'] < MAX_FAILURES
            or not invocation(marker['invocation_id'])
            or service.get('LoadState') != 'loaded' or service.get('ActiveState') != 'failed'
            or service.get('InvocationID') != marker['invocation_id']):
        return False
    try:
        if not isinstance(marker['failed_at'],str) or len(marker['failed_at']) > 64:
            return False
        failed = datetime.fromisoformat(marker['failed_at'])
        return (failed.utcoffset() is not None and failed.astimezone(ZONE).date() == local.date()
                and 0 <= (now-failed).total_seconds() <= 1800)
    except (ValueError,TypeError):
        return False


def run(command):
    result = subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
    if result.returncode:
        raise RuntimeError('forecast recovery systemd request failed')
    return result.stdout.decode()


def owned_permissions(path,information):
    """Allow legacy owner-only groups without altering shared permissions."""
    if information.st_uid != os.getuid() or information.st_mode & 0o002:
        return False
    if information.st_mode & 0o020:
        owner = pwd.getpwuid(information.st_uid)
        group = grp.getgrgid(information.st_gid)
        members = set(group.gr_mem) | {entry.pw_name for entry in pwd.getpwall()
                                      if entry.pw_gid == information.st_gid}
        if (information.st_gid != owner.pw_gid or members != {owner.pw_name}
                or 'system.posix_acl_access' in os.listxattr(path,follow_symlinks=False)):
            return False
    return True


def read_state():
    parent = STATE.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or not owned_permissions(STATE.parent,parent)
            or STATE.parent.resolve() != STATE.parent):
        raise ValueError('owned forecast state directory required')
    descriptor = os.open(STATE,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(descriptor,'rb') as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or not owned_permissions(STATE,before)
                or before.st_nlink != 1 or before.st_size > 256*1024):
            raise ValueError('bounded owned forecast state required')
        raw = stream.read(256*1024+1)
        after = os.fstat(stream.fileno())
        if ((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)
                != (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or len(raw)>256*1024):
            raise ValueError('forecast state changed during recovery check')
    def unique(pairs):
        result = {}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate forecast state field')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite forecast state')))


def command(arguments):
    if arguments not in (['--check'],['--run']):
        raise ValueError('no arbitrary unit, state or target interface')
    if arguments == ['--run'] and not RELEASE_READY:
        raise ValueError('forecast recovery release gate is off')
    properties = run(['systemctl','--user','show',UNIT,'-p','LoadState','-p','ActiveState','-p','InvocationID'])
    service = dict(line.split('=',1) for line in properties.splitlines() if '=' in line)
    ready = eligible(read_state(),datetime.now(timezone.utc),service)
    if ready and arguments == ['--run']:
        # Recheck the failed invocation immediately before requesting one job.
        again = run(['systemctl','--user','show',UNIT,'-p','ActiveState','-p','InvocationID'])
        checked = dict(line.split('=',1) for line in again.splitlines() if '=' in line)
        if checked != {'ActiveState':'failed','InvocationID':service['InvocationID']}:
            raise ValueError('forecast invocation changed during recovery')
        if not eligible(read_state(),datetime.now(timezone.utc),service):
            raise ValueError('forecast state or recovery window changed')
        run(['systemctl','--user','start','--no-block',UNIT])
    return {'eligible':ready,'release_ready':RELEASE_READY,
            'start_requested':ready and arguments == ['--run']}


if __name__ == '__main__':
    try:
        print(json.dumps(command(sys.argv[1:]),sort_keys=True))
    except Exception:
        raise SystemExit('forecast recovery withheld; private diagnostics not emitted') from None
