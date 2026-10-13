"""Explicit administrator migration, never imported by runtime startup."""
import argparse
from pathlib import Path
from services.lorawan.storage import DDL


def migrate(admin_dsn,*,runtime_role,environment):
    import re
    import psycopg2
    from psycopg2 import sql
    if not re.fullmatch('[a-z][a-z0-9_]{0,47}',runtime_role) or environment not in ('production','simulation'):
        raise ValueError('explicit bounded role and environment required')
    with psycopg2.connect(admin_dsn,connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute('CREATE SCHEMA IF NOT EXISTS earthship_observations')
            cursor.execute('SET LOCAL search_path=earthship_observations,pg_catalog')
            cursor.execute(DDL)
            cursor.execute('SELECT value FROM metadata WHERE id=%s',('environment',))
            row=cursor.fetchone()
            if row is not None and row[0]!=environment:raise ValueError('journal environment differs; simulation cannot share production data')
            cursor.execute('INSERT INTO metadata(id,value) VALUES(%s,%s) ON CONFLICT(id) DO NOTHING',('environment',environment))
            cursor.execute('REVOKE ALL ON SCHEMA earthship_observations FROM PUBLIC')
            cursor.execute(sql.SQL('GRANT USAGE ON SCHEMA earthship_observations TO {}').format(sql.Identifier(runtime_role)))
            cursor.execute(sql.SQL('GRANT SELECT,INSERT ON raw_events,observations,seen TO {}').format(sql.Identifier(runtime_role)))
            cursor.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON states TO {}').format(sql.Identifier(runtime_role)))
            cursor.execute(sql.SQL('GRANT SELECT ON metadata TO {}').format(sql.Identifier(runtime_role)))


def main():
    parser=argparse.ArgumentParser(description='Staged schema migration. Production execution requires explicit operator authorization.')
    parser.add_argument('--admin-dsn-file',required=True);parser.add_argument('--runtime-role',required=True)
    parser.add_argument('--environment',choices=['production','simulation'],required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        print('Dry run: creates dedicated earthship_observations schema, immutable journal tables, environment binding and least-privilege runtime grants. No SQL executed.');return
    source=Path(args.admin_dsn_file)
    if source.stat().st_mode&0o077:raise ValueError('administrator DSN must have mode 0600')
    migrate(source.read_text().strip(),runtime_role=args.runtime_role,environment=args.environment)
    print('Observation schema and environment binding verified.')


if __name__=='__main__':main()
