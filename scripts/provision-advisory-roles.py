#!/usr/bin/env python3
"""One-shot create-only outcome credentials/roles; never inserts test evidence."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

CONFIG = Path('/home/sat/.config/hex/advisory-outcomes.env')
ROLES = ('advisory_writer', 'advisory_assessor')


def sql(statement):
    r = subprocess.run(['sudo', '-n', '-u', 'postgres', 'psql', '-X', '-d', 'openhab',
        '-At', '-v', 'ON_ERROR_STOP=1'], input=statement, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode:
        raise RuntimeError('role provisioning SQL failed; inspect before retrying')
    return r.stdout.strip()


def main():
    if CONFIG.exists() or CONFIG.is_symlink():
        raise RuntimeError('private configuration already exists')
    if sql("SELECT rolname FROM pg_roles WHERE rolname IN ('advisory_writer','advisory_assessor');"):
        raise RuntimeError('role collision; refusing adoption')
    if sql('SELECT version FROM energy_analytics.schema_migrations ORDER BY version;') != '1\n2\n3\n4':
        raise RuntimeError('migration ledger mismatch')
    if sql("SELECT itemid FROM public.items WHERE itemname='BMS_SOC_Evidence_JSON';") != '613':
        raise RuntimeError('atomic BMS mapping drift')
    if sys.argv[1:] != ['--apply']:
        print('preflight=PASS roles_absent=true ledger=1,2,3,4 mapping=613')
        return
    passwords = {role: secrets.token_urlsafe(36) for role in ROLES}
    dsns = {role: f'host=127.0.0.1 port=5432 dbname=openhab user={role} password={password}'
            for role, password in passwords.items()}
    cutover = datetime.now(timezone.utc).isoformat(timespec='seconds')
    values = dict(ADVISORY_CAPTURE_ENABLED='1', ADVISORY_ASSESS_ENABLED='1',
        ADVISORY_CAPTURE_BANK_EPOCH='discover_4_module_2026',
        ADVISORY_ASSESS_BANK_EPOCH='discover_4_module_2026',
        ADVISORY_ASSESS_CUTOVER_AT=cutover, ADVISORY_ASSESS_TIMEZONE='America/Denver',
        ADVISORY_CAPTURE_DSN=dsns['advisory_writer'], ADVISORY_ASSESS_DSN=dsns['advisory_assessor'])
    os.umask(0o077)
    patch = '*** Begin Patch\n*** Add File: ' + str(CONFIG) + '\n'
    patch += ''.join('+' + key + '="' + value + '"\n' for key, value in values.items()) + '*** End Patch\n'
    result = subprocess.run(['apply_patch'], input=patch, text=True, capture_output=True, timeout=10)
    if result.returncode:
        raise RuntimeError('private configuration staging failed')
    statements = ['BEGIN;', "SET LOCAL statement_timeout='5s';", "SET LOCAL lock_timeout='2s';"]
    for role in ROLES:
        statements.extend([
            f"CREATE ROLE {role} LOGIN PASSWORD '{passwords[role]}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 4;",
            f"ALTER ROLE {role} SET statement_timeout='2s';",
            f"ALTER ROLE {role} SET lock_timeout='1s';",
            f'GRANT CONNECT ON DATABASE openhab TO {role};',
            f'GRANT USAGE ON SCHEMA energy_analytics TO {role};'])
    statements.extend([
        'GRANT SELECT,INSERT ON energy_analytics.advisory_decisions,energy_analytics.advisory_results TO advisory_writer;',
        'GRANT SELECT ON energy_analytics.advisory_decisions,energy_analytics.advisory_results TO advisory_assessor;',
        'GRANT SELECT,INSERT ON energy_analytics.advisory_trough_outcomes,energy_analytics.advisory_trough_selection TO advisory_assessor;',
        'GRANT USAGE ON SCHEMA public TO advisory_assessor;',
        'GRANT SELECT ON public.items,public.item0613 TO advisory_assessor;', 'COMMIT;'])
    sql('\n'.join(statements))
    verify(dsns, cutover)


def verify(dsns, cutover):
    """Read-only effective-grant verification, also usable after partial install."""
    import psycopg2
    allowed = {
        'advisory_writer': {'energy_analytics.advisory_decisions': {'SELECT', 'INSERT'},
                            'energy_analytics.advisory_results': {'SELECT', 'INSERT'}},
        'advisory_assessor': {'energy_analytics.advisory_decisions': {'SELECT'},
            'energy_analytics.advisory_results': {'SELECT'},
            'energy_analytics.advisory_trough_outcomes': {'SELECT', 'INSERT'},
            'energy_analytics.advisory_trough_selection': {'SELECT', 'INSERT'},
            'public.items': {'SELECT'}, 'public.item0613': {'SELECT'}}}
    for role in ROLES:
        conn = psycopg2.connect(dsns[role], connect_timeout=3)
        try:
            conn.set_session(readonly=True)
            with conn.cursor() as c:
                c.execute('SELECT current_user')
                if c.fetchone() != (role,): raise RuntimeError('role identity mismatch')
                c.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user')
                if any(c.fetchone()): raise RuntimeError('elevated role attributes')
                c.execute('SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)')
                if c.fetchall(): raise RuntimeError('unexpected memberships')
                c.execute("SELECT nspname FROM pg_namespace WHERE nspname IN ('public','energy_analytics') AND has_schema_privilege(current_user,oid,'CREATE')")
                if c.fetchall(): raise RuntimeError('unexpected schema creation privilege')
                c.execute("SELECT n.nspname||'.'||r.relname,r.oid FROM pg_class r JOIN pg_namespace n ON n.oid=r.relnamespace WHERE r.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema')")
                for table, oid in c.fetchall():
                    for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                        c.execute('SELECT has_table_privilege(current_user,%s::oid,%s)', (oid, privilege))
                        if c.fetchone()[0] != (privilege in allowed[role].get(table, set())):
                            raise RuntimeError('effective privilege mismatch')
                for table in allowed[role]:
                    c.execute('SELECT 1 FROM ' + table + ' LIMIT 1')
        finally:
            conn.close()
    if CONFIG.stat().st_mode & 0o077:
        raise RuntimeError('private config permissions mismatch')
    print(json.dumps({'provisioning': 'PASS', 'roles': list(ROLES), 'effective_privileges': 'exact',
                      'assessment_cutover': cutover, 'config_mode': '0600', 'records_inserted': 0}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__, file=sys.stderr)
        raise SystemExit(1) from None
