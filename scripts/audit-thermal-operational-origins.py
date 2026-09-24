#!/usr/bin/env python3
"""Read-only historical, origin-time thermal persistence baseline.

Uses only forecasts captured by each origin and receipt-qualified temperatures.
Actions are optional and, even when present, are as-of knowledge rather than
proof of execution. This does not score a physical model or qualify advice.
"""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
sys.path.insert(0, '/home/sat/Solar_PV/analytics/src')

import psycopg2  # noqa: E402
from earthship_energy.db import parse_openhab_jdbc_config  # noqa: E402
from thermal_model.action_history import fetch_origin_actions  # noqa: E402
from thermal_model.forecast_history import _utc, fetch_origin_forecast  # noqa: E402
from thermal_model.operational_origin import pair_persistence_outcome  # noqa: E402
from thermal_temperature_runtime import collect  # noqa: E402

CONFIG = '/home/sat/.config/hex/weather-temperature-db.json'
POLICY = '/home/sat/.config/hex/weather-temperature-policy.json'
JDBC_CONFIG = '/var/lib/openhab/config/org/openhab/jdbc.config'
MAX_ORIGINS = 96
MAX_WINDOW = timedelta(days=14)


def aware(text):
    at = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError('timestamps must include a timezone')
    at = at.astimezone(timezone.utc)
    if at.second or at.microsecond or at.minute % 5:
        raise ValueError('origins must align to five minutes')
    return at


def audit(start, end, *, step_hours, horizon_hours, assessed_at,
          forecast_reader, temperature_reader, action_reader=None):
    start, end, assessed_at = map(_utc, (start, end, assessed_at))
    if any(at.second or at.microsecond or at.minute % 5 for at in (start, end)):
        raise ValueError('origin bounds must align to five minutes')
    if not start < end <= assessed_at or end - start > MAX_WINDOW:
        raise ValueError('bounded completed origin window required')
    if type(step_hours) is not int or step_hours not in (1, 2, 3, 6, 12, 24):
        raise ValueError('step must be one of 1, 2, 3, 6, 12 or 24 hours')
    if type(horizon_hours) is not int or horizon_hours not in (1, 6, 12, 24, 48):
        raise ValueError('unsupported evaluation horizon')
    origins = []
    at = start
    while at < end:
        origins.append(at)
        if len(origins) > MAX_ORIGINS:
            raise ValueError('origin count exceeds bound')
        at += timedelta(hours=step_hours)
    counts = Counter()
    pairs = []
    for origin in origins:
        result = pair_persistence_outcome(origin, horizon_hours=horizon_hours,
            assessed_at=assessed_at, forecast_reader=forecast_reader,
            temperature_reader=temperature_reader, action_reader=action_reader)
        status = result['status']
        counts[status if status != 'unavailable' else result['reason']] += 1
        if status == 'paired':
            coverage = result['action_snapshot_coverage']
            pairs.append({'origin': origin.isoformat(),
                          'target': result['target'].isoformat(),
                          'absolute_error_f': round(result['absolute_error_f'], 4),
                          'signed_error_f': round(result['signed_error_f'], 4),
                          'forecast_sha256': result['forecast_sha256'],
                          'action_knowledge': result['action_knowledge'],
                          'action_snapshot_coverage': coverage})
    coverages = [pair['action_snapshot_coverage'] for pair in pairs
                 if pair['action_snapshot_coverage'] is not None]
    return {'scope': 'origin_time_persistence_only_not_model_graduation',
            'start': start.isoformat(), 'end_exclusive': end.isoformat(),
            'assessed_at': assessed_at.isoformat(),
            'step_hours': step_hours, 'horizon_hours': horizon_hours,
            'action_as_of_requested': action_reader is not None,
            'origins': len(origins), 'counts': dict(sorted(counts.items())),
            'paired': len(pairs),
            'action_snapshot_coverage': {
                'paired_origins_with_snapshot': len(coverages),
                'paired_origins_with_all_actions': sum(
                    not coverage['missing_actions'] for coverage in coverages),
                'paired_origins_with_mode': sum(
                    coverage['mode_known'] for coverage in coverages)},
            'persistence_mae_f': (round(sum(pair['absolute_error_f'] for pair in pairs)
                                        / len(pairs), 4) if pairs else None),
            'pairs': pairs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since', required=True)
    parser.add_argument('--until', required=True, help='exclusive origin bound')
    parser.add_argument('--step-hours', type=int, default=6)
    parser.add_argument('--horizon-hours', type=int, default=24)
    parser.add_argument('--actions', action='store_true',
                        help='include restricted journal as-of snapshot; not outcome proof')
    args = parser.parse_args()
    start, end = aware(args.since), aware(args.until)
    now = datetime.now(timezone.utc)
    settings = parse_openhab_jdbc_config(JDBC_CONFIG)
    forecast_factory = lambda: psycopg2.connect(**settings.connect_kwargs,
                                                 connect_timeout=5)
    def temperature_reader(*, stream, targets, assessed_at):
        return collect({'stream': stream, 'targets': targets, 'assessed_at': assessed_at},
                       config_path=CONFIG, policy_path=POLICY)
    action_reader = None
    if args.actions:
        dsn = os.environ.get('THERMAL_DATABASE_URL')
        if not dsn:
            parser.error('--actions requires THERMAL_DATABASE_URL')
        action_factory = lambda: psycopg2.connect(dsn, connect_timeout=5)
        action_reader = lambda *, origin: fetch_origin_actions(action_factory,
                                                               origin=origin)
    result = audit(start, end, step_hours=args.step_hours,
        horizon_hours=args.horizon_hours, assessed_at=now,
        forecast_reader=lambda *, origin, horizon_hours: fetch_origin_forecast(
            forecast_factory, origin=origin, horizon_hours=horizon_hours),
        temperature_reader=temperature_reader, action_reader=action_reader)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
