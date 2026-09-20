"""One-shot additive local reader role/config; no existing role or file overwrite.

Only use after the receipt Item's JDBC table exists. Password material is sent
over stdin to psql/apply_patch and is never printed or embedded in arguments.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

CONFIG = Path('/home/sat/.config/hex/weather-temperature-db.json')
ROLE = 'weather_temperature_reader'


def sql(statement, *, tuples=False):
    result = subprocess.run(['sudo', '-n', '-u', 'postgres', 'psql', '-X', '-d', 'openhab',
        '-v', 'ON_ERROR_STOP=1', '-At' if tuples else '-q'], input=statement,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    if result.returncode:
        raise RuntimeError('Database provisioning failed; inspect role and config before retrying')
    return result.stdout.strip()


def main():
    if CONFIG.exists() or CONFIG.is_symlink():
        raise RuntimeError('Configuration exists; refusing overwrite')
    if sql(f"SELECT rolname FROM pg_roles WHERE rolname='{ROLE}';", tuples=True):
        raise RuntimeError('Role exists; refusing overwrite')
    mapping = sql("SELECT itemid FROM public.items WHERE itemname='Weather_Temperature_Evidence_JSON';", tuples=True)
    if not mapping.isdigit() or not 0 <= int(mapping) <= 2147483647:
        raise RuntimeError('Unique persisted evidence mapping required')
    table = f'item{int(mapping):04d}'
    if sys.argv[1:] != ['--apply']:
        print(f'preflight=PASS role={ROLE} table={table}')
        return
    password = secrets.token_urlsafe(36)
    config = dict(host='127.0.0.1', port=5432, dbname='openhab', user=ROLE, password=password)
    # A private config exists before commit, so an interruption cannot lose the
    # generated credential. Any partial installation requires explicit review.
    os.umask(0o077)
    patch = '*** Begin Patch\n*** Add File: ' + str(CONFIG) + '\n+' + json.dumps(config) + '\n*** End Patch\n'
    result = subprocess.run(['apply_patch'], input=patch, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=10)
    if result.returncode:
        raise RuntimeError('Private config creation failed; no database change requested')
    sql(f"""BEGIN;
CREATE ROLE {ROLE} LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE {ROLE} SET default_transaction_read_only=on;
ALTER ROLE {ROLE} SET statement_timeout='2s';
ALTER ROLE {ROLE} SET lock_timeout='1s';
GRANT CONNECT ON DATABASE openhab TO {ROLE};
GRANT USAGE ON SCHEMA public TO {ROLE};
GRANT SELECT ON public.items, public.{table} TO {ROLE};
COMMIT;""")
    from hourly_temperature_runtime import read_db_config
    import psycopg2
    config = read_db_config(str(CONFIG))
    with psycopg2.connect(**config, connect_timeout=3) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone() != ('on',):
                raise RuntimeError('Read-only default unverified')
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND has_table_privilege(current_user, schemaname||'.'||tablename,'SELECT') ORDER BY tablename")
            if [r[0] for r in cursor.fetchall()] != sorted(['items', table]):
                raise RuntimeError('Unexpected read privileges')
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND has_table_privilege(current_user, schemaname||'.'||tablename,'INSERT,UPDATE,DELETE,TRUNCATE')")
            if cursor.fetchall():
                raise RuntimeError('Unexpected write privileges')
    print(f'provisioning=PASS role={ROLE} select_only=items,{table} config_mode=0600')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Provisioning stopped: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__), file=sys.stderr)
        raise SystemExit(1) from None
