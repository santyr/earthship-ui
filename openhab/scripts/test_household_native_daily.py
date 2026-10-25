"""Daily training advances the local-day boundary without redundant fitting."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import pytest


def daily():
    path=Path(__file__).with_name('household_native_daily.py')
    assert path.exists(), 'daily native scheduler has not been implemented'
    spec=importlib.util.spec_from_file_location('daily_test_subject',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('now,expected', [
    ('2026-10-15T12:50:00+00:00','2026-10-15T06:00:00+00:00'),
    ('2026-11-02T13:50:00+00:00','2026-11-02T07:00:00+00:00'),
    ('2026-10-15T05:59:00+00:00','2026-10-14T06:00:00+00:00'),
])
def test_cutoff_is_last_local_midnight_including_dst(now,expected):
    assert daily().training_cutoff(datetime.fromisoformat(now),'America/Denver').isoformat()==expected


def test_capture_chunks_cover_only_missing_days_without_gaps():
    m=daily();start=datetime(2026,10,12,6,tzinfo=timezone.utc);end=datetime(2026,10,17,6,tzinfo=timezone.utc)
    chunks=m.capture_windows(start,end)
    assert chunks==[(start,datetime(2026,10,14,6,tzinfo=timezone.utc)),(datetime(2026,10,14,6,tzinfo=timezone.utc),datetime(2026,10,16,6,tzinfo=timezone.utc)),(datetime(2026,10,16,6,tzinfo=timezone.utc),end)]


class Backend:
    def __init__(self,trained,fail=None):self.trained=trained;self.calls=[];self.fail=fail
    def current(self):return {'trained_through':self.trained,'stage':'old','deployment_sha256':'old-pin'}
    def prepare(self,cutoff,previous):
        self.calls.append(('prepare',cutoff,previous));return {'stage':'new'}
    def activate(self,selection,previous):
        self.calls.append(('activate',selection,previous))
        if self.fail:raise ValueError(self.fail)
        return {'status':'native_family_activated'}


def test_current_model_skips_capture_fit_and_handoff():
    b=Backend('2026-10-14T06:00:00+00:00')
    result=daily().run_daily(b,now=datetime(2026,10,14,18,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert result['status']=='already_current';assert b.calls==[]


def test_next_day_prepares_then_activates_with_original_selection():
    b=Backend('2026-10-14T06:00:00+00:00')
    result=daily().run_daily(b,now=datetime(2026,10,15,13,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert result['status']=='native_family_activated'
    assert b.calls[0][1]==datetime(2026,10,15,6,tzinfo=timezone.utc)
    assert b.calls[1][2]['deployment_sha256']=='old-pin'


def test_failed_preparation_never_changes_live_selection():
    b=Backend('2026-10-14T06:00:00+00:00')
    def refuse(*args):raise ValueError('insufficient usable data')
    b.prepare=refuse
    with pytest.raises(ValueError,match='insufficient usable data'):
        daily().run_daily(b,now=datetime(2026,10,15,13,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert b.calls==[]


def test_rolling_parts_keep_crossing_interval_but_drop_expired_parts():
    m=daily();target=datetime(2026,10,20,6,tzinfo=timezone.utc)
    rows=[{'path':'a','start':'2026-10-11T06:00:00+00:00','end':'2026-10-13T06:00:00+00:00'}, {'path':'b','start':'2026-10-13T06:00:00+00:00','end':'2026-10-15T06:00:00+00:00'}, {'path':'c','start':'2026-10-15T06:00:00+00:00','end':'2026-10-17T06:00:00+00:00'}]
    assert m.retained_parts(rows,target)==rows[1:]
    rows[2]['start']='2026-10-16T06:00:00+00:00'
    with pytest.raises(ValueError,match='adjacent'):m.retained_parts(rows,target)


def test_training_builds_real_new_fit_evidence_before_packaging(tmp_path,monkeypatch):
    import json
    import household_native_training as training
    import native_thermal_artifact as artifacts
    from test_installed_shade_inputs import snapshot, END
    from test_native_thermal_inputs import geometry
    from thermal_model.training_inputs import write_training_inputs_v2
    tmp_path.chmod(0o700)
    record=snapshot();source=tmp_path/'source';source.mkdir(mode=0o700)
    write_training_inputs_v2(source,record)
    snapshot_path=source/(record['snapshot_sha256']+'.training-inputs-v2.json')
    geom=geometry(record)
    geom_path=tmp_path/'geometry.json';training.save(geom_path,geom.to_dict())
    backend=training.NativeTraining.__new__(training.NativeTraining)
    backend.state=tmp_path;backend.repo=Path(__file__).resolve().parents[2];backend.guard=lambda:None
    backend.snapshot=lambda run,cutoff:snapshot_path
    backend.geometry=lambda run,rec,previous:(geom,geom_path,{})
    monkeypatch.setattr(artifacts,'current_native_runtime',lambda **kwargs:{'test_binding':'unchanged'})
    packaged=[]
    def package(run,originals,runtime,previous,libraries,commit):
        evidence=json.loads(originals['fit_evidence'].read_bytes())
        assert evidence['fit']['fit_executed'] is True
        assert evidence['schema']=='earthship-native-development-fit-evidence/v4'
        assert evidence['fit']['model_rule']=='earthship-native-irradiance-shade-dynamics/v4'
        assert len(evidence['fit']['coefficients'])==14
        assert datetime.fromisoformat(evidence['fit']['training_end'])==END
        assert evidence['fit']['endpoint_count']>0
        assert evidence['fit_runtime']==runtime
        assert evidence['production_model_changed'] is False
        packaged.append(originals)
        return {'trained_through':evidence['fit']['training_end']}
    backend.package=package
    result=backend.prepare(END,{'stage':'unused'})
    assert datetime.fromisoformat(result['trained_through'])==END
    assert len(packaged)==1


def test_raw_part_fingerprint_drift_is_rejected_without_recapture(tmp_path):
    import household_native_training as training
    tmp_path.chmod(0o700)
    path=tmp_path/'raw.json';training.save(path,{'changed':True})
    training.save(tmp_path/'raw-parts.json',[dict(path=str(path),start='2026-10-14T06:00:00+00:00',
        end='2026-10-15T06:00:00+00:00',sha256='0'*64)])
    backend=training.NativeTraining.__new__(training.NativeTraining)
    backend.state=tmp_path;backend.capture_config={};backend.guard=lambda:None
    with pytest.raises(ValueError,match='bytes changed'):
        backend.raw_parts(datetime(2026,10,15,6,tzinfo=timezone.utc))


def test_first_run_creates_owned_lock_and_concurrent_run_refuses(tmp_path):
    import household_native_training as training
    tmp_path.chmod(0o700)
    lock=tmp_path/'daily.lock'
    assert hasattr(training,'daily_lock'), 'first-run daily lock initialization is missing'
    with training.daily_lock(lock):
        inode=lock.stat().st_ino
        with pytest.raises(BlockingIOError):
            with training.daily_lock(lock):pass
    with training.daily_lock(lock):assert lock.stat().st_ino==inode
    assert lock.stat().st_mode & 0o777 == 0o600


def test_load_domain_refresh_runs_even_when_thermal_is_already_current():
    b=Backend('2026-10-15T06:00:00+00:00');calls=[]
    b.prepare_ac_load=lambda cutoff:calls.append(cutoff) or dict(status='load_profile_prepared')
    result=daily().run_daily(b,now=datetime(2026,10,15,13,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert result['status']=='already_current' and result['ac_load']['status']=='load_profile_prepared'
    assert calls==[datetime(2026,10,15,6,tzinfo=timezone.utc)] and b.calls==[]


def test_load_failure_is_sanitized_and_does_not_prevent_thermal_refresh():
    b=Backend('2026-10-14T06:00:00+00:00');calls=[]
    def failed(cutoff):calls.append(cutoff);raise ValueError('private source detail must not be published')
    b.prepare_ac_load=failed
    result=daily().run_daily(b,now=datetime(2026,10,15,13,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert result['status']=='native_family_activated' and len(calls)==1
    assert result['ac_load']==dict(status='deferred',reason='load_profile_refresh_failed',automatic_actuation=False)
    assert 'private source' not in str(result)


def test_load_refresh_precedes_thermal_selection_and_retains_its_own_status():
    b=Backend('2026-10-14T06:00:00+00:00');calls=[]
    b.prepare_ac_load=lambda cutoff:calls.append('load') or dict(status='load_profile_prepared')
    def failed_current():calls.append('thermal');raise ValueError('thermal selection unavailable')
    b.current=failed_current
    with pytest.raises(ValueError,match='thermal selection unavailable'):
        daily().run_daily(b,now=datetime(2026,10,15,13,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert calls==['load','thermal']


@pytest.mark.parametrize('now,expected',[
    ('2026-10-19T23:50:00+00:00','2026-10-19T18:00:00+00:00'),
    ('2026-10-20T00:50:00+00:00','2026-10-20T00:00:00+00:00'),
    ('2026-11-02T13:50:00+00:00','2026-11-02T13:00:00+00:00'),
    ('2026-11-01T08:30:00+00:00','2026-11-01T06:00:00+00:00'),
])
def test_six_hour_cutoff_respects_local_time_and_dst(now,expected):
    assert daily().training_cutoff(datetime.fromisoformat(now),'America/Denver',cadence='six_hourly').isoformat()==expected


def test_intraday_thermal_refresh_keeps_daily_load_cutoff():
    b=Backend('2026-10-15T06:00:00+00:00');loads=[]
    b.prepare_ac_load=lambda cutoff:loads.append(cutoff) or {'status':'load_profile_already_current'}
    result=daily().run_daily(b,now=datetime(2026,10,15,19,tzinfo=timezone.utc),timezone_name='America/Denver',cadence='six_hourly')
    assert b.calls[0][1]==datetime(2026,10,15,18,tzinfo=timezone.utc)
    assert loads==[datetime(2026,10,15,6,tzinfo=timezone.utc)]
    assert result['fit_executed'] is True


def test_intraday_state_uses_long_original_prefix_without_mutating_it():
    from copy import deepcopy
    rows=[{'path':str(i),'start':f'2026-10-{10+i*2:02d}T06:00:00+00:00','end':f'2026-10-{12+i*2:02d}T06:00:00+00:00','sha256':str(i)*64} for i in range(3)]
    original=deepcopy(rows);selected=daily().long_part_prefix(rows)
    assert selected==rows[:2] and rows==original
    short=dict(rows[0],end='2026-10-10T12:00:00+00:00')
    assert daily().long_part_prefix([short])==[]


def test_valid_retained_package_retries_activation_without_a_second_fit():
    b=Backend('2026-10-14T06:00:00+00:00')
    b.retry_selection=lambda cutoff,previous:{'stage':'retained-qualified'}
    result=daily().run_daily(b,now=datetime(2026,10,15,13,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert b.calls==[('activate',{'stage':'retained-qualified'},b.current())]
    assert result['fit_executed'] is False


@pytest.mark.parametrize('primary,cleanup',[(True,True),(False,True),(False,False)])
def test_main_persists_primary_and_cleanup_domains_separately(tmp_path,monkeypatch,capsys,primary,cleanup):
    import json
    import household_native_training as training
    import household_native_daily as module
    tmp_path.chmod(0o700);config=tmp_path/'config.json';training.save(config,{'timezone':'UTC'})
    backend=Backend('2000-01-01T00:00:00+00:00');backend.state=tmp_path
    calls=[]
    def activate(*args):
        if primary:raise ValueError('private model payload '+('x'*10000))
        return {'status':'native_family_activated'}
    def close():
        calls.append('close')
        if cleanup:raise TimeoutError('external cleanup acknowledgment missing')
    backend.activate=activate;backend.close_reservation=close
    monkeypatch.setattr(training,'NativeTraining',lambda config:backend)
    assert module.main(['--config',str(config)])==int(primary or cleanup)
    result=json.loads((tmp_path/'last-result.json').read_bytes())
    assert json.loads(capsys.readouterr().out)==result
    assert calls==['close']
    if primary:
        assert result['error']=='ValueError'
        assert result['reason']=='native_refresh_failed'
        assert result['cleanup_failure']=={'error':'TimeoutError','reason':'external cleanup acknowledgment missing'}
        assert 'private model payload' not in json.dumps(result) and len(json.dumps(result))<1024
    elif cleanup:
        assert result['error']=='TimeoutError' and result['reason']=='external cleanup acknowledgment missing'
        assert result['failure_domain']=='cleanup' and 'cleanup_failure' not in result
    else:
        assert result['status']=='native_family_activated' and 'cleanup_failure' not in result


def test_cleanup_failure_does_not_replace_cancellation():
    import household_native_daily as module
    backend=Backend('2000-01-01T00:00:00+00:00')
    def activate(*args):raise KeyboardInterrupt('original cancellation')
    def close():raise ValueError('private cleanup details')
    backend.activate=activate;backend.close_reservation=close
    with pytest.raises(KeyboardInterrupt,match='original cancellation') as captured:
        module.run_daily(backend,now=datetime(2026,10,25,tzinfo=timezone.utc),timezone_name='UTC')
    assert captured.value.native_cleanup_failure=={'error':'ValueError','reason':'native_refresh_failed'}


def test_child_failure_is_bound_and_preserved_in_parent_daily_result(tmp_path,monkeypatch,capsys):
    import contextlib,json,os,subprocess,sys
    from types import SimpleNamespace
    import household_native_daily as module
    import household_native_training as training
    import household_native_lifecycle as life
    tmp_path.chmod(0o700);run=training.directory(tmp_path/'run');reservation=training.directory(tmp_path/('a'*32))
    config=tmp_path/'config.json';training.save(config,{'timezone':'UTC'})
    backend=training.NativeTraining.__new__(training.NativeTraining);backend.state=tmp_path;backend.guard=lambda:None
    backend.reservation=SimpleNamespace(directory=reservation,check=lambda:None)
    backend.current=lambda:dict(trained_through='2000-01-01T00:00:00+00:00',stage='old',deployment_sha256='a'*64)
    backend.prepare=lambda *args:dict(stage=str(run/'final'))
    backend.retry_selection=lambda *args:None
    def close():raise TimeoutError('external cleanup acknowledgment missing')
    backend.close_reservation=close
    monkeypatch.setattr(training,'NativeTraining',lambda config:backend)
    monkeypatch.setattr(training,'selected_family_interpreter',lambda *a,**kw:{'path':sys.executable})
    monkeypatch.setattr(life,'activation_lock',lambda run:contextlib.nullcontext())
    def child_activate(run):raise TimeoutError('external activation owner acknowledgment missing')
    monkeypatch.setattr(training,'activate',child_activate)
    def child(command,*,environment,lock,guard):
        with monkeypatch.context() as patch:
            for key in ('EARTHSHIP_NATIVE_DAILY_LOCK_FD','EARTHSHIP_NATIVE_RESERVATION'):patch.setenv(key,environment[key])
            assert module.main(['--activate',str(run)])==1
        raise subprocess.CalledProcessError(1,command)
    monkeypatch.setattr(life,'run_activation_child',child)
    assert module.main(['--config',str(config)])==1
    result=json.loads((tmp_path/'last-result.json').read_bytes())
    assert result['error']=='TimeoutError' and result['reason']=='external activation owner acknowledgment missing'
    assert result['cleanup_failure']=={'error':'TimeoutError','reason':'external cleanup acknowledgment missing'}
    failure=json.loads((run/('activation-failure-'+reservation.name+'.json')).read_bytes())
    assert failure['nonce']==reservation.name and failure['run']==str(run)
    assert failure['failure']=={'error':'TimeoutError','reason':'external activation owner acknowledgment missing'}


def retained_retry_case(tmp_path,monkeypatch):
    """Exercise real retry/history/package control flow with private inputs.

    Numerical receipt admission and stage/family validation have their own real
    fixtures; their expensive or manager-facing boundaries are doubled here.
    The checkpoint, index, history inventory, Git provenance and package writes
    under test are real.
    """
    import json,subprocess
    from hashlib import sha256
    from types import SimpleNamespace
    import household_native_training as training
    import household_native_lifecycle as lifecycle
    import household_native_family as family
    import household_cycle_deploy as deploy
    import household_forecast_score as scorer
    import native_model_serving_receipt as serving
    import native_thermal_artifact as artifact
    from test_native_history_retirement import mutable_history_case
    case=mutable_history_case(tmp_path,monkeypatch)
    backend=case.backend;backend.state=training.directory(tmp_path/'learner')
    repo=training.directory(tmp_path/'repo');backend.repo=repo
    sources={'openhab/scripts/household_native_training.py':b'# original controller\n',
        'openhab/scripts/native_thermal_fit.py':b'# immutable fitted source\n'}
    for name,raw in sources.items():
        path=repo/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_bytes(raw)
    def git(*args):return subprocess.check_output(['git','-C',str(repo),*args]).decode().strip()
    git('init','-q');git('add','.')
    git('-c','commit.gpgsign=false','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','retained source')
    revision=git('rev-parse','HEAD')
    run=training.directory(backend.state/'retained');stage=training.directory(run/'final')
    cutoff=case.now;previous=dict(case.refs[-1],trained_through=(cutoff-training.timedelta(hours=6)).isoformat())
    candidate=dict(artifact_sha256='c'*64,runtime_sha256='d'*64,runtime={'original_runtime':True},
        created_at=cutoff.isoformat(),fit={'training_end':cutoff.isoformat()},originals={})
    for role in ('snapshot','dataset','geometry','fit_evidence'):
        path=run/(role+'.json');training.save(path,{'original':role,'code_revision':revision})
        candidate['originals'][role]={'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}
    candidate_path=run/'candidate.json';training.save(candidate_path,candidate)
    receipt=run/'receipt.json';training.save(receipt,{'original_admission':True})
    receipt_pin=sha256(receipt.read_bytes()).hexdigest()
    previous_config=Path(json.loads((Path(previous['stage'])/'cycle.json').read_bytes())['forecast_config'])
    settings=json.loads(previous_config.read_bytes());old_candidate=tmp_path/'incumbent.json'
    training.save(old_candidate,{'artifact_sha256':settings['artifact_sha256']})
    settings['candidate_path']=str(old_candidate);training.save(previous_config,settings)
    retained_settings=dict(settings,candidate_path=str(candidate_path),artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'],model_receipt_path=str(receipt),model_receipt_sha256=receipt_pin)
    training.save(run/'final-config.json',retained_settings)
    training.save(run/'geometry-libraries.json',{'original_libraries':True})
    training.save(stage/'cycle.json',{'forecast_config':str(run/'final-config.json')})
    record=dict(code_revision=revision,source_manifest={name:sha256(raw).hexdigest() for name,raw in sources.items()},
        artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'])
    training.save(stage/'deployment.json',record);pin=sha256((stage/'deployment.json').read_bytes()).hexdigest()
    selection=dict(stage=str(stage),deployment_sha256=pin,artifact_sha256=candidate['artifact_sha256'],trained_through=cutoff.isoformat())
    proof=case.history.assess(case.refs,now=cutoff,guard=lambda:None)
    training.save(run/'score-history-window.json',proof)
    training.save(run/'final-selection.json',selection)
    training.save(run/'activation-input.json',dict(selection=selection,previous=previous))
    training.save(run/'model-admission.json',dict(reused=False,original=None))
    training.save(run/'score-dispatch.json',dict(schema='earthship-native-score-dispatch/v2',current='current',historical=case.refs[1:]))
    names=('activation-input.json','final-selection.json','final-config.json','score-history-window.json','model-admission.json','score-dispatch.json')
    checkpoint=dict(selection=selection,previous=previous,cutoff=cutoff.isoformat(),code_revision=revision,attempts=1,
        files={name:sha256((run/name).read_bytes()).hexdigest() for name in names})
    training.save(backend.state/'activation-retry.json',checkpoint)
    immutable={path:path.read_bytes() for path in run.rglob('*') if path.is_file()}
    history_verify=deploy.verify_stage
    records={str(stage):record}
    monkeypatch.setattr(deploy,'verify_stage',lambda path,**kwargs:records[str(path)] if str(path) in records else history_verify(path,**kwargs))
    monkeypatch.setattr(family,'verify',lambda path,**kwargs:dict(deployment_sha256=pin))
    monkeypatch.setattr(scorer,'read_score_dispatch',lambda path,**kwargs:dict(historical=case.refs[:2] if Path(path)==Path(previous['stage']) else case.refs[1:]))
    monkeypatch.setattr(serving,'load_serving_selection',lambda path,**kwargs:selection)
    monkeypatch.setattr(serving,'read_serving_model',lambda *args,**kwargs:SimpleNamespace(candidate=candidate,runtime=candidate['runtime'],verify_bindings=lambda **kw:None))
    monkeypatch.setattr(artifact,'current_native_runtime',lambda **kwargs:candidate['runtime'])
    numerical=[]
    def rederive(*,originals,runtime,previous,created_at,guard):
        guard();assert previous==candidate and runtime==candidate['runtime']
        assert originals=={key:Path(ref['path']) for key,ref in candidate['originals'].items()}
        numerical.append(True);return candidate
    monkeypatch.setattr(training,'build_deployment_candidate',rederive)
    def admission(actual,*,selections,guard):
        guard();assert actual==candidate and selections==[{key:selection[key] for key in ('stage','deployment_sha256')}]
        return dict(candidate_path=str(candidate_path),receipt_path=str(receipt),receipt_sha256=receipt_pin,
            verified_at=cutoff.isoformat(),source_stage=str(stage),source_deployment_sha256=pin)
    monkeypatch.setattr(training,'retained_model_admission',admission)
    def forbidden(*args,**kwargs):pytest.fail('retained retry must not fit or issue a replacement admission')
    monkeypatch.setattr(serving,'admit_model',forbidden)
    import native_thermal_fit
    monkeypatch.setattr(native_thermal_fit,'fit_native_development',forbidden)
    backend.inputs={key:str(tmp_path/key) for key in ('parameters','observation_cache','service_file','service_base_config')}
    backend.inputs['parameters_sha256']='e'*64
    def stage_candidate(**kwargs):
        output=training.directory(kwargs['stage']);body=dict(record,code_revision=kwargs['code_revision'])
        training.save(output/'deployment.json',body);records[str(output)]=body
    monkeypatch.setattr(deploy,'stage_deployment',stage_candidate)
    def dispatch(*,historical_selections,output,guard):
        guard();training.save(output,dict(schema='earthship-native-score-dispatch/v2',current='current',historical=list(historical_selections)))
        return dict(path=str(output),sha256=sha256(output.read_bytes()).hexdigest())
    monkeypatch.setattr(family,'prepare_score_dispatch',dispatch)
    monkeypatch.setattr(family,'prepare',lambda *args,**kwargs:kwargs['guard']())
    monkeypatch.setattr(training,'selected_family_interpreter',lambda *args,**kwargs:{'path':'/private/python3.12','sha256':'f'*64})
    owners=[]
    class Reservation:
        def __init__(self,state,run,previous,*,guard):self.check=guard;owners.append(run)
    monkeypatch.setattr(lifecycle,'Reservation',Reservation)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return cutoff
    monkeypatch.setattr(training,'datetime',Clock)
    return SimpleNamespace(
        history=case,backend=backend,run=run,selection=selection,previous=previous,cutoff=cutoff,checkpoint=checkpoint,
        immutable=immutable,candidate=candidate,candidate_path=candidate_path,receipt=receipt,numerical=numerical,owners=owners,git=git,record=record)


def test_retained_retry_repackages_normal_index_advance_without_refitting_or_rewriting_originals(tmp_path,monkeypatch):
    import json
    case=retained_retry_case(tmp_path,monkeypatch);case.history.advance()
    selection=case.backend.retry_selection(case.cutoff,case.previous)
    assert selection!=case.selection and selection['artifact_sha256']==case.selection['artifact_sha256']
    assert selection['trained_through']==case.selection['trained_through']
    new_run=Path(selection['stage']).parent
    assert new_run.parent==case.backend.state and new_run!=case.run
    assert all(path.read_bytes()==raw for path,raw in case.immutable.items())
    checkpoint=json.loads((case.backend.state/'activation-retry.json').read_bytes())
    assert checkpoint==dict(case.checkpoint,attempts=2)
    settings=json.loads((new_run/'final-config.json').read_bytes())
    assert settings['candidate_path']==str(case.candidate_path) and settings['model_receipt_path']==str(case.receipt)
    fresh=json.loads((new_run/'score-history-window.json').read_bytes())
    assert case.history.history.revalidate(fresh,now=case.cutoff,guard=lambda:None)==fresh
    assert case.numerical==[True] and case.owners==[new_run]
    provenance=json.loads((new_run/'retained-fit.json').read_bytes())
    assert provenance['original_retry']==case.checkpoint
    assert provenance['activation_code_revision']==case.git('rev-parse','HEAD')
    with pytest.raises(ValueError,match='exhausted'):
        case.backend.retry_selection(case.cutoff,case.previous)


@pytest.mark.parametrize('damage',['exhausted','previous','handoff','checkpoint_pin','missing_pin','requested_run'])
def test_retained_retry_refuses_invalid_owner_or_checkpoint_before_packaging(tmp_path,monkeypatch,damage):
    import json
    import household_native_training as training
    case=retained_retry_case(tmp_path,monkeypatch);previous=case.previous;kwargs={}
    if damage=='exhausted':case.checkpoint['attempts']=2
    elif damage=='previous':previous=dict(previous,deployment_sha256='0'*64)
    elif damage=='handoff':training.directory(case.run/'handoff')
    elif damage=='checkpoint_pin':(case.run/'activation-input.json').write_bytes(b'{}')
    elif damage=='missing_pin':case.checkpoint['files'].pop('score-history-window.json')
    else:kwargs['requested_run']=case.backend.state/'other-run'
    training.save(case.backend.state/'activation-retry.json',case.checkpoint)
    with pytest.raises(ValueError):case.backend.retry_selection(case.cutoff,previous,**kwargs)
    assert case.owners==[] and case.numerical==[]
    assert json.loads((case.backend.state/'activation-retry.json').read_bytes())==case.checkpoint


def test_retained_retry_records_new_controller_revision_without_relabelling_fit(tmp_path,monkeypatch):
    import json
    case=retained_retry_case(tmp_path,monkeypatch)
    source=case.backend.repo/'openhab/scripts/household_native_training.py'
    source.write_bytes(b'# repaired controller\n')
    case.git('add','.')
    case.git('-c','commit.gpgsign=false','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','controller repair')
    revision=case.git('rev-parse','HEAD');assert revision!=case.checkpoint['code_revision']
    case.history.advance();selected=case.backend.retry_selection(case.cutoff,case.previous)
    new_run=Path(selected['stage']).parent
    assert json.loads((Path(selected['stage'])/'deployment.json').read_bytes())['code_revision']==revision
    assert json.loads((new_run/'retained-fit.json').read_bytes())['original_retry']['code_revision']==case.checkpoint['code_revision']
    assert all(path.read_bytes()==raw for path,raw in case.immutable.items())


@pytest.mark.parametrize('damage',['fitted_source','new_source','dirty','original_revision','dispatch'])
def test_retained_retry_rejects_incompatible_source_and_original_dispatch(tmp_path,monkeypatch,damage):
    import household_forecast_score as scorer
    case=retained_retry_case(tmp_path,monkeypatch)
    if damage=='original_revision':case.record['code_revision']='0'*40
    elif damage=='dispatch':monkeypatch.setattr(scorer,'read_score_dispatch',lambda *args,**kwargs:dict(historical=[]))
    else:
        name='native_thermal_fit.py' if damage=='fitted_source' else 'new_unreviewed.py' if damage=='new_source' else 'household_native_training.py'
        (case.backend.repo/'openhab/scripts'/name).write_bytes(b'# incompatible source\n')
        if damage!='dirty':
            case.git('add','.')
            case.git('-c','commit.gpgsign=false','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','incompatible source')
    with pytest.raises(ValueError):case.backend.retry_selection(case.cutoff,case.previous)
    assert case.owners==[] and case.numerical==[]


def test_retained_retry_respects_unresolved_reservation_before_numerical_or_history_reassembly(tmp_path,monkeypatch):
    import household_native_lifecycle as lifecycle
    case=retained_retry_case(tmp_path,monkeypatch);case.history.advance()
    def unresolved(*args,**kwargs):raise ValueError('previous reservation requires reconciliation')
    monkeypatch.setattr(lifecycle,'Reservation',unresolved)
    with pytest.raises(ValueError,match='reconciliation'):
        case.backend.retry_selection(case.cutoff,case.previous)
    assert case.numerical==[] and all(path.read_bytes()==raw for path,raw in case.immutable.items())


def test_standalone_retry_binds_requested_original_then_activates_derived_candidate(tmp_path,monkeypatch,capsys):
    import json
    import household_native_training as training
    import household_native_daily as module
    import thermal_model.runtime_bundle as bundle
    backend=Backend('2000-01-01T00:00:00+00:00');backend.state=training.directory(tmp_path/'state')
    original=backend.state/'original';derived=backend.state/'derived'
    def retry(cutoff,previous,*,requested_run):
        if requested_run!=original:raise ValueError('exact original retained run required')
        return dict(stage=str(derived/'final'))
    backend.retry_selection=retry
    monkeypatch.setattr(training,'NativeTraining',lambda config:backend)
    trusted=Path('/home/sat/.local/state/earthship-weather/audit-rollout-8f3747-20261020-native/native-config.json')
    read=bundle._owned_bytes
    monkeypatch.setattr(bundle,'_owned_bytes',lambda path,*args:json.dumps({'timezone':'UTC'}).encode() if path==trusted else read(path,*args))
    monkeypatch.delenv('EARTHSHIP_NATIVE_DAILY_LOCK_FD',raising=False)
    assert module.main(['--activate',str(original)])==0
    assert backend.calls==[('activate',{'stage':str(derived/'final')},backend.current())]
    assert json.loads(capsys.readouterr().out)['status']=='native_family_activated'
