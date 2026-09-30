#!/usr/bin/env python3
"""Read-only, fixed-split daylight/season outdoor forecast residual experiment.

One 08:45 Mountain origin per day and a 24-hour target; no live model writes,
coefficient installation, training labels for actions or production skill claim.
"""

import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'openhab/scripts'), '/home/sat/Solar_PV/analytics/src']

from forecast_solar_ablation import compare, SEASONS  # noqa: E402
from thermal_model.forecast_history import fetch_origin_forecast  # noqa: E402
from thermal_model.temperature_history import _validate_receipt  # noqa: E402
from thermal_temperature_runtime import collect  # noqa: E402

ZONE = ZoneInfo('America/Denver')
SOLAR_ITEMS = ('Sun_Daylight_Duration', 'Sun_SeasonName')


def origins(start_day, end_day, *, now):
    if (type(start_day) is not date or type(end_day) is not date
            or not 1 <= (end_day - start_day).days <= 31
            or now.utcoffset() is None):
        raise ValueError('one through 31 elapsed local dates required')
    result = [datetime.combine(start_day + timedelta(days=i), time(8, 45), ZONE)
              .astimezone(timezone.utc) for i in range((end_day - start_day).days)]
    # Daily local origins crossing a spring-forward transition overlap their
    # 24-hour targets. This experiment deliberately refuses that comparison.
    if (result[-1] + timedelta(hours=24) > now
            or any(b - a < timedelta(hours=24) for a, b in zip(result, result[1:]))):
        raise ValueError('completed nonoverlapping 24-hour targets required')
    return result


def solar_history(get, origin_times):
    result = {}
    for name in SOLAR_ITEMS:
        start = (datetime.combine(origin_times[0].astimezone(ZONE).date(), time.min, ZONE)
                 if name == 'Sun_Daylight_Duration' else origin_times[0] - timedelta(days=366))
        query = urlencode({'serviceId': 'jdbc', 'starttime': start.isoformat(),
                           'endtime': origin_times[-1].isoformat()})
        payload = get('/persistence/items/' + name + '?' + query)
        rows = payload.get('data') if isinstance(payload, dict) else None
        count = str(payload.get('datapoints')) if isinstance(payload, dict) else ''
        limit = 64 if name == 'Sun_Daylight_Duration' else 2048
        if (not isinstance(rows, list) or not len(rows) <= limit
                or payload.get('name') != name or count != str(len(rows))):
            raise ValueError('bounded exact solar archive required')
        parsed = []
        previous = None
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {'time', 'state'}
                    or type(row['time']) is not int or not isinstance(row['state'], str)
                    or not 1 <= len(row['state']) <= 64):
                raise ValueError('solar archive row invalid')
            stamp = datetime.fromtimestamp(row['time'] / 1000, timezone.utc)
            if not start <= stamp <= origin_times[-1] or (previous is not None and stamp <= previous):
                raise ValueError('solar archive ordering invalid')
            previous = stamp
            value = row['state']
            if name == 'Sun_Daylight_Duration':
                # The installed Number:Time Item/JDBC representation is seconds.
                # Other suffixes are refused, not guessed as minutes or hours.
                value = float(value.removesuffix(' s')) / 3600
                if not math.isfinite(value) or not 0 <= value <= 24:
                    raise ValueError('invalid daylight duration')
            elif value not in SEASONS:
                raise ValueError('invalid astronomical season')
            parsed.append((stamp, value))
        result[name] = parsed
    return result


def context_at(history, origin):
    selected = []
    for name in SOLAR_ITEMS:
        rows = [row for row in history[name] if row[0] <= origin]
        if name == 'Sun_Daylight_Duration':
            rows = [row for row in rows if row[0].astimezone(ZONE).date() == origin.astimezone(ZONE).date()]
        if not rows:
            return None
        selected.append(rows[-1])
    digest = sha256(json.dumps([(SOLAR_ITEMS[i], at.isoformat(), value)
        for i, (at, value) in enumerate(selected)], separators=(',', ':'),
        allow_nan=False).encode()).hexdigest()
    return selected[0][1], selected[1][1], digest


