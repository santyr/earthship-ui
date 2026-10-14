"""Private cycle configuration cannot choose arbitrary execution or leak data."""
import importlib,json,os
from pathlib import Path
import pytest

def api():return importlib.import_module('household_cycle_sources')

def config(tmp_path):
    return {'schema':'earthship-household-cycle-config/v1',
        'forecast_config':str(tmp_path/'forecast.json'),
        'retained_energy_parameters':str(tmp_path/'original-parameters.json'),
        'parameters_sha256':'a'*64,
        'evidence_directory':str(tmp_path/'private'),
        'observation_cache':str(tmp_path/'private'/'observation.json')}

def test_owned_configuration_preserves_original_parameters_and_explicit_cache(tmp_path):
    original=config(tmp_path);path=tmp_path/'cycle.json'
    path.write_text(json.dumps(original));path.chmod(0o600)
    assert api().load_cycle_settings(path)==original
    assert json.loads(path.read_text())==original

@pytest.mark.parametrize('damage',['schema','extra','digest','relative','mode','symlink'])
def test_unsafe_configuration_refuses_before_any_live_collection(damage,tmp_path):
    original=config(tmp_path)
    if damage=='schema':original['schema']='future/v99'
    if damage=='extra':original['command']='operator-only payload'
    if damage=='digest':original['parameters_sha256']='invalid'
    if damage=='relative':original['forecast_config']='relative/config.json'
    path=tmp_path/'cycle.json';path.write_text(json.dumps(original));path.chmod(0o644 if damage=='mode' else 0o600)
    if damage=='symlink':
        alias=tmp_path/'alias.json';alias.symlink_to(path);path=alias
    with pytest.raises(ValueError):api().load_cycle_settings(path)

def collector_fixture(tmp_path,monkeypatch):
    from datetime import timedelta
    from uuid import UUID
    from household.codec import canonical
    from thermal_model.temperature_history import STREAMS,POLICY
    from test_forecast_pre_dusk import NOW,evidence
    from test_pv_day_evidence import receipt
    from test_household_power_snapshot import source
    from test_weather_temperature_history import Connection
    from test_household_energy_configuration_capture import files
    from test_household_measured_weather import sources
    from household import measured_weather_capture
    module=api()
    monkeypatch.setattr(module,'DAILY_STATE_PATH',tmp_path/'absent-daily-state.json',raising=False)
    paths={name:tmp_path/(name+'.json') for name in ('energy_db','native_db','native_policy')}
    policy={'version':2,'streams':{stream:{'model':model,'sensor_id':sensor,**POLICY,'sensor_epoch':str(UUID(int=30+index))} for index,(name,(stream,model,sensor)) in enumerate(STREAMS.items())}}
    for name,path in paths.items():
        path.write_bytes(canonical(policy if name=='native_policy' else {'fixture':name}));path.chmod(0o600)
    monkeypatch.setattr(module,'PRIVATE_PATHS',paths)
    token=tmp_path/'token';token.write_text('test-only-origin-marker');token.chmod(0o600)
    raw={'BMS_SOC_Evidence_JSON':evidence(),
         'MPPT60_PV_Day_Evidence_JSON':json.dumps(receipt(NOW-timedelta(seconds=2),1)),
         'Power_Evidence_JSON':source()['raw'],'Inverter_AC_Evidence_JSON':source('inverter_ac')['raw']}
    connections=[]
    class EnergyConnection(Connection):
        def execute(self,query,params=None):
            super().execute(query,params)
            if 'FROM public.items' in query:self.item=params[0]
        def fetchall(self):
            if 'public.items' in self.calls[-1][0]:return [(613,)]
            return [(NOW,raw[self.item])]
    def connection_factory(path,user):
        def connect(**kwargs):
            connection=EnergyConnection() if user=='energy_power_reader' else Connection(rows=[])
            connections.append(connection);return connection
        return connect
    monkeypatch.setattr(module,'_connection',connection_factory)
    files(tmp_path,monkeypatch)
    measured=sources(at=NOW)
    policies={}
    for kind,row in measured.items():
        p=tmp_path/(kind+'-policy.json');p.write_text(row['policy_raw']);p.chmod(0o600);policies[kind]=p
    monkeypatch.setattr(measured_weather_capture,'FIXED_POLICY_PATHS',policies)
    monkeypatch.setattr(measured_weather_capture,'_http_get',lambda **kw:measured[kw['kind']]['raw'])
    owner_calls=[]
    def owner(item,*,remaining):
        assert 0<remaining()<=10;owner_calls.append(item);return raw[item]
    collector=module.CycleSourceCollector(token_file=token,openhab_base='http://127.0.0.1:8080/rest',code_revision='c'*40,clock=lambda:NOW,owner_reader=owner,rule_reader=lambda **kw:'[]')
    return collector,raw,owner_calls,connections,NOW

