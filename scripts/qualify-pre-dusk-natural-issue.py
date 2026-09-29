#!/usr/bin/env python3
"""Read-only natural pre-dusk issue and optional completed-night score check."""

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'openhab/scripts'), '/home/sat/Solar_PV/analytics/src']

from earthship_energy.db import parse_openhab_jdbc_config  # noqa: E402
from earthship_energy.materialize import load_epoch_config  # noqa: E402
from earthship_energy.series import local_day_bounds  # noqa: E402
from pre_dusk_issue_source import read_issue_source  # noqa: E402
from pre_dusk_release import qualify_day, score_completed_day  # noqa: E402
from pre_dusk_tuning_history import local_get  # noqa: E402
from pre_dusk_tuning_outcome import read_completed_outcome  # noqa: E402
from openhab_sanity_check import token  # noqa: E402


JDBC = '/home/sat/.config/hex/energy-power-reader.jdbc'


def restricted_connection():
    import psycopg2
    settings = parse_openhab_jdbc_config(JDBC)
    if (settings.host, settings.port, settings.dbname, settings.user) != (
            '127.0.0.1', 5432, 'openhab', 'energy_power_reader'):
        raise ValueError('restricted source reader required')
    return lambda: psycopg2.connect(
        **settings.connect_kwargs, connect_timeout=3,
        options='-c default_transaction_read_only=on -c statement_timeout=3000')


def source_reader(issue):
    return read_issue_source(restricted_connection(), issue)


def outcome_reader(day, now):
    bank = [epoch for epoch in load_epoch_config()
            if epoch.current_analytics and epoch.start_local_date is not None
            and epoch.start_local_date <= day
            and (epoch.end_local_date_exclusive is None
                 or day < epoch.end_local_date_exclusive)]
    if len(bank) != 1:
        raise ValueError('one physical bank epoch required')
    epoch = bank[0]
    return read_completed_outcome(
        restricted_connection(), day=day, as_of=now,
        epoch_start=local_day_bounds(epoch.start_local_date, 'America/Denver')[0],
        epoch_end=(local_day_bounds(epoch.end_local_date_exclusive,
                                    'America/Denver')[0]
                   if epoch.end_local_date_exclusive is not None else None))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day', required=True, type=date.fromisoformat,
                        help='America/Denver prediction date (YYYY-MM-DD)')
    parser.add_argument('--score-completed-night', action='store_true',
                        help='compare both original issues after the following 11:00 outcome')
    args = parser.parse_args(argv)
    try:
        auth = token()
        reader = lambda path: local_get(path, token=auth)
        now = datetime.now(timezone.utc)
        if args.score_completed_night:
            result = score_completed_day(reader, source_reader, outcome_reader,
                                         day=args.day, now=now)
        else:
            result = qualify_day(reader, source_reader, day=args.day, now=now)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        wanted = 'scored_completed_night' if args.score_completed_night else 'qualified_natural_issue'
        return 0 if result['status'] == wanted else 2
    except Exception:
        # No token, DSN, original source JSON or remote diagnostic is logged.
        print('{"status":"withheld","reason":"natural issue qualification unavailable"}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
