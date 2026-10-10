#!/usr/bin/env python3
"""Check private scoring settings or explicitly collect one mature horizon."""
import argparse
import fcntl
import stat
import json
import os
from pathlib import Path


class SharedScoreLock:
    """Hold an existing owned private inode; never create or follow a lock."""
    def __init__(self,path):self.path=Path(path);self.fd=None
    def __enter__(self):
        from thermal_model.forcing_capture import _private_directory
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


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--contract-version',type=int,choices=(1,2),default=2,
        help='2 scores raw calibrated publications; 1 scores base shadow calibration origins')
    intent=parser.add_mutually_exclusive_group()
    intent.add_argument('--collect',action='store_true')
    intent.add_argument('--batch',action='store_true')
    parser.add_argument('--queue',type=Path)
    parser.add_argument('--origin',type=Path)
    parser.add_argument('--shared-lock',type=Path)
    parser.add_argument('--horizon',type=int,choices=(1,6,12,24))
    args=parser.parse_args(argv)
    if args.collect and (args.origin is None or args.horizon is None or args.shared_lock is None or args.queue is not None):parser.error('explicit original publication, mature horizon and shared lock required')
    if args.batch and (args.queue is None or args.shared_lock is None or args.origin is not None or args.horizon is not None):parser.error('explicit queue and shared lock required for batch')
    if not (args.collect or args.batch) and any(value is not None for value in (args.origin,args.horizon,args.shared_lock,args.queue)):parser.error('source reads require explicit collection intent')
    try:
        if args.collect or args.batch:
            from thermal_installed_intel import _resource_preflight
            _resource_preflight()
            os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        from thermal_model.installed_shade_score_inputs import load_score_settings,load_raw_score_settings,ScoreReader
        loader=load_raw_score_settings if args.contract_version==2 else load_score_settings
        settings=loader(args.config)
        if not (args.collect or args.batch):
            print(json.dumps(dict(status='configuration_verified',collection_executed=False,release_authorized=False)));return 0
        from thermal_model.installed_shade_score_collection import collect_published_score,collect_raw_published_score
        collect=collect_raw_published_score if args.contract_version==2 else collect_published_score
        with SharedScoreLock(args.shared_lock) as held:
            backend=ScoreReader(settings,shared_lock_guard=held.verify)
            if args.batch:
                from thermal_model.installed_shade_score_jobs import collect_queued_score,collect_raw_queued_score
                queued=collect_raw_queued_score if args.contract_version==2 else collect_queued_score
                result=queued(queue_path=args.queue,output_directory=settings['output_directory'],backend=backend)
            else:
                result=collect(origin_path=args.origin,horizon_hours=args.horizon,
                    output_directory=settings['output_directory'],backend=backend)
            held.verify()
        print(json.dumps(result,sort_keys=True));return 0 if result['status'] in ('scored','pending','busy','queue_complete','completion_verified') else 1
    except BlockingIOError:
        print(json.dumps(dict(status='busy',collection_executed=False,release_authorized=False)));return 75
    except Exception:
        # Never emit credential/config/transport exception bytes or tracebacks.
        print(json.dumps(dict(status='withheld',collection_executed=False,release_authorized=False)));return 1


if __name__=='__main__':raise SystemExit(main())
