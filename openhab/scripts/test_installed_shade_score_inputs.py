"""Read-only score transport and private configuration; no household sources."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import subprocess
import sys
import pytest
from thermal_model.temperature_history import STREAMS,POLICY
from test_thermal_sensor_epoch_history import EPOCHS
from test_weather_temperature_history import Connection


class WindowConnection(Connection):
    """Read-only transport double honors the actual SQL endpoint bounds."""
    def fetchone(self):
        query,params=self.calls[-1]
        if 'WHERE time <' in query:
            return next((row for row in reversed(self.rows) if row[0]<params[0]),None)
        return super().fetchone()
    def fetchall(self):
        query,params=self.calls[-1]
        if 'WHERE time >=' in query:return [row for row in self.rows if params[0]<=row[0]<=params[1]]
        return super().fetchall()


def module():
    from thermal_model import installed_shade_score_inputs
    return installed_shade_score_inputs


@pytest.fixture
def settings(tmp_path):
    tmp_path.chmod(0o700);archive=tmp_path/'out';archive.mkdir(mode=0o700)
    sources={key:str(tmp_path/key) for key in ('token_file','native_db_config','native_policy')}
    for path in sources.values():Path(path).write_text('fixture');Path(path).chmod(0o600)
    policy=dict(version=2,streams={stream:dict(model=model,sensor_id=sensor,**POLICY,sensor_epoch=EPOCHS[role]) for role,(stream,model,sensor) in STREAMS.items()})
    Path(sources['native_policy']).write_text(json.dumps(policy))
    config=dict(schema='earthship-installed-shade-score-config/v1',openhab_base='http://127.0.0.1:8080/rest',output_directory=str(archive),**sources)
    path=tmp_path/'settings.json';path.write_text(json.dumps(config));path.chmod(0o600)
    return path,config


def test_only_closed_private_settings_allow_score_reader(settings):
    path,config=settings;m=module();assert m.load_score_settings(path)==config
    for field in ('active','assessed_at','forecast_dsn_file'):
        path.write_text(json.dumps({**config,field:True}))
        with pytest.raises(ValueError):m.load_score_settings(path)
    path.write_text(json.dumps(config));Path(config['token_file']).chmod(0o644)
    with pytest.raises(ValueError):m.load_score_settings(path)


def test_original_jdbc_query_uses_actual_receipt_window_instead_of_today(settings,monkeypatch):
    m=module();reader=m.ScoreReader(settings[1]);now=datetime(2026,10,8,12,tzinfo=timezone.utc)
    receipt=dict(item='Thermal_Model_JSON',time=int(now.timestamp()*1000),state='{}');observed=[]
    def persisted(item,state,*,since,until,preflight=None):
        if preflight:preflight()
        observed.append((item,state,since,until));return receipt
    monkeypatch.setattr(reader.transport,'persisted',persisted)
    assert reader.publication(receipt)==receipt
    assert observed==[('Thermal_Model_JSON','{}',now,now+timedelta(milliseconds=1))]
    with pytest.raises(ValueError):reader.publication({**receipt,'item':'SouthOutlet_Outlet1_Switch'})


def test_native_reader_binds_original_phase_and_assessment_without_fallback(settings,monkeypatch):
    import hourly_temperature_runtime
    from test_weather_temperature_history import Connection
    m=module();reader=m.ScoreReader(settings[1]);now=datetime(2026,10,8,12,tzinfo=timezone.utc)
    connection=Connection(rows=[])
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _: {})
    monkeypatch.setattr(reader,'_connect',lambda config:connection)
    result=reader.native([now],assessed_at=now,sensor_epoch=EPOCHS['air'])
    assert result==[(now,None)] and connection.closed
    assert connection.calls[-1][1]==(now-timedelta(seconds=120),now)
    assert len(reader.native_source_paths)==1
    with pytest.raises(ValueError):reader.native([now],assessed_at=now,sensor_epoch=EPOCHS['mass'])


def test_changed_private_source_file_refuses_collection(settings):
    m=module();reader=m.ScoreReader(settings[1]);Path(settings[1]['token_file']).write_text('changed')
    with pytest.raises(ValueError):reader.verify_unchanged()


def test_database_error_is_a_withheld_source_and_connection_is_read_only(settings,monkeypatch):
    import psycopg2
    from psycopg2.extensions import parse_dsn
    m=module();reader=m.ScoreReader(settings[1]);observed=[]
    def unavailable(dsn):observed.append(parse_dsn(dsn));raise psycopg2.OperationalError('synthetic unavailable source')
    monkeypatch.setattr(psycopg2,'connect',unavailable)
    with pytest.raises(ValueError):reader._connect(dict(dbname='openhab',user='weather_temperature_reader',host='127.0.0.1',password=Path(settings[1]['token_file']).read_text()))
    assert observed and 'default_transaction_read_only=on' in observed[0]['options']
    assert int(observed[0]['connect_timeout'])<=3


def test_cli_explicit_base_profile_checks_only_config_with_no_sources_or_retention(settings):
    path,config=settings;module();script=Path(__file__).resolve().parent/'thermal_installed_score.py'
    result=subprocess.run([sys.executable,str(script),'--contract-version','1','--config',str(path)],check=True,capture_output=True,text=True)
    assert json.loads(result.stdout)==dict(status='configuration_verified',collection_executed=False,release_authorized=False)
    assert list(Path(config['output_directory']).iterdir())==[]


def test_real_jdbc_transport_is_get_only_and_preserves_exact_original_time(settings):
    from test_installed_shade_live_inputs import Response
    m=module();reader=m.ScoreReader(settings[1]);at=datetime(2026,10,8,12,tzinfo=timezone.utc)
    receipt=dict(item='Thermal_OriginalForecast_JSON',time=int(at.timestamp()*1000),state='{}');requests=[]
    def open(request,timeout):
        requests.append(request)
        return Response(dict(data=[{k:v for k,v in receipt.items() if k!='item'}]),request.full_url)
    reader.transport.opener=open
    assert reader.publication(receipt)==receipt
    assert len(requests)==1 and requests[0].method=='GET' and requests[0].data is None
    assert '/persistence/items/Thermal_OriginalForecast_JSON?' in requests[0].full_url
    assert '/commands' not in requests[0].full_url and '/runnow' not in requests[0].full_url


def test_cli_missing_original_cannot_query_household_or_retain_data(settings):
    path,config=settings;script=Path(__file__).resolve().parent/'thermal_installed_score.py'
    lock=path.parent/'global-lock';lock.touch(mode=0o600)
    result=subprocess.run([sys.executable,str(script),'--contract-version','1','--config',str(path),'--collect',
        '--origin',str(path.parent/'missing.installed-shade-origin-v3.json'),'--horizon','1',
        '--shared-lock',str(lock)],capture_output=True,text=True)
    assert result.returncode==1 and json.loads(result.stdout)['status']=='withheld'
    assert 'traceback' not in result.stderr.lower() and list(Path(config['output_directory']).iterdir())==[]


def test_native_reader_retains_raw_query_and_returns_only_replayed_selection(settings,tmp_path,monkeypatch):
    from test_thermal_sensor_epoch_history import sources
    from test_weather_temperature_history import Connection
    from test_weather_temperature_reader import AT
    from weather_temperature_sources import read_temperature_source,replay_temperature_source
    _,raw=sources(tmp_path,monkeypatch);m=module();reader=m.ScoreReader(settings[1])
    connections=[]
    def connect(config):
        connection=WindowConnection(rows=raw);connections.append(connection);return connection
    monkeypatch.setattr(reader,'_connect',connect)
    targets=[AT+timedelta(seconds=60),AT+timedelta(seconds=360)]
    grid=reader.native(targets,assessed_at=AT+timedelta(minutes=10),sensor_epoch=EPOCHS['air'])
    assert [r['temperatureF'] for _,r in grid]==[70.,71.]
    assert len(reader.native_source_paths)==2
    selected=[]
    for name in reader.native_source_paths:
        p=Path(name);packet=read_temperature_source(p.parent,p)
        assert len(packet['targets'])==1
        selected.extend(replay_temperature_source(packet))
    assert selected==grid and all(c.closed for c in connections)
    assert len(connections)==2
    assert all(c.calls[-1][1][1]-c.calls[-1][1][0]==timedelta(seconds=120) for c in connections)


def test_configuration_drift_during_native_read_cannot_retain_a_score_source(settings,tmp_path,monkeypatch):
    from test_thermal_sensor_epoch_history import sources
    from test_weather_temperature_history import Connection
    from test_weather_temperature_reader import AT
    _,raw=sources(tmp_path,monkeypatch);m=module();reader=m.ScoreReader(settings[1])
    def connect(config):
        Path(settings[1]['token_file']).write_text('synthetic changed credential')
        return Connection(rows=raw[:1])
    monkeypatch.setattr(reader,'_connect',connect)
    with pytest.raises(ValueError):reader.native([AT+timedelta(seconds=60)],assessed_at=AT+timedelta(minutes=10),sensor_epoch=EPOCHS['air'])
    assert list(Path(settings[1]['output_directory']).iterdir())==[]


def test_identical_endpoint_reuses_immutable_source_but_replays_again(settings,tmp_path,monkeypatch):
    from test_thermal_sensor_epoch_history import sources
    from test_weather_temperature_reader import AT
    _,raw=sources(tmp_path,monkeypatch);m=module();reader=m.ScoreReader(settings[1]);connections=[]
    def connect(config):
        c=WindowConnection(rows=raw);connections.append(c);return c
    monkeypatch.setattr(reader,'_connect',connect)
    target=AT+timedelta(seconds=60);assessed=AT+timedelta(minutes=10)
    first=reader.native([target],assessed_at=assessed,sensor_epoch=EPOCHS['air'])
    first[0][1]['temperatureF']=99.
    second=reader.native([target],assessed_at=assessed,sensor_epoch=EPOCHS['air'])
    assert second[0][1]['temperatureF']==70.
    assert len(connections)==1 and len(reader.native_source_paths)==1
    Path(reader.native_source_paths[0]).unlink()
    with pytest.raises((ValueError,OSError)):reader.native([target],assessed_at=assessed,sensor_epoch=EPOCHS['air'])
    assert len(connections)==1


@pytest.mark.parametrize('barrier',[False,True])
def test_far_endpoint_queries_keep_small_raw_windows_and_invalid_barriers(settings,monkeypatch,barrier):
    import hourly_temperature_runtime
    from weather_temperature_evidence import TemperaturePolicy,MODELS
    from weather_temperature_receiver import TemperatureCollector
    from weather_temperature_sources import read_temperature_source
    from test_weather_temperature_reader import AT
    policy=TemperaturePolicy('Fineoffset-WH32B',235,**POLICY);clock={'at':AT,'tick':1000}
    source=TemperatureCollector({'indoor':policy},sensor_epochs={'indoor':EPOCHS['air']},clock=lambda:clock['at'],monotonic=lambda:clock['tick'],process_id=lambda:1)
    raw=[]
    for index in range(289):
        at=AT+timedelta(minutes=5*index);clock.update(at=at,tick=1000+index*300)
        source.observe({'model':policy.model,'id':str(policy.sensor_id),MODELS[policy.model][1]:'70'})
        raw.append((at+timedelta(seconds=20),json.dumps(source.snapshot())))
    targets=[AT+timedelta(seconds=60),AT+timedelta(days=1,seconds=60)]
    if barrier:raw.append((targets[-1]-timedelta(seconds=10),None))
    reader=module().ScoreReader(settings[1]);connections=[]
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _: {})
    def connect(config):
        c=WindowConnection(rows=raw);connections.append(c);return c
    monkeypatch.setattr(reader,'_connect',connect)
    selected=reader.native(targets,assessed_at=targets[-1]+timedelta(minutes=10),sensor_epoch=EPOCHS['air'])
    assert [r['temperatureF'] if r else None for _,r in selected]==[70.,None if barrier else 70.]
    packets=[read_temperature_source(Path(p).parent,Path(p)) for p in reader.native_source_paths]
    assert sum(len(p['native_rows']) for p in packets)<=4
    assert len(connections)==2 and all(c.closed for c in connections)


@pytest.mark.parametrize('version',[1,3,4])
@pytest.mark.parametrize('lost',['configuration','lock'])
def test_score_reader_cannot_publish_raw_query_when_guard_is_lost_during_temporary_write(settings,monkeypatch,lost,version):
    import hourly_temperature_runtime
    import os
    m=module();state={'held':True}
    def guard():
        if not state['held']:raise ValueError('synthetic lock lost')
    reader=m.ScoreReader({**settings[1],'schema':f'earthship-installed-shade-score-config/v{version}'},shared_lock_guard=guard)
    now=datetime(2026,10,8,12,tzinfo=timezone.utc)
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _: {})
    monkeypatch.setattr(reader,'_connect',lambda _:WindowConnection(rows=[]))
    original=os.chmod
    def write_then_lose(path,mode,*args,**kwargs):
        original(path,mode,*args,**kwargs)
        if Path(path).name.startswith('.temperature-origin-'):
            if lost=='configuration':Path(settings[1]['token_file']).write_text('synthetic changed credential')
            else:state['held']=False
    monkeypatch.setattr(os,'chmod',write_then_lose)
    with pytest.raises(ValueError):reader.native([now],assessed_at=now,sensor_epoch=EPOCHS['air'])
    assert list(Path(settings[1]['output_directory']).iterdir())==[]
    assert reader.native_source_paths==[]


@pytest.mark.parametrize('when',['before','after'])
def test_score_reader_read_budget_refuses_operations_outside_shared_lock(settings,when):
    state={'held':True};effects=[]
    def guard():
        if not state['held']:raise ValueError('synthetic lock lost')
    reader=module().ScoreReader(settings[1],shared_lock_guard=guard)
    def operation():
        effects.append('response');state['held']=False;return 'synthetic response'
    if when=='before':state['held']=False
    with pytest.raises(ValueError):reader.budget.call(operation)
    assert effects==([] if when=='before' else ['response'])



def test_explicit_source_score_configuration_refuses_legacy_and_override_paths(settings):
    m=module();assert hasattr(m,'load_source_score_settings'),'missing explicit source score settings'
    path,value=settings;value={**value,'schema':'earthship-installed-shade-score-config/v3'}
    path.write_text(json.dumps(value))
    assert m.load_source_score_settings(path)==value
    for reader in (m.load_score_settings,m.load_raw_score_settings):
        with pytest.raises(ValueError):reader(path)
    path.write_text(json.dumps({**value,'active':True}))
    with pytest.raises(ValueError):m.load_source_score_settings(path)
    path.write_text(json.dumps({**value,'schema':'earthship-installed-shade-score-config/v2'}))
    with pytest.raises(ValueError):m.load_source_score_settings(path)


def test_cli_explicit_source_profile_checks_config_without_source_access(settings):
    path,value=settings;value={**value,'schema':'earthship-installed-shade-score-config/v3'}
    path.write_text(json.dumps(value))
    script=Path(__file__).resolve().parent/'thermal_installed_score.py'
    result=subprocess.run([sys.executable,str(script),'--contract-version','3','--config',str(path)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)==dict(status='configuration_verified',collection_executed=False,release_authorized=False)
    assert list(Path(value['output_directory']).iterdir())==[]


@pytest.mark.parametrize('guard',[None,'not callable'])
def test_source_score_reader_requires_held_guard_before_private_reads(settings,monkeypatch,guard):
    m=module();value={**settings[1],'schema':'earthship-installed-shade-score-config/v3'}
    monkeypatch.setattr(m,'_owned_bytes',lambda *a,**kw:pytest.fail('source scorer read private files before a held guard'))
    with pytest.raises(ValueError):m.ScoreReader(value,shared_lock_guard=guard)


@pytest.mark.parametrize('when',['pacing','response'])
def test_source_acquisition_refuses_shared_deadline_expiry_at_http_boundaries(settings,when):
    from thermal_model.capture_readers import ReadBudget
    from thermal_model.replay_budget import shared_replay_budget
    from test_installed_shade_live_inputs import Response
    reader=module().ScoreReader({**settings[1],'schema':'earthship-installed-shade-score-config/v3'},shared_lock_guard=lambda:None)
    clock={'tick':0.};requests=[]
    def remaining():
        reader.verify_unchanged()  # Real queue callback: must not recurse.
        return 0.5-clock['tick']
    def sleep(delay):clock['tick']+=delay
    reader.budget=ReadBudget(85,clock=lambda:clock['tick'],sleeper=sleep)
    reader.transport.budget=reader.budget
    if when=='pacing':reader.budget.begin()
    at=datetime(2026,10,8,12,tzinfo=timezone.utc)
    receipt=dict(item='Thermal_Model_JSON',time=int(at.timestamp()*1000),state='{}')
    def open(request,timeout):
        requests.append(timeout)
        response=Response(dict(data=[{k:v for k,v in receipt.items() if k!='item'}]),request.full_url)
        if when=='response':clock['tick']=1.
        return response
    reader.transport.opener=open
    with shared_replay_budget(remaining):
        with pytest.raises(ValueError):reader.publication(receipt)
    assert requests==([] if when=='pacing' else [0.5])


def test_source_acquisition_expiry_during_native_temporary_write_leaves_no_query(settings,monkeypatch):
    import hourly_temperature_runtime,os
    from thermal_model.replay_budget import shared_replay_budget
    reader=module().ScoreReader({**settings[1],'schema':'earthship-installed-shade-score-config/v3'},shared_lock_guard=lambda:None)
    state={'remaining':55.}
    def remaining():reader.verify_unchanged();return state['remaining']
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _: {})
    monkeypatch.setattr(reader,'_connect',lambda _:WindowConnection(rows=[]))
    original=os.chmod
    def expired(path,mode,*args,**kwargs):
        original(path,mode,*args,**kwargs)
        if Path(path).name.startswith('.temperature-origin-'):state['remaining']=0.
    monkeypatch.setattr(os,'chmod',expired)
    now=datetime(2026,10,8,12,tzinfo=timezone.utc)
    with shared_replay_budget(remaining):
        with pytest.raises(ValueError):reader.native([now],assessed_at=now,sensor_epoch=EPOCHS['air'])
    assert list(Path(settings[1]['output_directory']).iterdir())==[]
    assert reader.native_source_paths==[]


def test_source_connection_closes_if_shared_deadline_expires_during_connect(settings,monkeypatch):
    import psycopg2
    from thermal_model.replay_budget import shared_replay_budget
    reader=module().ScoreReader({**settings[1],'schema':'earthship-installed-shade-score-config/v3'},shared_lock_guard=lambda:None)
    state={'remaining':55.};connection=WindowConnection(rows=[])
    def remaining():reader.verify_unchanged();return state['remaining']
    def connect(_):state['remaining']=0.;return connection
    monkeypatch.setattr(psycopg2,'connect',connect)
    with shared_replay_budget(remaining):
        with pytest.raises(ValueError):reader._connect(dict(dbname='openhab',user='weather_temperature_reader',host='127.0.0.1',password=Path(settings[1]['token_file']).read_text()))
    assert connection.closed


def test_source_native_deadline_stops_subsequent_transaction_statements(settings,monkeypatch):
    import hourly_temperature_runtime
    from thermal_model.replay_budget import shared_replay_budget
    reader=module().ScoreReader({**settings[1],'schema':'earthship-installed-shade-score-config/v3'},shared_lock_guard=lambda:None)
    state={'remaining':55.}
    def remaining():reader.verify_unchanged();return state['remaining']
    class ExpiringConnection(WindowConnection):
        def execute(self,query,params=None):
            super().execute(query,params)
            if query=='SHOW transaction_read_only':state['remaining']=0.
    connection=ExpiringConnection(rows=[])
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _: {})
    monkeypatch.setattr(reader,'_connect',lambda _:connection)
    now=datetime(2026,10,8,12,tzinfo=timezone.utc)
    with shared_replay_budget(remaining):
        with pytest.raises(ValueError):reader.native([now],assessed_at=now,sensor_epoch=EPOCHS['air'])
    assert connection.closed
    assert not any(query=='SHOW transaction_isolation' or query.startswith('SELECT') for query,_ in connection.calls)
    assert list(Path(settings[1]['output_directory']).iterdir())==[]


def test_source_native_statement_timeout_is_clipped_to_shared_remaining(settings,monkeypatch):
    import hourly_temperature_runtime
    from thermal_model.replay_budget import shared_replay_budget
    reader=module().ScoreReader({**settings[1],'schema':'earthship-installed-shade-score-config/v3'},shared_lock_guard=lambda:None)
    connection=WindowConnection(rows=[])
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _: {})
    monkeypatch.setattr(reader,'_connect',lambda _:connection)
    now=datetime(2026,10,8,12,tzinfo=timezone.utc)
    with shared_replay_budget(lambda:0.75):
        assert reader.native([now],assessed_at=now,sensor_epoch=EPOCHS['air'])==[(now,None)]
    timeouts=[params for query,params in connection.calls if query=='SET LOCAL statement_timeout = %s']
    assert timeouts and all(params==('750ms',) for params in timeouts)
    assert connection.closed


def test_source_connect_rechecks_timeout_after_final_configuration_guard(settings,monkeypatch):
    import psycopg2
    from thermal_model.replay_budget import shared_replay_budget
    reader=module().ScoreReader({**settings[1],'schema':'earthship-installed-shade-score-config/v3'},shared_lock_guard=lambda:None)
    state={'remaining':3.};opened=[];original=reader._acquisition_check
    def guard():original();state['remaining']-=0.75
    monkeypatch.setattr(reader,'_acquisition_check',guard)
    def connect(_):opened.append(True);return WindowConnection(rows=[])
    monkeypatch.setattr(psycopg2,'connect',connect)
    with shared_replay_budget(lambda:state['remaining']):
        with pytest.raises(ValueError):reader._connect(dict(dbname='openhab',user='weather_temperature_reader',host='127.0.0.1',password=Path(settings[1]['token_file']).read_text()))
    assert opened==[]


def test_compressed_score_profile_is_explicit_and_requires_lock(settings):
    path,config=settings;m=module();config={**config,'schema':'earthship-installed-shade-score-config/v4'}
    path.write_text(json.dumps(config));loader=getattr(m,'load_compressed_source_score_settings',None)
    assert callable(loader),'missing explicit compressed score configuration'
    assert loader(path)==config
    for old in (m.load_score_settings,m.load_raw_score_settings,m.load_source_score_settings):
        with pytest.raises(ValueError):old(path)
    with pytest.raises(ValueError):m.ScoreReader(config)


def test_compressed_score_acquisition_retains_exact_sources_and_reuses_queries(settings,tmp_path,monkeypatch):
    import hourly_temperature_runtime
    from test_thermal_sensor_epoch_history import sources
    from test_weather_temperature_reader import AT
    from weather_temperature_sources import read_compressed_temperature_source,read_temperature_source,replay_temperature_source
    _,raw=sources(tmp_path,monkeypatch);m=module()
    assert hasattr(m,'COMPRESSED_SOURCE_SCHEMA'),'missing compressed score acquisition profile'
    reader=m.ScoreReader({**settings[1],'schema':m.COMPRESSED_SOURCE_SCHEMA},shared_lock_guard=lambda:None)
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _: {})
    connections=[]
    def connect(_):
        c=WindowConnection(rows=raw);connections.append(c);return c
    monkeypatch.setattr(reader,'_connect',connect)
    target=AT+timedelta(seconds=60);assessed=AT+timedelta(minutes=10)
    first=reader.native([target],assessed_at=assessed,sensor_epoch=EPOCHS['air'])
    assert first[0][1]['temperatureF']==70.
    path=Path(reader.native_source_paths[0]);packet=read_compressed_temperature_source(path.parent,path)
    assert replay_temperature_source(packet)==first
    with pytest.raises(ValueError):read_temperature_source(path.parent,path)
    assert reader.native([target],assessed_at=assessed,sensor_epoch=EPOCHS['air'])==first
    assert len(connections)==1 and connections[0].closed
    path.unlink()
    with pytest.raises((ValueError,OSError)):reader.native([target],assessed_at=assessed,sensor_epoch=EPOCHS['air'])
    assert len(connections)==1
