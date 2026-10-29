"""Stage A only: two pre-exec OFDs, no Docker or physical/financial operation.

stdin is the original real admission OFD. stdout is the disposable probe OFD;
never print to stdout. PID1 stores BOTH original OFDs under distinct names.
On systemd259, CollectMode must remain inactive to retain failed units;
--collect would permit start-limit garbage collection despite stored FDs.
Recovery uses the named descriptors, never transient stdin/stdout retention.
"""
import argparse
from hashlib import sha256
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from services.lorawan.tests import qualification_guard as guard
from services.lorawan.tests.qualification_runtime import SystemdNotify,check_service_context


class ProbeStore:
    """Probe only: real reservation first/last, disposable lifetime witness."""
    def __init__(self,*,notify,barrier,count):
        self.notify=notify;self.barrier=barrier;self.count=count

    def pin(self,*,real,disposable):
        for name,fd,expected in [('admission',real,1),('probe',disposable,2)]:
            self.notify('FDSTORE=1\nFDNAME='+name+'\nFDPOLL=0',fd)
            self.barrier();guard.require(self.count()==expected)

    def release(self):
        for name,expected in [('probe',1),('admission',0)]:
            self.notify('FDSTOREREMOVE=1\nFDNAME='+name)
            self.barrier();guard.require(self.count()==expected)


def probe_descriptors(environment):
    if not any(name in environment for name in ('LISTEN_PID','LISTEN_FDS','LISTEN_FDNAMES')):return None
    guard.require(environment.get('LISTEN_PID')==str(os.getpid()) and environment.get('LISTEN_FDS')=='2')
    names=environment.get('LISTEN_FDNAMES','').split(':')
    guard.require(len(names)==2 and set(names)=={'admission','probe'})
    return {name:3+index for index,name in enumerate(names)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--nonce',required=True)
    args=parser.parse_args(argv);directory=args.directory
    guard.require(re.fullmatch('[a-f0-9]{32}',args.nonce))
    unit='earthship-sensor-guard-'+args.nonce+'.service';check_service_context(unit)
    info=directory.lstat();guard.require(directory.resolve()==directory and info.st_uid==1000 and stat.S_IMODE(info.st_mode)==0o700)
    path=directory/'manifest.json';raw=path.read_bytes();digest=sha256(raw).hexdigest();manifest=guard.read_private(path)
    guard.require(manifest['schema']=='earthship-sensor-lifetime-probe/v1' and manifest['nonce']==args.nonce)
    source=Path(manifest['source_root']);module_dir=source/'services/lorawan/tests'
    guard.require(Path(__file__).resolve()==module_dir/'qualification_lifetime_probe.py')
    for name,expected in manifest['sources'].items():
        guard.require(name in ('qualification_guard.py','qualification_runtime.py','stack_ownership.py','qualification_lifetime_probe.py','qualification_controller.py'))
        p=module_dir/name;meta=p.lstat()
        guard.require(p.resolve()==p and meta.st_uid==1000 and meta.st_nlink==1 and stat.S_IMODE(meta.st_mode)==0o400 and sha256(p.read_bytes()).hexdigest()==expected)
    guard.require(len(manifest['sources'])==5)
    for relative in ['services','services/lorawan','services/lorawan/tests']:
        guard.require((source/relative/'__init__.py').read_bytes()==b'')
    inherited=probe_descriptors(os.environ)
    descriptors=inherited or {'admission':0,'probe':1}
    for name,key in [('admission','real_lock'),('probe','probe_lock')]:
        value=manifest[key];guard.verify_lock(value['path'],descriptors[name],uid=1000,identity=(value['dev'],value['ino']))
    collect=subprocess.check_output(['/usr/bin/systemctl','show','--value','-p','CollectMode',unit],text=True,timeout=5).strip()
    guard.require(collect=='inactive','failed units must remain loaded on systemd259')
    notify=SystemdNotify(os.environ['NOTIFY_SOCKET'])
    def count():
        value=subprocess.check_output(['/usr/bin/systemctl','show','--value','-p','NFileDescriptorStore',unit],text=True,timeout=5).strip()
        guard.require(value in ('0','1','2'));return int(value)
    store=ProbeStore(notify=notify,barrier=notify.barrier,count=count)
    receipt=directory/'probe-receipt.json'
    recovered=False
    if inherited is not None:
        guard.require(count()==2 and receipt.exists())
        previous=guard.read_private(receipt);guard.require(previous.get('manifest_sha256')==digest)
        recovered=True
    else:guard.require(count()==0)
    guard.persist(receipt,{'phase':'recovered' if recovered else 'before-pin','manifest_sha256':digest,'pid':os.getpid(),
                           'real_fd':descriptors['admission'],'probe_fd':descriptors['probe'],'inherited_fds':inherited})
    pinned=recovered
    while time.monotonic()<manifest['deadline']:
        guard.require(path.read_bytes()==raw)
        for name,key in [('admission','real_lock'),('probe','probe_lock')]:
            value=manifest[key];guard.verify_lock(value['path'],descriptors[name],uid=1000,identity=(value['dev'],value['ino']))
        command_path=directory/'probe-command.json'
        command=guard.read_private(command_path) if command_path.exists() else {'operation':'wait','nonce':args.nonce}
        guard.require(set(command)=={'operation','nonce'} and command['nonce']==args.nonce and command['operation'] in ('wait','pin','release'))
        if not pinned and command['operation']=='pin':
            store.pin(real=descriptors['admission'],disposable=descriptors['probe']);pinned=True
            guard.persist(receipt,{'phase':'pinned','manifest_sha256':digest,'pid':os.getpid(),'real_fd':descriptors['admission'],'probe_fd':descriptors['probe'],'inherited_fds':None})
            notify('READY=1');notify.barrier()
        elif pinned and recovered:
            notify('READY=1');notify.barrier();recovered=False
        if command['operation']=='release':
            guard.require(pinned)
            # Stage A has no containers. The parent must separately prove the
            # tested controller/root-client cgroup is empty before release.
            from services.lorawan.tests.qualification_runtime import Controller
            controller=Controller(manifest['controller'])
            guard.require(not controller.populated(),'controller/root client must be quiescent before release')
            guard.persist(receipt,{'phase':'terminal','manifest_sha256':digest,'pid':os.getpid()})
            store.release();return 0
        time.sleep(.1)
    raise guard.Refused('probe deadline expired; retain FDStore for reconciliation')


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print('Lifetime probe refused; inspect owned receipt and retained descriptors before reconciliation.',file=sys.stderr)
        raise SystemExit(1)
