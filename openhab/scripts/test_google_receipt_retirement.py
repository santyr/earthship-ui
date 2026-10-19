"""Shared thermal replay refuses retired weather and binds Google source code."""
from datetime import datetime,timedelta
import json
from pathlib import Path
import pytest
from weather_learning.tests.learning_fixtures import T,SITE,full_snapshot
from weather_learning.native_forecast import make_native_forecast


def retired():
    value=json.loads((Path(__file__).resolve().parents[2]/'tests/fixtures/retired-weather-receipts-v2.json').read_bytes())
    for key in ('origin','issued_at','captured_at'):value[key]=datetime.fromisoformat(value[key])
    for row in value['rows']:row['at']=datetime.fromisoformat(row['at'])
    for row in value['metric_receipts']:
        for index in range(3):row[index]=datetime.fromisoformat(row[index])
    return value


def test_shared_receipt_verifier_refuses_well_formed_retired_receipts():
    from thermal_model.forecast_history import verify_origin_forecast_receipts
    with pytest.raises(ValueError):verify_origin_forecast_receipts(retired())


def test_installed_shade_forcing_cannot_replay_retired_provider():
    from thermal_model.installed_shade_origin import _forecast_forcing
    value=retired();origin=value['origin']
    with pytest.raises(ValueError):_forecast_forcing(value,origin,origin,dict(indoor_shade_closed=0.,outdoor_shade_present=1.,vent_open=0.))


def test_operational_origin_refuses_retired_weather_before_temperature_reads():
    from thermal_model.operational_origin import assemble_origin
    value=retired()
    with pytest.raises(ValueError):assemble_origin(value['origin'],horizon_hours=1,forecast_reader=lambda **kw:value,
        temperature_reader=lambda **kw:pytest.fail('retired forecast reached local measurements'))


def test_airflow_cannot_replay_retired_provider():
    from thermal_model.airflow_forecast import _hourly
    value=retired();value.pop('schema');value.pop('metric_receipts')
    with pytest.raises(ValueError):_hourly(value,value['origin'],1)


def test_legacy_metric_selectors_are_removed():
    from thermal_model import forecast_history
    for name in ('select_origin_forecast','select_origin_forecast_with_receipts','_select_origin_forecast'):
        assert not hasattr(forecast_history,name),name


def test_airflow_accepts_original_google_with_unknown_weather_code():
    from thermal_model.airflow_forecast import _hourly
    origin=T+timedelta(hours=8,minutes=15)
    value=make_native_forecast(full_snapshot(),origin=origin,available_by=origin-timedelta(seconds=30),horizon_hours=6,site=SITE)
    rows,targets=_hourly(value,origin,6)
    assert len(rows)==len(targets)==8
    assert rows[0]['weatherCode'] is None and rows[0]['tempF']==50


def test_operational_origin_accepts_original_google_without_relabelling():
    from thermal_model.operational_origin import assemble_origin
    from test_thermal_operational_origin import ORIGIN,temperatures
    source=full_snapshot(ORIGIN.replace(minute=0)-timedelta(hours=8))
    value=make_native_forecast(source,origin=ORIGIN,available_by=ORIGIN-timedelta(seconds=30),horizon_hours=24,site=SITE)
    result=assemble_origin(ORIGIN,horizon_hours=24,forecast_reader=lambda **kw:value,temperature_reader=temperatures)
    assert result['status']=='available' and result['forecast']==value


def test_replay_runtime_closures_include_google_original_validation_dependencies():
    from thermal_model.installed_shade_origin import RUNTIME_PATHS
    from thermal_model.airflow_artifact import runtime_manifest
    names={'thermal_model/forecast_history.py','weather_learning/native_forecast.py','weather_learning/weathernext_ee.py',
        'weather_learning/normalize.py','weather_learning/contracts.py','weather_learning/features.py','weather_learning/evidence.py',
        'weather_learning/config.py','weather_learning/transport.py'}
    assert names<=set(RUNTIME_PATHS)
    assert names<={row['path'] for row in runtime_manifest()['files']}
