#!/usr/bin/env python3
"""Read-only, bounded first-natural-issue check; never triggers a forecast."""

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'openhab/scripts'), '/home/sat/Solar_PV/analytics/src']

from earthship_energy.db import parse_openhab_jdbc_config  # noqa: E402
from pre_dusk_issue_source import read_issue_source  # noqa: E402
from pre_dusk_release import qualify_day  # noqa: E402
from pre_dusk_tuning_history import local_get  # noqa: E402
from openhab_sanity_check import token  # noqa: E402


JDBC = '/home/sat/.config/hex/energy-power-reader.jdbc'


def source_reader(issue):
    import psycopg2
    settings = parse_openhab_jdbc_config(JDBC)
    if (settings.host, settings.port, settings.dbname, settings.user) != (
            '127.0.0.1', 5432, 'openhab', 'energy_power_reader'):
        raise ValueError('restricted source reader required')
    return read_issue_source(lambda: psycopg2.connect(
        **settings.connect_kwargs, connect_timeout=3,
        options='-c default_transaction_read_only=on -c statement_timeout=3000'), issue)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day', required=True, type=date.fromisoformat,
                        help='America/Denver prediction date (YYYY-MM-DD)')
    args = parser.parse_args(argv)
    try:
        auth = token()
        result = qualify_day(lambda path: local_get(path, token=auth), source_reader,
                             day=args.day, now=datetime.now(timezone.utc))
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0 if result['status'] == 'qualified_natural_issue' else 2
    except Exception:
        # No token, DSN, original source JSON or remote diagnostic is logged.
        print('{"status":"withheld","reason":"natural issue qualification unavailable"}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
