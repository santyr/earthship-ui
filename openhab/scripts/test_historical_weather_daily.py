from datetime import datetime,timezone
from pathlib import Path
import json
import pytest
from household_native_training import directory,save


@pytest.mark.parametrize("candidate", [None, "thermal-candidate.json"])
def test_existing_daily_owner_refreshes_irradiance_and_admission_after_weather(tmp_path,monkeypatch,candidate):
    import historical_weather_daily as api
    import hourly_temperature_runtime
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    base=directory(tmp_path/'.local/state/earthship-weather')
    for sub in ('historical-measurements','historical-radiation'):
        save(directory(base/sub)/('temperature-index.json' if sub.endswith('measurements') else 'radiation-index.json'),{'days':[{'date':'2026-10-01'}]})
    shadow=directory(base/'shadow')
    for sub in ('historical-learning-current','site-weather-current'):
        save(directory(base/sub)/'last-experiment.json',{'path':str(base/sub/'experiment')})
    conf=directory(tmp_path/'.config/earthship-weather');save(conf/'unused.json',{})
    env=conf/'runtime.env';env.write_text(''.join(k+'='+str(v)+'\n' for k,v in {'EARTHSHIP_WEATHER_ARCHIVE':base/'operational','EARTHSHIP_WEATHER_SHADOW_STATE':shadow,'EARTHSHIP_WEATHER_TEMPERATURE_POLICY':conf/'policy','EARTHSHIP_WEATHER_TEMPERATURE_DB_CONFIG':conf/'db'}.items()));env.chmod(0o600)
    pv=conf/'daily-pv.env';pv.write_text('EARTHSHIP_DAILY_PV_LIBRARIES='+str(conf/'geometry.json')+'\n');pv.chmod(0o600)
    monkeypatch.setattr(hourly_temperature_runtime,'_native_outdoor_policy',lambda x:(None,'fixture-epoch'))
    monkeypatch.setattr(api,'select',lambda *a,**kw:{'status':'selected'})
    calls=[]
    def run(args,**kw):
        from types import SimpleNamespace
        calls.append(args)
        return SimpleNamespace(stdout=b'{}',stderr=b'',returncode=0)
    monkeypatch.setattr(api.subprocess,'run',run)
    extra={} if candidate is None else dict(thermal_admission_selection=conf/candidate)
    out=api.run(runtime_env=env,code_revision='a'*40,root=tmp_path,clock=lambda:datetime(2026,10,20,12,35,tzinfo=timezone.utc),**extra)
    names=[Path(c[1]).name for c in calls]
    assert names[-4:]==['historical_radiation_capture.py','historical_irradiance_train.py','thermal_weather_admit.py','local_forecast_train.py']
    assert out['thermal_weather']=='refreshed_or_already_current'
    train=calls[names.index('historical_irradiance_train.py')]
    assert '--operational-archive' in train and '--libraries' in train

    admission=calls[names.index('thermal_weather_admit.py')]
    assert admission[2:]==([] if candidate is None else ['--selection',str(conf/candidate)])


def test_relative_thermal_candidate_is_rejected_before_work(tmp_path):
    import historical_weather_daily as api
    with pytest.raises(ValueError,match='absolute'):
        api.run(runtime_env=tmp_path/'absent',code_revision='a'*40,thermal_admission_selection=Path('relative.json'))


def test_thermal_readmit_post_respects_owner_deadline():
    from thermal_weather_readmit_post import remaining_budget
    assert remaining_budget(start_usec=1000000,now_monotonic=11.,timeout_seconds=960)==90
    assert remaining_budget(start_usec=1000000,now_monotonic=901.,timeout_seconds=960)==45
    assert remaining_budget(start_usec=1000000,now_monotonic=950.,timeout_seconds=960)==0
    assert remaining_budget(start_usec=0,now_monotonic=950.,timeout_seconds=960)==0
    assert remaining_budget(start_usec=1000000000,now_monotonic=950.,timeout_seconds=960)==0


def _post_fixture(tmp_path,monkeypatch):
    import thermal_weather_readmit_post as api
    from hashlib import sha256
    worker=tmp_path/'openhab/scripts/thermal_weather_readmit.py';worker.parent.mkdir(parents=True);worker.write_bytes(b'fixture never executed')
    monkeypatch.setattr(api,'ROOT',tmp_path)
    config=dict(schema='earthship-thermal-weather-readmit-post/v1',consumer_source_root=str(tmp_path/'consumer'),original_source_roots=[str(tmp_path/'original')],candidate_selection=str(tmp_path/'candidate.json'),selection=str(tmp_path/'serving.json'),output=str(tmp_path/'proofs'),worker_sha256=sha256(worker.read_bytes()).hexdigest())
    path=tmp_path/'post.json';save(path,config)
    return api,path,config


def test_cold_post_admits_with_only_remaining_deadline_and_never_reposts(tmp_path,monkeypatch):
    from types import SimpleNamespace
    api,path,config=_post_fixture(tmp_path,monkeypatch);calls=[]
    def execute(args,**kw):calls.append((args,kw));return SimpleNamespace(returncode=1)
    report,code=api.run(path,clock=lambda:901.,metadata=lambda:(1000000,960),execute=execute)
    assert code==1 and report['status']=='thermal_readmit_unavailable_previous_preserved'
    assert len(calls)==1
    args,kw=calls[0];assert kw['timeout']==45
    assert args[args.index('--seconds')+1]=='30' and args[args.index('--maximum-seconds')+1]=='25'
    assert args[args.index('--original-selection')+1]==config['candidate_selection']
    assert args[args.index('--selection')+1]==config['selection']
    assert '--production' in args and args[args.index('--tasks')+1]=='24'
    assert kw['stdout']==kw['stderr']
    assert api.run(path,clock=lambda:950.,metadata=lambda:(1000000,960),execute=execute)[1]==75
    assert len(calls)==1 # No work can begin past the original owner's deadline.


@pytest.mark.parametrize('kind',['coupled-pointers','changed-worker','unexpected-field'])
def test_cold_post_refuses_invalid_configuration_before_work(tmp_path,monkeypatch,kind):
    api,path,config=_post_fixture(tmp_path,monkeypatch)
    if kind=='coupled-pointers':config['candidate_selection']=config['selection']
    if kind=='changed-worker':config['worker_sha256']='0'*64
    if kind=='unexpected-field':config['arbitrary_command']='private'
    save(path,config)
    with pytest.raises(ValueError):api.run(path,metadata=lambda:pytest.fail('must not reach owner or spawn'))


def test_cold_post_cli_withholds_private_failure_diagnostics(tmp_path,monkeypatch,capsys):
    import thermal_weather_readmit_post as api
    def fail(*a,**kw):raise ValueError('/private/path secret-value')
    monkeypatch.setattr(api,'run',fail)
    assert api.main(['--config',str(tmp_path/'private')])==1
    output=capsys.readouterr()
    assert '/private/' not in output.out+output.err and 'secret-value' not in output.out+output.err
    assert json.loads(output.out)['status']=='thermal_readmit_unavailable_previous_preserved'
