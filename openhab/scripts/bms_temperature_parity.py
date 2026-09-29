"""Read-only parity assessment for the change-only BMS Fahrenheit scaler.

This checks values only after actual native raw-temperature changes. An old
timestamp on an unchanged Fahrenheit Item is not itself evidence of failure.
The assessment is diagnostic and never authorizes Energy-quality publication.
"""

from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from math import floor, isfinite

from bms_aux_evidence import parse_bms_aux_receipt, qualify_bms_aux_day


SETTLE = timedelta(seconds=30)
MAX_DERIVED_ROWS = 5000


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('aware BMS parity timestamp required')
    return value.astimezone(timezone.utc)


def expected_fahrenheit(raw):
    """Match JavaScript Math.round(... * 10) / 10, including negative ties."""
    if type(raw) is not int or not 23300 <= raw <= 33855:
        raise ValueError('native temperature out of bounds')
    value = (raw * 0.01 - 273) * 9 / 5 + 32
    return floor(value * 10 + 0.5) / 10


def assess_bms_temperature_parity(local_date, *, as_of, cutover, observations,
                                  derived_points, site_timezone='America/Denver'):
    """Compare stable source transitions to the as-of derived Item value.

    `observations` are bounded, chronological JDBC auxiliary receipt rows.
    `derived_points` include at most one pre-day carry and in-day change-only
    Fahrenheit rows. A source transition too near another transition, a
    barrier, expiry or day-end is not scored.
    """
    rows = tuple(observations)
    day = qualify_bms_aux_day(local_date, as_of=as_of, cutover=cutover,
                              observations=rows, site_timezone=site_timezone)
    start, end = datetime.fromisoformat(day['window_start']), datetime.fromisoformat(day['window_end'])
    if len(derived_points) > MAX_DERIVED_ROWS:
        raise ValueError('derived temperature row budget exceeded')
    times, values = [], []
    for at, value in derived_points:
        at = _utc(at)
        if (not at < end or times and at <= times[-1]
                or type(value) not in (int, float) or not -50 <= value <= 100
                or not isfinite(value)):
            raise ValueError('invalid derived temperature series')
        times.append(at)
        values.append(float(value))

    receipts = [parse_bms_aux_receipt(raw, persisted) for persisted, raw in rows]
    transitions = []
    prior_value = None
    prior_epoch = None
    for receipt in receipts:
        field = receipt.fields['battery.temperature_raw']
        if receipt.epoch != prior_epoch or field.status != 'valid':
            prior_value = None
        if field.status == 'valid':
            if prior_value is not None and field.value != prior_value:
                transitions.append((receipt.persisted_at, field.value,
                                    field.valid_until))
            prior_value = field.value
        prior_epoch = receipt.epoch

    # A later source receipt can supersede a candidate before the scaler has
    # settled. Check every receipt, not only distinct-value transitions.
    receipt_times = [receipt.persisted_at for receipt in receipts]
    checked, skipped, mismatches = 0, 0, []
    for at, raw, valid_until in transitions:
        checkpoint = at + SETTLE
        index = bisect_right(receipt_times, at)
        next_receipt = receipt_times[index] if index < len(receipt_times) else end
        if (at < start or checkpoint >= min(next_receipt, valid_until, end)):
            skipped += 1
            continue
        index = bisect_right(times, checkpoint) - 1
        expected = expected_fahrenheit(raw)
        actual = values[index] if index >= 0 else None
        checked += 1
        # The live scaler posts only at >=0.2 F delta, and the Item is rounded
        # to a tenth. A held Item within 0.2 F is therefore consistent.
        if actual is None or abs(actual - expected) > 0.201:
            mismatches.append({'at': at.isoformat(), 'expected_f': expected,
                               'actual_f': actual})
    return {
        'local_date': day['local_date'],
        'source_item': day['source_item'],
        'source_temperature_quality': day['fields']['battery.temperature_raw']['quality'],
        'source_temperature_coverage': day['fields']['battery.temperature_raw']['coverage'],
        'raw_transitions': len(transitions),
        'checked_transitions': checked,
        'skipped_transitions': skipped,
        'mismatches': mismatches,
        'status': ('mismatch' if mismatches else 'observed_consistent' if checked
                   else 'insufficient_changes'),
    }
