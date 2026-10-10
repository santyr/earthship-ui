"""Explicit v2 capture; native receipt parsing is real, SQL transport is synthetic."""
from datetime import timedelta
import json
from pathlib import Path
import pytest
from test_thermal_sensor_epoch_history import sources,EPOCHS,AT,Connection
from test_thermal_capture_backends import environment
from test_thermal_sensor_epoch_training import inputs_v2
from thermal_model.capture_readers import ReadBudget
from thermal_model.schema import THERMAL_ITEMS
from thermal_model.temperature_history import STREAMS
import thermal_model.capture_backends as backends


def test_capture_backend_v2_preserves_native_hardware_and_session_identity(tmp_path,monkeypatch):
    from test_capture_thermal_inputs import configuration
    capture_config,_,_=configuration(tmp_path)
    native_path=json.loads(capture_config.read_text())['native_db_config']
    db_config=json.loads(Path(native_path).read_text())
    policy,rows=sources(tmp_path,monkeypatch);connections=[];clock=[0.]
    import hourly_temperature_runtime
    # Connection transport is replaced; policy/collector/history validation is real.
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _:dict(db_config))
    def connect(dsn):
        value=Connection(rows=rows);connections.append(value);return value
    monkeypatch.setattr(backends.psycopg2,'connect',connect)
    env=environment(AT);env['THERMAL_TEMP_POLICY']=str(policy)
    budget=ReadBudget(10,clock=lambda:clock[0],sleeper=lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    reader=backends.configured_capture_history_v2(lambda *args:pytest.fail('native temperatures used legacy'),AT+timedelta(minutes=10),environ=env,budget=budget)
    for role in STREAMS:
        assert reader(THERMAL_ITEMS[role],AT,AT+timedelta(minutes=10))==[(AT,70),(AT+timedelta(minutes=5),71)]
    for role in STREAMS:
        native=reader.temperature_grids()[role]
        assert {value['sensorEpoch'] for _,value in native}=={EPOCHS[role]}
        assert len({value['streamEpoch'] for _,value in native})==2
    assert reader.evidence_manifest()['version']==2
    assert budget.requests==3 and clock[0]==2
    assert all(c.closed and c.session['readonly'] for c in connections)


@pytest.mark.parametrize('damage',['v1','foreign_sensor','missing_role'])
def test_capture_backend_v2_refuses_bad_policy_before_database(tmp_path,monkeypatch,damage):
    policy,rows=sources(tmp_path,monkeypatch);doc=json.loads(policy.read_text())
    if damage=='v1':
        doc['version']=1
        for value in doc['streams'].values():value.pop('sensor_epoch')
    elif damage=='foreign_sensor':doc['streams']['indoor']['sensor_id']+=1
    else:doc['streams'].pop('outdoor')
    policy.write_text(json.dumps(doc))
    monkeypatch.setattr(backends.psycopg2,'connect',lambda *args:pytest.fail('invalid policy connected'))
    env=environment(AT);env['THERMAL_TEMP_POLICY']=str(policy)
    with pytest.raises(ValueError):backends.configured_capture_history_v2(lambda *args:[],AT+timedelta(hours=1),environ=env,budget=ReadBudget(10))


def cli_context(tmp_path):
    from test_capture_thermal_inputs import cli,configuration,private_file
    command=cli();config,destination,_=configuration(tmp_path)
    doc=json.loads(config.read_text());policy=Path(doc['native_policy']);value=json.loads(policy.read_text())
    value['version']=2
    for role,(stream,_,_) in STREAMS.items():value['streams'][stream]['sensor_epoch']=EPOCHS[role]
    private_file(policy,json.dumps(value))
    return command,config,destination


def test_explicit_v2_capture_preflight_is_read_only(tmp_path,monkeypatch,capsys):
    command,config,destination=cli_context(tmp_path)
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(command,'run_guarded_capture',lambda *args,**kwargs:pytest.fail('preflight launched worker'))
    assert command.main(['--config',str(config),'--destination',str(destination),'--receipt-version','2','--check-only'])==0
    assert json.loads(capsys.readouterr().out)['release_authorized'] is False
    assert list(destination.iterdir())==[]


def test_capture_default_v1_refuses_v2_policy(tmp_path,monkeypatch):
    command,config,destination=cli_context(tmp_path)
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    assert command.main(['--config',str(config),'--destination',str(destination),'--check-only'])==2
    assert list(destination.iterdir())==[]


def test_v2_capture_worker_saves_original_input_without_fitting(tmp_path,monkeypatch):
    from thermal_model.training_inputs import read_training_inputs_v2
    command,config,destination=cli_context(tmp_path);data=inputs_v2()
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(command.os,'getpriority',lambda *args:15)
    for key in ('EARTHSHIP_THERMAL_INPUT_CAPTURE','EARTHSHIP_GUARDED_CAPTURE_WORKER'):monkeypatch.setenv(key,'1')
    for key in ('EARTHSHIP_REMOTE_QUALIFICATION_FIT','EARTHSHIP_QUALIFICATION_FIT'):monkeypatch.setenv(key,'0')
    monkeypatch.setattr(command,'_capture_revision',lambda:'a'*64)
    monkeypatch.setattr(backends,'configured_capture_history_v2',lambda *args,**kwargs:data['series_reader'])
    monkeypatch.setattr(backends,'configured_capture_history',lambda *args,**kwargs:pytest.fail('v2 selected legacy history'))
    monkeypatch.setattr(backends,'configured_capture_journal',lambda **kwargs:data['journal'])
    import thermal_model.pipeline as pipeline
    monkeypatch.setattr(pipeline,'run_training',lambda **kwargs:pytest.fail('capture fitted model'))
    from hashlib import sha256
    digest=sha256(config.read_bytes()).hexdigest()
    assert command.main(['--config',str(config),'--destination',str(destination),'--receipt-version','2','--worker','--expected-config-digest',digest])==0
    receipt=json.loads((destination/'capture-receipt.json').read_text())
    assert all(receipt[key] is False for key in ('fitting_executed','installed','release_authorized'))
    record=read_training_inputs_v2(destination/(receipt['snapshot_sha256']+'.training-inputs-v2.json'))
    for role,native in record['temperature_grids'].items():
        assert {value['sensorEpoch'] for _,value in native}=={EPOCHS[role]}
        assert len({value['streamEpoch'] for _,value in native})==2


def test_parent_propagates_explicit_v2_to_guarded_worker(tmp_path,monkeypatch):
    command,config,destination=cli_context(tmp_path);calls=[]
    monkeypatch.setenv('EARTHSHIP_THERMAL_INPUT_CAPTURE','1')
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    def failed(argv,**kwargs):calls.append((argv,kwargs));return 2
    monkeypatch.setattr(command,'run_guarded_capture',failed)
    assert command.main(['--config',str(config),'--destination',str(destination),'--receipt-version','2'])==2
    argv,limits=calls[0]
    assert argv[argv.index('--receipt-version')+1]=='2' and limits=={'seconds':90}


def test_capture_v2_pins_hardware_phase_across_policy_change(tmp_path,monkeypatch):
    policy,rows=sources(tmp_path,monkeypatch)
    env=environment(AT);env['THERMAL_TEMP_POLICY']=str(policy)
    reader=backends.configured_capture_history_v2(lambda *args:pytest.fail('phase change used fallback'),AT+timedelta(hours=1),environ=env,budget=ReadBudget(10))
    doc=json.loads(policy.read_text());doc['streams']['indoor']['sensor_epoch']=EPOCHS['mass'];policy.write_text(json.dumps(doc))
    monkeypatch.setattr(backends.psycopg2,'connect',lambda *args:pytest.fail('changed phase connected'))
    with pytest.raises(ValueError):reader(THERMAL_ITEMS['air'],AT,AT+timedelta(minutes=10))


def test_v2_capture_refuses_late_result_without_fallback(tmp_path,monkeypatch):
    import thermal_temperature_runtime as runtime
    policy,rows=sources(tmp_path,monkeypatch);clock=[0.]
    env=environment(AT);env['THERMAL_TEMP_POLICY']=str(policy)
    def late(request,**kwargs):
        clock[0]=11
        return [(AT,None),(AT+timedelta(minutes=5),None)]
    monkeypatch.setattr(runtime,'collect_v2',late)
    reader=backends.configured_capture_history_v2(lambda *args:pytest.fail('late source fell back'),AT+timedelta(hours=1),environ=env,budget=ReadBudget(10,clock=lambda:clock[0]))
    with pytest.raises(ValueError):reader(THERMAL_ITEMS['air'],AT,AT+timedelta(minutes=10))


def test_v2_preflight_refuses_v1_policy(tmp_path,monkeypatch):
    from test_capture_thermal_inputs import configuration,cli
    command=cli();config,destination,_=configuration(tmp_path)
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(command,'run_guarded_capture',lambda *args,**kwargs:pytest.fail('v1 policy reached v2 worker'))
    assert command.main(['--config',str(config),'--destination',str(destination),'--receipt-version','2','--check-only'])==2


@pytest.mark.parametrize('flag',['EARTHSHIP_REMOTE_QUALIFICATION_FIT','EARTHSHIP_QUALIFICATION_FIT'])
def test_capture_worker_refuses_any_enabled_fit_opt_in(tmp_path,monkeypatch,flag):
    command,config,destination=cli_context(tmp_path)
    for key in ('EARTHSHIP_THERMAL_INPUT_CAPTURE','EARTHSHIP_GUARDED_CAPTURE_WORKER'):monkeypatch.setenv(key,'1')
    for key in ('EARTHSHIP_REMOTE_QUALIFICATION_FIT','EARTHSHIP_QUALIFICATION_FIT'):monkeypatch.setenv(key,'0')
    monkeypatch.setenv(flag,'1')
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(command.os,'getpriority',lambda *args:15)
    monkeypatch.setattr(command,'_context',lambda *args,**kwargs:pytest.fail('fit-enabled worker reached sources'))
    assert command.main(['--config',str(config),'--destination',str(destination),'--receipt-version','2','--worker'])==2


def test_pressure_aware_parent_routes_native_v2_and_strict_worker_flag(tmp_path,monkeypatch):
    command,config,destination=cli_context(tmp_path);calls=[]
    monkeypatch.setenv('EARTHSHIP_THERMAL_INPUT_CAPTURE','1')
    monkeypatch.setattr(command,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(command,'_pressure_preflight',lambda:None)
    monkeypatch.setattr(command,'run_guarded_capture',lambda *a,**k:pytest.fail('used legacy admission'))
    def stopped(argv,**kwargs):calls.append((argv,kwargs));return 2
    monkeypatch.setattr(command,'_run_pressure_worker',stopped)
    assert command.main(['--config',str(config),'--destination',str(destination),'--receipt-version','2','--pressure-aware'])==2
    argv,limits=calls[0]
    assert '--pressure-aware' in argv and argv[argv.index('--receipt-version')+1]=='2'
    assert limits=={'seconds':90}
