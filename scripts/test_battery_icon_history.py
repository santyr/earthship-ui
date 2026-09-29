from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from battery_icon_history import baseline, verify_prefix  # noqa: E402


class Cursor:
    def __init__(self, db):
        self.db = db
        self.result = []
        self.index = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        statement = str(query)
        rows = sorted(self.db.rows)
        if 'SELECT itemid' in statement:
            self.result = [(self.db.item_id,)]
        elif 'statement_timeout' in statement:
            self.result = []
        elif 'ORDER BY time DESC' in statement:
            self.result = [max(rows)] if rows else []
        elif 'count(*)' in statement:
            self.result = [(sum(stamp > params[0] for stamp, _ in rows),)]
        else:
            self.result = [(stamp, value) for stamp, value in rows
                           if not params or stamp <= params[0]]
        self.index = 0

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchmany(self, size):
        batch = self.result[self.index:self.index + size]
        self.index += size
        return batch


class Database:
    item_id = 31

    def __init__(self):
        start = datetime(2026, 9, 29, tzinfo=timezone.utc)
        self.rows = [(start, 'iconify:mdi:battery-80'),
                     (start + timedelta(hours=1), 'iconify:mdi:battery-70')]

    def cursor(self):
        return Cursor(self)


def test_accepts_only_later_append_and_preserves_existing_prefix():
    db = Database()
    before = baseline(db)
    assert verify_prefix(db, before)['added'] == 0
    db.rows.append((before.last_time + timedelta(hours=1), 'iconify:mdi:battery-60'))
    result = verify_prefix(db, before)
    assert result['added'] == 1
    assert result['last_state'] == 'iconify:mdi:battery-60'


@pytest.mark.parametrize('change', ['rewrite', 'delete', 'backfill', 'same_timestamp'])
def test_rejects_history_prefix_drift(change):
    db = Database()
    before = baseline(db)
    if change == 'rewrite':
        db.rows[0] = (db.rows[0][0], 'iconify:mdi:battery-90')
    elif change == 'delete':
        db.rows.pop(0)
    elif change == 'backfill':
        db.rows.append((db.rows[0][0] + timedelta(minutes=1), 'iconify:mdi:battery-90'))
    else:
        db.rows.append((before.last_time, 'iconify:mdi:battery-60'))
    with pytest.raises(RuntimeError, match='prefix changed'):
        verify_prefix(db, before)


def test_rejects_jdbc_identity_change():
    db = Database()
    before = baseline(db)
    db.item_id = 32
    with pytest.raises(RuntimeError, match='identity missing or changed'):
        verify_prefix(db, before)
