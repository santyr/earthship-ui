"""Bounded correction-aware journal reads using fake SQL connections only."""
from datetime import datetime,timedelta,timezone
import pytest
from thermal_model.journal import ActionJournal,JournalUnavailable
from thermal_model.capture_readers import ReadBudget

AT=datetime(2026,8,1,tzinfo=timezone.utc)
DSN='host=127.0.0.1 port=5432 dbname=openhab user=synthetic_reader password=synthetic'


class Connection:
    def __init__(self,rows=()):self.rows=rows;self.calls=[];self.closed=False;self.session=None
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def cursor(self):return self
    def execute(self,query,params=None):self.calls.append((query,params))
    def fetchall(self):return self.rows
    def fetchone(self):return ('on',)
    def get_transaction_status(self):return 0
    def set_session(self,**kwargs):self.session=kwargs
    def close(self):self.closed=True


@pytest.mark.parametrize('method',['effective_events','effective_modes'])
def test_opt_in_journal_bounds_keep_original_query_and_context(method,monkeypatch):
    import thermal_model.journal as journal_module
    original=Connection();limited=Connection()
    monkeypatch.setattr(journal_module.psycopg2,'connect',lambda dsn:original)
    assert getattr(ActionJournal(DSN),method)(AT,AT+timedelta(hours=1))==()
    bounded=ActionJournal(DSN,read_limit=2,read_connection_factory=lambda dsn:limited)
    assert getattr(bounded,method)(AT,AT+timedelta(hours=1))==()
    old_sql,old_params=original.calls[-1];new_sql,new_params=limited.calls[-1]
    assert old_sql+'\n LIMIT %s' in new_sql and new_params==old_params+(3,)
    assert 'octet_length' in new_sql and '> 2048' in new_sql and 'CASE WHEN' in new_sql
    assert 'correction.supersedes' in new_sql and 'effective_at < %s' in new_sql
    if method=='effective_events':assert 'kiva_recent' in new_sql and 'prior_by_action' in new_sql


@pytest.mark.parametrize('method',['effective_events','effective_modes'])
def test_overflow_refuses_whole_journal_result(method):
    journal=ActionJournal(DSN,read_limit=2,read_connection_factory=lambda dsn:Connection(rows=[object()]*3))
    with pytest.raises(JournalUnavailable):getattr(journal,method)(AT,AT+timedelta(hours=1))


@pytest.mark.parametrize('limit',[0,True,10001])
def test_invalid_journal_row_limit_refuses(limit):
    with pytest.raises(ValueError):ActionJournal(DSN,read_limit=limit)


def backend():
    from thermal_model.capture_backends import configured_capture_journal
    return configured_capture_journal


def test_capture_journal_shares_pacing_forces_read_only_and_closes(monkeypatch):
    import thermal_model.capture_backends as source
    clock=[0.];connections=[]
    def connect(dsn):
        value=Connection();connections.append((value,clock[0],dsn));return value
    monkeypatch.setattr(source.psycopg2,'connect',connect)
    def sleep(seconds):clock[0]+=seconds
    budget=ReadBudget(10,clock=lambda:clock[0],sleeper=sleep)
    journal=backend()(dsn=DSN,budget=budget)
    assert journal.effective_events(AT,AT+timedelta(hours=1))==()
    assert journal.effective_modes(AT,AT+timedelta(hours=1))==()
    assert [at for value,at,dsn in connections]==[0.,1.] and budget.requests==2
    assert all(value.closed and value.session['readonly'] for value,at,dsn in connections)
    assert all(value.calls[-1][1][-1]==10001 for value,at,dsn in connections)
    assert not hasattr(journal,'append')


def test_capture_journal_refuses_huge_interval_before_connection(monkeypatch):
    import thermal_model.capture_backends as source
    monkeypatch.setattr(source.psycopg2,'connect',lambda *args:pytest.fail('huge interval connected'))
    with pytest.raises(ValueError):backend()(dsn=DSN,budget=ReadBudget(5)).effective_events(AT,AT+timedelta(days=100))


@pytest.mark.parametrize('method,width',[('effective_events',11),('effective_modes',9)])
def test_oversized_journal_row_refuses_server_guard_marker(method,width):
    connection=Connection(rows=[tuple([None]*width+[True])])
    journal=ActionJournal(DSN,read_limit=2,read_connection_factory=lambda dsn:connection)
    with pytest.raises(JournalUnavailable):getattr(journal,method)(AT,AT+timedelta(hours=1))
    sql,params=connection.calls[-1]
    assert 'octet_length' in sql and 'capture_oversize' in sql and 'CASE WHEN' in sql
    assert params[-1]==3


@pytest.mark.parametrize('method',['effective_events','effective_modes'])
def test_bounded_rows_preserve_original_fields_and_confidence(method):
    from dataclasses import astuple
    from thermal_model.schema import ActionEvent,ModeEvent
    event=ActionEvent('synthetic-id','synthetic-key',AT,AT,'indoor_shade','closed','historical_reconstruction',.35,note='original note') if method=='effective_events' else ModeEvent('synthetic-id','synthetic-key',AT,AT,'winter','manual_dm',1.,note='original note')
    connection=Connection(rows=[astuple(event)+(False,)])
    journal=ActionJournal(DSN,read_limit=2,read_connection_factory=lambda dsn:connection)
    assert getattr(journal,method)(AT,AT+timedelta(hours=1))==(event,)


@pytest.mark.parametrize('damage',['busy','readonly','sql','expired'])
def test_capture_journal_failure_closes_connection_and_refuses(damage,monkeypatch):
    import thermal_model.capture_backends as source
    import psycopg2
    clock=[0.];connection=Connection()
    if damage=='busy':connection.get_transaction_status=lambda:1
    if damage=='readonly':connection.fetchone=lambda:('off',)
    original=connection.execute
    def execute(query,params=None):
        if query.startswith('SELECT '):
            if damage=='sql':raise psycopg2.OperationalError('private-test-marker')
            if damage=='expired':clock[0]=6
        original(query,params)
    connection.execute=execute
    monkeypatch.setattr(source.psycopg2,'connect',lambda dsn:connection)
    journal=backend()(dsn=DSN,budget=ReadBudget(5,clock=lambda:clock[0]))
    with pytest.raises(ValueError) as error:journal.effective_events(AT,AT+timedelta(hours=1))
    assert connection.closed and 'private-test-marker' not in str(error.value)
