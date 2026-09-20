"""Opt-in qualified hourly learning with a bounded read-only subprocess.

Absent opt-in preserves legacy operation. Invalid activation or unavailable
evidence skips learning without numeric-history fallback. The child cannot
save model state, publish Items, or send notifications.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from weather_temperature_reader import _utc


def read_db_config(path):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ValueError('absolute database config required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o077 or not 1 <= metadata.st_size <= 4096):
            raise ValueError('private owned database config required')
        with os.fdopen(fd, 'rb', closefd=False) as handle:
            raw = handle.read(4097)
    finally:
        os.close(fd)
    if len(raw) > 4096:
        raise ValueError('database config too large')
    from weather_temperature_config import _object
    config = json.loads(raw, object_pairs_hook=_object)
    if not isinstance(config, dict) or set(config) != {'host', 'port', 'dbname', 'user', 'password'}:
        raise ValueError('closed database config required')
    if (config['host'] != '127.0.0.1' or type(config['port']) is not int or config['port'] != 5432
            or config['dbname'] != 'openhab' or config['user'] != 'weather_temperature_reader'
            or not isinstance(config['password'], str) or not 1 <= len(config['password']) <= 256):
        raise ValueError('restricted evidence database required')
    return config


def collect(request, *, config_path, policy_path):
    from weather_temperature_config import load_temperature_policies
    from weather_temperature_history import fetch_temperature_target, TemperatureHistoryUnavailable
    import psycopg2
    if not isinstance(request, dict) or set(request) != {'targets', 'assessed_at'}:
        raise ValueError('closed request required')
    assessed = _utc(request['assessed_at'])
    if assessed > datetime.now(timezone.utc):
        raise ValueError('future assessment')
    targets = request['targets']
    if not isinstance(targets, list) or not 1 <= len(targets) <= 24:
        raise ValueError('bounded targets required')
    parsed = [_utc(t) for t in targets]
    if len(set(parsed)) != len(parsed) or any(t > assessed for t in parsed):
        raise ValueError('unique elapsed targets required')
    config = read_db_config(config_path)
    policy = load_temperature_policies(policy_path)['outdoor']
    if policy.model != 'Fineoffset-WH65B' or policy.sensor_id != 206:
        raise ValueError('approved outdoor identity required')
    results = {}
    for key, target in zip(targets, parsed):
        try:
            value = fetch_temperature_target(
                lambda: psycopg2.connect(**config, connect_timeout=3),
                target=target, assessed_at=assessed, stream='outdoor', policy=policy)
        except TemperatureHistoryUnavailable:
            value = None
        results[key] = None if value is None else {
            k: v.isoformat() if isinstance(v, datetime) else v for k, v in value.items()}
    return results


def score_runtime_hourly(state, now, scorer):
    enabled = os.environ.get('HOURLY_TEMP_QUALIFIED_ENABLE')
    if enabled is None:
        return scorer(state, now)
    try:
        if enabled != '1':
            raise ValueError('invalid explicit activation')
        cutover = os.environ.get('HOURLY_TEMP_EVIDENCE_CUTOVER')
        selected = []
        assessment = None
        def select(*, target, assessed_at):
            nonlocal assessment
            assessment = assessed_at
            selected.append(target.isoformat())
            return None
        preview = {k: deepcopy(state[k]) for k in ('hourly_temp_targets', 'hourly_temp_model') if k in state}
        scorer(preview, now, qualified_reader=select, evidence_cutover=cutover)
        results = {}
        if selected:
            request = {'targets': selected, 'assessed_at': assessment.isoformat()}
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--read'],
                input=json.dumps(request), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=30, check=True)
            if len(result.stdout.encode()) > 32768:
                raise ValueError('oversize evidence result')
            results = json.loads(result.stdout)
            if not isinstance(results, dict) or set(results) != set(selected):
                raise ValueError('unexpected evidence result')
            for evidence in results.values():
                if evidence is not None:
                    if not isinstance(evidence, dict):
                        raise ValueError('invalid evidence result')
                    for key in ('receivedAt', 'storedAt', 'validUntil'):
                        evidence[key] = _utc(evidence[key])
        count = scorer(state, now, qualified_reader=lambda **kw: results.get(kw['target'].isoformat()),
                       evidence_cutover=cutover)
        print(f'hourly qualified evidence: targets={len(selected)} scored={count}')
        return count
    except Exception:
        print('hourly qualified evidence unavailable; learning skipped without fallback', file=sys.stderr)
        return 0


def main():
    try:
        if sys.argv[1:] != ['--read']:
            raise ValueError('read-only worker invocation required')
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            raise ValueError('oversize request')
        results = collect(json.loads(raw), config_path=os.environ.get('HOURLY_TEMP_DB_CONFIG'),
                          policy_path=os.environ.get('HOURLY_TEMP_POLICY'))
        print(json.dumps(results, allow_nan=False, separators=(',', ':')))
    except Exception:
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
