"""Closed sensor qualification controller preparation; no effects at import.

The original shared launcher owns admission policy. These helpers only prepare
one stopped seven-service fixture and a fixed system-manager guardian invocation.
Installed-version lifecycle qualification is mandatory before operational use.
"""
from pathlib import Path
import re
from services.lorawan.tests.qualification_guard import require, persist, SERVICES


def check_budget(*,residual,other_children,direct_pids,swap):
    require(type(residual) is int and residual>=0 and not other_children and direct_pids==0 and swap==0,
            'original pool must be drained and swap-free')
    slack=6144*1024**2-residual-3520*1024**2
    require(slack>=256*1024**2,'original total lacks the explicit uncertainty reserve')
    return slack


def guardian_command(*,python,source,manifest,digest,root,nonce,mode='lifecycle-proof'):
    require(mode in ('qualification','lifecycle-proof'))
    require(re.fullmatch('[a-f0-9]{32}',nonce) and re.fullmatch('[a-f0-9]{64}',digest))
    require(all(Path(path).is_absolute() for path in (python,source,manifest,root)))
    name='earthship-sensor-guard-'+nonce
    properties=['User=sat','Group=sat','SupplementaryGroups=docker','MemoryMax=67108864','MemorySwapMax=0',
        'CPUQuota=50%','TasksMax='+('8' if mode=='qualification' else '16'),'NotifyAccess=main','Restart=on-failure','RestartSec=1',
        'TimeoutStopSec=infinity','FileDescriptorStoreMax=1','FileDescriptorStorePreserve=yes',
        'RuntimeDirectory='+name,'RuntimeDirectoryMode=0700','RuntimeDirectoryPreserve=yes',
        'BindsTo=user-runtime-dir@1000.service','After=user-runtime-dir@1000.service',
        'WorkingDirectory='+str(root)]
    return ['/usr/bin/sudo','-n','/usr/bin/systemd-run','--system','--pipe',
        '--service-type=notify','--unit='+name+'.service',
        *[part for value in properties for part in ('--property',value)],
        '--setenv=PYTHONDONTWRITEBYTECODE=1','--setenv=PYTHONPATH='+str(source),
        '--',str(python),'-B','-P','-m','services.lorawan.tests.qualification_runtime',
        '--mode',mode,'--manifest',str(manifest),'--sha256',digest,'--root',str(root),'--nonce',nonce]


def precreate(root,nonce,receipt,*,run):
    root=Path(root);receipt=Path(receipt)
    require(root.is_absolute() and root.resolve()==root and re.fullmatch('[a-f0-9]{32}',nonce))
    require(not receipt.exists(),'pending create intents require exact reconciliation')
    persist(receipt,{'schema':'earthship-sensor-create/v1','nonce':nonce,'root':str(root),
        'phase':'creating','ids':{},'intents':{service:'earthship-sensors-test-'+service+'-1' for service in SERVICES}})
    # Compose create does not start dependencies, run health checks or restart.
    # The source sets restart:no and mandatory nonce labels on every member.
    # On timeout/crash, retain these intents; never blindly retry or down/prune.
    run(['/snap/bin/docker','compose','-f',str(root/'deploy/lorawan/compose.test.yaml'),
         '--profile','*','create','--no-build','--pull','never'])


FROZEN_MODULES=('qualification_guard.py','qualification_runtime.py','stack_ownership.py','qualification_lifetime_probe.py','qualification_controller.py')


def freeze_sources(source,package):
    import hashlib,os,stat
    source=Path(source);package=Path(package);package.mkdir(mode=0o700)
    for relative in ['services','services/lorawan','services/lorawan/tests']:
        directory=package/relative;directory.mkdir(mode=0o700)
        path=directory/'__init__.py';path.write_bytes(b'');path.chmod(0o400)
    hashes={}
    for name in FROZEN_MODULES:
        path=source/name;info=path.lstat()
        require(path.resolve()==path and stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1)
        raw=path.read_bytes();require(len(raw)<=262144)
        target=package/'services/lorawan/tests'/name
        with target.open('xb') as output:output.write(raw);output.flush();os.fsync(output.fileno())
        target.chmod(0o400);hashes[name]=hashlib.sha256(raw).hexdigest()
    return hashes


def launch_lifetime(*,python,source,directory,nonce,real_fd,probe_fd,log,spawn,preinit_proof=False):
    argv=guardian_command(python=python,source=source,manifest=Path(directory)/'manifest.json',digest='0'*64,
                          root=directory,nonce=nonce)
    argv[argv.index('FileDescriptorStoreMax=1')]='FileDescriptorStoreMax=2'
    require(type(preinit_proof) is bool)
    if preinit_proof:
        index=argv.index('--');argv[index:index]=['--property','ExecStartPre=/usr/bin/sleep 10']
    index=argv.index('services.lorawan.tests.qualification_runtime')
    argv=argv[:index]+['services.lorawan.tests.qualification_lifetime_probe','--directory',str(directory),'--nonce',nonce]
    # systemd-run --pipe sends the original OFDs to PID1 before external exec.
    # No preexec callback, reopened inode, LOCK_UN, shell or late SCM transfer.
    return spawn(argv,stdin=real_fd,stdout=probe_fd,stderr=log,close_fds=True)


