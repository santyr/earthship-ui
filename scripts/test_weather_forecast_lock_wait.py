"""Real exclusive lock behavior; install guards never read live configuration."""
import configparser,importlib.util,json,shlex,subprocess,sys,types
from hashlib import sha256
from pathlib import Path
import pytest
from test_daily_forecast_lock_wait import holder

DROP=Path(__file__).resolve().parents[1]/'openhab/systemd/user/forecast-json.service.d/zzzz-weather-lock-wait.conf'
SCRIPT=Path(__file__).with_name('weather_forecast_lock_wait.py')


def command(tmp_path):
    assert DROP.exists(),'weather bounded-wait definition missing'
    policy=configparser.ConfigParser(strict=False);policy.read(DROP)
    argv=shlex.split(policy['Service']['ExecStart']);lock='/home/sat/.local/state/thermal-intel/native-input-consumers.lock'
    assert argv[:2]==['/usr/bin/flock','--wait'] and argv[2]=='90'
    assert argv[3]=='--conflict-exit-code=75' and argv[4]==lock and argv[-1]=='json'
    assert policy['Service']['TimeoutStartSec']=='210'
    options=argv[1:4];options[1]='0.4'
    worker=tmp_path/'worker.py';worker.write_text('from pathlib import Path\nimport sys\np=Path(sys.argv[1]);p.write_text(p.read_text()+"run\\n" if p.exists() else "run\\n")\n')
    return policy,['/usr/bin/flock',*options,str(tmp_path/'fixture.lock'),sys.executable,str(worker),str(tmp_path/'runs')]


def test_weather_waits_for_existing_lock_and_executes_once(tmp_path):
    _,argv=command(tmp_path);locked=holder(tmp_path,.2)
    try:
        result=subprocess.run(argv,capture_output=True,text=True,timeout=3)
        assert result.returncode==0 and (tmp_path/'runs').read_text()=='run\n'
    finally:locked.wait(timeout=3)


def test_weather_wait_exhaustion_is_failure_without_running_worker(tmp_path):
    policy,argv=command(tmp_path);locked=holder(tmp_path,.9)
    try:
        result=subprocess.run(argv,capture_output=True,text=True,timeout=3)
        assert result.returncode==75 and not (tmp_path/'runs').exists()
        assert policy['Service'].get('SuccessExitStatus')==''
    finally:locked.wait(timeout=3)


def test_weather_uncontended_lock_runs_one_worker(tmp_path):
    _,argv=command(tmp_path)
    result=subprocess.run(argv,capture_output=True,text=True,timeout=3)
    assert result.returncode==0 and (tmp_path/'runs').read_text()=='run\n'


def module():
    assert SCRIPT.exists(),'guarded weather definition installer missing'
    spec=importlib.util.spec_from_file_location('weather_install_fixture',SCRIPT)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def fixture_install(tmp_path,monkeypatch):
    mod=module();source=DROP.read_bytes();template=tmp_path/'template.conf';template.write_bytes(source)
    profile=tmp_path/'profile.conf';profile.write_text('original bounded profile')
    target=tmp_path/'additive.conf';expected=tmp_path/'expected.json'
    original=['/usr/bin/flock','--nonblock','--conflict-exit-code=75',mod.LOCK,'/usr/bin/python3','/home/sat/openhab/scripts/forecast_intel.py','json']
    expected.write_text(json.dumps({'source_sha256':sha256(source).hexdigest(),'profile_sha256':sha256(profile.read_bytes()).hexdigest(),'invocation_id':'fixture-original','original_command':original}));expected.chmod(0o600)
    template.chmod(0o600);profile.chmod(0o600)
    for name,value in (('BASE',tmp_path),('TEMPLATE',template),('PROFILE',profile),('TARGET',target),('EXPECTED',expected)):monkeypatch.setattr(mod,name,value)
    manager={'reloaded':False};calls=[]
    def properties(unit,keys):
        if unit!='forecast-json.service':return {'MainPID':'0','ActiveState':'inactive','NextElapseUSecMonotonic':'fixture-next'}
        worker=['/usr/bin/flock','--wait','90','--conflict-exit-code=75',mod.LOCK,'/usr/bin/python3','/home/sat/openhab/scripts/forecast_intel.py','json'] if manager['reloaded'] else original
        return {**mod.CAPS,'MainPID':'0','ActiveState':'inactive','SubState':'dead','InvocationID':'fixture-original',
            'TimeoutStartUSec':'3min 30s' if manager['reloaded'] else '2min','ExecStart':'{ argv[]='+shlex.join(worker)+' ; }',
            'Environment':'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1','SuccessExitStatus':'' if manager['reloaded'] else '75'}
    def run(*args):calls.append(args);manager['reloaded']=True;return ''
    monkeypatch.setattr(mod,'properties',properties);monkeypatch.setattr(mod,'run',run)
    return mod,properties,calls


