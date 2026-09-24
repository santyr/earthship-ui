#!/usr/bin/env python3
"""Bounded-memory, read-only digest of a fixed Bitcoin price JDBC prefix.

Run before and after a provider handoff with the SAME UTC cutoff. Rows stream
through SHA-256; the million-row Item table is never loaded into Python memory.
This is a preservation check, not a backup or proof of natural writer recovery.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import sys

sys.path.insert(0, '/home/sat/Solar_PV/analytics/src')
from earthship_energy.db import parse_openhab_jdbc_config  # noqa: E402
import psycopg2  # noqa: E402
from psycopg2 import sql  # noqa: E402

CONFIG = '/var/lib/openhab/config/org/openhab/jdbc.config'
ITEM = 'BTC_USD_Price'
ITEM_ID = 34


class DigestSink:
    def __init__(self):
        self.digest = sha256()
        self.bytes_written = 0

    def write(self, chunk):
        if isinstance(chunk, str):
            chunk = chunk.encode('utf-8')
        self.digest.update(chunk)
        self.bytes_written += len(chunk)


def parse_cutoff(text):
    try:
        at = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('cutoff must be an ISO-8601 timestamp') from error
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError('cutoff must include a timezone')
    at = at.astimezone(timezone.utc)
    if at > datetime.now(timezone.utc):
        raise ValueError('cutoff must not be in the future')
    return at


def digest_history(cutoff):
    settings = parse_openhab_jdbc_config(CONFIG)
    db = psycopg2.connect(**settings.connect_kwargs, connect_timeout=5)
    db.set_session(readonly=True, isolation_level='REPEATABLE READ')
    try:
        with db.cursor() as cursor:
            cursor.execute("SET LOCAL TIME ZONE 'UTC'")
            cursor.execute("SET LOCAL DateStyle TO 'ISO, YMD'")
            cursor.execute('SET LOCAL extra_float_digits TO 3')
            cursor.execute('SET LOCAL statement_timeout TO 120000')
            cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s', (ITEM,))
            identities = cursor.fetchall()
            if identities != [(ITEM_ID,)]:
                raise RuntimeError('Bitcoin price JDBC identity changed')
            table = sql.Identifier('item' + str(ITEM_ID).zfill(4))
            cursor.execute(sql.SQL('SELECT count(*), min(time), max(time) '
                                   'FROM public.{} WHERE time < %s').format(table),
                           (cutoff,))
            count, first, last = cursor.fetchone()
            if count <= 0:
                raise RuntimeError('Bitcoin price JDBC prefix is empty')
            sink = DigestSink()
            query = sql.SQL('COPY (SELECT time,value FROM public.{} '
                            'WHERE time < {} ORDER BY time,value) '
                            'TO STDOUT WITH CSV').format(table, sql.Literal(cutoff))
            cursor.copy_expert(query.as_string(db), sink)
            if sink.bytes_written <= 0:
                raise RuntimeError('Bitcoin price JDBC stream is empty')
            return {'item': ITEM, 'jdbc_item_id': ITEM_ID,
                    'before_utc': cutoff.isoformat(), 'rows': count,
                    'first_utc': first.isoformat(), 'last_utc': last.isoformat(),
                    'stream_bytes': sink.bytes_written,
                    'sha256': sink.digest.hexdigest()}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True,
                        help='fixed aware ISO-8601 cutoff, exclusive')
    args = parser.parse_args()
    print(json.dumps(digest_history(parse_cutoff(args.before)), sort_keys=True))


if __name__ == '__main__':
    main()
