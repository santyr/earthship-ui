"""Read-only, as-issued same-local-clock thermal comparator; never a model."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from math import isfinite
from statistics import median
from zoneinfo import ZoneInfo

from thermal_model.temperature_history import _validate_receipt

POLICY = {'timezone': 'America/Denver', 'required_cycles': 7, 'lookback_days': 31,
          'clock_policy': 'unique_local_clocks_equal_elapsed_duration',
          'estimator': 'current_plus_median_prior_same_clock_changes'}


def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware comparator timestamp required')
    return value.astimezone(timezone.utc)


def temperature(value):
    if type(value) not in (int, float) or not isfinite(value) or not -40 <= value <= 140:
        raise ValueError('bounded comparator temperature required')
    return float(value)


def shifted_clock(value, days):
    """Reject ambiguous/nonexistent clocks, rather than silently selecting a fold."""
    local = utc(value).astimezone(ZoneInfo(POLICY['timezone']))
    naive = local.replace(tzinfo=None) - timedelta(days=days)
    candidates = set()
    for fold in (0, 1):
        proposed = naive.replace(tzinfo=local.tzinfo, fold=fold).astimezone(timezone.utc)
        if proposed.astimezone(local.tzinfo).replace(tzinfo=None) == naive:
            candidates.add(proposed)
    return next(iter(candidates)) if len(candidates) == 1 else None


def compare(*, issue, target, current_f, grid_reader):
    """Use seven latest qualified cycles, all strictly known before issue.

    The reader is called with the original issue as assessment, not today's
    clock. Invalid receipts/partial grids abort; missing receipts withhold a
    cycle. Long windows are split to honor the native 24-hour grid bound.
    No future outcome is used to choose cycles, tune weights or fit parameters.
    """
    issue, target = utc(issue), utc(target)
    current_f = temperature(current_f)
    if not issue < target <= issue + timedelta(hours=49):
        raise ValueError('bounded later comparator target required')
    cycles, exclusions = [], Counter()
    for lag in range(1, POLICY['lookback_days'] + 1):
        origin, end = shifted_clock(issue, lag), shifted_clock(target, lag)
        if origin is None or end is None:
            exclusions['ambiguous_or_nonexistent_local_clock'] += 1
            continue
        if not origin < end < issue:
            exclusions['not_strictly_historical'] += 1
            continue
        if end - origin != target - issue:
            exclusions['elapsed_duration_mismatch'] += 1
            continue
        chunks = [[origin, end]] if end - origin <= timedelta(days=1) else [[origin], [end]]
        receipts = []
        for chunk in chunks:
            rows = grid_reader(chunk, issue)
            if not isinstance(rows, list) or len(rows) != len(chunk):
                raise ValueError('incomplete comparator grid')
            for at, row in zip(chunk, rows):
                if not isinstance(row, (list, tuple)) or len(row) != 2 or utc(row[0]) != at:
                    raise ValueError('comparator grid target mismatch')
                receipt = row[1]
                if receipt is not None:
                    _validate_receipt(receipt, at)
                receipts.append(receipt)
        if any(value is None for value in receipts):
            exclusions['qualified_cycle_unavailable'] += 1
            continue
        start_receipt, end_receipt = receipts
        change = temperature(end_receipt['temperatureF']) - temperature(start_receipt['temperatureF'])
        cycles.append({'lag_days': lag, 'origin_at': origin.isoformat(), 'target_at': end.isoformat(),
            'change_f': change, 'receipts': [{
                key: utc(value).isoformat() if key in ('receivedAt', 'storedAt', 'validUntil') else value
                for key, value in receipt.items()} for receipt in receipts]})
        if len(cycles) == POLICY['required_cycles']:
            break
    evidence = json.dumps(cycles, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    result = {'policy': dict(POLICY), 'qualified_cycles': len(cycles),
              'selected_lag_days': [cycle['lag_days'] for cycle in cycles],
              'exclusions': dict(sorted(exclusions.items())),
              'evidence_sha256': sha256(evidence).hexdigest(), 'prediction_f': None,
              'status': 'insufficient_qualified_history'}
    if len(cycles) == POLICY['required_cycles']:
        predicted = current_f + median(cycle['change_f'] for cycle in cycles)
        if not -40 <= predicted <= 140:
            result['status'] = 'prediction_out_of_bounds'
        else:
            result.update(status='available', prediction_f=predicted)
    return result