@pytest.mark.parametrize('active',['thermal-provisional-forecast.service','thermal-provisional-score.service','forecast-json.service'])
def test_weather_install_refuses_active_consumer_before_write(active,tmp_path,monkeypatch):
    mod,original,calls=fixture_install(tmp_path,monkeypatch)
    def properties(unit,keys):
        state=original(unit,keys)
        if unit==active:state.update(MainPID='123',ActiveState='active')
        return state
    monkeypatch.setattr(mod,'properties',properties)
    with pytest.raises(ValueError):mod.execute(True)
    assert not mod.TARGET.exists() and calls==[]


@pytest.mark.parametrize('damage',['profile','template','existing_target','invocation'])
def test_weather_changed_install_context_cannot_write(damage,tmp_path,monkeypatch):
    mod,original,calls=fixture_install(tmp_path,monkeypatch)
    if damage=='profile':mod.PROFILE.write_text('changed')
    elif damage=='template':mod.TEMPLATE.write_text('changed')
    elif damage=='existing_target':mod.TARGET.write_text('another owner');mod.TARGET.chmod(0o600)
    else:
        def properties(unit,keys):
            state=original(unit,keys)
            if unit=='forecast-json.service':state['InvocationID']='another-invocation'
            return state
        monkeypatch.setattr(mod,'properties',properties)
    with pytest.raises(ValueError):mod.execute(True)
    assert calls==[] and (not mod.TARGET.exists() or mod.TARGET.read_text()=='another owner')


def test_weather_additive_install_preserves_original_profile_and_worker(tmp_path,monkeypatch,capsys):
    mod,_,calls=fixture_install(tmp_path,monkeypatch);before=mod.PROFILE.read_bytes()
    mod.execute(True)
    result=json.loads(capsys.readouterr().out)
    assert mod.TARGET.read_bytes()==mod.TEMPLATE.read_bytes() and mod.PROFILE.read_bytes()==before
    assert result['worker_started'] is False and result['effective_caps_verified'] is True
    assert calls==[('systemctl','--user','daemon-reload')]


@pytest.mark.parametrize('damage',['second_worker','post_command','wrong_wait','wrong_budget','accepted_exhaustion'])
def test_even_pinned_template_cannot_expand_weather_worker_contract(damage,tmp_path,monkeypatch):
    mod,_,calls=fixture_install(tmp_path,monkeypatch);source=mod.TEMPLATE.read_text()
    if damage=='second_worker':source+='\nExecStart=/usr/bin/false\n'
    elif damage=='post_command':source+='\nExecStartPost=/usr/bin/false\n'
    elif damage=='wrong_wait':source=source.replace('--wait 90','--wait 75')
    elif damage=='wrong_budget':source=source.replace('TimeoutStartSec=210','TimeoutStartSec=120')
    else:source=source.replace('SuccessExitStatus=','SuccessExitStatus=75')
    mod.TEMPLATE.write_text(source)
    expected=json.loads(mod.EXPECTED.read_text());expected['source_sha256']=sha256(mod.TEMPLATE.read_bytes()).hexdigest();mod.EXPECTED.write_text(json.dumps(expected))
    with pytest.raises(ValueError):mod.execute(True)
    assert not mod.TARGET.exists() and calls==[]
