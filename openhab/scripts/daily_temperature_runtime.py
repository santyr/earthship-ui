"""Qualified completed-day temperature evidence; bounded read-only worker.

Explicit opt-in requires complete receipt coverage, never a numeric fallback.
The worker cannot mutate learned state, publish Items or notify the operator.
"""
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

from weather_temperature_reader import _utc, _object, _reject_constant

COVERAGE_POLICY = 'complete_receipt_coverage_v1'
SOURCE_POLICY = dict(model='Fineoffset-WH65B', sensor_id=206,
                     minimum_f=-40, maximum_f=140, validity_seconds=120)
SUMMARY_FIELDS = {'observed_high_f', 'observed_low_f', 'covered_seconds',
                  'total_seconds', 'maximum_gap_seconds', 'fully_covered', 'history_sha256'}
SITE_ZONE = ZoneInfo('America/Denver')


def _request(request):
    if not isinstance(request, dict) or set(request) != {'start', 'end', 'assessed_at'}:
        raise ValueError('closed day request required')
    start, end, assessed = (_utc(request[k]) for k in ('start', 'end', 'assessed_at'))
    if not start < end <= assessed or end - start > timedelta(hours=25):
        raise ValueError('elapsed bounded window required')
    local_start, local_end = start.astimezone(SITE_ZONE), end.astimezone(SITE_ZONE)
    if (local_end.date() - local_start.date() != timedelta(days=1)
            or any((at.hour, at.minute, at.second, at.microsecond) != (0, 0, 0, 0)
                   for at in (local_start, local_end))):
        raise ValueError('complete Denver calendar day required')
    return start, end, assessed


def collect(request, *, config_path, policy_path):
    from dataclasses import asdict
    import psycopg2
    from hourly_temperature_runtime import read_db_config
    from weather_temperature_config import load_temperature_policies
    from weather_temperature_history import fetch_temperature_window
    start, end, assessed = _request(request)
    if assessed > datetime.now(timezone.utc):
        raise ValueError('future assessment')
    config = read_db_config(config_path)
    policy = load_temperature_policies(policy_path)['outdoor']
    if asdict(policy) != SOURCE_POLICY:
        raise ValueError('reviewed outdoor policy required')
    summary = fetch_temperature_window(lambda: psycopg2.connect(**config, connect_timeout=3),
        start=start, end=end, assessed_at=assessed, stream='outdoor', policy=policy,
        include_provenance=True)
    return dict(version=1, request=request, stream='outdoor', source_policy=SOURCE_POLICY,
                coverage_policy=COVERAGE_POLICY, summary=summary)