def assemble(origin_times, *, history, forecast_reader, temperature_reader, now):
    rows, counts = [], Counter()
    for origin in origin_times:
        solar = context_at(history, origin)
        if solar is None:
            counts['solar_context_unavailable'] += 1
            continue
        forecast = forecast_reader(origin=origin, horizon_hours=24)
        if forecast is None:
            counts['forecast_unavailable'] += 1
            continue
        # Reuse the strict forecast reader's immutable, complete issuance and
        # capture cutoff. The actual qualified outcome is never a forcing input.
        target = origin + timedelta(hours=24)
        if (forecast['origin'] != origin or forecast['horizon_hours'] != 24
                or forecast['issued_at'] > origin or forecast['captured_at'] > origin):
            raise ValueError('future forecast input')
        bracket = [row for row in forecast['rows'] if abs((row['at'] - target).total_seconds()) < 3600]
        if len(bracket) != 2 or not bracket[0]['at'] < target < bracket[1]['at']:
            raise ValueError('exact target hourly bracket required')
        weight = (target - bracket[0]['at']).total_seconds() / 3600
        predicted = bracket[0]['tempF'] * (1 - weight) + bracket[1]['tempF'] * weight
        outcome = temperature_reader(target=target, assessed_at=now)
        if outcome is None:
            counts['outdoor_receipt_unavailable'] += 1
            continue
        _validate_receipt(outcome, target)
        rows.append(dict(origin=origin, target=target, forecast_f=predicted,
            actual_f=outcome['temperatureF'], daylight_hours=solar[0], season=solar[1],
            outcome_stored_at=outcome['storedAt'], forecast_sha256=forecast['rows_sha256'],
            solar_sha256=solar[2], outcome_sha256=outcome['snapshotSha256']))
        counts['paired'] += 1
    return rows, dict(sorted(counts.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-day', type=date.fromisoformat, required=True)
    parser.add_argument('--end-day', type=date.fromisoformat, required=True, help='exclusive')
    parser.add_argument('--split-day', type=date.fromisoformat, required=True,
                        help='fixed first holdout local date; never optimize against this partition')
    args = parser.parse_args()
    if not args.start_day < args.split_day < args.end_day:
        raise ValueError('interior chronological split required')
    now = datetime.now(timezone.utc)
    selected = origins(args.start_day, args.end_day, now=now)
    split = datetime.combine(args.split_day, time(8, 45), ZONE).astimezone(timezone.utc)
    from earthship_energy.db import parse_openhab_jdbc_config
    import openhab_sanity_check as oh
    import psycopg2
    settings = parse_openhab_jdbc_config('/home/sat/.config/hex/energy-power-reader.jdbc')
    if (settings.host, settings.port, settings.dbname, settings.user) != (
            '127.0.0.1', 5432, 'openhab', 'energy_power_reader'):
        raise ValueError('restricted forecast reader required')
    def connection():
        return psycopg2.connect(**settings.connect_kwargs, connect_timeout=3,
                               options='-c default_transaction_read_only=on')
    def temperatures(*, target, assessed_at):
        return collect({'stream': 'outdoor', 'targets': [target], 'assessed_at': assessed_at},
            config_path='/home/sat/.config/hex/weather-temperature-db.json',
            policy_path='/home/sat/.config/hex/weather-temperature-policy.json')[0][1]
    history = solar_history(oh.get, selected)
    rows, counts = assemble(selected, history=history,
        forecast_reader=lambda **kw: fetch_origin_forecast(connection, **kw),
        temperature_reader=temperatures, now=now)
    result = compare(rows, split_at=split) if rows else {
        'status': 'withheld_no_pairs', 'production_changed': False, 'variants': {}}
    result.update(as_of=now.isoformat(), counts=counts, origins=len(selected),
                  horizon_hours=24, origin_local_time='08:45',
                  daylight_feature='origin_day_not_tomorrow',
                  current_production_kalman_scored=False)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('solar-context experiment unavailable; diagnostics withheld', file=sys.stderr)
        raise SystemExit(1) from None
