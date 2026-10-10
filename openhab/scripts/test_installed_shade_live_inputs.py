"""Bounded live transport/query contracts; no household calls or release proof."""
from datetime import timedelta,datetime,timezone
import io
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from thermal_model.capture_readers import ReadBudget


def module():
    from thermal_model import installed_shade_live_inputs
    return installed_shade_live_inputs


class Response(io.BytesIO):
    def __init__(self,data,url):super().__init__(json.dumps(data).encode());self.url=url
    def geturl(self):return self.url


def test_telemetry_transport_proves_exact_item_and_jdbc_receipt_and_never_sends_commands():
    m=module();at=datetime(2026,10,8,12,tzinfo=timezone.utc);state=json.dumps(dict(schema='unit',version=4))
    observed=[]
    def open(request,timeout):
        observed.append(request)
        if '/persistence/' in request.full_url:return Response(dict(data=[dict(time=int(at.timestamp()*1000),state=state)]),request.full_url)
        if request.method=='GET':return Response(dict(type='String',name='Thermal_Model_JSON'),request.full_url)
        return Response({},request.full_url)
    budget=ReadBudget(30,min_request_interval=1,sleeper=lambda _:None,clock=lambda:1)
    # Fixed test clock makes pacing explicit while real transport remains bounded.
    budget.next_request=None
    transport=m.TelemetryTransport(base='http://127.0.0.1:8080/rest',token_reader=lambda:'fixture',budget=budget,opener=open)
    transport.require_string('Thermal_Model_JSON');budget.next_request=None
    transport.put('Thermal_Model_JSON',state);budget.next_request=None
    actual=transport.persisted('Thermal_Model_JSON',state,since=at,until=at+timedelta(seconds=1))
    assert actual==dict(item='Thermal_Model_JSON',time=int(at.timestamp()*1000),state=state)
    assert observed[1].method=='PUT' and observed[1].data.decode()==state
    assert all('/commands' not in request.full_url and '/runnow' not in request.full_url for request in observed)
    with pytest.raises(ValueError):transport.put('SouthOutlet_Outlet1_Switch','ON')


@pytest.mark.parametrize('bad',['missing','old','different','duplicate','switch'])
def test_bad_item_or_persistence_never_becomes_delivery_proof(bad):
    m=module();at=datetime(2026,10,8,12,tzinfo=timezone.utc);state='{}'
    row=dict(time=int(at.timestamp()*1000),state=state)
    if bad=='old':row['time']-=1000
    if bad=='different':row['state']='[]'
    rows=[] if bad=='missing' else [row,row] if bad=='duplicate' else [row]
    def open(request,timeout):return Response(dict(data=rows) if '/persistence/' in request.full_url else dict(type='Switch',name='Thermal_Model_JSON'),request.full_url)
    budget=ReadBudget(30);transport=m.TelemetryTransport(base='http://127.0.0.1:8080/rest',token_reader=lambda:'fixture',budget=budget,opener=open)
    with pytest.raises(ValueError):
        if bad=='switch':transport.require_string('Thermal_Model_JSON')
        else:transport.persisted('Thermal_Model_JSON',state,since=at,until=at+timedelta(seconds=1))


def test_pending_weather_uses_actual_precollection_cutoff_and_preserves_old_api():
    from thermal_model import forecast_history as h
    from test_thermal_forecast_history import ORIGIN,issue,Connection
    cutoff=ORIGIN-timedelta(seconds=30)
    rows=issue(ORIGIN-timedelta(hours=2),ORIGIN-timedelta(hours=1))
    late=issue(ORIGIN-timedelta(minutes=30),ORIGIN-timedelta(seconds=10))
    connection=Connection(rows+late)
    actual=h.fetch_pending_origin_forecast_with_receipts(lambda:connection,origin=ORIGIN,horizon_hours=1,available_by=cutoff)
    assert actual['issued_at']==ORIGIN-timedelta(hours=2)
    assert connection.cur.calls[-1][1][3]==cutoff
    assert connection.closed and connection.readonly
    legacy=h.fetch_origin_forecast_with_receipts(lambda:Connection(rows+late),origin=ORIGIN,horizon_hours=1)
    assert legacy['issued_at']==ORIGIN-timedelta(minutes=30)


