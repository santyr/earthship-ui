"""Read-only score transport and private configuration; no household sources."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import subprocess
import sys
import pytest
from thermal_model.temperature_history import STREAMS,POLICY
from test_thermal_sensor_epoch_history import EPOCHS


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
    def persisted(item,state,*,since,until):observed.append((item,state,since,until));return receipt
    monkeypatch.setattr(reader.transport,'persisted',persisted)
    assert reader.publication(receipt)==receipt
    assert observed==[('Thermal_Model_JSON','{}',now,now+timedelta(milliseconds=1))]
    with pytest.raises(ValueError):reader.publication({**receipt,'item':'SouthOutlet_Outlet1_Switch'})


def test_native_reader_binds_original_phase_and_assessment_without_fallback(settings,monkeypatch):
    import thermal_temperature_runtime as temperatures
    m=module();reader=m.ScoreReader(settings[1]);now=datetime(2026,10,8,12,tzinfo=timezone.utc);seen=[]
    def collect(request,**kwargs):seen.append(request);return [[now,None]]
    monkeypatch.setattr(temperatures,'collect_v2',collect)
    result=reader.native([now],assessed_at=now,sensor_epoch=EPOCHS['air'])
    assert result==[[now,None]]
    assert seen==[dict(stream='indoor',targets=[now.isoformat()],assessed_at=now.isoformat(),receipt_version=2,sensor_epoch=EPOCHS['air'])]
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


def test_cli_default_checks_only_config_with_no_sources_or_retention(settings):
    path,config=settings;module();script=Path(__file__).resolve().parent/'thermal_installed_score.py'
    result=subprocess.run([sys.executable,str(script),'--config',str(path)],check=True,capture_output=True,text=True)
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
    result=subprocess.run([sys.executable,str(script),'--config',str(path),'--collect',
        '--origin',str(path.parent/'missing.installed-shade-origin-v3.json'),'--horizon','1'],capture_output=True,text=True)
    assert result.returncode==1 and json.loads(result.stdout)['status']=='withheld'
    assert 'traceback' not in result.stderr.lower() and list(Path(config['output_directory']).iterdir())==[]
