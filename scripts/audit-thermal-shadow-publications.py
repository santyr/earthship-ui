#!/usr/bin/env python3
"""Score persisted shadow forecasts against qualified indoor outcomes, read-only.

Near-24-hour targets are the closest published hourly trajectory point within
30 minutes of the issue+24h mark. Results are overlapping observational pairs,
not independent days, causal action evidence, or a graduation decision.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
from math import isfinite
from pathlib import Path
import sys
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402
from thermal_temperature_runtime import collect  # noqa: E402
from thermal_model.temperature_history import _validate_receipt  # noqa: E402

ITEM = 'Thermal_Model_JSON'
CONFIG = '/home/sat/.config/hex/weather-temperature-db.json'
POLICY = '/home/sat/.config/hex/weather-temperature-policy.json'


def aware(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware timestamp required')
    return value.astimezone(timezone.utc)


def finite_temperature(value):
    if type(value) not in (int, float) or not isfinite(value) or not -40 <= value <= 140:
        raise ValueError('finite bounded temperature required')
    return float(value)


def select_pair(row, *, now):
    """Return a mature published pair or a reason; never use future outcomes."""
    now = aware(now)
    if not isinstance(row, dict) or set(row) != {'time', 'state'} or type(row['time']) is not int:
        raise ValueError('unexpected persisted publication row')
    stored = datetime.fromtimestamp(row['time'] / 1000, timezone.utc)
    publication = json.loads(row['state'])
    issue = aware(publication['generatedAt'])
    if issue > stored or stored > now:
        raise ValueError('publication was not available at its recorded time')
    if publication['status'] != 'shadow':
        return None, 'not_shadow'
    ages = publication['provenance']['currentAgeMinutes']
    if not isinstance(ages, dict) or any(type(ages.get(name)) not in (int, float)
            or not isfinite(ages[name]) or not 0 <= ages[name] <= 5 for name in ('air', 'mass')):
        return None, 'stale_initial'
    current = finite_temperature(publication['current']['hallwayF'])
    trajectory = publication['forecast']['trajectory']
    if not isinstance(trajectory, list) or len(trajectory) < 25:
        return None, 'trajectory_unavailable'
    candidates = []
    for point in trajectory:
        at = aware(point['at'])
        drift = abs((at - issue).total_seconds() - 86400)
        if drift <= 1800:
            candidates.append((drift, at, point))
    if not candidates:
        return None, 'near24h_target_unavailable'
    _, target, point = min(candidates, key=lambda entry: (entry[0], entry[1]))
    predicted = finite_temperature(point['hallwayF'])
    low, high = finite_temperature(point['lowF']), finite_temperature(point['highF'])
    if not low <= predicted <= high:
        raise ValueError('published prediction lies outside its interval')
    if target <= stored:
        raise ValueError('forecast target did not follow publication')
    if target > now - timedelta(minutes=5):
        return None, 'outcome_not_yet_due'
    model = publication['model']
    if aware(model['createdAt']) > issue or aware(model['trainedThrough']) > issue:
        raise ValueError('publication used a future model artifact')
    revision = model['codeRevision']
    if not isinstance(revision, str) or len(revision) < 12:
        raise ValueError('model revision missing')
    return {'issue': issue, 'target': target, 'model_f': predicted,
            'interval_low_f': low, 'interval_high_f': high,
            'persistence_f': current, 'revision': revision,
            'confidence': publication['confidence']['grade']}, None


def score(rows, *, now, outcome_reader):
    counts = Counter()
    groups = defaultdict(list)
    for row in rows:
        pair, reason = select_pair(row, now=now)
        if reason:
            counts[reason] += 1
            continue
        receipt = outcome_reader(pair['target'])
        if receipt is None:
            counts['qualified_outcome_unavailable'] += 1
            continue
        _validate_receipt(receipt, pair['target'])
        observed = float(receipt['temperatureF'])
        error = (pair['model_f'] - observed, pair['persistence_f'] - observed,
                 pair['interval_low_f'] <= observed <= pair['interval_high_f'],
                 pair['interval_high_f'] - pair['interval_low_f'])
        groups['overall'].append(error)
        groups['revision:' + pair['revision'][:12]].append(error)
        groups['issue_day:' + pair['issue'].date().isoformat()].append(error)
        counts['scored'] += 1
        counts['confidence:' + str(pair['confidence'])] += 1
    def metrics(errors):
        n = len(errors)
        return {'n': n,
                'model_mae_f': round(sum(abs(x[0]) for x in errors) / n, 4),
                'persistence_mae_f': round(sum(abs(x[1]) for x in errors) / n, 4),
                'model_bias_f': round(sum(x[0] for x in errors) / n, 4),
                'persistence_bias_f': round(sum(x[1] for x in errors) / n, 4),
                'interval_coverage': round(sum(x[2] for x in errors) / n, 4),
                'mean_interval_width_f': round(sum(x[3] for x in errors) / n, 4)}
    return {'scope': 'observational_shadow_publications_not_graduation',
            'publication_rows': len(rows), 'counts': dict(sorted(counts.items())),
            'groups': {key: metrics(value) for key, value in sorted(groups.items())}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since', default='2026-09-20T00:00:00+00:00')
    parser.add_argument('--until', default=None)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    start = aware(args.since)
    end = aware(args.until) if args.until else now
    if not start < end <= now or end - start > timedelta(days=31):
        raise ValueError('bounded elapsed publication window required')
    query = urlencode({'serviceId': 'jdbc', 'starttime': start.isoformat(),
                       'endtime': end.isoformat()})
    rows = oh.get('/persistence/items/' + ITEM + '?' + query)['data']
    if len(rows) > 1000:
        raise ValueError('publication row bound exceeded')
    def outcome(target):
        rows = collect({'stream': 'indoor', 'targets': [target], 'assessed_at': target},
                       config_path=CONFIG, policy_path=POLICY)
        if not isinstance(rows, list) or len(rows) != 1 or rows[0][0] != target:
            raise ValueError('qualified outcome reader returned unexpected target')
        return rows[0][1]
    print(json.dumps(score(rows, now=now, outcome_reader=outcome), sort_keys=True))


if __name__ == '__main__':
    main()
