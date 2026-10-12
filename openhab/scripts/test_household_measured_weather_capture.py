"""Fixed owner GETs and original policy files form one bounded acquisition."""
import importlib,json
from pathlib import Path
import pytest
from test_household_measured_weather import sources,AT


def api():return importlib.import_module('household.measured_weather_capture')


def setup(tmp_path,monkeypatch):
    original=sources();paths={kind:tmp_path/(kind+'-policy.json') for kind in original}
    for kind,path in paths.items():path.write_text(original[kind]['policy_raw']);path.chmod(0o600)
    monkeypatch.setattr(api(),'FIXED_POLICY_PATHS',paths)
    monkeypatch.setattr(api(),'_runtime_manifest',lambda:{'fixture':'a'*64})
    calls=[]
    def getter(*,kind,url,remaining):
        assert url==original[kind]['source_endpoint'] and 0<remaining()<=15
        calls.append(kind);return original[kind]['raw']
    return original,paths,calls,getter


def collect(getter,**changes):return api().collect_measured_weather(source_getter=getter,clock=lambda:AT,monotonic=lambda:0.,**changes)


def test_exact_receiver_policy_and_stable_current_owner_are_retained(tmp_path,monkeypatch):
    original,paths,calls,getter=setup(tmp_path,monkeypatch);before={kind:(p.read_bytes(),p.stat().st_mode) for kind,p in paths.items()}
    context=collect(getter);body=context.to_dict()
    assert calls==['radiation','rain','radiation','rain']
    for kind,row in body['sources'].items():
        assert row['raw']==original[kind]['raw'] and row['policy_raw']==original[kind]['policy_raw']
        assert row['expected_epoch']==original[kind]['expected_epoch']
        assert row['available_at']==AT.isoformat() and row['policy_available_at']==AT.isoformat()
        assert (paths[kind].read_bytes(),paths[kind].stat().st_mode)==before[kind]
    assert body['as_of']==body['created_at']==AT.isoformat()


@pytest.mark.parametrize('damage',['missing_radiation','malformed_radiation','missing_rain','missing_policy'])
def test_independent_source_unavailability_preserves_valid_companion(damage,tmp_path,monkeypatch):
    from household.measured_weather import project_measured_weather
    original,paths,_,getter=setup(tmp_path,monkeypatch)
    if damage=='missing_policy':paths['radiation'].unlink()
    def read(**request):
        raw=getter(**request)
        if damage=='missing_radiation' and request['kind']=='radiation' or damage=='missing_rain' and request['kind']=='rain':return None
        if damage=='malformed_radiation' and request['kind']=='radiation':return 'invalid JSON'
        return raw
    rows=project_measured_weather(collect(read))['observations']
    broken='rain_counter_in' if damage=='missing_rain' else 'light_lux'
    good='light_lux' if damage=='missing_rain' else 'rain_counter_in'
    assert rows[broken]['value'] is None and rows[good]['value'] is not None


@pytest.mark.parametrize('damage',['epoch','sequence','faults','rain_packets'])
def test_owner_restart_or_counter_regression_cannot_be_sealed(damage,tmp_path,monkeypatch):
    original,_,_,getter=setup(tmp_path,monkeypatch);counts={kind:0 for kind in original}
    def read(**request):
        kind=request['kind'];counts[kind]+=1;body=json.loads(getter(**request))
        if kind=='radiation':
            if damage=='faults':
                body.update(sequence=3 if counts[kind]==1 else 4,faultCount=2 if counts[kind]==1 else 1)
                body['record']['sequence']=body['sequence']
            if counts[kind]==2:
                if damage=='epoch':body['streamEpoch']='00000000-0000-0000-0000-000000000007';body['record']['streamEpoch']=body['streamEpoch']
                elif damage=='sequence':body.update(sequence=0,faultCount=0,record=None)
        elif damage=='rain_packets' and counts[kind]==2:body.update(packetCount=0,record=None)
        return json.dumps(body)
    with pytest.raises(ValueError):collect(read)


@pytest.mark.parametrize('damage',['symlink','oversize','encoding','directory','group_write'])
def test_unsafe_policy_transport_refuses_capture(damage,tmp_path,monkeypatch):
    _,paths,_,getter=setup(tmp_path,monkeypatch);path=paths['radiation']
    if damage=='symlink':path.unlink();path.symlink_to(paths['rain'])
    elif damage=='oversize':path.write_text('x'*4097)
    elif damage=='encoding':path.write_bytes(b'\xff')
    elif damage=='directory':path.unlink();path.mkdir()
    else:path.chmod(0o660)
    with pytest.raises(ValueError):collect(getter)


