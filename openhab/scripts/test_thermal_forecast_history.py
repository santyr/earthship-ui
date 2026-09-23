from datetime import datetime, timedelta, timezone

import pytest

from thermal_model.forecast_history import fetch_origin_forecast, select_origin_forecast

UTC = timezone.utc
ORIGIN = datetime(2026, 9, 23, 13, 30, tzinfo=UTC)
FIRST = ORIGIN.replace(minute=0)
METRICS = ('temperature_f', 'radiation_wm2', 'wind_mph', 'weather_code')


def issue(issued_at, captured_at, *, missing=None, late=None):
    records = []
    for hour in range(3):
        for index, metric in enumerate(METRICS):
            if (hour, metric) == missing:
                continue
            receipt = captured_at + (timedelta(hours=1) if (hour, metric) == late else timedelta())
            records.append((issued_at, receipt, FIRST + timedelta(hours=hour),
                            metric, float(hour * 10 + index)))
    return records


def test_latest_complete_captured_issue_wins_without_mixing_or_future_capture():
    older = issue(ORIGIN - timedelta(hours=2), ORIGIN - timedelta(hours=1))
    newer = issue(ORIGIN - timedelta(minutes=30), ORIGIN - timedelta(minutes=5),
                  late=(2, 'wind_mph'))
    chosen = select_origin_forecast(newer + older, origin=ORIGIN, horizon_hours=1)
    assert chosen['issued_at'] == ORIGIN - timedelta(hours=2)
    assert chosen['captured_at'] == ORIGIN - timedelta(hours=1)
    assert len(chosen['rows']) == 3
    assert chosen['rows'][2]['windMph'] == 22.0
    assert select_origin_forecast(list(reversed(newer + older)),
                                  origin=ORIGIN, horizon_hours=1)['rows_sha256'] == chosen['rows_sha256']


def test_no_complete_asof_issue_is_explicitly_unavailable():
    rows = issue(ORIGIN - timedelta(hours=1), ORIGIN - timedelta(minutes=20),
                 missing=(1, 'radiation_wm2'))
    assert select_origin_forecast(rows, origin=ORIGIN, horizon_hours=1) is None
    assert select_origin_forecast(issue(ORIGIN - timedelta(hours=7), ORIGIN - timedelta(hours=7)),
                                  origin=ORIGIN, horizon_hours=1) is None


@pytest.mark.parametrize('origin,hours', [(ORIGIN.replace(tzinfo=None), 1), (ORIGIN, True),
                                         (ORIGIN, 0), (ORIGIN, 73)])
def test_invalid_origin_or_horizon_refused(origin, hours):
    with pytest.raises(ValueError):
        select_origin_forecast([], origin=origin, horizon_hours=hours)


class Cursor:
    def __init__(self, records):
        self.records = records
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, query, params=None): self.calls.append((query, params))
    def fetchone(self): return ('on',)
    def fetchall(self): return self.records


class Connection:
    def __init__(self, records):
        self.cur = Cursor(records)
        self.readonly = False
        self.closed = False
    def get_transaction_status(self): return 0
    def set_session(self, *, readonly, autocommit, isolation_level):
        self.readonly = readonly and not autocommit and isolation_level == 'REPEATABLE READ'
    def cursor(self): return self.cur
    def close(self): self.closed = True


def test_database_reader_enforces_capture_cutoff_and_closes_connection():
    connection = Connection(issue(ORIGIN - timedelta(hours=2), ORIGIN - timedelta(hours=1)))
    result = fetch_origin_forecast(lambda: connection, origin=ORIGIN, horizon_hours=1)
    assert result is not None and connection.readonly and connection.closed
    query, params = connection.cur.calls[-1]
    assert 'captured_at <= %s' in query
    assert params[3] == ORIGIN
    assert params[4] == FIRST and params[5] == FIRST + timedelta(hours=2)
