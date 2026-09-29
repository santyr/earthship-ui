"""The tuning outcome reader must preserve the existing strict SoC boundary."""

from datetime import date, datetime, timedelta, timezone

import pytest

from advisory_windows import trough_window
from pre_dusk_tuning_outcome import OutcomeHistoryUnavailable, read_completed_outcome


DAY = date(2026, 9, 28)
WINDOW = trough_window(DAY, 'America/Denver')
EPOCH = datetime(2026, 7, 19, 6, tzinfo=timezone.utc)
AFTER = WINDOW.end.replace(hour=18)


class Cursor:
    def __init__(self, mapping=((613,),)):
        self.mapping = mapping
        self.last = ''
        self.calls = []
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def execute(self, sql, params=None):
        self.last = sql
        self.calls.append((sql, params))
    def fetchone(self):
        if self.last == 'SHOW transaction_read_only':
            return ('on',)
        if self.last == 'SHOW transaction_isolation':
            return ('repeatable read',)
        raise AssertionError('unexpected fetchone')
    def fetchall(self):
        return self.mapping


class Connection:
    def __init__(self, mapping=((613,),)):
        self.cursor_instance = Cursor(mapping)
        self.closed = False
        self.session = None
    def get_transaction_status(self):
        return 0
    def set_session(self, **kwargs):
        self.session = kwargs
    def cursor(self):
        return self.cursor_instance
    def close(self):
        self.closed = True


def test_reads_only_atomic_soc_in_readonly_snapshot_and_closes():
    connection = Connection()
    called = []
    def read(conn, table, start, end, *, row_limit):
        called.append((conn, table, start, end, row_limit))
        return []
    def assess(**kwargs):
        assert kwargs['prediction_day'] == DAY
        assert kwargs['epoch_start'] == EPOCH
        return {'status':'measured', 'prediction_day':DAY.isoformat(),
                'source':'BMS_SOC_Evidence_JSON',
                'assessment_version':'atomic-soc-trough-v1',
                'min_soc_pct':84, 'coverage':0.99, 'evidence_digest':'a'*64}
    result = read_completed_outcome(lambda: connection, day=DAY, as_of=AFTER,
                                    epoch_start=EPOCH, reader=read, assessor=assess)
    assert result['status'] == 'measured'
    assert connection.closed
    assert connection.session == {'readonly': True, 'autocommit': False,
                                  'isolation_level': 'REPEATABLE READ'}
    assert called == [(connection, 'item0613', WINDOW.start-timedelta(seconds=120),
                       WINDOW.end, 10001)]
    assert any(sql.startswith('SELECT itemid FROM public.items') and params ==
               ('BMS_SOC_Evidence_JSON',) for sql, params in connection.cursor_instance.calls)


def test_refuses_incomplete_target_before_connecting():
    opened = []
    with pytest.raises(OutcomeHistoryUnavailable):
        read_completed_outcome(lambda: opened.append(True), day=DAY,
                               as_of=WINDOW.end.replace(hour=16), epoch_start=EPOCH)
    assert not opened


def test_refuses_ambiguous_mapping_and_closes():
    connection = Connection(mapping=((613,), (999,)))
    with pytest.raises(OutcomeHistoryUnavailable):
        read_completed_outcome(lambda: connection, day=DAY, as_of=AFTER,
                               epoch_start=EPOCH)
    assert connection.closed


def test_refuses_unqualified_assessment():
    connection = Connection()
    with pytest.raises(OutcomeHistoryUnavailable):
        read_completed_outcome(lambda: connection, day=DAY, as_of=AFTER,
                               epoch_start=EPOCH, reader=lambda *a, **k: [],
                               assessor=lambda **k: {'status':'insufficient_data'})
    assert connection.closed
