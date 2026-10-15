"""Bounded read-only day acquisition for the scheduled AC-output learner."""
from datetime import timedelta
from household.evidence import utc
from household_ac_load_sources import build_day_source,MAX_ROWS


def capture_day(*,connect,start,end,clock,remaining):
    start,end=utc(start),utc(end);requested=utc(clock());remaining()
    connection=connect(remaining=remaining)
    try:
        connection.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='2000ms'")
            cursor.execute("SET LOCAL lock_timeout='1000ms'")
            cursor.execute("SET LOCAL idle_in_transaction_session_timeout='5000ms'")
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone()!=('on',):raise ValueError('read-only original AC transaction required')
            remaining()
            cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',('Inverter_AC_Evidence_JSON',))
            mapping=cursor.fetchall()
            if len(mapping)!=1 or len(mapping[0])!=1 or type(mapping[0][0]) is not int or not 0<=mapping[0][0]<=2147483647:
                raise ValueError('unique integer original AC Item mapping required')
            item=mapping[0][0];remaining()
            cursor.execute(f'SELECT time,CASE WHEN octet_length(value::text)<=4096 THEN value::text ELSE NULL END FROM public.item{item:04d} WHERE time>=%s AND time<%s ORDER BY time ASC LIMIT {MAX_ROWS+1}',(start-timedelta(seconds=120),end))
            rows=cursor.fetchall();remaining();received=utc(clock())
            return build_day_source(rows=rows,start=start,end=end,requested_at=requested,received_at=received,item_id=item)
    finally:connection.close()
