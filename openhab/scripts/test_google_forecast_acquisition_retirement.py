"""The native collector has no legacy weather SQL or implicit reader selection."""
from datetime import timedelta
import pytest
from weather_learning.native_forecast import make_native_forecast
from weather_learning.tests.learning_fixtures import T,SITE,full_snapshot
from thermal_model import installed_shade_live_inputs as live

ISSUE=T+timedelta(hours=8,minutes=15)
KNOWN=ISSUE-timedelta(seconds=30)


def test_missing_weather_reader_refuses_before_private_source_reads(monkeypatch):
    monkeypatch.setattr(live,'_owned_bytes',lambda *a,**kw:pytest.fail('private source read before weather selection'))
    with pytest.raises(ValueError,match='explicit Google forecast reader'):
        live.LiveBackend({key:'/unused/'+key for key in live.SOURCE_PATHS},shared_lock_guard=lambda:None)


def test_obsolete_forecast_secret_is_refused_even_with_explicit_reader(monkeypatch):
    monkeypatch.setattr(live,'_owned_bytes',lambda *a,**kw:pytest.fail('obsolete forecast credential was read'))
    with pytest.raises(ValueError,match='forecast database'):
        live.LiveBackend({**{key:'/unused/'+key for key in live.SOURCE_PATHS},'forecast_dsn_file':'/unused/retired-weather'},shared_lock_guard=lambda:None,forecast_reader=lambda **kw:None)


def test_legacy_sql_acquisition_apis_are_removed():
    from thermal_model import forecast_history
    for name in ('fetch_origin_forecast','fetch_origin_forecast_with_receipts','fetch_pending_origin_forecast_with_receipts','_fetch_origin_forecast'):
        assert not hasattr(forecast_history,name),name


@pytest.mark.parametrize('damage',['legacy','origin','horizon','availability'])
def test_only_exact_google_request_can_reach_local_observation_collection(monkeypatch,damage):
    kwargs=dict(origin=ISSUE,available_by=KNOWN,horizon_hours=24,site=SITE)
    if damage=='origin':kwargs['origin']+=timedelta(minutes=5)
    elif damage=='horizon':kwargs['horizon_hours']=23
    elif damage=='availability':kwargs['available_by']-=timedelta(seconds=1)
    packet=make_native_forecast(full_snapshot(),**kwargs)
    if damage=='legacy':packet={'source':'open_meteo_openhab'}
    from test_thermal_sensor_epoch_history import EPOCHS
    backend=object.__new__(live.LiveBackend);backend.forecast_reader=lambda **kw:packet;backend.epochs=EPOCHS
    backend._connect=lambda *a,**kw:pytest.fail('local database read for invalid weather')
    backend._temperature_grid=lambda *a,**kw:pytest.fail('local observation read for invalid weather')
    monkeypatch.setattr(live,'_clock',lambda:KNOWN)
    with pytest.raises(ValueError):backend.collect(issue=ISSUE,known_at=KNOWN)