def test_policy_replacement_during_owner_reads_refuses_capture(tmp_path,monkeypatch):
    _,paths,_,getter=setup(tmp_path,monkeypatch);calls=0
    def read(**request):
        nonlocal calls
        calls+=1
        if calls==1:paths['radiation'].write_text('changed')
        return getter(**request)
    with pytest.raises(ValueError):collect(read)


def test_source_runtime_change_is_inside_same_acquisition(tmp_path,monkeypatch):
    _,_,_,getter=setup(tmp_path,monkeypatch);calls=0
    def runtime():
        nonlocal calls
        calls+=1
        return {'fixture':str(calls)*64}
    monkeypatch.setattr(api(),'_runtime_manifest',runtime)
    with pytest.raises(ValueError):collect(getter)


def test_external_budget_cannot_renew_local_deadline(tmp_path,monkeypatch):
    _,_,_,getter=setup(tmp_path,monkeypatch);ticks=iter([0.,16.])
    with pytest.raises(ValueError):api().collect_measured_weather(source_getter=getter,clock=lambda:AT,monotonic=lambda:next(ticks),remaining=lambda:15.)


def test_final_runtime_verification_cannot_outlive_outer_deadline(tmp_path,monkeypatch):
    _,_,_,getter=setup(tmp_path,monkeypatch);elapsed=[0.];calls=0
    def runtime():
        nonlocal calls
        calls+=1
        if calls==2:elapsed[0]=16.
        return {'fixture':'a'*64}
    monkeypatch.setattr(api(),'_runtime_manifest',runtime)
    with pytest.raises(ValueError):api().collect_measured_weather(source_getter=getter,clock=lambda:AT,monotonic=lambda:elapsed[0])


def test_receiver_response_cannot_exceed_original_byte_budget(tmp_path,monkeypatch):
    _,_,_,getter=setup(tmp_path,monkeypatch)
    def read(**request):return 'x'*8193 if request['kind']=='radiation' else getter(**request)
    with pytest.raises(ValueError):collect(read)


def test_http_transport_refuses_arbitrary_destination_before_io():
    with pytest.raises(ValueError):api()._http_get(kind='radiation',url='http://example.invalid/data',remaining=lambda:15.)


def test_http_transport_disables_proxies_and_bounds_original_body(monkeypatch):
    import urllib.request
    url='http://127.0.0.1:5000/radiation_evidence';observed=[]
    class Response:
        status=200
        def geturl(self):return url
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,maximum):observed.append(maximum);return b'x'*8193
    class Opener:
        def open(self,request,timeout):
            assert request.get_method()=='GET' and request.full_url==url and 0<timeout<=2
            return Response()
    def opener(*handlers):
        assert any(isinstance(h,urllib.request.ProxyHandler) and h.proxies=={} for h in handlers)
        return Opener()
    monkeypatch.setattr(urllib.request,'build_opener',opener)
    with pytest.raises(ValueError):api()._http_get(kind='radiation',url=url,remaining=lambda:15.)
    assert observed==[8193]


def test_measured_only_cli_never_opens_a_database(tmp_path,monkeypatch,capsys):
    _,_,_,getter=setup(tmp_path,monkeypatch)
    import household_capture
    monkeypatch.setattr(api(),'_http_get',getter)
    def forbidden(*a,**k):pytest.fail('database access in measured-only capture')
    monkeypatch.setattr(household_capture,'_connection',forbidden)
    assert household_capture.main(['--measured-weather-only'])==0
    assert json.loads(capsys.readouterr().out)['schema']=='earthship-household-measured-weather/v1'


@pytest.mark.parametrize('arguments',[['--measured-weather-only','--config','unused.json'],['--measured-weather-only','--configuration-only']])
def test_measured_only_mode_cannot_mix_capture_contracts(arguments):
    import household_capture
    with pytest.raises(SystemExit):household_capture.main(arguments)


