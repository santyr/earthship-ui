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
    assert code==1 and report['status']=='thermal_readmit_unchanged'
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
    assert json.loads(output.out)['status']=='thermal_readmit_selection_uncertain'


def test_failed_child_after_publication_does_not_claim_previous_selector_preserved(tmp_path,monkeypatch):
    from types import SimpleNamespace
    api,path,config=_post_fixture(tmp_path,monkeypatch)
    target=Path(config['selection']);save(target,{'fixture':'previous'})
    def published(*a,**kw):save(target,{'fixture':'changed'});return SimpleNamespace(returncode=1)
    report,code=api.run(path,clock=lambda:901.,metadata=lambda:(1000000,960),execute=published)
    assert code==1
    assert report['status']=='thermal_readmit_selection_uncertain'
    assert report['selection_outcome']=='changed_unverified'
    assert json.loads(target.read_bytes())=={'fixture':'changed'}


def _post_bridge(tmp_path,monkeypatch):
    from hashlib import sha256
    from test_thermal_weather_admit import bridge_fixture
    import thermal_weather_readmit_post as api
    args,kwargs,old,producer,consumer=bridge_fixture(tmp_path,monkeypatch)
    serving=tmp_path/'serving-pointer.json';serving.write_bytes(args['selection'].read_bytes());serving.chmod(0o600)
    kwargs['selection']=serving
    worker=api.ROOT/'openhab/scripts/thermal_weather_readmit.py'
    config=dict(schema='earthship-thermal-weather-readmit-post/v1',consumer_source_root=str(consumer),
        original_source_roots=[str(producer)],candidate_selection=str(args['selection']),selection=str(serving),
        output=str(kwargs['output']),worker_sha256=sha256(worker.read_bytes()).hexdigest())
    path=tmp_path/'post.json';save(path,config)
    return api,path,kwargs


@pytest.mark.parametrize('termination',['success','failure','timeout','cancelled'])
def test_post_observes_verified_publication_independently_from_child_termination(tmp_path,monkeypatch,termination):
    from types import SimpleNamespace
    import subprocess
    import thermal_weather_readmit as child
    api,path,kwargs=_post_bridge(tmp_path,monkeypatch)
    before=kwargs['selection'].read_bytes();calls=[]
    def execute(*args,**options):
        calls.append(1);child.readmit(**kwargs)
        if termination=='timeout':raise subprocess.TimeoutExpired('private-child-command',options['timeout'])
        if termination=='cancelled':raise KeyboardInterrupt()
        return SimpleNamespace(returncode=0 if termination=='success' else 1)
    report,code=api.run(path,clock=lambda:901.,metadata=lambda:(1000000,960),execute=execute)
    assert code=={'success':0,'failure':1,'timeout':124,'cancelled':130}[termination]
    assert report['status']=='thermal_readmit_selection_changed_verified'
    assert report['selection_outcome']=='changed_verified'
    assert report['execution_status']=={'success':'succeeded','failure':'failed','timeout':'timed_out','cancelled':'cancelled'}[termination]
    assert report['child_exit_code']==({'success':0,'failure':1}.get(termination))
    assert report['selection_writer']=='unattributed'
    assert report['admission_sha256'] and report['compatibility_sha256']
    assert kwargs['selection'].read_bytes()!=before and len(calls)==1
    assert str(tmp_path) not in json.dumps(report)


@pytest.mark.parametrize('damage',['proof','consumer','selector_mode','changed_during_readback'])
def test_post_does_not_call_unverified_or_concurrently_replaced_selection_usable(tmp_path,monkeypatch,damage):
    from types import SimpleNamespace
    import thermal_weather_readmit as child
    api,path,kwargs=_post_bridge(tmp_path,monkeypatch);published=[]
    def execute(*a,**kw):
        result=child.readmit(**kwargs)
        if damage=='proof':Path(result['compatibility_path']).write_bytes(b'{}')
        if damage=='consumer':
            p=kwargs['consumer_source_root']/'openhab/scripts/weather_learning/site_calibration.py';p.write_bytes(p.read_bytes()+b'\n# drift')
        if damage=='selector_mode':kwargs['selection'].chmod(0o644)
        if damage=='changed_during_readback':
            original=child.hash_reference;changed=[False]
            def hash_and_change(ref,**options):
                original(ref,**options)
                if not changed[0]:save(kwargs['selection'],{'independent_writer':'newer'});changed[0]=True
            monkeypatch.setattr(child,'hash_reference',hash_and_change)
        published.append(kwargs['selection'].read_bytes());return SimpleNamespace(returncode=1)
    report,code=api.run(path,clock=lambda:901.,metadata=lambda:(1000000,960),execute=execute)
    assert code==1 and report['status']=='thermal_readmit_selection_uncertain'
    assert 'admission_sha256' not in report
    # No automatic rollback or repeat, including another writer's update.
    if damage=='changed_during_readback':assert json.loads(kwargs['selection'].read_bytes())=={'independent_writer':'newer'}
    else:assert kwargs['selection'].read_bytes()==published[0]


def test_post_readback_deadline_cannot_renew_or_undo_a_published_selector(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import thermal_weather_readmit as child
    api,path,kwargs=_post_bridge(tmp_path,monkeypatch);tick=[901.]
    def execute(*a,**kw):
        child.readmit(**kwargs);tick[0]=960.;return SimpleNamespace(returncode=0)
    report,code=api.run(path,clock=lambda:tick[0],metadata=lambda:(1000000,960),execute=execute)
    assert code!=0 and report['status']=='thermal_readmit_selection_uncertain'
    assert json.loads(kwargs['selection'].read_bytes())['schema']=='earthship-thermal-weather-selection/v1'


@pytest.mark.parametrize('termination',['success','failure','timeout'])
def test_post_unchanged_result_is_based_on_actual_bytes_even_for_failed_children(tmp_path,monkeypatch,termination):
    from types import SimpleNamespace
    import subprocess
    api,path,config=_post_fixture(tmp_path,monkeypatch)
    pointer=Path(config['selection']);save(pointer,{'fixture':'previous'});before=pointer.read_bytes()
    def execute(*a,**kw):
        if termination=='timeout':raise subprocess.TimeoutExpired('private',kw['timeout'])
        return SimpleNamespace(returncode=0 if termination=='success' else 1)
    report,code=api.run(path,clock=lambda:901.,metadata=lambda:(1000000,960),execute=execute)
    assert code=={'success':0,'failure':1,'timeout':124}[termination]
    assert report['status']=='thermal_readmit_unchanged' and report['selection_present'] is True
    assert report['selection_before_sha256']==report['selection_after_sha256']
    assert 'admission_sha256' not in report and pointer.read_bytes()==before


def test_post_unreadable_prior_selector_is_uncertain_and_does_not_launch(tmp_path,monkeypatch):
    api,path,config=_post_fixture(tmp_path,monkeypatch)
    pointer=Path(config['selection']);save(pointer,{'fixture':'previous'});pointer.chmod(0o644)
    report,code=api.run(path,clock=lambda:901.,metadata=lambda:(1000000,960),
        execute=lambda *a,**kw:pytest.fail('unsafe prior selector must not launch'))
    assert code==1 and report['status']=='thermal_readmit_selection_uncertain'
    assert report['execution_status']=='not_started'
