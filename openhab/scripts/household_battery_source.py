"""Fixed, bounded read-only acquisition of original BMS target rows."""
from datetime import datetime,timedelta,timezone
from household.evidence import utc
from household.battery_outcomes import build_endpoint_source


def fetch_endpoint(connection_factory,*,target_at,remaining,clock=lambda:datetime.now(timezone.utc)):
    target=utc(target_at);requested=utc(clock());connection=None
    if requested<target+timedelta(minutes=5):raise ValueError('mature battery target required')
    def check():
        value=remaining()
        if type(value) not in (int,float) or not .001<=value<=15:raise ValueError('battery endpoint deadline elapsed')
        return max(1,min(2000,int(value*1000)))
    try:
        check();connection=connection_factory();check()
        if connection.get_transaction_status()!=0:raise ValueError('dedicated idle endpoint connection required')
        connection.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            def execute(query,params=None):
                cursor.execute('SET LOCAL statement_timeout = %s',(str(check())+'ms',));check()
                cursor.execute(query,params);check()
            execute("SET LOCAL lock_timeout = '1000ms'")
            execute("SET LOCAL idle_in_transaction_session_timeout = '5000ms'")
            execute('SHOW transaction_read_only')
            if cursor.fetchone()!=('on',):raise ValueError('read-only endpoint transaction required')
            execute('SHOW transaction_isolation')
            if cursor.fetchone()!=('repeatable read',):raise ValueError('stable endpoint transaction required')
            execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',('BMS_SOC_Evidence_JSON',))
            mapping=cursor.fetchall()
            if len(mapping)!=1 or len(mapping[0])!=1 or type(mapping[0][0]) is not int or not 0<=mapping[0][0]<=2147483647:
                raise ValueError('unique original battery Item required')
            item_id=mapping[0][0];table=f'public.item{item_id:04d}'
            execute(f'SELECT time, CASE WHEN octet_length(value::text)<=4096 THEN value::text ELSE NULL END FROM {table} WHERE time >= %s AND time <= %s ORDER BY time DESC LIMIT 2',(target-timedelta(seconds=120),target))
            rows=cursor.fetchall()
        check()
        return build_endpoint_source(rows=rows,target_at=target,requested_at=requested,received_at=clock(),item_id=item_id)
    finally:
        if connection is not None:connection.close()
