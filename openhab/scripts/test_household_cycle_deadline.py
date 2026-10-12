"""Real process alarms protect the original publisher, not just elapsed checks."""
import importlib,signal,time
from datetime import datetime,timezone
import pytest


def api():return importlib.import_module('household_cycle_deadline')


def test_total_deadline_escapes_exception_catching_operations_and_restores_alarm():
    module=api();prior=signal.getsignal(signal.SIGALRM);completed=[]
    with pytest.raises(module.ObservationDeadline):
        with module.observation_deadline(.06):
            try:time.sleep(.15)
            except Exception:completed.append('swallowed')
    assert completed==[]
    assert signal.getsignal(signal.SIGALRM)==prior
    assert signal.getitimer(signal.ITIMER_REAL)==(0.,0.)


def test_foreign_timer_is_preserved():
    module=api();prior=signal.getsignal(signal.SIGALRM)
    handler=lambda *args:None
    signal.signal(signal.SIGALRM,handler);signal.setitimer(signal.ITIMER_REAL,1.)
    try:
        with pytest.raises(ValueError):
            with module.observation_deadline(.1):pytest.fail('foreign alarm replaced')
        assert signal.getsignal(signal.SIGALRM) is handler
        assert signal.getitimer(signal.ITIMER_REAL)[0]>.5
    finally:signal.setitimer(signal.ITIMER_REAL,0.);signal.signal(signal.SIGALRM,prior)

@pytest.mark.parametrize('transport',['measured','owner'])
def test_transport_timeout_cannot_renew_or_disable_total_deadline(transport,monkeypatch):
    module=api()
    from household_cycle_sources import CycleSourceCollector
    from household import measured_weather_capture
    started=time.monotonic();deadline=started+.06
    def remaining():
        value=deadline-time.monotonic()
        if value<=0:raise ValueError('total deadline elapsed')
        return value
    class Response:
        status=200
        def __init__(self,url):self.url=url
        def geturl(self):return self.url
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):time.sleep(.15);return b'{"state":"unused"}'
    class Opener:
        def open(self,request,**kw):return Response(request.full_url)
    import urllib.request
    monkeypatch.setattr(urllib.request,'build_opener',lambda *args:Opener())
    with pytest.raises(module.ObservationDeadline):
        with module.observation_deadline(.06):
            if transport=='owner':
                from household_cycle_sources import CycleSourceCollector
                collector=CycleSourceCollector.__new__(CycleSourceCollector)
                collector.base='http://127.0.0.1:8080/rest';collector.token='fixture-marker'
                collector._owner_http('Inverter_AC_Evidence_JSON',remaining=remaining)
            else:
                from household import measured_weather_capture
                kind=next(iter(measured_weather_capture.SOURCES))
                with module.borrow_observation_timer():
                    measured_weather_capture._http_get(kind=kind,url=measured_weather_capture.SOURCES[kind][1],remaining=remaining)
    assert time.monotonic()-started<.14
    assert signal.getitimer(signal.ITIMER_REAL)==(0.,0.)
