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
