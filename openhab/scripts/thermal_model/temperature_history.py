"""Explicit legacy/receipt cutover for thermal five-minute temperature inputs."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import math
import re
from uuid import UUID

from weather_temperature_reader import _utc
from .schema import THERMAL_ITEMS

STEP = timedelta(minutes=5)
STREAMS = {'air': ('indoor', 'Fineoffset-WH32B', 235),
           'mass': ('north_wall', 'AmbientWeather-WH31E', 193),
           'outdoor': ('outdoor', 'Fineoffset-WH65B', 206)}
POLICY = {'minimum_f': -40, 'maximum_f': 140, 'validity_seconds': 120}


def _ceil(value):
    floor = value.replace(minute=value.minute // 5 * 5, second=0, microsecond=0)
    return floor if floor == value else floor + STEP


class QualifiedTemperatureHistory:
    """Callable series reader; grid_reader failures abort training, never fall back.

    grid_reader(stream, targets, assessed_at) returns qualified metadata pairs.
    Every post-cutover target is emitted, including NaN barriers. Other roles
    retain their existing source contract and are never called receipt-qualified.
    """
    def __init__(self, legacy_reader, grid_reader, *, cutover, assessed_at):
        self.cutover, self.assessed_at = _utc(cutover), _utc(assessed_at)
        if self.cutover != _ceil(self.cutover) or self.cutover > self.assessed_at:
            raise ValueError('elapsed five-minute-aligned cutover required')
        self.legacy_reader, self.grid_reader = legacy_reader, grid_reader
        self._evidence = {}
        self._window = None

    def __call__(self, item, start, end):
        start, end = _utc(start), _utc(end)
        if not start < end <= self.assessed_at or end - start > timedelta(days=401):
            raise ValueError('bounded elapsed training window required')
        if self._window is not None and self._window != (start, end):
            raise ValueError('reader cannot mix training windows')
        self._window = (start, end)
        role = next((role for role in STREAMS if THERMAL_ITEMS[role] == item), None)
        if role is None:
            return self.legacy_reader(item, start, end)
        stream, model, sensor_id = STREAMS[role]
        legacy_end = min(end, self.cutover)
        points = list(self.legacy_reader(item, start, legacy_end)) if start < legacy_end else []
        if any(not start <= _utc(at) < legacy_end for at, _ in points):
            raise ValueError('legacy reader crossed its cutover boundary')
        evidence = dict(stream=stream, model=model, sensor_id=sensor_id, policy=dict(POLICY),
                        legacy_points=len(points), targets=0, qualified=0, missing=0)
        digest = sha256()
        cursor = _ceil(max(start, self.cutover))
        while cursor < end:
            targets = []
            while len(targets) < 288 and cursor < end:
                targets.append(cursor)
                cursor += STEP
            rows = self.grid_reader(stream, targets, self.assessed_at)
            if not isinstance(rows, list) or len(rows) != len(targets):
                raise ValueError('incomplete qualified grid')
            for target, row in zip(targets, rows):
                at, value = row
                if _utc(at) != target:
                    raise ValueError('qualified grid target mismatch')
                if value is not None:
                    _validate_receipt(value, target)
                canonical = None if value is None else {
                    key: _utc(val).isoformat() if key in ('receivedAt', 'storedAt', 'validUntil') else val
                    for key, val in value.items()}
                digest.update((json.dumps([target.isoformat(), canonical], sort_keys=True,
                                          separators=(',', ':'), allow_nan=False) + '\n').encode())
                points.append((target, math.nan if value is None else float(value['temperatureF'])))
                evidence['targets'] += 1
                evidence['missing' if value is None else 'qualified'] += 1
        evidence['grid_sha256'] = digest.hexdigest()
        self._evidence[role] = evidence
        return points

    def evidence_manifest(self):
        if set(self._evidence) != set(STREAMS):
            raise ValueError('incomplete temperature source evidence')
        return dict(version=1, cutover=self.cutover.isoformat(),
                    semantics='legacy_before_cutover_receipt_asof_after',
                    roles=deepcopy(self._evidence))


def _validate_receipt(value, target):
    if not isinstance(value, dict) or set(value) != {
        'temperatureF', 'receivedAt', 'storedAt', 'validUntil', 'streamEpoch', 'snapshotSha256'}:
        raise ValueError('closed qualified receipt required')
    received, stored, expires = (_utc(value[key]) for key in ('receivedAt', 'storedAt', 'validUntil'))
    number = value['temperatureF']
    if (not received <= stored <= target < expires or not 0 < (expires-received).total_seconds() <= 120
            or type(number) not in (int, float) or not math.isfinite(number) or not -40 <= number <= 140
            or str(UUID(value['streamEpoch'])) != value['streamEpoch']
            or not re.fullmatch('[0-9a-f]{64}', value['snapshotSha256'])):
        raise ValueError('unqualified temperature receipt')


def validate_evidence_manifest(evidence, *, start=None, end=None):
    if not isinstance(evidence, dict) or set(evidence) != {'version','cutover','semantics','roles'}:
        raise ValueError('closed temperature evidence manifest required')
    cutover = _utc(evidence['cutover'])
    if (type(evidence['version']) is not int or evidence['version'] != 1 or cutover != _ceil(cutover)
            or evidence['semantics'] != 'legacy_before_cutover_receipt_asof_after'
            or not isinstance(evidence['roles'], dict) or set(evidence['roles']) != set(STREAMS)):
        raise ValueError('invalid temperature evidence contract')
    for role, (stream, model, sensor_id) in STREAMS.items():
        info = evidence['roles'][role]
        if not isinstance(info, dict) or set(info) != {
            'stream','model','sensor_id','policy','legacy_points','targets','qualified','missing','grid_sha256'}:
            raise ValueError('closed temperature role evidence required')
        if (info['stream'] != stream or info['model'] != model or type(info['sensor_id']) is not int
                or info['sensor_id'] != sensor_id or info['policy'] != POLICY):
            raise ValueError('temperature policy identity mismatch')
        for key in ('legacy_points','targets','qualified','missing'):
            if type(info[key]) is not int or info[key] < 0:
                raise ValueError('nonnegative evidence counts required')
        if info['targets'] != info['qualified'] + info['missing']:
            raise ValueError('temperature evidence counts disagree')
        if start is not None and end is not None:
            first = _ceil(max(_utc(start), cutover))
            expected = max(0, math.ceil((_utc(end) - first) / STEP))
            if info['targets'] != expected:
                raise ValueError('temperature targets disagree with training window')
        if not isinstance(info['grid_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', info['grid_sha256']):
            raise ValueError('temperature grid digest required')