def test_private_live_config_refuses_active_dates_extra_fields_and_public_secrets(tmp_path):
    m=module();tmp_path.chmod(0o700)
    archive=tmp_path/'evidence';archive.mkdir(mode=0o700)
    fields={name:str(tmp_path/name) for name in ('release_inputs_path','token_file','journal_dsn_file','forecast_dsn_file','native_db_config','native_policy')}
    for name in fields:Path(fields[name]).write_text('fixture');Path(fields[name]).chmod(0o600)
    config=dict(schema='earthship-installed-shade-live-config/v1',openhab_base='http://127.0.0.1:8080/rest',evidence_directory=str(archive),**fields)
    path=tmp_path/'config';path.write_text(json.dumps(config));path.chmod(0o600)
    loaded=m.load_live_settings(path);assert loaded['evidence_directory']==str(archive)
    for key in ('active','assessed_at'):
        path.write_text(json.dumps({**config,key:True}))
        with pytest.raises(ValueError):m.load_live_settings(path)
    path.write_text(json.dumps(config));Path(fields['token_file']).chmod(0o644)
    with pytest.raises(ValueError):m.load_live_settings(path)



def test_database_transport_failure_is_an_unavailable_source_not_uncaught_worker_failure(monkeypatch):
    import psycopg2
    m=module();backend=object.__new__(m.LiveBackend)
    backend.budget=ReadBudget(30)
    def refused(_):raise psycopg2.OperationalError('synthetic unavailable source')
    monkeypatch.setattr(psycopg2,'connect',refused)
    with pytest.raises(ValueError,match='source unavailable'):backend._connect('synthetic')



def test_cli_explicit_legacy_profile_checks_private_config_with_no_live_transports(tmp_path):
    import subprocess,sys
    m=module();tmp_path.chmod(0o700);archive=tmp_path/'evidence';archive.mkdir(mode=0o700)
    fields={name:str(tmp_path/name) for name in ('release_inputs_path','token_file','journal_dsn_file','forecast_dsn_file','native_db_config','native_policy')}
    for name in fields:Path(fields[name]).write_text('fixture');Path(fields[name]).chmod(0o600)
    config=dict(schema='earthship-installed-shade-live-config/v1',openhab_base='http://127.0.0.1:8080/rest',evidence_directory=str(archive),**fields)
    path=tmp_path/'config';path.write_text(json.dumps(config));path.chmod(0o600)
    script=Path(__file__).resolve().parent/'thermal_installed_intel.py'
    result=subprocess.run([sys.executable,str(script),'--config',str(path),'--contract-version','1'],check=True,capture_output=True,text=True)
    assert json.loads(result.stdout)==dict(status='configuration_verified',publication_executed=False,automatic_actuation=False)
    assert list(archive.iterdir())==[]


@pytest.mark.parametrize('delay',['item_lookup','request_pacing'])
def test_final_send_guard_runs_after_metadata_and_pacing_and_blocks_expired_native_input(delay):
    from thermal_temperature_runtime import validate_shadow_receipt_expiry
    from thermal_model.temperature_history import STREAMS
    m=module();at=datetime(2026,10,8,12,tzinfo=timezone.utc);clock=[0.0];observed=[]
    current={role:dict(at=at,validUntil=at+timedelta(seconds=1)) for role in STREAMS}
    def sleep(seconds):clock[0]+=seconds
    def open(request,timeout):
        observed.append(request.method)
        if request.method=='GET':
            if delay=='item_lookup':clock[0]+=1.0
            return Response(dict(type='String',name='Thermal_Model_JSON'),request.full_url)
        return Response({},request.full_url)
    budget=ReadBudget(30,min_request_interval=1,sleeper=sleep,clock=lambda:clock[0])
    transport=m.TelemetryTransport(base='http://127.0.0.1:8080/rest',token_reader=lambda:'fixture',budget=budget,opener=open)
    guarded=[]
    def final_guard():
        guarded.append(clock[0])
        validate_shadow_receipt_expiry(current,at+timedelta(seconds=clock[0]))
    with pytest.raises(ValueError,match='expired current'):
        transport.put('Thermal_Model_JSON','{}',preflight=final_guard)
    assert guarded and guarded[0]>=1.0
    assert observed==['GET']



