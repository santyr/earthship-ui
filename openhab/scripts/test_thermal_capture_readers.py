"""Bounded capture-only transport, with fake HTTP and no database connections."""
from datetime import datetime,timedelta,timezone
from io import BytesIO
import json
import pytest
from psycopg2.extensions import parse_dsn
from thermal_model.schema import THERMAL_ITEMS


def module():
    from thermal_model import capture_readers
    return capture_readers


def test_http_capture_reads_only_gets_in_bounded_daily_chunks():
    source=module();start=datetime(2026,8,1,tzinfo=timezone.utc);end=start+timedelta(days=2)
    calls=[]
    def opener(request,timeout):
        calls.append((request.get_method(),request.full_url,timeout))
        at=start+timedelta(days=len(calls)-1)
        return BytesIO(json.dumps({'data':[{'time':at.timestamp()*1000,'state':'72 F'},{'time':(at+timedelta(minutes=5)).timestamp()*1000,'state':'UNDEF'}]}).encode())
    reader=source.BoundedJDBCReader(base='http://127.0.0.1:8080/rest',token_reader=lambda:'synthetic-token',budget=source.ReadBudget(30),opener=opener)
    rows=reader(THERMAL_ITEMS['air'],start,end)
    assert len(rows)==4 and rows[0][1]==72 and rows[1][1] is None
    assert len(calls)==2 and all(method=='GET' and 0<timeout<=5 for method,url,timeout in calls)
    assert all('serviceId=jdbc' in url for method,url,timeout in calls)


@pytest.mark.parametrize('damage',['large','bad_item','remote_base','expired'])
def test_bad_or_excessive_http_capture_refuses(damage):
    source=module();now=datetime(2026,8,1,tzinfo=timezone.utc);clock=[0.]
    budget=source.ReadBudget(5,clock=lambda:clock[0]);item=THERMAL_ITEMS['air'];base='http://127.0.0.1:8080/rest'
    if damage=='bad_item':item='../outside'
    if damage=='remote_base':base='https://unapproved.invalid/rest'
    if damage=='expired':clock[0]=6
    def opener(request,timeout):
        if damage!='large':pytest.fail('invalid context reached HTTP')
        return BytesIO(b'x'*(source.MAX_RESPONSE_BYTES+1))
    with pytest.raises(ValueError):
        reader=source.BoundedJDBCReader(base=base,token_reader=lambda:'synthetic-token',budget=budget,opener=opener)
        reader(item,now,now+timedelta(hours=1))


def test_redirects_refuse_capture():
    source=module();now=datetime(2026,8,1,tzinfo=timezone.utc)
    class Redirect(BytesIO):
        def geturl(self):return 'https://unapproved.invalid/data'
    def opener(request,timeout):return Redirect(b'{"data":[]}')
    reader=source.BoundedJDBCReader(base='http://127.0.0.1:8080/rest',token_reader=lambda:'synthetic-token',budget=source.ReadBudget(5),opener=opener)
    with pytest.raises(ValueError):reader(THERMAL_ITEMS['air'],now,now+timedelta(hours=1))


def test_journal_dsn_forces_read_only_timeouts_and_local_connection():
    source=module();value=source.bounded_journal_dsn('host=127.0.0.1 port=5432 dbname=openhab user=synthetic_reader password=synthetic options=-cbogus=1')
    parsed=parse_dsn(value)
    assert parsed['connect_timeout']=='3'
    assert 'default_transaction_read_only=on' in parsed['options']
    assert 'statement_timeout=5000' in parsed['options'] and 'lock_timeout=1000' in parsed['options']
    assert 'bogus' not in parsed['options']


@pytest.mark.parametrize('dsn',['host=remote.invalid dbname=openhab user=x password=x','host=127.0.0.1 dbname=other user=x password=x','host=127.0.0.1 dbname=openhab user=postgres password=x'])
def test_unapproved_journal_endpoint_refuses(dsn):
    with pytest.raises(ValueError):module().bounded_journal_dsn(dsn)


