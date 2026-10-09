#!/usr/bin/env python3
"""Check private configuration or explicitly collect one original outcome."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import stat

from forecast_input_capture import _directory
from forecast_temperature_origin import _read
from weather_temperature_config import _object,_nonfinite
from hourly_temperature_runtime import read_db_config
from thermal_installed_intel import _resource_preflight

BASES={'http://127.0.0.1:8080/rest','http://localhost:8080/rest','http://127.0.0.1:5190/rest'}
SCHEMA='earthship-temperature-correction-collect-config/v1'
FILES={'token_file','native_db_config','shared_lock'}
DIRECTORIES={'origin_directory','output_directory'}
FIELDS=FILES|DIRECTORIES|{'schema','openhab_base'}


def _clock():return datetime.now(timezone.utc)


def load_settings(path):
    path=Path(path);_directory(path.parent)
    value=json.loads(_read(path,8192),object_pairs_hook=_object,parse_constant=_nonfinite)
    if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA or value['openhab_base'] not in BASES:
        raise ValueError('closed private collection configuration required')
    for key in FILES|DIRECTORIES:
        name=value[key]
        if not isinstance(name,str) or not 1<=len(name)<=1024:raise ValueError('bounded explicit source path required')
        p=Path(name)
        if not p.is_absolute() or p.resolve(strict=True)!=p:raise ValueError('resolved absolute source path required')
        if key in DIRECTORIES:_directory(p)
        else:_directory(p.parent);_read(p,8192)
    if value['origin_directory']==value['output_directory']:raise ValueError('separate original and outcome archives required')
    read_db_config(value['native_db_config'])
    token=_read(Path(value['token_file']),4096).decode().strip()
    if not token or any(ord(c)<32 for c in token):raise ValueError('bounded existing token required')
    return deepcopy(value)


class Backend:
    def __init__(self,settings,*,lock_identity=None):
        from forecast_temperature_reads import DetailReader
        self.settings=deepcopy(settings)
        lock=Path(settings['shared_lock']).lstat()
        self.lock_identity=lock_identity or (lock.st_dev,lock.st_ino)
        self.hashes={key:sha256(_read(Path(settings[key]),8192)).hexdigest() for key in FILES}
        self.verify_unchanged()
        self.detail=DetailReader(base=settings['openhab_base'],token_reader=self._token)
    def _token(self):
        self.verify_unchanged()
        return _read(Path(self.settings['token_file']),4096).decode().strip()
    def verify_unchanged(self):
        lock=Path(self.settings['shared_lock']).lstat()
        if (lock.st_dev,lock.st_ino)!=self.lock_identity:
            raise ValueError('shared lock inode changed')
        if any(sha256(_read(Path(self.settings[key]),8192)).hexdigest()!=digest for key,digest in self.hashes.items()):
            raise ValueError('original private source configuration changed')
    def publication(self,origin):return self.detail.publication(origin)
    def native(self,*,start,end,assessed_at):
        from forecast_temperature_reads import native_rows
        self.verify_unchanged()
        config=read_db_config(self.settings['native_db_config'])
        def connect():
            import psycopg2
            return psycopg2.connect(**config,connect_timeout=3)
        return native_rows(connect,start=start,end=end,assessed_at=assessed_at,now=_clock())


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--collect',action='store_true')
    parser.add_argument('--origin-sha256');parser.add_argument('--target')
    args=parser.parse_args(argv)
    if args.collect and (args.origin_sha256 is None or args.target is None):parser.error('explicit original digest and target required')
    if not args.collect and (args.origin_sha256 is not None or args.target is not None):parser.error('source reads require --collect')
    base={'collection_executed':False,'release_authority':False}
    try:
        settings=load_settings(args.config)
        if not args.collect:print(json.dumps(dict(base,status='configuration_verified')));return 0
        _resource_preflight()
        os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        fd=os.open(settings['shared_lock'],os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
                raise ValueError('original private shared lock required')
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:print(json.dumps(dict(base,status='busy')));return 0
            from forecast_temperature_collection import collect_target
            result=collect_target(origin_directory=settings['origin_directory'],origin_sha256=args.origin_sha256,
                target=args.target,assessed_at=_clock().isoformat(),output_directory=settings['output_directory'],backend=Backend(settings,lock_identity=(info.st_dev,info.st_ino)))
        finally:os.close(fd)
        result['collection_executed']=result['status'] in ('qualified','withheld')
        print(json.dumps(result,sort_keys=True));return 0
    except Exception:
        print(json.dumps(dict(base,status='withheld_failure')));return 1


if __name__=='__main__':raise SystemExit(main())
