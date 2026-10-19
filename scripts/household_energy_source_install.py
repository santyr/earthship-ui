"""Install reviewed source bytes coherently; no worker or provider invocation."""
import sys
if sys.flags.optimize:
    raise RuntimeError("optimized deployment execution refused")

from pathlib import Path
from hashlib import sha256
import argparse,ast,importlib.util,json,os,stat,subprocess,tempfile
from thermal_model.capture_guard import SharedScoreLock
from thermal_model.serial_publication_caps import _resource_preflight

BASE=Path('.superpowers/sdd/2026-10-11-household-model-plan-replay/energy-production-stage-f281f4a').resolve()
LIVE=Path('/home/sat/openhab/scripts')
NAMES={'forecast_intel.py','forecast_ml_evidence.py','qualified_soc_forecast.py'}|{'household/'+name+'.py' for name in ('__init__','codec','evidence','snapshot','control_contracts','energy_model')}
HEAD='f281f4ae7f7d5c16de4dc8e36177675a17ff1562'
LOCK='/home/sat/.local/state/thermal-intel/native-input-consumers.lock'


def read(path,maximum=262144):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_size>maximum:raise ValueError('owned bounded source required')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(maximum+1)
        if len(raw)>maximum:raise ValueError('source too large')
        return raw,stat.S_IMODE(info.st_mode)
    finally:os.close(fd)


def module():
    path=Path('scripts/daily_forecast_lock_wait.py').resolve();spec=importlib.util.spec_from_file_location('verified_consumer_checks',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def verify_command(checks,state):
    wanted=["/usr/bin/flock","--wait","90","--conflict-exit-code=75",LOCK,"/usr/bin/python3",str(LIVE/"forecast_intel.py")]
    if checks.argv(state["ExecStart"])!=wanted or state["SuccessExitStatus"]:
        raise ValueError("effective worker lock contract changed")
    companions={
        "forecast-json.service":["/usr/bin/flock","--nonblock","--conflict-exit-code=75",LOCK,"/usr/bin/python3",str(LIVE/"forecast_intel.py"),"json"],
        "forecast-pre-dusk.service":["/usr/bin/flock","--wait","20","--conflict-exit-code=75",LOCK,"/usr/bin/python3",str(LIVE/"forecast_pre_dusk.py")],
    }
    for unit,command in companions.items():
        state=checks.properties(unit,["ExecStart","TimeoutStartUSec","SuccessExitStatus"])
        actual=checks.argv(state["ExecStart"])
        if unit=="forecast-json.service" and actual==["/usr/bin/flock","--wait","90","--conflict-exit-code=75",LOCK,"/usr/bin/python3",str(LIVE/"forecast_intel.py"),"json"]:
            if state.get("TimeoutStartUSec")!="3min 30s" or state.get("SuccessExitStatus")!="":
                raise ValueError("bounded weather consumer budget or failure contract changed")
        else:
            if actual!=command:
                raise ValueError("companion source consumer lock contract changed")
            if unit=="forecast-json.service" and (state.get("TimeoutStartUSec")!="2min" or state.get("SuccessExitStatus")!="75"):
                raise ValueError("legacy weather consumer budget or success contract changed")


def prepare():
    _resource_preflight();manifest=json.loads(read(BASE/'source-manifest.json')[0]);assert manifest['reviewed_head']==HEAD
    assert len(manifest['files'])==len(NAMES) and {row['name'] for row in manifest['files']}==NAMES
    if LIVE.resolve()!=LIVE or LIVE.stat().st_uid!=os.getuid() or (LIVE/'household').exists():raise ValueError('unowned existing package or directory')
    sources={};modes={}
    for row in manifest['files']:
        name=row['name'];target=LIVE/name
        assert Path(row['target'])==target and Path(row['staged'])==BASE/'sources'/name
        raw,_=read(Path(row['staged']));assert sha256(raw).hexdigest()==row['source_sha256'];ast.parse(raw)
        reviewed=subprocess.check_output(['git','show',HEAD+':openhab/scripts/'+name],timeout=5)
        assert reviewed==raw
        if row['existing_target_sha256'] is None:
            assert name.startswith('household/') and not target.exists();mode=0o644
        else:
            existing,mode=read(target);assert sha256(existing).hexdigest()==row['existing_target_sha256']
        sources[name]=raw;modes[name]=mode
    checks=module();state=checks.inspect();verify_command(checks,state);profile=read(checks.PROFILE,8192)[0]
    return sources,modes,checks,state,profile


def atomic(path,raw,mode):
    fd,temp=tempfile.mkstemp(prefix='.energy-input-source-',dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if Path(temp).exists():Path(temp).unlink()


def execute(apply):
    sources,modes,checks,before,profile=prepare()
    verify_command(checks,before)
    if not apply:
        print(json.dumps({'status':'source_preflight_passed','files':len(sources),'production_installed':False,'worker_started':False}));return
    with SharedScoreLock(LOCK) as lock:
        # Revalidate every source, target and consumer after exclusive acquisition.
        again,again_modes,_,state,again_profile=prepare();assert again==sources and again_modes==modes and again_profile==profile
        assert state['InvocationID']==before['InvocationID'];lock.verify()
        package=Path(tempfile.mkdtemp(prefix='.energy-household-',dir=LIVE));package.chmod(0o755)
        for name in sorted(NAMES):
            if name.startswith('household/'):atomic(package/Path(name).name,sources[name],modes[name])
        assert not (LIVE/'household').exists();os.rename(package,LIVE/'household');lock.verify()
        for name in ('forecast_ml_evidence.py','qualified_soc_forecast.py','forecast_intel.py'):
            atomic(LIVE/name,sources[name],modes[name]);lock.verify()
        assert all(read(LIVE/name)[0]==raw for name,raw in sources.items())
        after=checks.inspect();verify_command(checks,after);assert after['InvocationID']==before['InvocationID'] and read(checks.PROFILE,8192)[0]==profile
        lock.verify()
    print(json.dumps({'status':'source_installed_waiting_natural_issue','files':len(sources),'source_head':HEAD,'worker_started':False,'caps_and_invocation_unchanged':True}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    try:execute(args.apply)
    except Exception as e:
        print(json.dumps({'status':'source_install_refused','exception_class':type(e).__name__,'worker_started':False}));raise SystemExit(1)
