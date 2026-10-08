"""Capture-only native history using existing qualification and shared budgets."""
import os
import psycopg2
from psycopg2.extensions import make_dsn,parse_dsn

from .capture_readers import bounded_journal_dsn
from .graduation_policy import _utc
from .temperature_history import QualifiedTemperatureHistory


def configured_capture_history(legacy_reader,now,*,environ,budget):
    env=dict(environ)
    if env.get('THERMAL_TEMP_QUALIFIED_ENABLE')!='1':raise ValueError('explicit native capture history required')
    for key in ('THERMAL_TEMP_DB_CONFIG','THERMAL_TEMP_POLICY'):
        if not isinstance(env.get(key),str) or not os.path.isabs(env[key]):raise ValueError('explicit absolute native capture configuration required')
    assessed=_utc(now);cutover=_utc(env.get('THERMAL_TEMP_EVIDENCE_CUTOVER'))
    def connect(config):
        # The existing collector first validates the private config and fixed reader role.
        params=parse_dsn(bounded_journal_dsn(make_dsn(**config)))
        timeout=budget.begin()
        # libpq rounds connect timeouts below two seconds upward; refuse instead.
        if timeout<2:raise ValueError('native capture connection deadline unavailable')
        params['connect_timeout']=str(min(3,int(timeout)))
        return psycopg2.connect(make_dsn(**params))
    def read(stream,targets,assessed_at):
        from thermal_temperature_runtime import collect
        budget.remaining()
        request=dict(stream=stream,targets=[at.isoformat() for at in targets],assessed_at=assessed_at.isoformat())
        rows=collect(request,config_path=env['THERMAL_TEMP_DB_CONFIG'],policy_path=env['THERMAL_TEMP_POLICY'],connection_factory=connect)
        budget.remaining()
        return rows
    return QualifiedTemperatureHistory(legacy_reader,read,cutover=cutover,assessed_at=assessed,retain_raw=True)


class _ClosingConnection:
    def __init__(self,connection,budget):self.connection=connection;self.budget=budget
    def __enter__(self):
        try:
            self.budget.remaining()
            return self.connection.__enter__()
        except BaseException:
            self.connection.close();raise
    def __exit__(self,*args):
        try:return self.connection.__exit__(*args)
        finally:self.connection.close()


class _CaptureJournal:
    def __init__(self,journal,budget):self._journal=journal;self.budget=budget
    def _read(self,name,start,end):
        from .journal import JournalUnavailable
        from .training_inputs import MAX_WINDOW_STEPS
        from .temperature_history import STEP
        start,end=map(_utc,(start,end))
        if not start<end or end-start>MAX_WINDOW_STEPS*STEP:raise ValueError('bounded capture journal interval required')
        self.budget.remaining()
        try:rows=getattr(self._journal,name)(start,end)
        except (psycopg2.Error,JournalUnavailable):raise ValueError('bounded capture journal unavailable') from None
        self.budget.remaining()
        return rows
    def effective_events(self,start,end):return self._read('effective_events',start,end)
    def effective_modes(self,start,end):return self._read('effective_modes',start,end)


def configured_capture_journal(*,dsn,budget):
    from .journal import ActionJournal
    from .training_inputs import MAX_EVENTS
    bounded=bounded_journal_dsn(dsn)
    def connect(dsn):
        params=parse_dsn(dsn);timeout=budget.begin()
        if timeout<2:raise ValueError('journal capture connection deadline unavailable')
        params['connect_timeout']=str(min(3,int(timeout)))
        connection=psycopg2.connect(make_dsn(**params))
        try:
            if connection.get_transaction_status()!=0:raise ValueError('dedicated idle capture connection required')
            connection.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
            with connection.cursor() as cursor:
                cursor.execute('SHOW transaction_read_only')
                if cursor.fetchone()!=('on',):raise ValueError('read-only capture journal transaction required')
            return _ClosingConnection(connection,budget)
        except BaseException:
            connection.close();raise
    return _CaptureJournal(ActionJournal(bounded,read_limit=MAX_EVENTS,read_connection_factory=connect),budget)