def test_real_collector_compiles_exact_sources_with_unknown_native_fields(tmp_path,monkeypatch):
    from household.power_snapshot import replay_power_snapshot
    collector,raw,calls,connections,now=collector_fixture(tmp_path,monkeypatch)
    result=collector(issue=now+__import__('datetime').timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    receipt=result['power_receipt']
    assert replay_power_snapshot(receipt,runtime_manifest=receipt['runtime_manifest'])==receipt
    assert receipt['snapshot']['domains']['energy']['inverter_output_w']['value']==1000
    assert receipt['snapshot']['domains']['thermal']['air_temperature']['value'] is None
    assert result['owner_bindings']['before']['Inverter_AC_Evidence_JSON']['raw']==raw['Inverter_AC_Evidence_JSON']
    assert len(calls)==8 and all(c.closed for c in connections)
    assert all(c.session=={'readonly':True,'autocommit':False,'isolation_level':'REPEATABLE READ'} for c in connections)
    assert result['automatic_actuation'] is False

def test_owner_restart_between_reads_refuses_the_frame(tmp_path,monkeypatch):
    collector,raw,calls,_,now=collector_fixture(tmp_path,monkeypatch)
    original=collector.owner_reader
    def changed(item,**kw):
        value=original(item,**kw)
        if len(calls)>4 and item=='Inverter_AC_Evidence_JSON':
            body=json.loads(value);body['streamEpoch']='00000000-0000-0000-0000-000000000099';return json.dumps(body)
        return value
    collector.owner_reader=changed
    with pytest.raises(ValueError):collector(issue=now+__import__('datetime').timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)

def test_external_deadline_is_not_replaced_by_fifteen_second_collectors(tmp_path,monkeypatch):
    collector,_,_,connections,now=collector_fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):collector(issue=now+__import__('datetime').timedelta(seconds=8),remaining=lambda:0.,guard=lambda:None)
    assert connections==[]

@pytest.mark.parametrize('kind',['bank','weather_policy','runtime'])
def test_configuration_and_runtime_stay_bound_through_final_frame(kind,tmp_path,monkeypatch):
    from datetime import timedelta
    from household import energy_configuration_capture,measured_weather_capture
    import household.power_snapshot as power
    collector,raw,calls,_,now=collector_fixture(tmp_path,monkeypatch)
    if kind=='runtime':
        original=power.compile_power_inputs
        def compile(*args,**kw):
            result=original(*args,**kw)
            collector.runtime_reader=lambda:{'changed':'a'*64}
            return result
        monkeypatch.setattr(power,'compile_power_inputs',compile)
    else:
        owner=collector.owner_reader
        path=next(iter((energy_configuration_capture.FIXED_PATHS if kind=='bank' else measured_weather_capture.FIXED_POLICY_PATHS).values()))
        def changed(item,**kw):
            result=owner(item,**kw)
            if len(calls)==8:path.write_text(path.read_text()+'\n')
            return result
        collector.owner_reader=changed
    with pytest.raises(ValueError):
        collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)


def test_source_collector_accepts_bounded_eight_second_transport_budget(tmp_path,monkeypatch):
    from datetime import timedelta
    collector,raw,owner_calls,connections,now=collector_fixture(tmp_path,monkeypatch)
    result=collector(issue=now+timedelta(seconds=12),remaining=lambda:8.,guard=lambda:None)
    assert result['issue']==(now+timedelta(seconds=12)).isoformat()
    assert owner_calls


def test_cycle_reuses_one_bounded_transport_for_owner_and_measured_receipts(tmp_path,monkeypatch):
    from household import measured_weather_capture
    original_measured=measured_weather_capture._http_get
    module=api();prepared=[];requests=[]
    class Response:
        status=200
        def __init__(self,url):self.url=url
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def geturl(self):return self.url
        def read(self,maximum):
            assert maximum<=8193
            return b'{"state":"direct-original-marker"}'
    class Opener:
        def open(self,request,*,timeout):
            assert request.get_method()=='GET' and 0<timeout<=2
            requests.append(request.full_url);return Response(request.full_url)
    def build(*handlers):
        prepared.append(handlers);return Opener()
    monkeypatch.setattr(module.urllib.request,'build_opener',build)
    collector,raw,calls,connections,now=collector_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(measured_weather_capture,'_http_get',original_measured)
    assert collector._owner_transport('BMS_SOC_Evidence_JSON',remaining=lambda:2.)=='direct-original-marker'
    assert collector._owner_transport('Inverter_AC_Evidence_JSON',remaining=lambda:2.)=='direct-original-marker'
    assert collector._measured_http(kind='radiation',url=measured_weather_capture.SOURCES['radiation'][1],remaining=lambda:2.)=='{"state":"direct-original-marker"}'
    assert len(prepared)==1 and len(requests)==3