def lifetime_main(argv=None):
    """Run only after the parent hands over the coordinated Stage A window."""
    import argparse,fcntl,hashlib,json,os,stat,subprocess,sys,time
    from services.lorawan.tests.qualification_guard import verify_lock
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--nonce',required=True)
    parser.add_argument('--preinit-proof',action='store_true')
    args=parser.parse_args(argv);require(re.fullmatch('[a-f0-9]{32}',args.nonce))
    directory=args.directory;require(directory.is_absolute() and directory.resolve()==directory)
    require(sys.version_info[:2]==(3,12) and os.environ.get('PYTHONDONTWRITEBYTECODE')=='1')
    relative=Path('/proc/self/cgroup').read_text().strip().removeprefix('0::')
    prefix='/user.slice/user-1000.slice/user@1000.service/earthship.slice/earthship-work.slice/'
    require(relative.startswith(prefix) and re.fullmatch(r'earthship-job-[a-f0-9]{32}\.scope',relative[len(prefix):]))
    unit=relative[len(prefix):];scope=Path('/sys/fs/cgroup')/relative.lstrip('/');pool=scope.parent
    for path,expected in [(scope/'memory.max','1073741824'),(scope/'memory.swap.max','0'),(scope/'pids.max','96'),
                          (pool/'memory.max','6442450944'),(pool/'memory.swap.max','0'),(pool/'pids.max','256'),(pool/'cpu.max','800000 100000')]:
        require(path.read_text().strip()==expected,'Stage A original scope/pool cap differs')
    subprocess.run(['/usr/bin/systemctl','--user','set-property','--runtime',unit,'CPUQuota=200%'],check=True,timeout=5)
    quota,period=(scope/'cpu.max').read_text().split();require(int(quota)==2*int(period))
    directory.mkdir(mode=0o700)
    frozen=directory/'source';hashes=freeze_sources(Path(__file__).resolve().parent,frozen)
    lock=Path('/run/user/1000/earthship-job-admission.lock')
    real=os.open(lock,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
    probe=None
    try:
        info=os.fstat(real);require(stat.S_ISREG(info.st_mode) and info.st_uid==1000 and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1)
        try:fcntl.flock(real,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 75
        verify_lock(lock,real,uid=1000,identity=(info.st_dev,info.st_ino))
        # No externally running member exists before these checks. Other jobs
        # must drain naturally; refusal never raises the pool or retries starts.
        require([p for p in pool.iterdir() if p.is_dir()]==[scope] and not (pool/'cgroup.procs').read_text().strip())
        residual=max(0,int((pool/'memory.current').read_text())-int((scope/'memory.current').read_text()))
        require(residual+(1024+64+256)*1024**2<=6144*1024**2 and (pool/'memory.swap.current').read_text().strip()=='0')
        memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
        require(int(memory['MemAvailable'].split()[0])*1024 >= (3*1024+1024+64)*1024**2)
        pressure=Path('/proc/pressure/memory').read_text().splitlines()
        require(all(float(dict(part.split('=') for part in row.split()[1:])['avg10'])<1 for row in pressure))
        probe_path=directory/'probe.lock';probe=os.open(probe_path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB);probe_info=os.fstat(probe)
        start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]);scope_info=scope.stat()
        invocation=subprocess.check_output(['/usr/bin/systemctl','--user','show','--value','-p','InvocationID',unit],text=True,timeout=5).strip()
        require(re.fullmatch('[a-f0-9]{32}',invocation))
        manifest={'schema':'earthship-sensor-lifetime-probe/v1','nonce':args.nonce,'source_root':str(frozen),
            'sources':hashes,'real_lock':{'path':str(lock),'dev':info.st_dev,'ino':info.st_ino},
            'probe_lock':{'path':str(probe_path),'dev':probe_info.st_dev,'ino':probe_info.st_ino},
            'controller':{'pid':os.getpid(),'starttime':start,'uid':1000,'cgroup':relative,'dev':scope_info.st_dev,
                'ino':scope_info.st_ino,'unit':unit,'invocation':invocation,'guardian_unit':'earthship-sensor-guard-'+args.nonce+'.service'},
            'preinit_proof':args.preinit_proof,'residual_bytes':residual,'pool_events':(pool/'memory.events').read_text(),'deadline':time.monotonic()+1800}
        persist(directory/'manifest.json',manifest)
        with (directory/'guardian.stderr').open('xb') as log:
            process=launch_lifetime(python=Path(sys.executable),source=frozen,directory=directory,nonce=args.nonce,
                real_fd=real,probe_fd=probe,log=log,spawn=subprocess.Popen,preinit_proof=args.preinit_proof)
            return process.wait()
    finally:
        if probe is not None:os.close(probe)
        os.close(real)  # Never LOCK_UN; PID1 may still own both original OFDs.


if __name__=='__main__':
    raise SystemExit(lifetime_main())