def test_live_source_collection_keeps_preissue_knowledge_native_epoch_and_actual_grid(monkeypatch):
    from thermal_model import action_history,forecast_history
    from thermal_model.temperature_history import STREAMS
    from test_installed_shade_origin import weather,actions,EPOCHS
    import test_thermal_sensor_epoch_origins as native
    import thermal_temperature_runtime as temperatures
    m=module();issue=datetime(2026,12,19,7,5,tzinfo=timezone.utc);known=issue-timedelta(seconds=45)
    monkeypatch.setattr(m,'_clock',lambda:known)
    monkeypatch.setattr(native,'NOW',known)
    original_collector=native.TemperatureCollector
    class ChangingMassCollector(original_collector):
        def observe(self,message):
            stream,model,sensor=STREAMS['mass']
            if message['model']==model and message['id']==str(sensor):
                message={**message,native.MODELS[model][1]:str(70+(self.clock()-known).total_seconds()/86400*3)}
            return super().observe(message)
    monkeypatch.setattr(native,'TemperatureCollector',ChangingMassCollector)
    read=native.native_grid();requests=[];queried=[]
    def pending(factory,*,origin,horizon_hours,available_by):
        queried.append(('weather',origin,available_by));assert horizon_hours==24
        return weather(issue)
    def origin_actions(factory,*,origin):
        queried.append(('actions',origin));return actions(origin)
    def collect(request,*,config_path,policy_path,connection_factory):
        requests.append(request)
        assert request['receipt_version']==2 and request['sensor_epoch'] in EPOCHS.values()
        assert config_path=='native-config' and policy_path=='native-policy'
        return read(request['stream'],[datetime.fromisoformat(t) for t in request['targets']],datetime.fromisoformat(request['assessed_at']))
    monkeypatch.setattr(forecast_history,'fetch_pending_origin_forecast_with_receipts',pending)
    monkeypatch.setattr(action_history,'fetch_origin_actions',origin_actions)
    monkeypatch.setattr(temperatures,'collect_v2',collect)
    backend=object.__new__(m.LiveBackend);backend.settings=dict(native_db_config='native-config',native_policy='native-policy')
    backend.epochs=EPOCHS;backend.budget=ReadBudget(30);backend.journal_dsn=backend.forecast_dsn='unused'
    result=backend.collect(issue=issue,known_at=known)
    assert queried==[('weather',issue,known),('actions',known)]
    assert len(requests)==3 and all(len(row['targets'])==289 for row in requests)
    # Off-grid knowledge clock adds one actual current target to 288 history targets.
    assert all(row['targets'][-1]==known.isoformat() for row in requests)
    assert all(datetime.fromisoformat(row['assessed_at'])==known for row in requests)
    assert set(result['current'])==set(STREAMS)
    assert result['action_snapshot']['origin']==issue
    assert all(datetime.fromisoformat(row['created_at'])<=known for row in result['action_snapshot']['actions'].values())
    assert result['action_snapshot']['actions']['outdoor_shade']['state']=='installed'
    assert all(row['at']<=known for row in result['current'].values())
    assert all(role['identity']['sensor_epoch']==EPOCHS[name] for name,role in result['origin_temperatures']['roles'].items())
    from thermal_model.origin_capture import _temperatures
    from thermal_model.forcing_capture import _canonical
    proof=json.loads(_canonical(result['origin_temperatures']))
    raw_mass=proof['roles']['mass']['grid'][-1][1]['temperatureF']
    assert result['current']['mass']['value']!=pytest.approx(raw_mass,abs=0.01)
    receipt=proof['roles']['mass']['grid'][-1][1]
    assert result['current']['mass']['at']==datetime.fromisoformat(receipt['receivedAt'])
    assert result['current']['mass']['validUntil']==datetime.fromisoformat(receipt['validUntil'])
    epochs,initial=_temperatures(proof,result['current'],issued_at=issue,published_at=issue,version=2)
    assert epochs==EPOCHS and initial['mass']==result['current']['mass']['value']


