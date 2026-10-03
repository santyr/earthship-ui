"""Default-off receipt-only radiation input for thermal shadow forecasts.

One bounded read-only subprocess/connection for the current native receipt.
No training, historical qualification, numeric fallback or source activation.
"""
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from uuid import UUID

from weather_radiation_evidence import CONVERSION, RadiationPolicy
from weather_radiation_reader import _utc, _unique, _constant

POLICY = RadiationPolicy(sensor_id=206, validity_seconds=120)
TIME_FIELDS = {'radioDecodedAt', 'receivedAt', 'storedAt', 'validUntil'}
RECEIPT_FIELDS = TIME_FIELDS | {'irradianceWm2', 'lightLux', 'streamEpoch',
    'sequence', 'faultCount', 'fault_visibility', 'timeBasis', 'snapshotSha256'}


def read_db_config(path):
    """Reuse only the existing private, explicitly restricted local JDBC role."""
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ValueError('absolute database config required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or not 1 <= info.st_size <= 4096):
            raise ValueError('private owned database config required')
        with os.fdopen(fd, 'rb', closefd=False) as handle:
            raw = handle.read(4097)
    finally:
        os.close(fd)
    if len(raw) > 4096:
        raise ValueError('bounded database config required')
    values = {}
    for line in raw.decode('utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not separator or key not in {'url', 'user', 'password'} or key in values:
            raise ValueError('closed unambiguous database configuration required')
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        values[key] = value
    if (set(values) != {'url', 'user', 'password'}
            or values['url'] != 'jdbc:postgresql://127.0.0.1:5432/openhab'
            or values['user'] != 'energy_power_reader'
            or not 1 <= len(values['password']) <= 256):
        raise ValueError('restricted local evidence database required')
    return dict(host='127.0.0.1', port=5432, dbname='openhab',
                user='energy_power_reader', password=values['password'])


def _validate_receipt(value, *, target, cutover):
    if not isinstance(value, dict) or set(value) != RECEIPT_FIELDS:
        raise ValueError('closed native radiation receipt required')
    value = {key: _utc(val) if key in TIME_FIELDS else val for key, val in value.items()}
    decoded, received, stored, expires = (value[key] for key in (
        'radioDecodedAt', 'receivedAt', 'storedAt', 'validUntil'))
    lux, watts = value['lightLux'], value['irradianceWm2']
    if (not cutover <= min(decoded, received, stored)
            or not received <= stored <= target < expires or decoded > target
            or decoded.microsecond != 0 or decoded > received+timedelta(seconds=5)
            or expires != min(decoded, received)+timedelta(seconds=POLICY.validity_seconds)
            or value['fault_visibility'] != 'verified' or value['timeBasis'] != 'radio_decode_utc'
            or type(value['sequence']) is not int or not 1 <= value['sequence'] <= 2**53-1
            or type(value['faultCount']) is not int or not 0 <= value['faultCount'] < value['sequence']
            or str(UUID(value['streamEpoch'])) != value['streamEpoch']
            or not isinstance(value['snapshotSha256'], str)
            or re.fullmatch('[0-9a-f]{64}', value['snapshotSha256']) is None
            or type(lux) not in (int, float) or not math.isfinite(lux) or not 0 <= lux <= 200000
            or type(watts) not in (int, float) or not math.isfinite(watts)
            or watts != round(min(lux/CONVERSION['luxPerWm2'], CONVERSION['maximumWm2']), 2)):
        raise ValueError('unqualified native radiation receipt')
    return value


def configured_shadow_radiation(now, environ=None):
    env = dict(os.environ if environ is None else environ)
    enabled = env.get('THERMAL_RADIATION_SHADOW_QUALIFIED_ENABLE')
    if enabled is None:
        return None
    try:
        if enabled != '1':
            raise ValueError('explicit radiation activation required')
        now = _utc(now)
        cutover = _utc(env.get('THERMAL_RADIATION_EVIDENCE_CUTOVER'))
        if cutover > now:
            raise ValueError('elapsed radiation cutover required')
        for key in ('THERMAL_RADIATION_DB_CONFIG', 'THERMAL_RADIATION_POLICY'):
            if not env.get(key) or not os.path.isabs(env[key]):
                raise ValueError('absolute evidence configuration required')
        request = dict(target=now.isoformat(), assessed_at=now.isoformat(), cutover=cutover.isoformat())
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--read'],
            input=json.dumps(request), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=30, check=True, env=env)
        if len(result.stdout.encode()) > 262144:
            raise ValueError('oversize radiation result')
        rows = json.loads(result.stdout, object_pairs_hook=_unique, parse_constant=_constant)
        if (not isinstance(rows, list) or len(rows) != 1
                or not isinstance(rows[0], list) or len(rows[0]) != 2 or _utc(rows[0][0]) != now):
            raise ValueError('exact current radiation target required')
        receipt = _validate_receipt(rows[0][1], target=now, cutover=cutover)
        return dict(history=(), current=dict(at=receipt['radioDecodedAt'],
            value=receipt['irradianceWm2'], validUntil=receipt['validUntil'], sourceEvidence=receipt))
    except Exception:
        raise ValueError('qualified shadow radiation evidence unavailable') from None


def validate_shadow_radiation_expiry(current, at):
    reading = (current or {}).get('radiation', {})
    if 'validUntil' in reading and not _utc(reading['at']) <= _utc(at) < _utc(reading['validUntil']):
        raise ValueError('expired current radiation receipt')


def collect(request, *, config_path, policy_path):
    import psycopg2
    from weather_radiation_config import load_radiation_policy
    from weather_radiation_history import fetch_radiation_grid
    if not isinstance(request, dict) or set(request) != {'target', 'assessed_at', 'cutover'}:
        raise ValueError('closed radiation worker request required')
    target, assessed, cutover = map(_utc, (request['target'], request['assessed_at'], request['cutover']))
    if not cutover <= target <= assessed <= datetime.now(timezone.utc):
        raise ValueError('elapsed post-cutover radiation target required')
    policy = load_radiation_policy(policy_path)
    if policy != POLICY:
        raise ValueError('approved radiation identity and expiry required')
    if os.environ.get('PGSERVICE') or os.environ.get('PGSERVICEFILE'):
        raise ValueError('implicit database services refused')
    config = read_db_config(config_path)
    return fetch_radiation_grid(lambda: psycopg2.connect(**config, hostaddr='127.0.0.1',
        connect_timeout=3, options='-c default_transaction_read_only=on'),
        targets=[target], assessed_at=assessed, cutover=cutover, policy=policy)


def main():
    try:
        if sys.argv[1:] != ['--read']:
            raise ValueError('read-only worker invocation required')
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            raise ValueError('bounded radiation request required')
        rows = collect(json.loads(raw, object_pairs_hook=_unique, parse_constant=_constant),
            config_path=os.environ.get('THERMAL_RADIATION_DB_CONFIG'),
            policy_path=os.environ.get('THERMAL_RADIATION_POLICY'))
        print(json.dumps(rows, default=lambda value: value.isoformat(), allow_nan=False,
                         separators=(',', ':')))
    except Exception:
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
