"""Guarded additive definition install; never starts or interrupts a worker."""
from pathlib import Path
from hashlib import sha256
import argparse,json,os,re,shlex,stat,subprocess,tempfile

BASE=Path('/home/sat/.config/systemd/user/forecast-intel.service.d')
PROFILE=BASE/'zzz-bounded-native-inputs.conf'
TARGET=BASE/'zzzz-daily-lock-wait.conf'
TEMPLATE=Path('openhab/systemd/user/forecast-intel.service.d/zzzz-daily-lock-wait.conf')
EXPECTED=Path('.superpowers/sdd/2026-10-11-daily-forecast-lock-wait/expected-install.json')
OTHER_CONSUMERS=('thermal-provisional-forecast.service','thermal-provisional-score.service',
                 'thermal-model-shadow.service','forecast-json.service','forecast-pre-dusk.service','forecast-temperature-score.service')
CAPS={'Type':'oneshot','Restart':'no','TimeoutStartUSec':'3min','CPUQuotaPerSecUSec':'200ms',
      'MemoryMax':'268435456','MemorySwapMax':'0','TasksMax':'24','Nice':'15','IOSchedulingClass':'3','IOWeight':'10','Slice':'earthship-inputs.slice'}


def read(path,maximum,private=False):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum or info.st_uid!=os.getuid() or private and stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError('owned regular source required')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(maximum+1)
        if len(raw)>maximum:raise ValueError('bounded source required')
        return raw
    finally:os.close(fd)


def run(*args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=8)
    if result.returncode:raise ValueError('definition command refused')
    return result.stdout.strip()


def properties(unit,keys):
    return dict(line.split('=',1) for line in run('systemctl','--user','show',unit,*['--property='+key for key in keys]).splitlines() if '=' in line)


def argv(raw):
    match=re.search(r'argv\[\]=(.+?)\s*;',raw)
    if match is None:raise ValueError('exact manager command required')
    return shlex.split(match.group(1))


def inspect():
    for unit in OTHER_CONSUMERS:
        other=properties(unit,['MainPID','ActiveState'])
        if other.get('MainPID')!='0' or other.get('ActiveState') not in ('inactive','failed'):
            raise ValueError('another forecast consumer still active')
    value=properties('forecast-intel.service',list(CAPS)+['MainPID','ActiveState','SubState','InvocationID','ExecStart','Environment','SuccessExitStatus'])
    if any(value.get(key)!=expected for key,expected in CAPS.items()):raise ValueError('effective resource envelope changed')
    if value.get('MainPID')!='0' or value.get('ActiveState') not in ('inactive','failed'):raise ValueError('daily consumer still active')
    env=dict(item.split('=',1) for item in shlex.split(value['Environment']))
    if any(env.get(key)!='1' for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):raise ValueError('numerical threads changed')
    return value


def execute(apply):
    expected=json.loads(read(EXPECTED,8192,True));source=read(TEMPLATE,8192);profile=read(PROFILE,8192)
    if sha256(source).hexdigest()!=expected['source_sha256'] or sha256(profile).hexdigest()!=expected['profile_sha256']:
        raise ValueError('reviewed source or original profile changed')
    before=inspect();original_command=expected['original_command'];command=next(line[len('ExecStart='):] for line in source.decode().splitlines() if line.startswith('ExecStart=') and line!='ExecStart=')
    wanted=shlex.split(command)
    if before['InvocationID']!=expected['invocation_id']:raise ValueError('original invocation changed')
    if TARGET.exists():
        if read(TARGET,8192)!=source:raise ValueError('unowned additive definition exists')
    elif argv(before['ExecStart'])!=original_command:raise ValueError('original worker command changed')
    if not apply:
        print(json.dumps({'status':'preflight_passed','effective_caps_verified':True,'definition_installed':TARGET.exists(),'live_writes':False}));return
    # Recheck immediately before creating the one additive file. No overwrite.
    current=inspect()
    if current['InvocationID']!=before['InvocationID'] or sha256(read(PROFILE,8192)).hexdigest()!=expected['profile_sha256'] or read(TEMPLATE,8192)!=source:
        raise ValueError('install context changed')
    if not TARGET.exists():
        fd,path=tempfile.mkstemp(prefix='.daily-lock-wait-',dir=BASE)
        try:
            os.fchmod(fd,0o644)
            with os.fdopen(fd,'wb') as stream:stream.write(source);stream.flush();os.fsync(stream.fileno())
            os.link(path,TARGET,follow_symlinks=False)
        finally:os.unlink(path)
    run('systemctl','--user','daemon-reload')
    after=inspect()
    if (argv(after['ExecStart'])!=wanted or after['SuccessExitStatus'] or after['InvocationID']!=before['InvocationID'] or
        read(TARGET,8192)!=source or sha256(read(PROFILE,8192)).hexdigest()!=expected['profile_sha256']):
        raise ValueError('installed definition readback refused')
    timer=properties('forecast-intel.timer',['ActiveState','NextElapseUSecRealtime'])
    print(json.dumps({'status':'installed_waiting_natural_issue','effective_caps_verified':True,'source_sha256':expected['source_sha256'],
        'worker_started':False,'next_natural_issue':timer['NextElapseUSecRealtime'],'timer_active':timer['ActiveState']=='active'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    try:execute(args.apply)
    except Exception:
        print(json.dumps({'status':'definition_install_refused','worker_started':False}));raise SystemExit(1)
