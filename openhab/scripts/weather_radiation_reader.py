"""Pure, bounded radiation-proxy qualification from original persisted receipts.

No calibrated pyranometer/PV-energy claim, interpolation, numeric fallback,
database access, learning or control. v1 evidence retains diagnostic value but
cannot prove faults overwritten between polls. v2 cumulative counters close that
visibility gap without requiring every valid native packet to be persisted.
"""
from datetime import datetime, timedelta, timezone
from collections import Counter
from hashlib import sha256
import json
import math
from uuid import UUID

from weather_radiation_evidence import CONVERSION, MODELS, RadiationPolicy

MAX_BYTES = 8192
MAX_ROWS = 10000
FIELDS = {'version', 'streamEpoch', 'recordedAt', 'model', 'sourceModel',
          'sensorId', 'field', 'status', 'reason', 'timeBasis', 'radioDecodedAt',
          'receivedAt', 'validUntil', 'lightLux', 'irradianceWm2', 'conversion', 'sequence'}
INVALID_REASONS = {'model_ambiguous', 'identity_missing_or_ambiguous', 'lux_invalid',
    'conversion_missing_or_mismatched', 'source_time_invalid', 'source_time_future',
    'source_time_expired', 'source_time_regressed', 'source_time_conflict', 'expired'}


def _utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('aware timestamp required')
    return value.astimezone(timezone.utc)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _constant(_):
    raise ValueError('nonfinite JSON')


def _counter(value):
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise ValueError('bounded integer counter required')
    return value


def _snapshot(raw, stored, policy):
    if not isinstance(raw, str) or len(raw.encode()) > MAX_BYTES:
        raise ValueError('bounded original JSON required')
    e = json.loads(raw, object_pairs_hook=_unique, parse_constant=_constant)
    if not isinstance(e, dict) or type(e.get('version')) is not int or e['version'] not in (1, 2):
        raise ValueError('unsupported radiation envelope')
    keys = {'version', 'streamEpoch', 'sequence', 'record'}
    if e['version'] == 2:
        keys.add('faultCount')
    if set(e) != keys or not isinstance(e['streamEpoch'], str) or str(UUID(e['streamEpoch'])) != e['streamEpoch']:
        raise ValueError('closed envelope and canonical epoch required')
    seq = _counter(e['sequence'])
    faults = None if e['version'] == 1 else _counter(e['faultCount'])
    if faults is not None and faults > seq:
        raise ValueError('inconsistent fault counter')
    r = e['record']
    if r is None:
        if seq != 0 or faults not in (None, 0):
            raise ValueError('missing source record')
        return e, None
    if not isinstance(r, dict) or set(r) != FIELDS:
        raise ValueError('closed radiation record required')
    if (type(r['version']) is not int or r['version'] != 1 or r['streamEpoch'] != e['streamEpoch']
            or type(r['sequence']) is not int or r['sequence'] != seq or seq == 0
            or r['model'] != 'Fineoffset-WH65B' or type(r['sensorId']) is not int
            or r['sensorId'] != policy.sensor_id or r['field'] != 'light_lux'
            or r['timeBasis'] != 'radio_decode_utc' or r['conversion'] != CONVERSION):
        raise ValueError('radiation identity or conversion mismatch')
    recorded = _utc(r['recordedAt'])
    if recorded > stored:
        raise ValueError('future receiver record')
    if r['status'] == 'invalid':
        if (r['reason'] not in INVALID_REASONS
                or any(r[k] is not None for k in ('receivedAt', 'validUntil', 'lightLux', 'irradianceWm2'))
                or faults == 0):
            raise ValueError('invalid fault barrier')
        return e, None
    if r['status'] != 'valid' or r['reason'] != 'accepted' or r['sourceModel'] not in MODELS:
        raise ValueError('accepted native source required')
    received, decoded, until = map(_utc, (r['receivedAt'], r['radioDecodedAt'], r['validUntil']))
    lux, watts = r['lightLux'], r['irradianceWm2']
    if (received != recorded or decoded.microsecond != 0
            or decoded > received + timedelta(seconds=5)
            or until != min(received, decoded) + timedelta(seconds=policy.validity_seconds)
            or received >= until or faults is not None and faults >= seq
            or type(lux) not in (int, float) or not math.isfinite(lux) or not 0 <= lux <= 200000
            or type(watts) not in (int, float) or not math.isfinite(watts)
            or watts != round(min(lux / CONVERSION['luxPerWm2'], CONVERSION['maximumWm2']), 2)):
        raise ValueError('native receipt time, value or conversion invalid')
    return e, dict(irradianceWm2=watts, lightLux=lux, radioDecodedAt=decoded,
        receivedAt=received, validUntil=until, storedAt=stored, streamEpoch=e['streamEpoch'],
        sequence=seq, faultCount=faults, fault_visibility='unverified' if faults is None else 'verified',
        timeBasis='radio_decode_utc', snapshotSha256=sha256(raw.encode()).hexdigest())