def test_budget_rechecks_after_blocking_query_and_counts_requests():
    source=module();clock=[0.];budget=source.ReadBudget(2,clock=lambda:clock[0],max_requests=1)
    def slow():clock[0]=3;return []
    with pytest.raises(ValueError):budget.call(slow)
    clock[0]=0;budget=source.ReadBudget(2,clock=lambda:clock[0],max_requests=1)
    assert budget.call(lambda:[])==[]
    with pytest.raises(ValueError):budget.call(lambda:[])


def test_journal_connection_address_and_port_cannot_inherit_ambient_defaults():
    parsed=parse_dsn(module().bounded_journal_dsn('host=127.0.0.1 dbname=openhab user=synthetic_reader password=synthetic'))
    assert parsed['hostaddr']=='127.0.0.1' and parsed['port']=='5432'


def test_bad_journal_dsn_is_sanitized():
    with pytest.raises(ValueError) as exc:module().bounded_journal_dsn("host=127.0.0.1 password='private-test-marker")
    assert 'private-test-marker' not in str(exc.value)


def test_out_of_range_history_timestamp_refuses_consistently():
    source=module();now=datetime(2026,8,1,tzinfo=timezone.utc)
    def opener(request,timeout):return BytesIO(json.dumps({'data':[{'time':1e200,'state':'72 F'}]}).encode())
    reader=source.BoundedJDBCReader(base='http://127.0.0.1:8080/rest',token_reader=lambda:'synthetic',budget=source.ReadBudget(5),opener=opener)
    with pytest.raises(ValueError):reader(THERMAL_ITEMS['air'],now,now+timedelta(hours=1))


def test_fractional_end_requests_all_included_points_and_filters_extra():
    from urllib.parse import urlparse,parse_qs
    source=module();start=datetime(2026,8,1,tzinfo=timezone.utc);end=start+timedelta(microseconds=500000)
    points=[start+timedelta(microseconds=250000),start+timedelta(microseconds=750000)]
    def opener(request,timeout):
        query=parse_qs(urlparse(request.full_url).query)
        left=datetime.fromisoformat(query['starttime'][0]);right=datetime.fromisoformat(query['endtime'][0])
        return BytesIO(json.dumps({'data':[{'time':at.timestamp()*1000,'state':'72 F'} for at in points if left<=at<right]}).encode())
    reader=source.BoundedJDBCReader(base='http://127.0.0.1:8080/rest',token_reader=lambda:'synthetic',budget=source.ReadBudget(5),opener=opener)
    assert reader(THERMAL_ITEMS['air'],start,end)==[(points[0],72.)]


@pytest.mark.parametrize('damage',['aggregate_bytes','points','token','hostaddr','service','passfile'])
def test_capture_additional_resource_and_routing_bounds(damage,monkeypatch):
    source=module();now=datetime(2026,8,1,tzinfo=timezone.utc)
    if damage in ('hostaddr','service','passfile'):
        with pytest.raises(ValueError):
            source.bounded_journal_dsn('host=127.0.0.1 dbname=openhab user=synthetic_reader password=synthetic '+damage+'=synthetic')
        return
    payload=json.dumps({'data':[{'time':now.timestamp()*1000,'state':'72 F'}]}).encode()
    calls=[]
    def opener(request,timeout):calls.append(request);return BytesIO(payload)
    reader=source.BoundedJDBCReader(base='http://127.0.0.1:8080/rest',token_reader=lambda:'bad\nheader' if damage=='token' else 'synthetic',budget=source.ReadBudget(5),opener=opener)
    if damage=='aggregate_bytes':reader.total_bytes=source.MAX_HTTP_TOTAL_BYTES-len(payload)+1
    if damage=='points':reader.total_points=source.MAX_SERIES_POINTS
    with pytest.raises(ValueError):reader(THERMAL_ITEMS['air'],now,now+timedelta(hours=1))
    assert len(calls)==(0 if damage=='token' else 1)


@pytest.mark.parametrize('rate',[None,0,True,1048577])
def test_capture_byte_pacing_cannot_be_disabled_or_raised(rate):
    source=module()
    with pytest.raises(ValueError):
        source.BoundedJDBCReader(base='http://127.0.0.1:8080/rest',token_reader=lambda:'synthetic',budget=source.ReadBudget(5),max_read_bytes_per_second=rate)
