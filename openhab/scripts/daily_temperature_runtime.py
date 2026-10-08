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
                  'total_seconds', 'maximum_gap_seconds', 'gap_count',
                  'fully_covered', 'history_sha256'}
SITE_ZONE = ZoneInfo('America/Denver')


def _request(request, *, version=1, sensor_epoch=None):
    fields = {'start', 'end', 'assessed_at'}
    if version == 2:
        fields |= {'receipt_version', 'sensor_epoch'}
    if not isinstance(request, dict) or set(request) != fields:
        raise ValueError('closed day request required')
    if version == 2:
        from weather_temperature_evidence import sensor_epoch_id
        if (type(request['receipt_version']) is not int or request['receipt_version'] != 2
                or sensor_epoch_id(request['sensor_epoch']) != sensor_epoch_id(sensor_epoch)):
            raise ValueError('native daily phase differs from request')
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
    return _collect(request, config_path=config_path, policy_path=policy_path, version=1)


def collect_v2(request, *, config_path, policy_path):
    return _collect(request, config_path=config_path, policy_path=policy_path, version=2)


def _native_policy(path):
    from dataclasses import asdict
    from hourly_temperature_runtime import _native_outdoor_policy
    policy, phase = _native_outdoor_policy(path)
    if asdict(policy) != SOURCE_POLICY:
        raise ValueError('reviewed daily outdoor policy required')
    return policy, phase


def _collect(request, *, config_path, policy_path, version):
    from dataclasses import asdict
    import psycopg2
    from hourly_temperature_runtime import read_db_config
    from weather_temperature_config import load_temperature_policies
    from weather_temperature_history import fetch_temperature_window, fetch_temperature_window_v2
    phase = None
    if version == 2:
        policy, phase = _native_policy(policy_path)
    start, end, assessed = _request(request, version=version, sensor_epoch=phase)
    if assessed > datetime.now(timezone.utc):
        raise ValueError('future assessment')
    config = read_db_config(config_path)
    if version == 1:
        policy = load_temperature_policies(policy_path)['outdoor']
    if asdict(policy) != SOURCE_POLICY:
        raise ValueError('reviewed outdoor policy required')
    fetch = fetch_temperature_window_v2 if version == 2 else fetch_temperature_window
    kwargs = {'sensor_epoch': phase} if version == 2 else {}
    summary = fetch(lambda: psycopg2.connect(**config, connect_timeout=3),
        start=start, end=end, assessed_at=assessed, stream='outdoor', policy=policy,
        include_provenance=True, **kwargs)
    result = dict(version=version, request=request, stream='outdoor', source_policy=SOURCE_POLICY,
                  coverage_policy=COVERAGE_POLICY, summary=summary)
    if version == 2:
        result['sensor_epoch'] = phase
    return result


def validate_result(result, request):
    return _validate_result(result, request, version=1, sensor_epoch=None)


def validate_result_v2(result, request, *, sensor_epoch):
    return _validate_result(result, request, version=2, sensor_epoch=sensor_epoch)


def _validate_result(result, request, *, version, sensor_epoch):
    start, end, _ = _request(request, version=version, sensor_epoch=sensor_epoch)
    if (not isinstance(result, dict) or set(result) != {
            'version', 'request', 'stream', 'source_policy', 'coverage_policy', 'summary'} | ({'sensor_epoch'} if version == 2 else set())
            or type(result['version']) is not int or result['version'] != version
            or result['request'] != request or result['stream'] != 'outdoor'
            or result['source_policy'] != SOURCE_POLICY
            or result['coverage_policy'] != COVERAGE_POLICY):
        raise ValueError('unexpected daily evidence metadata')
    summary = result['summary']
    if not isinstance(summary, dict) or set(summary) != SUMMARY_FIELDS | ({'receiptVersion', 'sensorEpoch'} if version == 2 else set()):
        raise ValueError('closed daily summary required')
    if version == 2:
        from weather_temperature_evidence import sensor_epoch_id
        if (sensor_epoch_id(result['sensor_epoch']) != sensor_epoch_id(sensor_epoch)
                or sensor_epoch_id(summary['sensorEpoch']) != sensor_epoch_id(sensor_epoch)
                or type(summary['receiptVersion']) is not int or summary['receiptVersion'] != 2):
            raise ValueError('unexpected daily sensor phase')
    def finite(value):
        return type(value) in (int, float) and math.isfinite(value)
    for key in ('covered_seconds', 'total_seconds', 'maximum_gap_seconds'):
        if not finite(summary[key]): raise ValueError('finite coverage required')
    total, covered, gap = (summary[k] for k in ('total_seconds', 'covered_seconds', 'maximum_gap_seconds'))
    gaps = summary['gap_count']
    if (total != (end-start).total_seconds() or not 0 <= covered <= total
            or gap < 0 or round(gap * 1000000) > round(total * 1000000) - round(covered * 1000000)
            or (gap == 0) != (covered == total)
            or type(gaps) is not int or not 0 <= gaps <= 10001
            or (gaps == 0) != (covered == total)
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
        version = env.get('DAILY_TEMP_RECEIPT_VERSION', '1')
        if version not in ('1', '2'):
            raise ValueError('explicit receipt version required')
        if env.get('DAILY_TEMP_QUALIFIED_ENABLE') != '1':
            raise ValueError('qualified daily opt-in required')
        if env.get('DAILY_TEMP_COVERAGE_POLICY') != COVERAGE_POLICY:
            raise ValueError('explicit complete coverage policy required')
        cutover = _utc(env.get('DAILY_TEMP_EVIDENCE_CUTOVER'))
        start, end, assessed_at = map(_utc, (start, end, assessed_at))
        request = dict(start=start.isoformat(), end=end.isoformat(), assessed_at=assessed_at.isoformat())
        phase = None
        if version == '2':
            _, phase = _native_policy(env.get('DAILY_TEMP_POLICY'))
            request.update(receipt_version=2, sensor_epoch=phase)
        _request(request, version=int(version), sensor_epoch=phase)
        if start < cutover: raise ValueError('pre-cutover day')
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--read-v2' if version == '2' else '--read'],
            input=json.dumps(request), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=30, check=True, env=env)
        if len(child.stdout.encode()) > 8192: raise ValueError('oversize daily evidence')
        decoded = json.loads(child.stdout, object_pairs_hook=_object, parse_constant=_reject_constant)
        result = (validate_result_v2(decoded, request, sensor_epoch=phase) if version == '2'
                  else validate_result(decoded, request))
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
        if sys.argv[1:] not in (['--read'], ['--read-v2']): raise ValueError('read-only invocation required')
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096: raise ValueError('oversize request')
        collector = collect_v2 if sys.argv[1:] == ['--read-v2'] else collect
        result = collector(json.loads(raw, object_pairs_hook=_object, parse_constant=_reject_constant),
            config_path=os.environ.get('DAILY_TEMP_DB_CONFIG'),
            policy_path=os.environ.get('DAILY_TEMP_POLICY'))
        print(json.dumps(result, allow_nan=False, separators=(',', ':')))
    except Exception:
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