def _rows(rows):
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError('bounded complete row list required')
    result = []
    for stored, raw in rows:
        stored = _utc(stored)
        if result and stored <= result[-1][0]:
            if (stored, raw) == result[-1]:
                continue
            raise ValueError('unordered or conflicting persistence rows')
        result.append((stored, raw))
    return result


def _timeline(rows, policy):
    timeline, uncertainties = [], []
    epoch = None
    seen_epochs = set()
    high_source = None
    high_sequence = high_faults = 0
    last_record = None
    previous_at = None
    previous_source_at = None
    barrier = None
    for stored, raw in rows:
        flags = set()
        candidate = None
        try:
            e, candidate = _snapshot(raw, stored, policy)
            new_epoch = e['streamEpoch'] != epoch
            if new_epoch:
                if e['streamEpoch'] in seen_epochs:
                    raise ValueError('closed receiver epoch reappeared')
                if epoch is not None:
                    flags.add('restart')
                    barrier = previous_at
                epoch = e['streamEpoch']
                seen_epochs.add(epoch)
                high_sequence = high_faults = 0
                last_record = None
            seq, faults = e['sequence'], e.get('faultCount')
            if seq < high_sequence or faults is not None and faults < high_faults:
                raise ValueError('counter regression')
            if faults is not None and faults > high_faults and previous_at is not None and not new_epoch:
                flags.add('source_fault')
            if seq == high_sequence and last_record is not None and e['record'] != last_record:
                if candidate is not None or e['record'] is None or e['record']['reason'] != 'expired':
                    raise ValueError('same-sequence source conflict')
            if candidate is not None:
                duplicate = seq == high_sequence and e['record'] == last_record
                if duplicate and faults is not None and faults != high_faults:
                    raise ValueError('duplicate native receipt cannot change fault count')
                if (not duplicate and high_source is not None and candidate['radioDecodedAt'] <= high_source
                        or barrier is not None and (candidate['receivedAt'] <= barrier
                                                   or candidate['radioDecodedAt'] <= barrier)):
                    raise ValueError('source replay across barrier')
                high_source = candidate['radioDecodedAt']
            high_sequence = seq
            high_faults = high_faults if faults is None else faults
            last_record = e['record']
            if candidate is None:
                flags.add('unavailable')
                barrier = stored
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            flags.add('malformed_or_replayed')
            candidate = None
            barrier = stored
        if previous_at is not None and flags & {'source_fault', 'restart'}:
            uncertainties.append((previous_source_at or previous_at, stored, flags & {'source_fault', 'restart'}))
        timeline.append((stored, candidate, flags))
        previous_at = stored
        previous_source_at = None if candidate is None else min(candidate['receivedAt'], candidate['radioDecodedAt'])
    return timeline, uncertainties


def _validate(*, start, end, assessed_at, history_start, cutover, policy):
    if not isinstance(policy, RadiationPolicy):
        raise ValueError('explicit radiation policy required')
    start, end, assessed, history, cutover = map(_utc, (start, end, assessed_at, history_start, cutover))
    if not cutover <= start <= end <= assessed or end - start > timedelta(hours=25):
        raise ValueError('elapsed post-cutover window required')
    if history > start - timedelta(seconds=policy.validity_seconds):
        raise ValueError('complete query and original carry required')
    return start, end


def select_radiation_at(rows, *, target, assessed_at, history_start, cutover, policy):
    """As-of diagnostic; never uses a post-target snapshot or renews native expiry."""
    try:
        target, _ = _validate(start=target, end=target, assessed_at=assessed_at,
            history_start=history_start, cutover=cutover, policy=policy)
        timeline, _ = _timeline([(at, raw) for at, raw in _rows(rows) if at <= target], policy)
        evidence = timeline[-1][1] if timeline else None
        return (dict(evidence) if evidence is not None
                and min(evidence['storedAt'], evidence['receivedAt'], evidence['radioDecodedAt']) >= _utc(cutover)
                and evidence['radioDecodedAt'] <= target < evidence['validUntil'] else None)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return None