def source_backend_case(tmp_path,monkeypatch,*,source=True,guard=lambda:None):
    from test_thermal_sensor_epoch_history import sources,EPOCHS
    from test_weather_temperature_history import Connection
    from test_weather_temperature_reader import AT
    from thermal_model import forecast_history,action_history
    import hourly_temperature_runtime
    m=module();policy,rows=sources(tmp_path,monkeypatch);tmp_path.chmod(0o700)
    archive=tmp_path/'queries';archive.mkdir(mode=0o700)
    rows.insert(1,(AT+timedelta(seconds=30),None));known=AT+timedelta(minutes=6)
    backend=object.__new__(m.SourceLiveBackend if source else m.LiveBackend)
    backend.settings=dict(native_db_config='/fixture/db',native_policy=str(policy),evidence_directory=str(archive))
    backend.epochs=dict(EPOCHS);backend.budget=ReadBudget(30,guard=guard);backend.hashes={}
    backend.journal_dsn=backend.forecast_dsn='fixture'
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _:dict(host='127.0.0.1',dbname='openhab',user='reader_fixture',password='fixture'))
    connections=[]
    def connect(_):
        connection=Connection(rows=rows);connections.append(connection);return connection
    backend._connect=connect
    monkeypatch.setattr(forecast_history,'fetch_pending_origin_forecast_with_receipts',lambda *a,**kw:dict(fixture='weather_acquisition'))
    monkeypatch.setattr(action_history,'fetch_origin_actions',lambda *a,**kw:dict(origin=known,fixture='action_acquisition'))
    return backend,known,archive,connections


def test_source_live_backend_archives_and_replays_original_issue_queries(tmp_path,monkeypatch):
    from weather_temperature_sources import read_temperature_source,replay_temperature_source
    from thermal_model.installed_shade_raw_score_sources import build_native_origin_binding
    m=module();assert hasattr(m,'SourceLiveBackend'),'missing raw issue-source backend'
    backend,known,archive,connections=source_backend_case(tmp_path,monkeypatch)
    issue=known+timedelta(seconds=30);inputs=backend.collect(issue=issue,known_at=known)
    binding=build_native_origin_binding(inputs['origin_temperatures'],source_paths=inputs['native_source_paths'],issue_at=issue)
    assert binding['release_authority'] is False
    assert set(inputs)=={'forecast','current','origin_temperatures','action_snapshot','native_source_paths'}
    assert len(list(archive.iterdir()))==3 and len(connections)==3
    assert all(c.closed and c.session['readonly'] is True for c in connections)
    assert inputs['action_snapshot']['origin']==issue
    for role,name in inputs['native_source_paths'].items():
        path=Path(name);assert path.stat().st_mode&0o777==0o600
        packet=read_temperature_source(archive,path)
        assert packet['native_rows'][1][1] is None
        assert json.loads(module()._canonical(replay_temperature_source(packet)))==json.loads(module()._canonical(inputs['origin_temperatures']['roles'][role]['grid']))


def test_old_live_backend_retains_its_receipt_only_contract(tmp_path,monkeypatch):
    backend,known,archive,_=source_backend_case(tmp_path,monkeypatch,source=False)
    inputs=backend.collect(issue=known+timedelta(seconds=30),known_at=known)
    assert set(inputs)=={'forecast','current','origin_temperatures','action_snapshot'}
    assert list(archive.iterdir())==[]


def test_source_live_backend_refuses_lock_loss_before_archiving_query(tmp_path,monkeypatch):
    from test_weather_temperature_history import Connection
    held=[True]
    def guard():
        if not held[0]:raise ValueError('held fixture guard lost')
    backend,known,archive,connections=source_backend_case(tmp_path,monkeypatch,guard=guard)
    original=Connection.close
    def lost(connection):
        original(connection);held[0]=False
    monkeypatch.setattr(Connection,'close',lost)
    with pytest.raises(ValueError):backend.collect(issue=known+timedelta(seconds=30),known_at=known)
    assert len(connections)==1 and connections[0].closed
    assert list(archive.iterdir())==[]


def test_source_live_backend_refuses_lock_loss_during_temporary_query_write(tmp_path,monkeypatch):
    import os
    held=[True]
    def guard():
        if not held[0]:raise ValueError('held fixture guard lost')
    backend,known,archive,_=source_backend_case(tmp_path,monkeypatch,guard=guard)
    original=os.chmod
    def lost(path,mode,*args,**kwargs):
        original(path,mode,*args,**kwargs)
        if Path(path).name.startswith('.temperature-origin-'):held[0]=False
    monkeypatch.setattr(os,'chmod',lost)
    with pytest.raises(ValueError):backend.collect(issue=known+timedelta(seconds=30),known_at=known)
    assert list(archive.iterdir())==[]
