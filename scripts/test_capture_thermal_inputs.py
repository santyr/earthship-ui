"""Private capture command routing; all source backends replaced with fixtures."""
import importlib.util
from pathlib import Path
from datetime import timedelta
import json
import pytest
from test_thermal_training_inputs import inputs


def cli():
    spec=importlib.util.spec_from_file_location('capture_inputs_cli',Path(__file__).with_name('capture-thermal-inputs.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def private_file(path,text):path.write_text(text);path.chmod(0o600);return path


def configuration(tmp_path):
    from thermal_model.temperature_history import STREAMS,POLICY
    tmp_path.chmod(0o700);data=inputs();destination=tmp_path/'output';destination.mkdir(mode=0o700)
    value=dict(start=data['start'].isoformat(),end=data['end'].isoformat(),openhab_base='http://127.0.0.1:8080/rest',
        token_file=str(private_file(tmp_path/'token','synthetic-token')),
        journal_dsn_file=str(private_file(tmp_path/'journal','host=127.0.0.1 dbname=openhab user=synthetic_reader password=synthetic')),
        native_db_config=str(private_file(tmp_path/'native-db',json.dumps(dict(host='127.0.0.1',port=5432,dbname='openhab',user='weather_temperature_reader',password='synthetic')))),native_policy=str(private_file(tmp_path/'policy',json.dumps(dict(version=1,streams={stream:dict(model=model,sensor_id=sensor,**POLICY) for stream,model,sensor in STREAMS.values()})))),
        native_cutover=data['start'].isoformat())
    config=private_file(tmp_path/'capture.json',json.dumps(value))
    return config,destination,data


def test_check_only_never_launches_or_reads_sources(tmp_path,monkeypatch,capsys):
    command=cli();config,destination,data=configuration(tmp_path)
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(command,'run_guarded_capture',lambda *args,**kwargs:pytest.fail('check launched worker'))
    assert command.main(['--config',str(config),'--destination',str(destination),'--check-only'])==0
    assert json.loads(capsys.readouterr().out)['status']=='capture_config_verified'
    assert list(destination.iterdir())==[]


def test_capture_requires_explicit_intent_before_launch(tmp_path,monkeypatch):
    command=cli();config,destination,data=configuration(tmp_path)
    monkeypatch.delenv('EARTHSHIP_THERMAL_INPUT_CAPTURE',raising=False)
    monkeypatch.setattr(command,'run_guarded_capture',lambda *args,**kwargs:pytest.fail('capture launched without intent'))
    assert command.main(['--config',str(config),'--destination',str(destination)])==2


@pytest.mark.parametrize('damage',['exposed_config','nonempty','remote','impossible_budget'])
def test_invalid_capture_context_refuses_before_worker(tmp_path,monkeypatch,damage):
    command=cli();config,destination,data=configuration(tmp_path)
    value=json.loads(config.read_text())
    if damage=='exposed_config':config.chmod(0o644)
    if damage=='nonempty':(destination/'existing').write_text('retained')
    if damage=='remote':value['openhab_base']='https://unapproved.invalid/rest'
    if damage=='impossible_budget':value['start']=(data['end']-timedelta(days=30)).isoformat()
    if damage in ('remote','impossible_budget'):private_file(config,json.dumps(value))
    monkeypatch.setenv('EARTHSHIP_THERMAL_INPUT_CAPTURE','1')
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(command,'run_guarded_capture',lambda *args,**kwargs:pytest.fail('invalid context launched'))
    assert command.main(['--config',str(config),'--destination',str(destination)])==2


@pytest.mark.parametrize('damage',['none','changed_code','receipt_failure'])
def test_worker_captures_fixture_without_fit_or_publication(tmp_path,monkeypatch,damage):
    command=cli();config,destination,data=configuration(tmp_path)
    import thermal_model.capture_backends as backends
    import thermal_model.capture_readers as readers
    import thermal_model.pipeline as pipeline
    monkeypatch.setenv('EARTHSHIP_GUARDED_CAPTURE_WORKER','1')
    monkeypatch.setenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT','0')
    monkeypatch.setenv('EARTHSHIP_THERMAL_INPUT_CAPTURE','1')
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(command.os,'getpriority',lambda *args:15)
    monkeypatch.setattr(backends,'configured_capture_history',lambda *args,**kwargs:data['series_reader'])
    monkeypatch.setattr(backends,'configured_capture_journal',lambda **kwargs:data['journal'])
    monkeypatch.setattr(readers,'BoundedJDBCReader',lambda **kwargs:lambda *args:pytest.fail('fixture source bypassed'))
    monkeypatch.setattr(pipeline,'run_training',lambda **kwargs:pytest.fail('capture fitted'))
    revisions=iter(['a'*64,'b'*64] if damage=='changed_code' else ['a'*64,'a'*64])
    monkeypatch.setattr(command,'_capture_revision',lambda:next(revisions))
    if damage=='receipt_failure':
        import thermal_model.runtime_bundle as runtime
        def fail(*args):raise OSError('synthetic receipt failure')
        monkeypatch.setattr(runtime,'_write_private',fail)
    from hashlib import sha256
    status=command.main(['--config',str(config),'--destination',str(destination),'--worker','--expected-config-digest',sha256(config.read_bytes()).hexdigest()])
    if damage!='none':
        assert status==2 and not (destination/'capture-receipt.json').exists()
        if damage=='changed_code':assert list(destination.iterdir())==[]
        return
    assert status==0
    receipt=json.loads((destination/'capture-receipt.json').read_text())
    assert receipt['fitting_executed'] is False and receipt['release_authorized'] is False
    from thermal_model.training_inputs import read_training_inputs
    record=read_training_inputs(destination/(receipt['snapshot_sha256']+'.training-inputs-v1.json'))
    assert record['dataset_manifest']['sample_count']==4
    assert record['events'][0]['source']=='historical_reconstruction'


def test_collection_revision_binds_capture_sources(monkeypatch):
    command=cli();seen=[];raw=[b'synthetic source']
    import thermal_model.origin_capture as origin
    def source(path,maximum):seen.append(str(path.relative_to(command.ROOT)));return raw[0]
    monkeypatch.setattr(origin,'_source_bytes',source)
    first=command._capture_revision()
    assert {'scripts/capture-thermal-inputs.py','openhab/scripts/thermal_model/capture_guard.py','openhab/scripts/thermal_model/capture_readers.py','openhab/scripts/thermal_model/capture_backends.py','openhab/scripts/thermal_model/training_inputs.py'}<=set(seen)
    raw[0]=b'changed source'
    assert command._capture_revision()!=first


def test_bad_native_policy_refuses_during_preflight(tmp_path,monkeypatch):
    command=cli();config,destination,data=configuration(tmp_path)
    value=json.loads(config.read_text());private_file(Path(value['native_policy']),'{}')
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(command,'run_guarded_capture',lambda *args,**kwargs:pytest.fail('invalid native policy launched worker'))
    assert command.main(['--config',str(config),'--destination',str(destination),'--check-only'])==2


@pytest.mark.parametrize('helper',['environment_bundle','rollback'])
def test_collection_revision_changes_for_executed_safety_helper(monkeypatch,helper):
    command=cli();changed=[False]
    import thermal_model.origin_capture as origin
    target='openhab/scripts/thermal_model/'+helper+'.py'
    def source(path,maximum):return b'changed' if changed[0] and str(path.relative_to(command.ROOT))==target else b'original'
    monkeypatch.setattr(origin,'_source_bytes',source)
    first=command._capture_revision();changed[0]=True
    assert command._capture_revision()!=first


def test_worker_config_digest_mismatch_refuses_before_collection(tmp_path,monkeypatch):
    command=cli();config,destination,data=configuration(tmp_path)
    monkeypatch.setenv('EARTHSHIP_GUARDED_CAPTURE_WORKER','1');monkeypatch.setenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT','0');monkeypatch.setenv('EARTHSHIP_THERMAL_INPUT_CAPTURE','1')
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None);monkeypatch.setattr(command.os,'getpriority',lambda *args:15)
    monkeypatch.setattr(command,'_worker',lambda *args:pytest.fail('changed configuration collected'))
    assert command.main(['--config',str(config),'--destination',str(destination),'--worker','--expected-config-digest','0'*64])==2


def test_parent_worker_failure_emits_no_success_receipt(tmp_path,monkeypatch,capsys):
    command=cli();config,destination,data=configuration(tmp_path);calls=[]
    monkeypatch.setenv('EARTHSHIP_THERMAL_INPUT_CAPTURE','1');monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    def failed(argv,**kwargs):calls.append((argv,kwargs));return 2
    monkeypatch.setattr(command,'run_guarded_capture',failed)
    assert command.main(['--config',str(config),'--destination',str(destination)])==2
    assert calls[0][1]=={'seconds':90} and '--worker' in calls[0][0] and '--expected-config-digest' in calls[0][0]
    assert capsys.readouterr().out=='' and list(destination.iterdir())==[]
