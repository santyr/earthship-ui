#!/usr/bin/env python3
"""Read-only capture-safe thermal origin/persistence audit, not model scoring.

The forecast and initial temperatures must be available at each origin; a
qualified indoor receipt at the later target supplies the outcome. No observed
future weather or action history is used as forecast forcing. The report makes
no thermal model, action-benefit or graduation claim.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'openhab/scripts'), '/home/sat/Solar_PV/analytics/src']

from earthship_energy.db import parse_openhab_jdbc_config  # noqa: E402
from thermal_model.forecast_history import _utc, fetch_origin_forecast  # noqa: E402
from thermal_model.operational_origin import pair_persistence_outcome  # noqa: E402
from thermal_temperature_runtime import collect  # noqa: E402

JDBC = '/home/sat/.config/hex/energy-power-reader.jdbc'
TEMPERATURE_DB = '/home/sat/.config/hex/weather-temperature-db.json'
TEMPERATURE_POLICY = '/home/sat/.config/hex/weather-temperature-policy.json'
MAX_SPAN = timedelta(days=4)
STEP = timedelta(hours=1)


def summarize(pairs, *, origin_count, horizon_hours):
    counts = Counter(pair.get('reason', pair['status']) for pair in pairs)
    scored = sorted((pair for pair in pairs if pair['status'] == 'paired'),
                    key=lambda pair: pair['origin'])
    selected = []
    previous_target = None
    for pair in scored:
        if previous_target is None or pair['origin'] >= previous_target:
            selected.append(pair)
            previous_target = pair['target']

    def metrics(group):
        if not group:
            return {'count': 0, 'mae_f': None, 'bias_f': None}
        return {'count': len(group),
                'mae_f': round(sum(pair['absolute_error_f'] for pair in group) / len(group), 4),
                'bias_f': round(sum(pair['signed_error_f'] for pair in group) / len(group), 4)}

    return {'status': 'complete', 'scope': 'capture_safe_persistence_baseline_only',
            'horizon_hours': horizon_hours, 'origins': origin_count,
            'counts': dict(sorted(counts.items())),
            'overlapping': metrics(scored), 'nonoverlapping': metrics(selected),
            'action_benefit_proven': False, 'model_scored': False,
            'nonoverlap_policy': 'chronological_origin_at_or_after_prior_target'}


def audit(*, start, end, horizon_hours, now, connection_factory,
          temperature_reader):
    start, end, now = map(_utc, (start, end, now))
    if (start.second or start.microsecond or start.minute % 5
            or end.second or end.microsecond or end.minute % 5
            or not start < end <= now or end - start > MAX_SPAN
            or (end - start) / STEP > 96):
        raise ValueError('bounded aligned origin window required')
    origins = []
    cursor = start
    while cursor < end:
        origins.append(cursor)
        cursor += STEP
    pairs = [pair_persistence_outcome(origin, horizon_hours=horizon_hours,
             assessed_at=now,
             forecast_reader=lambda **kwargs: fetch_origin_forecast(connection_factory, **kwargs),
             temperature_reader=temperature_reader)
             for origin in origins]
    return summarize(pairs, origin_count=len(origins), horizon_hours=horizon_hours)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True, help='UTC-aware first origin')
    parser.add_argument('--end', required=True, help='UTC-aware exclusive end')
    parser.add_argument('--horizon-hours', type=int, choices=(1, 6, 12, 24, 48), default=24)
    args = parser.parse_args()
    settings = parse_openhab_jdbc_config(JDBC)
    if (settings.host, settings.port, settings.dbname, settings.user) != (
            '127.0.0.1', 5432, 'openhab', 'energy_power_reader'):
        raise ValueError('restricted forecast reader required')
    import psycopg2
    def connection():
        return psycopg2.connect(**settings.connect_kwargs, connect_timeout=3,
            options='-c default_transaction_read_only=on -c statement_timeout=3000')
    def temperatures(*, stream, targets, assessed_at):
        return collect({'stream': stream, 'targets': targets, 'assessed_at': assessed_at},
                       config_path=TEMPERATURE_DB, policy_path=TEMPERATURE_POLICY)
    result = audit(start=datetime.fromisoformat(args.start),
        end=datetime.fromisoformat(args.end), horizon_hours=args.horizon_hours,
        now=datetime.now(timezone.utc), connection_factory=connection,
        temperature_reader=temperatures)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