def select_radiation_window(rows, *, start, end, assessed_at, history_start, cutover, policy):
    """Half-open elapsed exposure-proxy window, not calibrated physical energy.

    Every original failure remains a barrier. Hidden v2 faults conservatively
    invalidate the interval since the previous persisted snapshot. A closing
    closing receipt up to one TTL after end reveals boundary faults but contributes
    no future value. Its native observation must reach/past end. Missing closing
    evidence cannot prove a clean complete window.
    Integral uses persisted sample-and-hold; it does not recover unpersisted
    valid readings. Only clean, fully covered v2 windows expose a total.
    """
    start, end = _validate(start=start, end=end, assessed_at=assessed_at,
        history_start=history_start, cutover=cutover, policy=policy)
    if start == end:
        raise ValueError('positive elapsed window required')
    normalized = _rows(rows)
    latest = min(_utc(assessed_at), end + timedelta(seconds=policy.validity_seconds))
    if any(at > latest for at, _ in normalized):
        raise ValueError('rows outside bounded elapsed query')
    timeline, uncertainties = _timeline(normalized, policy)
    cutover = _utc(cutover)
    uncertainty_events = sorted(
        [(a, 1, flags) for a, _, flags in uncertainties]
        + [(b, -1, flags) for _, b, flags in uncertainties], key=lambda row: row[0])
    boundaries = sorted({start, end, *(at for at, _, _ in timeline if start < at < end),
        *(e['validUntil'] for _, e, _ in timeline if e is not None and start < e['validUntil'] < end),
        *(e['radioDecodedAt'] for _, e, _ in timeline if e is not None and start < e['radioDecodedAt'] < end),
        *(at for at, _, _ in uncertainty_events if start < at < end)})
    covered = integral = gap = max_gap = 0.0
    gaps = index = 0
    evidence = None
    reasons = set()
    if not any(at >= end and e is not None
               and min(e['radioDecodedAt'], e['receivedAt']) >= end
               and e['fault_visibility'] == 'verified' for at, e, _ in timeline):
        reasons.add('closing_receipt_unverified')
    low = high = None
    active_uncertainty = Counter()
    uncertainty_index = 0
    for left, right in zip(boundaries, boundaries[1:]):
        while index < len(timeline) and timeline[index][0] <= left:
            at, evidence, flags = timeline[index]
            if at >= start:
                reasons.update(flags)
            index += 1
        # Sweep once rather than rescanning every fault interval at every sample.
        while uncertainty_index < len(uncertainty_events) and uncertainty_events[uncertainty_index][0] <= left:
            _, delta, flags = uncertainty_events[uncertainty_index]
            for flag in flags:
                active_uncertainty[flag] += delta
            uncertainty_index += 1
        uncertain = {flag for flag, count in active_uncertainty.items() if count > 0}
        reasons.update(uncertain)
        valid = (evidence is not None and evidence['radioDecodedAt'] <= left < evidence['validUntil']
                 and min(evidence['storedAt'], evidence['receivedAt'], evidence['radioDecodedAt']) >= cutover
                 and not uncertain)
        duration = (right - left).total_seconds()
        if valid:
            covered += duration
            integral += evidence['irradianceWm2'] * duration / 3600
            high = evidence['irradianceWm2'] if high is None else max(high, evidence['irradianceWm2'])
            low = evidence['irradianceWm2'] if low is None else min(low, evidence['irradianceWm2'])
            if evidence['fault_visibility'] != 'verified':
                reasons.add('legacy_fault_visibility_unverified')
            gap = 0.0
        else:
            if gap == 0:
                gaps += 1
            gap += duration
            max_gap = max(max_gap, gap)
    total = (end - start).total_seconds()
    if covered != total:
        reasons.add('coverage_gap')
    clean = covered == total and not reasons
    return dict(status='ok' if clean else 'partial', reasons=sorted(reasons),
        covered_seconds=covered, total_seconds=total, gap_count=gaps, maximum_gap_seconds=max_gap,
        fully_covered=covered == total, irradiance_wh_m2=integral if clean else None,
        covered_irradiance_wh_m2=integral, observed_high_w_m2=high, observed_low_w_m2=low,
        time_basis='radio_decode_utc', integral_basis='persisted_sample_and_hold_lux_proxy',
        source_rows=len(normalized), history_sha256=sha256(json.dumps(
            [[at.isoformat(), raw] for at, raw in normalized], ensure_ascii=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest())
