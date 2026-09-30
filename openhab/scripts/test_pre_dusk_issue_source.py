"""The issue-time SoC source must be the original latest persisted receipt."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from pre_dusk_issue_source import IssueSourceUnavailable, read_issue_source, read_issue_input


ISSUE = datetime(2026, 9, 29, 23, 30, tzinfo=timezone.utc)
RECORDED = ISSUE - timedelta(seconds=20)
STORED = RECORDED + timedelta(seconds=5)
EPOCH = '123e4567-e89b-42d3-a456-426614174000'
stamp = lambda at: int(at.timestamp() * 1000)
RAW = json.dumps({'version': 1, 'streamEpoch': EPOCH,
    'recordedAt': stamp(RECORDED), 'status': 'valid', 'reason': 'ok',
    'observedAt': stamp(RECORDED), 'scaleObservedAt': stamp(RECORDED),
    'validUntil': stamp(RECORDED + timedelta(seconds=120)), 'soc': 99})
ISSUED = {'issuedAt': ISSUE.isoformat(), 'socRecordedAt': RECORDED.isoformat(),
          'socStreamEpoch': EPOCH, 'socEvidenceSha256': sha256(RAW.encode()).hexdigest(),
          'socAtIssuePct': 99}


class Cursor:
    def __init__(self, mapping=((613,),), rows=((STORED, RAW),), readonly=True):
        self.mapping, self.rows, self.readonly = mapping, rows, readonly
        self.sql = ''
        self.calls = []
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def execute(self, sql, params=None):
        self.sql = sql
        self.calls.append((sql, params))
    def fetchone(self):
        if self.sql == 'SHOW transaction_read_only':
            return ('on' if self.readonly else 'off',)
        if self.sql == 'SHOW transaction_isolation':
            return ('repeatable read',)
        raise AssertionError('unexpected fetchone')
    def fetchall(self):
        if self.sql.startswith('SELECT itemid'):
            return self.mapping
        if self.sql.startswith('SELECT time, value'):
            return self.rows
        raise AssertionError('unexpected fetchall')


class Connection:
    def __init__(self, **kwargs):
        self.cursor_instance = Cursor(**kwargs)
        self.session = None
        self.closed = False
    def get_transaction_status(self):
        return 0
    def set_session(self, **kwargs):
        self.session = kwargs
    def cursor(self):
        return self.cursor_instance
    def close(self):
        self.closed = True


def test_latest_original_receipt_is_checked_in_restricted_snapshot():
    connection = Connection(rows=((STORED, RAW), (STORED-timedelta(seconds=60), 'old')))
    result = read_issue_source(lambda: connection, ISSUED)
    assert result == {'source_item': 'BMS_SOC_Evidence_JSON',
        'source_persisted_at': STORED.isoformat(),
        'source_stream_epoch': EPOCH,
        'source_digest_sha256': ISSUED['socEvidenceSha256']}
    assert connection.closed
    assert connection.session == {'readonly': True, 'autocommit': False,
                                  'isolation_level': 'REPEATABLE READ'}
    calls = connection.cursor_instance.calls
    assert any(sql.startswith('SELECT itemid') and params == ('BMS_SOC_Evidence_JSON',)
               for sql, params in calls)
    assert any('FROM public.item0613' in sql and 'ORDER BY time DESC LIMIT 2' in sql
               and params == (ISSUE,) for sql, params in calls)


def test_internal_original_input_uses_same_qualified_snapshot_without_changing_public_result():
    connection = Connection()
    internal = read_issue_input(lambda: connection, ISSUED)
    assert internal['original_soc'] == RAW
    assert internal['metadata'] == read_issue_source(lambda: Connection(), ISSUED)
    assert connection.closed
    assert 'original_soc' not in internal['metadata']


@pytest.mark.parametrize('kwargs', [
    {'mapping': ((613,), (999,))},
    {'rows': ()},
    {'rows': ((STORED, RAW), (STORED, RAW))},
    {'rows': ((STORED, 'UNDEF'),)},
    {'rows': ((ISSUE + timedelta(seconds=1), RAW),)},
    {'readonly': False},
])
def test_missing_ambiguous_or_changed_source_refuses_and_closes(kwargs):
    connection = Connection(**kwargs)
    with pytest.raises(IssueSourceUnavailable):
        read_issue_source(lambda: connection, ISSUED)
    assert connection.closed