@pytest.mark.parametrize('status',[500,502,504])
def test_http_endpoint_failure_preserves_independent_rain(status,tmp_path,monkeypatch):
    import urllib.request,urllib.error
    from io import BytesIO
    from household.measured_weather import project_measured_weather
    original,_,_,_=setup(tmp_path,monkeypatch)
    class Opener:
        def open(self,request,timeout):
            if request.full_url==original['radiation']['source_endpoint']:
                raise urllib.error.HTTPError(request.full_url,status,'unavailable',{},None)
            response=BytesIO(original['rain']['raw'].encode())
            response.status=200;response.geturl=lambda:request.full_url
            return response
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
    rows=project_measured_weather(collect(api()._http_get))['observations']
    assert rows['light_lux']['value'] is None and rows['rain_counter_in']['value']==12.3


@pytest.mark.parametrize('kind',['radiation','rain'])
def test_unchanged_source_counter_cannot_change_record(kind,tmp_path,monkeypatch):
    _,_,_,getter=setup(tmp_path,monkeypatch);seen=0
    def read(**request):
        nonlocal seen
        raw=getter(**request)
        if request['kind']==kind:
            seen+=1
            if seen==2:
                body=json.loads(raw)
                if kind=='radiation':body['record'].update(lightLux=25340,irradianceWm2=200)
                else:body['record']['totalRainIn']=12.4
                raw=json.dumps(body)
        return raw
    with pytest.raises(ValueError):collect(read)


def test_trickled_http_body_cannot_outlive_total_budget(monkeypatch):
    import socket,threading,time
    server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1)
    stop=threading.Event()
    def serve():
        with server:
            connection,_=server.accept()
            with connection:
                connection.recv(4096)
                connection.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 20\r\n\r\n')
                try:
                    for _ in range(20):
                        if stop.wait(.04):break
                        connection.sendall(b'x')
                except OSError:pass
    worker=threading.Thread(target=serve,daemon=True);worker.start()
    url='http://127.0.0.1:'+str(server.getsockname()[1])+'/radiation_evidence'
    monkeypatch.setitem(api().SOURCES,'radiation',('Weather_Radiation_Evidence_JSON',url,8192))
    started=time.monotonic()
    def remaining():
        budget=.25-(time.monotonic()-started)
        if budget<=.001:raise ValueError('common acquisition elapsed')
        return budget
    try:
        with pytest.raises(ValueError):api()._http_get(kind='radiation',url=url,remaining=remaining)
        assert time.monotonic()-started<.65
    finally:stop.set();worker.join(timeout=1.)


@pytest.mark.parametrize('kind',['radiation','rain'])
def test_original_expiry_transition_preserves_valid_companion(kind,tmp_path,monkeypatch):
    from household.measured_weather import project_measured_weather
    _,_,_,getter=setup(tmp_path,monkeypatch);seen=0
    def read(**request):
        nonlocal seen
        raw=getter(**request)
        if request['kind']==kind:
            seen+=1
            if seen==2:
                body=json.loads(raw);record=body['record']
                record.update(status='invalid',reason='expired',receivedAt=None,validUntil=None)
                if kind=='radiation':
                    record.update(lightLux=None,irradianceWm2=None);body['faultCount']+=1
                else:record.update(totalRainIn=None,recordedAt=AT.isoformat())
                raw=json.dumps(body)
        return raw
    rows=project_measured_weather(collect(read))['observations']
    bad,good=('light_lux','rain_counter_in') if kind=='radiation' else ('rain_counter_in','light_lux')
    assert rows[bad]['value'] is None and rows[good]['value'] is not None


def test_http_timeout_restores_alarm_and_preserves_independent_rain(tmp_path,monkeypatch):
    import signal,urllib.request
    from io import BytesIO
    from household.measured_weather import project_measured_weather
    original,_,_,_=setup(tmp_path,monkeypatch);prior=signal.getsignal(signal.SIGALRM)
    class Opener:
        def open(self,request,timeout):
            if request.full_url==original['radiation']['source_endpoint']:raise TimeoutError('endpoint unavailable')
            response=BytesIO(original['rain']['raw'].encode());response.status=200
            response.geturl=lambda:request.full_url
            return response
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
    rows=project_measured_weather(collect(api()._http_get))['observations']
    assert rows['light_lux']['value'] is None and rows['rain_counter_in']['value']==12.3
    assert signal.getsignal(signal.SIGALRM)==prior and signal.getitimer(signal.ITIMER_REAL)==(0.,0.)
