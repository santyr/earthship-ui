from datetime import timedelta

import pytest
from test_weather_temperature_reader import AT, POLICY, raw
from weather_temperature_history import EVIDENCE_ITEM, TemperatureHistoryUnavailable, fetch_temperature_target


class Connection:
    def __init__(self, *, mapping=None, carry=None, rows=None, read_only='on', isolation='repeatable read', fail=None):
        self.mapping = [(613,)] if mapping is None else mapping
        self.carry = carry; self.rows = [(AT, raw())] if rows is None else rows
        self.read_only = read_only; self.isolation = isolation; self.fail = fail
        self.calls = []; self.closed = False; self.session = None
    def get_transaction_status(self): return 0
    def set_session(self, **kwargs): self.session = kwargs
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query, params=None):
        self.calls.append((query, params))
        if self.fail and self.fail in query: raise RuntimeError('SECRET database details')
    def fetchone(self):
        query = self.calls[-1][0]
        if query == 'SHOW transaction_read_only': return (self.read_only,)
        if query == 'SHOW transaction_isolation': return (self.isolation,)
        return self.carry
    def fetchall(self): return self.mapping if 'public.items' in self.calls[-1][0] else self.rows
    def close(self): self.closed = True


def fetch(connection):
    return fetch_temperature_target(lambda: connection, target=AT + timedelta(seconds=60),
                                    assessed_at=AT + timedelta(minutes=5), stream='indoor', policy=POLICY)


def test_bounded_read_only_exact_mapping_and_original_timestamps():
    c = Connection(carry=(AT - timedelta(seconds=90), raw(-90)))
    result = fetch(c)
    assert result['temperatureF'] == 70 and result['storedAt'] == AT
    assert c.session == {'readonly': True, 'autocommit': False, 'isolation_level': 'REPEATABLE READ'}
    assert c.closed
    assert c.calls[5][1] == (EVIDENCE_ITEM,)
    assert c.calls[-2][1] == (AT - timedelta(seconds=60),)
    assert c.calls[-1][1] == (AT - timedelta(seconds=60), AT + timedelta(seconds=60))
    assert 'public.item0613' in c.calls[-1][0]
    assert 'LIMIT 10001' in c.calls[-1][0]
    assert 'octet_length' in c.calls[-1][0]
    assert all(q.startswith(('SET LOCAL', 'SHOW ', 'SELECT ')) for q, _ in c.calls)


@pytest.mark.parametrize('mapping', [[], [(613,), (614,)], [('613',)], [(True,)], [(-1,)], [(2**31,)]])
def test_missing_or_ambiguous_mapping_has_no_other_item_fallback(mapping):
    c = Connection(mapping=mapping)
    with pytest.raises(TemperatureHistoryUnavailable): fetch(c)
    assert c.closed
    assert not any('FROM public.item0' in query for query, _ in c.calls)


@pytest.mark.parametrize('kwargs', [{'read_only': 'off'}, {'isolation': 'read committed'}, {'fail': 'public.items'},
                                 {'fail': 'time >='}, {'rows': [(AT, raw())] * 10001}])
def test_failed_or_incomplete_query_never_returns_partial_measurement(kwargs):
    c = Connection(**kwargs)
    with pytest.raises(TemperatureHistoryUnavailable) as error: fetch(c)
    assert str(error.value) == 'temperature evidence history unavailable'
    assert c.closed


def test_unknown_or_oversized_latest_row_remains_barrier():
    c = Connection(rows=[(AT, raw()), (AT + timedelta(seconds=30), None)])
    assert fetch(c) is None
    assert c.closed


def test_out_of_window_or_relabelled_carry_is_rejected():
    for c in [Connection(carry=(AT, raw())), Connection(rows=[(AT + timedelta(seconds=61), raw(61))])]:
        with pytest.raises(TemperatureHistoryUnavailable): fetch(c)


def test_future_target_fails_before_connecting():
    def forbidden(): pytest.fail('future target opened connection')
    with pytest.raises(TemperatureHistoryUnavailable):
        fetch_temperature_target(forbidden, target=AT + timedelta(seconds=1), assessed_at=AT,
                                 stream='indoor', policy=POLICY)
