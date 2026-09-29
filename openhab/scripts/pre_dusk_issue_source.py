"""Read-only exact atomic-SoC source lookup for one issued pre-dusk forecast.

Only the latest original JDBC receipt at or before the issue may qualify.
No current held Item, later receipt or alternate table can substitute for it.
"""

from datetime import datetime, timezone

from pre_dusk_tuning import verify_issue_soc


ITEM = 'BMS_SOC_Evidence_JSON'


class IssueSourceUnavailable(ValueError):
    """The original source-bound issue input cannot be established."""


def read_issue_source(connection_factory, pre_dusk):
    connection = None
    try:
        if not callable(connection_factory) or not isinstance(pre_dusk, dict):
            raise ValueError('connection and issue required')
        issue = datetime.fromisoformat(pre_dusk['issuedAt'].replace('Z', '+00:00'))
        if issue.utcoffset() is None:
            raise ValueError('aware issue required')
        issue = issue.astimezone(timezone.utc)
        connection = connection_factory()
        if connection.get_transaction_status() != 0:
            raise ValueError('dedicated idle connection required')
        connection.set_session(readonly=True, autocommit=False,
                               isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '2000ms'")
            cursor.execute("SET LOCAL lock_timeout = '1000ms'")
            cursor.execute("SET LOCAL idle_in_transaction_session_timeout = '5000ms'")
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone() != ('on',):
                raise ValueError('read-only snapshot required')
            cursor.execute('SHOW transaction_isolation')
            if cursor.fetchone() != ('repeatable read',):
                raise ValueError('stable snapshot required')
            cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2', (ITEM,))
            matches = cursor.fetchall()
            if (len(matches) != 1 or type(matches[0][0]) is not int
                    or not 0 <= matches[0][0] <= 2147483647):
                raise ValueError('unique atomic SoC mapping required')
            table = f'item{matches[0][0]:04d}'
            cursor.execute(f'''SELECT time, value FROM public.{table}
                WHERE time <= %s ORDER BY time DESC LIMIT 2''', (issue,))
            rows = cursor.fetchall()
        if (not 1 <= len(rows) <= 2 or len(rows[0]) != 2
                or len(rows) == 2 and rows[1][0] == rows[0][0]):
            raise ValueError('unique latest source row required')
        persisted_at, raw = rows[0]
        if (not isinstance(persisted_at, datetime) or persisted_at.utcoffset() is None
                or not isinstance(raw, str)):
            raise ValueError('original source row invalid')
        verify_issue_soc(pre_dusk, raw, persisted_at.isoformat())
        return {'source_item': ITEM, 'source_persisted_at':
                persisted_at.astimezone(timezone.utc).isoformat(),
                'source_stream_epoch': pre_dusk['socStreamEpoch'],
                'source_digest_sha256': pre_dusk['socEvidenceSha256']}
    except Exception:
        # Never print the database URL or original atomic evidence JSON.
        raise IssueSourceUnavailable('pre-dusk issue source unavailable') from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
