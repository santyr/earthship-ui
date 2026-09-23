from datetime import datetime, timedelta, timezone

import pytest

from thermal_model.operational_origin import assemble_origin

ORIGIN = datetime(2026, 9, 23, 14, 45, tzinfo=timezone.utc)
EPOCH = '864142d5-99ee-4b7a-b5fc-e6a96e7274d8'


def forecast(*, origin, horizon_hours):
    first = origin.replace(minute=0)
    rows = [{'at': first + timedelta(hours=hour), 'tempF': 59.0,
             'radiationWm2': 0.0, 'windMph': 2.0, 'weatherCode': 0}
            for hour in range(horizon_hours + 2)]
    return {'source': 'open_meteo_openhab', 'origin': origin, 'horizon_hours': horizon_hours,
            'issued_at': origin - timedelta(hours=1),
            'captured_at': origin - timedelta(minutes=20),
            'rows_sha256': 'a' * 64, 'rows': rows}


def temperatures(*, stream, targets, assessed_at):
    at = targets[0]
    assert at == assessed_at == ORIGIN
    return [(at, {'temperatureF': {'indoor': 70, 'north_wall': 68,
                                   'outdoor': 59}[stream],
                  'receivedAt': at - timedelta(seconds=40),
                  'storedAt': at - timedelta(seconds=30),
                  'validUntil': at + timedelta(seconds=80),
                  'streamEpoch': EPOCH, 'snapshotSha256': 'b' * 64})]


def test_complete_origin_preserves_capture_receipts_without_scoring_actions():
    result = assemble_origin(ORIGIN, horizon_hours=24,
                             forecast_reader=forecast, temperature_reader=temperatures)
    assert result['status'] == 'available'
    assert result['initial'] == {'air_f': 70, 'mass_f': 68, 'outdoor_f': 59}
    assert result['receipts']['air']['stored_at'] < ORIGIN
    assert result['forecast']['captured_at'] < ORIGIN
    assert result['action_knowledge'] == 'not_qualified'


def test_missing_receipt_cannot_borrow_an_older_or_other_sensor_value():
    def missing(**kwargs):
        return [(ORIGIN, None)] if kwargs['stream'] == 'north_wall' else temperatures(**kwargs)
    result = assemble_origin(ORIGIN, horizon_hours=24,
                             forecast_reader=forecast, temperature_reader=missing)
    assert result == {'status': 'unavailable', 'reason': 'mass_receipt_unavailable',
                      'origin': ORIGIN}


def test_late_forecast_and_post_origin_receipt_are_refused():
    def late_forecast(**kwargs):
        return {**forecast(**kwargs), 'captured_at': ORIGIN + timedelta(seconds=1)}
    with pytest.raises(ValueError, match='forecast is not available'):
        assemble_origin(ORIGIN, horizon_hours=24,
                        forecast_reader=late_forecast, temperature_reader=temperatures)
    def late_receipt(**kwargs):
        rows = temperatures(**kwargs)
        rows[0][1]['storedAt'] = ORIGIN + timedelta(seconds=1)
        return rows
    with pytest.raises(ValueError, match='unqualified temperature receipt'):
        assemble_origin(ORIGIN, horizon_hours=24,
                        forecast_reader=forecast, temperature_reader=late_receipt)


def test_origin_must_be_five_minute_aligned():
    with pytest.raises(ValueError, match='align'):
        assemble_origin(ORIGIN + timedelta(minutes=1), horizon_hours=24,
                        forecast_reader=forecast, temperature_reader=temperatures)


def test_partial_forecast_cannot_be_treated_as_an_operational_origin():
    def partial(**kwargs):
        value = forecast(**kwargs)
        value['rows'].pop()
        return value
    with pytest.raises(ValueError, match='hourly bracket'):
        assemble_origin(ORIGIN, horizon_hours=24,
                        forecast_reader=partial, temperature_reader=temperatures)
