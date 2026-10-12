"""Guarded additive definition install; never starts or interrupts a worker."""
from pathlib import Path
from hashlib import sha256
import argparse,configparser,json,os,re,shlex,stat,subprocess,tempfile

LOCK='/home/sat/.local/state/thermal-intel/native-input-consumers.lock'
ORIGINAL=['/usr/bin/flock','--nonblock','--conflict-exit-code=75',LOCK,'/usr/bin/python3','/home/sat/openhab/scripts/forecast_intel.py','json']
WANTED=['/usr/bin/flock','--wait','90','--conflict-exit-code=75',LOCK,'/usr/bin/python3','/home/sat/openhab/scripts/forecast_intel.py','json']
BASE=Path('/home/sat/.config/systemd/user/forecast-json.service.d')
FRAGMENT=BASE.parent/'forecast-json.service'
PROFILE=BASE/'zzz-bounded-native-inputs.conf'
TARGET=BASE/'zzzz-weather-lock-wait.conf'
TEMPLATE=Path('openhab/systemd/user/forecast-json.service.d/zzzz-weather-lock-wait.conf')
EXPECTED=Path('.superpowers/sdd/2026-10-11-household-weather-lock-wait/expected-install.json')
OTHER_CONSUMERS=('thermal-provisional-forecast.service','thermal-provisional-score.service',
                 'thermal-model-shadow.service','forecast-intel.service','forecast-pre-dusk.service','forecast-temperature-score.service')
CAPS={'Type':'oneshot','Restart':'no','CPUQuotaPerSecUSec':'200ms',
      'MemoryMax':'268435456','MemorySwapMax':'0','TasksMax':'24','Nice':'15','IOSchedulingClass':'3','IOWeight':'10','Slice':'earthship-inputs.slice'}


def read(path,maximum,private=False):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode&0o022 or private and stat.S_IMODE(info.st_mode)!=0o600:
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
    matches=re.findall(r'argv\[\]=(.+?)\s*;',raw)
    if len(matches)!=1:raise ValueError('exact single manager command required')
    return shlex.split(matches[0])


HOOKS=('ExecCondition','ExecStartPre','ExecStartPost','ExecReload','ExecStop','ExecStopPost')


def verify_definitions(state,expected,source):
    original=expected['definition_sources']
    if (not isinstance(original,dict) or not 2<=len(original)<=16 or
        not {str(FRAGMENT),str(PROFILE)}<=set(original) or str(TARGET) in original):
        raise ValueError('complete original definition inventory required')
    for name,wanted in original.items():
        path=Path(name)
        if (not path.is_absolute() or path.resolve()!=path or path!=FRAGMENT and path.parent!=BASE or
            not isinstance(wanted,str) or re.fullmatch('[0-9a-f]{64}',wanted) is None or
            sha256(read(path,8192)).hexdigest()!=wanted):
            raise ValueError('original definition source changed')
    if original[str(PROFILE)]!=expected['profile_sha256']:raise ValueError('original profile identity differs')
    loaded=[state['FragmentPath'],*shlex.split(state['DropInPaths'])]
    wanted=set(original)|({str(TARGET)} if TARGET.exists() else set())
    if state['FragmentPath']!=str(FRAGMENT) or len(loaded)!=len(wanted) or set(loaded)!=wanted:
        raise ValueError('unknown or missing effective definition')
    if TARGET.exists() and read(TARGET,8192)!=source:raise ValueError('additive definition differs')


def inspect():
    for unit in OTHER_CONSUMERS:
        other=properties(unit,['MainPID','ActiveState'])
        if other.get('MainPID')!='0' or other.get('ActiveState') not in ('inactive','failed'):
            raise ValueError('another forecast consumer still active')
    value=properties('forecast-json.service',list(CAPS)+list(HOOKS)+['FragmentPath','DropInPaths','MainPID','ActiveState','SubState','InvocationID','ExecStart','Environment','SuccessExitStatus','TimeoutStartUSec'])
    if any(value.get(key)!=expected for key,expected in CAPS.items()):raise ValueError('effective resource envelope changed')
    if any(value.get(key)!='' for key in HOOKS):raise ValueError('extra effective worker commands refused')
    if value.get('MainPID')!='0' or value.get('ActiveState') not in ('inactive','failed'):raise ValueError('weather consumer still active')
    env=dict(item.split('=',1) for item in shlex.split(value['Environment']))
    if any(env.get(key)!='1' for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):raise ValueError('numerical threads changed')
    return value


