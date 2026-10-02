from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from test_weather_rain_history import Connection
from test_weather_radiation_reader import AT, POLICY, raw
from weather_radiation_history import (ITEM, RadiationHistoryUnavailable,
    fetch_radiation_at, fetch_radiation_day, fetch_radiation_window)


def read(connection):
    return fetch_radiation_at(lambda: connection, target=AT + timedelta(seconds=60),
        assessed_at=AT + timedelta(minutes=5), cutover=AT - timedelta(hours=1), policy=POLICY)


def fixture(**kwargs):
    return Connection(carry=(AT - timedelta(seconds=90), raw(-90)),
        rows=[(AT, raw(sequence=2))], matches=[(664,)], **kwargs)


def test_unique_item_original_carry_readonly_transaction_and_no_writes():
    c = fixture()
    assert read(c)['irradianceWm2'] == 100
    assert c.closed and c.session == dict(readonly=True, autocommit=False, isolation_level='REPEATABLE READ')
    assert ('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2', (ITEM,)) in c.queries
    selects = [(sql, args) for sql, args in c.queries if 'SELECT time' in sql]
    assert len(selects) == 2
    assert all('public.item0664' in sql and 'octet_length(value::text) <= 8192' in sql for sql, _ in selects)
    assert 'LIMIT 10001' in selects[-1][0]
    assert not any(word in sql for sql, _ in c.queries for word in ('INSERT', 'UPDATE', 'DELETE', 'COMMIT'))


@pytest.mark.parametrize('mapping', [[], [(664,), (665,)], [('664',)], [(True,)], [(-1,)]])
def test_ambiguous_or_malformed_mapping_refuses_without_source_read(mapping):
    c = fixture(); c.matches = mapping
    with pytest.raises(RadiationHistoryUnavailable):
        read(c)
    assert c.closed and not any('SELECT time' in sql for sql, _ in c.queries)


@pytest.mark.parametrize('settings', [dict(readonly=False), dict(repeatable=False),
    dict(status=2), dict(fail_source=True)])
def test_transaction_and_permission_failures_are_sanitized(settings):
    c = fixture(**settings)
    with pytest.raises(RadiationHistoryUnavailable, match='^radiation history unavailable$'):
        read(c)
    assert c.closed


def test_null_and_oversize_rows_remain_barriers():
    for value in (None, 'x' * 8193):
        c = fixture(); c.rows.append((AT + timedelta(seconds=30), value))
        assert read(c) is None and c.closed


@pytest.mark.parametrize('day,hours', [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_complete_local_dst_day_uses_elapsed_hours_and_closing_receipt(day, hours):
    zone = ZoneInfo('America/Denver')
    start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    rows = [(start + timedelta(seconds=offset), raw(
        int((start + timedelta(seconds=offset) - AT).total_seconds()), sequence=seq))
        for seq, offset in enumerate(range(-180, hours * 3600 + 1, 60), 1)]
    c = fixture(); c.carry = rows[0]; c.rows = rows[1:]
    result = fetch_radiation_day(lambda: c, local_date=day, as_of=end + timedelta(seconds=120),
        cutover=start - timedelta(days=1), policy=POLICY)
    assert result['status'] == 'ok' and result['total_seconds'] == hours * 3600
    assert result['irradiance_wh_m2'] == pytest.approx(100 * hours)
    assert result['local_date'] == day.isoformat() and c.closed


def test_pre_cutover_and_unelapsed_queries_refuse_before_connecting():
    calls = []
    factory = lambda: calls.append(True)
    for cutover, assessed in ((AT + timedelta(seconds=1), AT + timedelta(hours=1)),
                              (AT - timedelta(hours=1), AT)):
        with pytest.raises(RadiationHistoryUnavailable):
            fetch_radiation_window(factory, start=AT, end=AT + timedelta(seconds=120),
                assessed_at=assessed, cutover=cutover, policy=POLICY)
    assert calls == []


def test_row_budget_and_out_of_query_rows_refuse():
    c = fixture(); c.rows = c.rows * 10001
    with pytest.raises(RadiationHistoryUnavailable):
        read(c)
    c = fixture(); c.rows.append((AT + timedelta(minutes=1, seconds=1), raw(61, sequence=3)))
    with pytest.raises(RadiationHistoryUnavailable):
        read(c)
