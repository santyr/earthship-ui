"""Read-only, append-only JDBC evidence for a BatteryIcon ownership handoff."""
from dataclasses import dataclass
from hashlib import sha256

from psycopg2 import sql


ITEM = 'BatteryIcon'
ITEM_ID = 31


@dataclass(frozen=True)
class Snapshot:
    item_id: int
    count: int
    last_time: object
    last_state: str
    digest: str


def _identity(db):
    with db.cursor() as cursor:
        cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s', (ITEM,))
        rows = cursor.fetchall()
    if rows != [(ITEM_ID,)]:
        raise RuntimeError('BatteryIcon JDBC identity missing or changed')
    return ITEM_ID


def _scan(db, item_id, *, through=None):
    digest = sha256()
    count = 0
    last_time = last_state = None
    table = sql.Identifier('item' + str(item_id).zfill(4))
    query = sql.SQL('SELECT time,value FROM public.{}').format(table)
    params = ()
    if through is not None:
        query += sql.SQL(' WHERE time<=%s')
        params = (through,)
    query += sql.SQL(' ORDER BY time,value')
    with db.cursor() as cursor:
        cursor.execute("SET statement_timeout='20s'")
        cursor.execute(query, params)
        while True:
            batch = cursor.fetchmany(1000)
            if not batch:
                break
            for stamp, value in batch:
                count += 1
                last_time, last_state = stamp, str(value)
                digest.update((str(stamp) + '\t' + str(value) + '\n').encode())
    if count == 0:
        raise RuntimeError('BatteryIcon JDBC history empty')
    return Snapshot(item_id, count, last_time, last_state, digest.hexdigest())


def baseline(db):
    return _scan(db, _identity(db))


def verify_prefix(db, before):
    """Reject deletion/rewrite/backfill through cutoff; allow only later rows."""
    if not isinstance(before, Snapshot) or before.item_id != ITEM_ID:
        raise RuntimeError('untrusted BatteryIcon history baseline')
    if _identity(db) != before.item_id:
        raise RuntimeError('BatteryIcon JDBC identity changed')
    prefix = _scan(db, before.item_id, through=before.last_time)
    if prefix != before:
        raise RuntimeError('BatteryIcon JDBC history prefix changed')
    with db.cursor() as cursor:
        cursor.execute(sql.SQL('SELECT time,value FROM public.{} '
                               'ORDER BY time DESC,value DESC LIMIT 1').format(
                                   sql.Identifier('item' + str(before.item_id).zfill(4))))
        latest = cursor.fetchone()
        cursor.execute(sql.SQL('SELECT count(*) FROM public.{} WHERE time>%s').format(
            sql.Identifier('item' + str(before.item_id).zfill(4))), (before.last_time,))
        added = cursor.fetchone()[0]
    if latest is None or type(added) is not int or added < 0:
        raise RuntimeError('BatteryIcon JDBC tail unavailable')
    if added == 0 and (latest[0], str(latest[1])) != (before.last_time, before.last_state):
        raise RuntimeError('BatteryIcon JDBC latest state changed without append')
    if added > 0 and latest[0] <= before.last_time:
        raise RuntimeError('BatteryIcon JDBC new rows are not later')
    return {'added': added, 'last_time': latest[0], 'last_state': str(latest[1])}
