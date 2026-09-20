"""Opt-in, bounded read-only temperature worker for thermal history ingestion."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from thermal_model.temperature_history import QualifiedTemperatureHistory, STREAMS, POLICY, _validate_receipt
from weather_temperature_reader import _utc


def configured_history(legacy_reader, now, environ=None):
    env = dict(os.environ if environ is None else environ)
    enabled = env.get('THERMAL_TEMP_QUALIFIED_ENABLE')
    if enabled is None:
        return legacy_reader
    if enabled != '1':
        raise ValueError('explicit qualified thermal history is unavailable')
    cutover = _utc(env.get('THERMAL_TEMP_EVIDENCE_CUTOVER'))
    read = _configured_grid_reader(env, budget=900)
    return QualifiedTemperatureHistory(legacy_reader, read, cutover=cutover, assessed_at=now)


def _configured_grid_reader(env, *, budget):
    for key in ('THERMAL_TEMP_DB_CONFIG', 'THERMAL_TEMP_POLICY'):
        if not env.get(key) or not os.path.isabs(env[key]):
            raise ValueError('explicit absolute thermal evidence configuration required')
    deadline = time.monotonic() + budget
    def read(stream, targets, assessed_at):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('thermal evidence read budget exceeded')
        request = dict(stream=stream, targets=[at.isoformat() for at in targets],
                       assessed_at=assessed_at.isoformat())
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--read'],
            input=json.dumps(request), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=min(30, remaining), check=True, env=env)
        if len(result.stdout.encode()) > 262144:
            raise ValueError('oversize thermal temperature result')
        rows = json.loads(result.stdout)
        if not isinstance(rows, list) or len(rows) != len(targets):
            raise ValueError('incomplete thermal temperature result')
        return [(_utc(at), None if value is None else {
            key: _utc(val) if key in ('receivedAt','storedAt','validUntil') else val
            for key, val in value.items()}) for at, value in rows]
    return read


def configured_shadow_temperatures(now, environ=None):
    env = dict(os.environ if environ is None else environ)
    enabled = env.get('THERMAL_TEMP_SHADOW_QUALIFIED_ENABLE')
    if enabled is None:
        return None
    if enabled != '1':
        raise ValueError('explicit qualified shadow temperatures unavailable')
    try:
        return shadow_temperatures(now, _configured_grid_reader(env, budget=90))
    except Exception:
        raise ValueError('qualified shadow temperature evidence unavailable') from None


def shadow_temperatures(now, grid_reader):
    """Receipt-only trailing history and current observations; no legacy carry."""
    now = _utc(now)
    floor = now.replace(minute=now.minute//5*5, second=0, microsecond=0)
    targets = [floor-timedelta(minutes=5*i) for i in reversed(range(288))]
    if targets[-1] != now:
        targets.append(now)
    result = {}
    for role, (stream, _, _) in STREAMS.items():
        rows = grid_reader(stream, targets, now)
        if not isinstance(rows, list) or len(rows) != len(targets):
            raise ValueError('incomplete shadow receipt history')
        history = []
        latest = None
        for target, (at, value) in zip(targets, rows):
            if _utc(at) != target:
                raise ValueError('shadow receipt target mismatch')
            if value is not None:
                _validate_receipt(value, target)
            # The exact current target is handled separately, not relabeled
            # to a historical bucket or fabricated sensor receipt timestamp.
            if target < now:
                history.append((target, float('nan') if value is None else value['temperatureF']))
            else:
                latest = value
        if latest is None:
            raise ValueError(f'unqualified current {role} temperature receipt')
        result[role] = dict(history=tuple(history), current={
            'at': _utc(latest['receivedAt']), 'value': latest['temperatureF'],
            'validUntil': _utc(latest['validUntil'])})
    return result


def validate_shadow_receipt_expiry(current, at):
    for role in STREAMS:
        reading = (current or {}).get(role, {})
        if 'validUntil' in reading and not _utc(reading['at']) <= _utc(at) < _utc(reading['validUntil']):
            raise ValueError(f'expired current {role} temperature receipt')


def collect(request, *, config_path, policy_path):
    import psycopg2
    from hourly_temperature_runtime import read_db_config
    from weather_temperature_config import load_temperature_policies
    from weather_temperature_history import fetch_temperature_grid
    if not isinstance(request, dict) or set(request) != {'stream','targets','assessed_at'}:
        raise ValueError('closed thermal evidence request required')
    expected = next((identity for identity in STREAMS.values() if identity[0] == request['stream']), None)
    if expected is None:
        raise ValueError('approved thermal stream required')
    assessed = _utc(request['assessed_at'])
    if assessed > datetime.now(timezone.utc):
        raise ValueError('future thermal assessment')
    policy = load_temperature_policies(policy_path)[expected[0]]
    if asdict(policy) != dict(model=expected[1], sensor_id=expected[2], **POLICY):
        raise ValueError('approved thermal identity and expiry policy required')
    config = read_db_config(config_path)
    return fetch_temperature_grid(lambda: psycopg2.connect(**config, connect_timeout=3),
        targets=request['targets'], assessed_at=assessed, stream=expected[0], policy=policy)


def main():
    try:
        if sys.argv[1:] != ['--read']:
            raise ValueError('read-only worker invocation required')
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            raise ValueError('oversize thermal request')
        rows = collect(json.loads(raw), config_path=os.environ.get('THERMAL_TEMP_DB_CONFIG'),
                       policy_path=os.environ.get('THERMAL_TEMP_POLICY'))
        print(json.dumps(rows, default=lambda val: val.isoformat(), allow_nan=False,
                         separators=(',', ':')))
    except Exception:
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
