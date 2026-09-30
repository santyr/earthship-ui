from datetime import date, datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location('solar_experiment', Path(__file__).with_name('experiment-forecast-solar-context.py'))
q = module_from_spec(spec); spec.loader.exec_module(q)
ORIGIN = datetime(2026, 9, 20, 14, 45, tzinfo=timezone.utc)


def test_elapsed_daily_bounds_and_spring_dst_overlap():
    times = q.origins(date(2026, 9, 1), date(2026, 9, 20), now=ORIGIN + timedelta(days=2))
    assert len(times) == 19 and times[0].hour == 14 and times[0].minute == 45
    for start, end in ((date(2026, 9, 1), date(2026, 11, 1)),
                       (date(2026, 3, 7), date(2026, 3, 10)),
                       (date(2026, 9, 20), date(2026, 9, 22))):
        with pytest.raises(ValueError): q.origins(start, end, now=ORIGIN)


def test_fall_dst_daily_origins_remain_local_and_nonoverlapping():
    times = q.origins(date(2026, 10, 31), date(2026, 11, 3), now=ORIGIN + timedelta(days=60))
    assert [(at.hour, at.minute) for at in times] == [(14, 45), (15, 45), (15, 45)]
    assert times[1] - times[0] == timedelta(hours=25)


def test_origin_context_does_not_use_future_row_or_previous_day_duration():
    history = {'Sun_Daylight_Duration': [(ORIGIN - timedelta(hours=8), 12.0),
                                         (ORIGIN + timedelta(hours=1), 11.0)],
               'Sun_SeasonName': [(ORIGIN - timedelta(days=80), 'SUMMER'),
                                  (ORIGIN + timedelta(days=2), 'AUTUMN')]}
    duration, season, digest = q.context_at(history, ORIGIN)
    assert duration == 12 and season == 'SUMMER' and len(digest) == 64
    history['Sun_Daylight_Duration'] = [(ORIGIN - timedelta(days=1), 12)]
    assert q.context_at(history, ORIGIN) is None


@pytest.mark.parametrize('damage', ['duplicate', 'wrong_item', 'bad_count', 'unit', 'nonfinite', 'future'])
def test_bad_solar_archive_refused(damage):
    millis = int((ORIGIN - timedelta(hours=1)).timestamp()*1000)
    def get(path):
        name = path.split('/items/')[1].split('?')[0]
        rows = [{'time': millis, 'state': '43200' if name == 'Sun_Daylight_Duration' else 'SUMMER'}]
        if name == 'Sun_Daylight_Duration':
            if damage == 'duplicate': rows *= 2
            elif damage == 'unit': rows[0]['state'] = '720 min'
            elif damage == 'nonfinite': rows[0]['state'] = 'nan'
            elif damage == 'future': rows[0]['time'] += 7200000
        return {'name': 'other' if damage == 'wrong_item' else name,
                'datapoints': 9 if damage == 'bad_count' else str(len(rows)), 'data': rows}
    with pytest.raises(ValueError): q.solar_history(get, [ORIGIN])


def test_missing_context_skips_readers_without_fabricating_pairs():
    def forbidden(**_): pytest.fail('reader should not run')
    rows, counts = q.assemble([ORIGIN], history={key: [] for key in q.SOLAR_ITEMS},
        forecast_reader=forbidden, temperature_reader=forbidden, now=ORIGIN + timedelta(days=2))
    assert rows == [] and counts == {'solar_context_unavailable': 1}


def test_complete_pair_interpolates_archived_forecast_not_observed_weather():
    target = ORIGIN + timedelta(hours=24)
    history = {'Sun_Daylight_Duration': [(ORIGIN - timedelta(hours=1), 12)],
               'Sun_SeasonName': [(ORIGIN - timedelta(days=80), 'SUMMER')]}
    forecast = {'origin': ORIGIN, 'horizon_hours': 24,
                'issued_at': ORIGIN - timedelta(hours=1),
                'captured_at': ORIGIN - timedelta(minutes=1),
                'rows_sha256': 'a'*64, 'rows': [
                    {'at': target.replace(minute=0), 'tempF': 60},
                    {'at': target.replace(minute=0) + timedelta(hours=1), 'tempF': 64}]}
    receipt = {'temperatureF': 70, 'receivedAt': target - timedelta(seconds=10),
               'storedAt': target - timedelta(seconds=5),
               'validUntil': target + timedelta(seconds=110),
               'streamEpoch': '12345678-1234-1234-1234-123456789abc',
               'snapshotSha256': 'b'*64}
    rows, counts = q.assemble([ORIGIN], history=history,
        forecast_reader=lambda **_: forecast, temperature_reader=lambda **_: receipt,
        now=target + timedelta(days=1))
    assert counts == {'paired': 1} and rows[0]['forecast_f'] == 63
    assert rows[0]['actual_f'] == 70
    forecast['captured_at'] = ORIGIN + timedelta(seconds=1)
    with pytest.raises(ValueError, match='future forecast'):
        q.assemble([ORIGIN], history=history,
            forecast_reader=lambda **_: forecast, temperature_reader=lambda **_: receipt,
            now=target + timedelta(days=1))