def validate_result(result, request):
    start, end, _ = _request(request)
    if (not isinstance(result, dict) or set(result) != {
            'version', 'request', 'stream', 'source_policy', 'coverage_policy', 'summary'}
            or type(result['version']) is not int or result['version'] != 1
            or result['request'] != request or result['stream'] != 'outdoor'
            or result['source_policy'] != SOURCE_POLICY
            or result['coverage_policy'] != COVERAGE_POLICY):
        raise ValueError('unexpected daily evidence metadata')
    summary = result['summary']
    if not isinstance(summary, dict) or set(summary) != SUMMARY_FIELDS:
        raise ValueError('closed daily summary required')
    def finite(value):
        return type(value) in (int, float) and math.isfinite(value)
    for key in ('covered_seconds', 'total_seconds', 'maximum_gap_seconds'):
        if not finite(summary[key]): raise ValueError('finite coverage required')
    total, covered, gap = (summary[k] for k in ('total_seconds', 'covered_seconds', 'maximum_gap_seconds'))
    if (total != (end-start).total_seconds() or not 0 <= covered <= total
            or gap < 0 or round(gap * 1000000) > round(total * 1000000) - round(covered * 1000000)
            or (gap == 0) != (covered == total)
            or type(summary['fully_covered']) is not bool
            or summary['fully_covered'] != (covered == total)):
        raise ValueError('inconsistent coverage')
    high, low = summary['observed_high_f'], summary['observed_low_f']
    if covered == 0:
        if high is not None or low is not None: raise ValueError('unobserved extrema')
    elif not (finite(high) and finite(low) and -40 <= low <= high <= 140):
        raise ValueError('invalid observed extrema')
    if not isinstance(summary['history_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', summary['history_sha256']):
        raise ValueError('history digest required')
    return result


def read_daily_actuals(start, end, assessed_at, environ=None):
    """Return high, low and provenance; explicit bad config/evidence skips both."""
    env = dict(os.environ if environ is None else environ)
    try:
        if env.get('DAILY_TEMP_QUALIFIED_ENABLE') != '1':
            raise ValueError('qualified daily opt-in required')
        if env.get('DAILY_TEMP_COVERAGE_POLICY') != COVERAGE_POLICY:
            raise ValueError('explicit complete coverage policy required')
        cutover = _utc(env.get('DAILY_TEMP_EVIDENCE_CUTOVER'))
        start, end, assessed_at = map(_utc, (start, end, assessed_at))
        request = dict(start=start.isoformat(), end=end.isoformat(), assessed_at=assessed_at.isoformat())
        _request(request)
        if start < cutover: raise ValueError('pre-cutover day')
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--read'],
            input=json.dumps(request), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=30, check=True, env=env)
        if len(child.stdout.encode()) > 8192: raise ValueError('oversize daily evidence')
        result = validate_result(json.loads(child.stdout, object_pairs_hook=_object,
                                           parse_constant=_reject_constant), request)
        summary = result['summary']
        if not summary['fully_covered']:
            print('daily qualified temperatures: incomplete receipt coverage; scoring skipped')
            return None, None, None
        result['cutover'] = cutover.isoformat()
        print('daily qualified temperatures: complete receipt coverage')
        return summary['observed_high_f'], summary['observed_low_f'], result
    except Exception:
        print('daily qualified temperatures unavailable; scoring skipped without fallback', file=sys.stderr)
        return None, None, None


def origin_eligible(prediction, day, evidence, zone, horizon_days):
    """Old origins are not retrospectively labeled qualified after activation."""
    if evidence is None:
        return True  # Legacy path only; unavailable qualified evidence has no actuals.
    try:
        issued = _utc(prediction['temperature_issued_at'])
        return (type(prediction['temperature_origin_version']) is int
                and prediction['temperature_origin_version'] == 1
                and issued >= _utc(evidence['cutover'])
                and issued < _utc(evidence['request']['end'])
                and issued.astimezone(zone).date() + timedelta(days=horizon_days) == day)
    except (KeyError, TypeError, ValueError):
        return False


def record_score(state, day, quantity, prediction, actual, evidence):
    if evidence is None: return
    rows = state.setdefault('daily_temperature_evidence', [])
    rows.append(dict(day=day, quantity=quantity, forecast_issued_at=prediction['temperature_issued_at'],
                     forecast_raw=prediction['lo' if quantity == 'lo' else 'hi'],
                     actual=actual, evidence=evidence))
    state['daily_temperature_evidence'] = rows[-96:]


def forecast_value_eligible(prediction, key, evidence):
    value = prediction.get(key)
    if evidence is None:
        return value is not None  # Preserve the non-opted-in contract.
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def main():
    try:
        if sys.argv[1:] != ['--read']: raise ValueError('read-only invocation required')
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096: raise ValueError('oversize request')
        result = collect(json.loads(raw, object_pairs_hook=_object, parse_constant=_reject_constant),
            config_path=os.environ.get('DAILY_TEMP_DB_CONFIG'),
            policy_path=os.environ.get('DAILY_TEMP_POLICY'))
        print(json.dumps(result, allow_nan=False, separators=(',', ':')))
    except Exception:
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