def execute(apply):
    expected=json.loads(read(EXPECTED,8192,True));source=read(TEMPLATE,8192);profile=read(PROFILE,8192)
    if sha256(source).hexdigest()!=expected['source_sha256'] or sha256(profile).hexdigest()!=expected['profile_sha256']:
        raise ValueError('reviewed source or original profile changed')
    before=inspect();original_command=expected['original_command'];command=next(line[len('ExecStart='):] for line in source.decode().splitlines() if line.startswith('ExecStart=') and line!='ExecStart=')
    verify_definitions(before,expected,source)
    wanted=shlex.split(command)
    policy=configparser.ConfigParser(strict=False);policy.read_string(source.decode())
    starts=[line.strip()[len('ExecStart='):] for line in source.decode().splitlines() if line.strip().startswith('ExecStart=')]
    if (len(starts)!=2 or starts[0]!='' or shlex.split(starts[1])!=WANTED or policy.defaults() or
        policy.sections()!=['Service'] or set(policy['Service'])!={'execstart','timeoutstartsec','successexitstatus'} or
        policy['Service']['TimeoutStartSec']!='210' or policy['Service']['SuccessExitStatus'] or wanted!=WANTED or original_command!=ORIGINAL):
        raise ValueError('fixed weather worker contract required')
    if before['InvocationID']!=expected['invocation_id']:raise ValueError('original invocation changed')
    if TARGET.exists():
        if (read(TARGET,8192)!=source or argv(before['ExecStart'])!=WANTED or before['SuccessExitStatus'] or before['TimeoutStartUSec']!='3min 30s'):
            raise ValueError('unowned additive definition or effective worker contract differs')
    elif (argv(before['ExecStart'])!=original_command or before['SuccessExitStatus']!='75' or before['TimeoutStartUSec']!='2min'):
        raise ValueError('original worker command or budget changed')
    if not apply:
        print(json.dumps({'status':'preflight_passed','effective_caps_verified':True,'definition_installed':TARGET.exists(),'live_writes':False}));return
    # Recheck immediately before creating the one additive file. No overwrite.
    current=inspect()
    verify_definitions(current,expected,source)
    if current!=before or sha256(read(PROFILE,8192)).hexdigest()!=expected['profile_sha256'] or read(TEMPLATE,8192)!=source:
        raise ValueError('install context changed')
    if not TARGET.exists():
        fd,path=tempfile.mkstemp(prefix='.weather-lock-wait-',dir=BASE)
        try:
            os.fchmod(fd,0o644)
            with os.fdopen(fd,'wb') as stream:stream.write(source);stream.flush();os.fsync(stream.fileno())
            os.link(path,TARGET,follow_symlinks=False)
        finally:os.unlink(path)
    run('systemctl','--user','daemon-reload')
    after=inspect()
    verify_definitions(after,expected,source)
    if (argv(after['ExecStart'])!=wanted or after['TimeoutStartUSec']!='3min 30s' or after['SuccessExitStatus'] or after['InvocationID']!=before['InvocationID'] or
        read(TARGET,8192)!=source or sha256(read(PROFILE,8192)).hexdigest()!=expected['profile_sha256']):
        raise ValueError('installed definition readback refused')
    timer=properties('forecast-json.timer',['ActiveState','NextElapseUSecMonotonic'])
    print(json.dumps({'status':'installed_waiting_natural_issue','effective_caps_verified':True,'source_sha256':expected['source_sha256'],
        'worker_started':False,'next_natural_issue':timer['NextElapseUSecMonotonic'],'timer_active':timer['ActiveState']=='active'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    try:execute(args.apply)
    except Exception:
        print(json.dumps({'status':'definition_install_refused','worker_started':False}));raise SystemExit(1)
