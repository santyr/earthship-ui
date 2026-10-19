"""Google hourly solar energies retain their trailing-interval meaning."""
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
import pytest
from google_weather_fixtures import forecast
from thermal_model.installed_shade_origin import _forecast_forcing

@pytest.mark.parametrize('minute', [0, 15, 55])
@pytest.mark.parametrize('base,change', [(200., 40.), (400., -80.), (0., 100.)])
def test_hourly_mean_irradiance_is_held_over_its_original_interval(minute, base, change):
    issue = datetime(2026, 10, 19, 12, minute, tzinfo=timezone.utc)
    known = issue - timedelta(seconds=30)
    original = forecast(issue, horizon_hours=2, available_by=known,
        radiation_wm2=base, radiation_step_wm2=change,
        temperature_f=50., temperature_step_f=3.)
    rows = original['rows']
    times = [datetime.fromisoformat(row['at']) for row in rows]
    forcings = _forecast_forcing(original, issue, known,
        dict(indoor_shade_closed=0., outdoor_shade_present=0., vent_open=0.))
    for forcing in forcings:
        index = bisect_left(times, forcing.at)
        assert forcing.radiation_wm2 == pytest.approx(rows[index]['radiationWm2'])
        fraction = (forcing.at - times[index-1]).total_seconds() / 3600
        expected = rows[index-1]['tempF'] + fraction * (rows[index]['tempF'] - rows[index-1]['tempF'])
        assert forcing.outdoor_f == pytest.approx(expected)
    actual = sum(f.radiation_wm2 / 12 for f in forcings)
    expected = sum(rows[bisect_left(times, issue + timedelta(minutes=5*i))]['radiationWm2'] / 12 for i in range(1,25))
    assert actual == pytest.approx(expected)
