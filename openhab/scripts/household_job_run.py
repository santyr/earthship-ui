#!/usr/bin/env python3
"""Run local development/ML work within the shared kernel resource budget."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys

from household_job_budget import AdmissionDeferred, MiB
from household_job_pool import POOL_NAME
from household_job_launch import launch_job


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minimum-mib',type=int,default=256)
    parser.add_argument('--preferred-mib',type=int,default=1024)
    parser.add_argument('--production',action='store_true')
    parser.add_argument('--collection',action='store_true',help='strict compatible acquisition leaf profile')
    parser.add_argument('--tasks',type=int,default=96)
    parser.add_argument('--seconds',type=int,default=600)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    command=args.command
    if command[:1]==['--']:command=command[1:]
    def interrupted(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    try:
        relative=subprocess.check_output(['systemctl','--user','show',POOL_NAME,
            '--value','-p','ControlGroup'],text=True,timeout=5).strip()
        prefix=f'/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/'
        if relative!=prefix+'earthship.slice/'+POOL_NAME:
            raise ValueError('active owned work slice required')
        return launch_job(command,pool_path=Path('/sys/fs/cgroup')/relative.lstrip('/'),
            lock_path=Path('/run/user')/str(os.getuid())/'earthship-job-admission.lock',
            minimum_bytes=args.minimum_mib*MiB,preferred_bytes=args.preferred_mib*MiB,
            production=args.production,tasks=args.tasks,seconds=args.seconds,collection=args.collection)
    except AdmissionDeferred:
        print('Job deferred: shared resource headroom is currently reserved.',file=sys.stderr);return 75
    except KeyboardInterrupt:
        return 130
    except (OSError,ValueError,TimeoutError,subprocess.SubprocessError):
        print('Job refused: shared resource admission could not be verified.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
