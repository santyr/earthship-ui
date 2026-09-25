#!/usr/bin/env python3
"""Private full database snapshot and network-isolated data restore rehearsal.

No production mutations. Ownership/ACL and external configuration restoration
are NOT qualified by this no-owner/no-privileges data rehearsal.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from private_receipt import save_private_json


def fingerprint_query(schema, table):
    for name in (schema, table):
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z_0-9]*', name):
            raise ValueError('unsupported SQL identifier')
    # Constant-size multiset accumulator, unlike string_agg of every row hash.
    # Count plus four signed 64-bit limb sums preserve duplicate multiplicity.
    limbs = [f"COALESCE(sum(('x'||substr(h,{i},16))::bit(64)::bigint),0)::text"
             for i in (1, 17, 33, 49)]
    return ('SELECT count(*)::text,' + ','.join(limbs) +
            " FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') h "
            f'FROM "{schema}"."{table}" t) rows;')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.destination_root.resolve(strict=True)
    if root != Path('/home/sat/backups/earthship-energy'):
        raise ValueError('only the established private backup root is allowed')
    if shutil.disk_usage(root).free < 80 * 1024**3:
        raise RuntimeError('80 GiB free space required')
    os.umask(0o077)
    dest = Path(tempfile.mkdtemp(prefix='full-restore-', dir=root))
    print('private_receipt=' + str(dest), flush=True)
    log = (dest / 'commands.log').open('xb')

    def run(argv, *, data=None, stdin=None, timeout=7200, env=None):
        result = subprocess.run(argv, input=data, stdin=stdin, stdout=subprocess.PIPE,
                                stderr=log, timeout=timeout, env=env)
        if result.returncode:
            raise RuntimeError('command failed; see private log: ' + argv[0])
        return result.stdout

    def save(name, value):
        save_private_json(dest, name, value)

    sys.path.insert(0, '/home/sat/Solar_PV/analytics/src')
    from earthship_energy.db import parse_openhab_jdbc_config
    import psycopg2
    settings = parse_openhab_jdbc_config('/var/lib/openhab/config/org/openhab/jdbc.config')
    archive = dest / 'openhab.dump'
    connection = psycopg2.connect(**settings.connect_kwargs, connect_timeout=5)
    original = {}
    started = datetime.now(timezone.utc).isoformat()
    try:
        connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='300s'; SET LOCAL lock_timeout='2s'; SET LOCAL timezone='UTC'; SET LOCAL work_mem='16MB'; SET LOCAL max_parallel_workers_per_gather=0")
            cursor.execute('SELECT pg_export_snapshot()')
            snapshot = cursor.fetchone()[0]
            cursor.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2")
            tables = cursor.fetchall()
            print('snapshot_tables=' + str(len(tables)), flush=True)
            for index, (schema, table) in enumerate(tables):
                cursor.execute(fingerprint_query(schema, table))
                original[schema + '.' + table] = list(cursor.fetchone())
                if index % 25 == 0:
                    print(f'fingerprinted={index + 1}/{len(tables)}', flush=True)
            save('source-fingerprints.json', original)
            env = {**os.environ, 'PGPASSWORD': settings.password, 'PGCONNECT_TIMEOUT': '5',
                   'PGOPTIONS': '-c default_transaction_read_only=on -c lock_timeout=2000'}
            run(['nice', '-n', '10', 'pg_dump', '-h', settings.host, '-p', str(settings.port),
                 '-U', settings.user, '-d', settings.dbname, '--format=custom',
                 '--snapshot=' + snapshot, '--file=' + str(archive)], env=env)
    finally:
        connection.close()
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    print('archive_complete=true', flush=True)
    marker = uuid.uuid4().hex
    container = None
    try:
        container = run(['docker', 'run', '--detach', '--network', 'none', '--memory', '1g',
                         '--memory-swap', '1g', '--cpus', '1', '--label', 'hex.full.restore=' + marker,
                         '--name', 'hex-full-restore-' + marker, '-e', 'POSTGRES_HOST_AUTH_METHOD=trust',
                         'postgres:16']).decode().strip()
        if not re.fullmatch('[0-9a-f]{64}', container):
            raise RuntimeError('invalid container identity')
        save('container.json', {'id': container, 'ownership_marker': marker})
        for _ in range(60):
            ready = subprocess.run(['docker', 'exec', container, 'pg_isready', '-U', 'postgres'],
                                   stdout=subprocess.DEVNULL, stderr=log, timeout=5)
            if ready.returncode == 0:
                break
            time.sleep(.5)
        else:
            raise RuntimeError('isolated database did not become ready')
        with archive.open('rb') as stream:
            run(['docker', 'exec', '-i', container, 'pg_restore', '--exit-on-error',
                 '--no-owner', '--no-privileges', '-U', 'postgres', '-d', 'postgres'], stdin=stream)
        print('restore_complete=true', flush=True)

        def query(sql):
            return run(['docker', 'exec', '-i', container, 'psql', '-X', '-q', '-At',
                        '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1'],
                       data=("SET timezone='UTC'; SET statement_timeout='300s'; SET work_mem='16MB'; " + sql).encode()).decode().strip()

        actual = query("SELECT schemaname||'.'||tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1;").splitlines()
        if actual != sorted(original):
            raise RuntimeError('restored table inventory mismatch')
        for index, (schema, table) in enumerate(tables):
            if query(fingerprint_query(schema, table)).split('|') != original[schema + '.' + table]:
                raise RuntimeError('restored data fingerprint mismatch')
            if index % 25 == 0:
                print(f'restored_verified={index + 1}/{len(tables)}', flush=True)
        save('backup-manifest.json', {
            'version': 1, 'database': settings.dbname, 'scope': 'full_database',
            'status': 'restore_verified', 'storage_scope': 'same_host',
            'archive_path': str(archive), 'archive_sha256': digest,
            'snapshot_started_at': started, 'verified_at': datetime.now(timezone.utc).isoformat(),
            'table_count': len(tables), 'fingerprint_algorithm': 'row_sha256_four_signed_limb_sums_v1',
            'fingerprints': original, 'production_mutations': False,
            'ownership_acl_restore_verified': False, 'external_config_restore_verified': False})
        print('full_database_data_restore_verified=true', flush=True)
    finally:
        if container and re.fullmatch('[0-9a-f]{64}', container):
            label = run(['docker', 'inspect', '--format', '{{index .Config.Labels "hex.full.restore"}}', container]).decode().strip()
            if label != marker:
                raise RuntimeError('container ownership mismatch; cleanup refused')
            # postgres:16 declares an anonymous data volume. Remove only the
            # verified owned container and its attached anonymous volumes.
            run(['docker', 'rm', '--force', '--volumes', container])
            print('owned_restore_container_removed=true', flush=True)
        log.close()


if __name__ == '__main__':
    main()
