#!/usr/bin/env python3
"""Read-only terrain daylight estimate from retained native five-minute geometry.

No acquisition, astronomy approximation, measured-light qualification or control
transport is provided. Each endpoint describes its preceding five-minute bin.
"""
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import json
import os
import stat
import sys
import time as timing

from astro_geometry_series import replay_series, SERIES_FIELDS
from household.codec import canonical, identity, loads
from household_solar_horizon import prepare_horizon_source, horizon_configuration, horizon_height

ROOT = Path(__file__).resolve().parents[2]
ZONE = 'America/Denver'
MAX_BYTES = 524288
MAX_FILES = 8192
RESOLUTION = 300


def _utc(now):
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError('aware current clock required')
    return now.astimezone(timezone.utc)


def project_day(raw: bytes, horizon_raw: bytes, now: datetime) -> dict:
    """Replay original pins and project only a complete current Denver day."""
    now = _utc(now)
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError('bounded original geometry required')
    value = loads(raw)
    if set(value) != SERIES_FIELDS:
        raise ValueError('closed original geometry series required')
    series = replay_series(raw, request=value['request'],
        expected_series_sha256=value['series_sha256'], expected_native_runtime=value['native_runtime'])
    descriptor = series.descriptor()
    if descriptor['timezone'] != ZONE or datetime.fromisoformat(descriptor['available_at']) > now:
        raise ValueError('available local native geometry required')
    if not isinstance(horizon_raw, bytes) or not 0 < len(horizon_raw) <= 16384:
        raise ValueError('original horizon bytes required')
    body = loads(horizon_raw)
    if not isinstance(body.get('recorded_at'), str):
        raise ValueError('original horizon availability required')
    horizon_source = prepare_horizon_source(horizon_raw,
        available_at=datetime.fromisoformat(body['recorded_at']))
    horizon, reason = horizon_configuration(horizon_source, origin=now,
        site=descriptor['site'], timezone_name=ZONE)
    if reason is not None or horizon is None:
        raise ValueError('matching original terrain horizon required')
    day = now.astimezone(ZoneInfo(ZONE)).date()
    start = datetime.combine(day, time(), ZoneInfo(ZONE)).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time(), ZoneInfo(ZONE)).astimezone(timezone.utc)
    seconds = int((end-start).total_seconds())
    expected = [(start+timedelta(seconds=i)).isoformat() for i in range(RESOLUTION, seconds+1, RESOLUTION)]
    rows = [row for cache in series.to_dict()['caches'] for row in cache['positions']
            if start < datetime.fromisoformat(row['at']) <= end]
    if [row['at'] for row in rows] != expected:
        raise ValueError('complete exact local-day endpoint coverage required')
    visible = [row for row in rows if row['elevation_degrees'] > max(0,
        horizon_height(horizon['profile'], row['azimuth_degrees']))]
    result = dict(schema='earthship-terrain-daylight/v1',
        method='native-five-minute-terrain-endpoint-mask/v1', day=day.isoformat(), timezone=ZONE,
        calculatedAt=now.isoformat(), dayStartAt=start.isoformat(), validUntil=end.isoformat(),
        geometryAvailableAt=descriptor['available_at'], geometrySha256=series.sha256,
        horizonSha256=horizon_source['sha256'], sourceRuntimeSha256=identity(descriptor['native_runtime']),
        daySeconds=seconds, terrainSunlightSeconds=RESOLUTION*len(visible),
        unobstructedSunlightSeconds=RESOLUTION*sum(row['elevation_degrees'] > 0 for row in rows),
        firstSunAt=(datetime.fromisoformat(visible[0]['at'])-timedelta(seconds=RESOLUTION)).isoformat() if visible else None,
        lastSunAt=visible[-1]['at'] if visible else None, resolutionSeconds=RESOLUTION,
        confidence='unvalidated_map_estimate', physical_calibration_qualified=False, automatic_actuation=False)
    if len(canonical(result)) > 16384:
        raise ValueError('bounded public daylight required')
    return result


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
        info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory(path, *, private):
    """Open every absolute path component without following symbolic links."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('absolute original input path required')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if private and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError('owned private geometry directory required')
        return fd
    except BaseException:
        os.close(fd)
        raise


def _unchanged(parent, name, signature):
    if _signature(os.stat(name, dir_fd=parent, follow_symlinks=False)) != signature:
        raise ValueError('original input changed')


def _read(parent, name, *, private, maximum, guard):
    guard()
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
    try:
        before = os.fstat(fd)
        owners = (os.getuid(),) if private else (0, os.getuid())
        modes = (0o600,) if private else (0o600, 0o644)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid not in owners or
                before.st_nlink != 1 or stat.S_IMODE(before.st_mode) not in modes or
                not 0 < before.st_size <= maximum):
            raise ValueError('bounded owned original input required')
        parts = bytearray()
        while True:
            guard()
            part = os.read(fd, min(65536, maximum+1-len(parts)))
            if not part:
                break
            parts.extend(part)
            if len(parts) > maximum:
                raise ValueError('original input exceeds bound')
        signature = _signature(before)
        if _signature(os.fstat(fd)) != signature:
            raise ValueError('original input changed while reading')
        _unchanged(parent, name, signature)
        return bytes(parts), signature
    finally:
        os.close(fd)


def read_day(geometry_root, horizon_path, now):
    """Choose the newest qualified cached series within fixed scan/time bounds."""
    now = _utc(now)
    deadline = timing.monotonic()+8
    def guard():
        if timing.monotonic() >= deadline:
            raise TimeoutError('daylight replay deadline exceeded')
    day = now.astimezone(ZoneInfo(ZONE)).date()
    start = datetime.combine(day, time(), ZoneInfo(ZONE)).astimezone(timezone.utc)
    end = datetime.combine(day+timedelta(days=1), time(), ZoneInfo(ZONE)).astimezone(timezone.utc)
    first_endpoint = (start+timedelta(seconds=RESOLUTION)).isoformat()
    last_endpoint = end.isoformat()
    root = Path(geometry_root)
    horizon_path = Path(horizon_path)
    root_fd = _directory(root, private=True)
    horizon_fd = None
    try:
        root_info = os.fstat(root_fd)
        horizon_fd = _directory(horizon_path.parent, private=False)
        horizon_raw, horizon_signature = _read(horizon_fd, horizon_path.name,
            private=False, maximum=16384, guard=guard)
        names = []
        with os.scandir(root_fd) as entries:
            for index, entry in enumerate(entries):
                guard()
                if index >= MAX_FILES:
                    raise ValueError('bounded geometry directory required')
                if entry.name.endswith('.geometry.json'):
                    names.append(entry.name)
                    if len(names) > MAX_FILES:
                        raise ValueError('bounded geometry cache required')
        selected = None
        for name in sorted(names):
            raw, signature = _read(root_fd, name, private=True, maximum=MAX_BYTES, guard=guard)
            try:
                original = loads(raw)
                request = original.get('request')
                if not isinstance(request, dict):
                    continue
                instants = request.get('instants')
                # This is rejection-only filtering, never geometry validation.
                # Any candidate still replays every original request/cache/hash.
                if (request.get('timezone') != ZONE or not isinstance(instants, list) or
                        first_endpoint not in instants or last_endpoint not in instants):
                    continue
                report = project_day(raw, horizon_raw, now)
            except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
                continue
            guard()
            key = (original['request']['requested_at'], report['geometryAvailableAt'], report['geometrySha256'])
            if selected is None or key > selected[0]:
                selected = (key, report, name, signature)
        if selected is None:
            raise ValueError('qualified current-day cached geometry unavailable')
        guard()
        _unchanged(root_fd, selected[2], selected[3])
        _unchanged(horizon_fd, horizon_path.name, horizon_signature)
        current_root = os.stat(root, follow_symlinks=False)
        if (_signature(current_root) != _signature(root_info) or
                _signature(os.fstat(root_fd)) != _signature(root_info)):
            raise ValueError('geometry directory changed')
        return selected[1]
    finally:
        os.close(root_fd)
        if horizon_fd is not None:
            os.close(horizon_fd)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # Argument diagnostics must not reflect private paths or coordinates.
        raise ValueError('invalid daylight worker arguments')


def main(argv=None, *, clock=lambda: datetime.now(timezone.utc)):
    parser = _Parser(description='Read retained terrain daylight estimate')
    parser.add_argument('--geometry-root', type=Path,
        default=Path.home()/'.local/state/earthship-weather/daily-pv/geometry')
    parser.add_argument('--horizon', type=Path, default=ROOT/'openhab/household-solar-horizon.json')
    try:
        args = parser.parse_args(argv)
        report = read_day(args.geometry_root, args.horizon, clock())
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        print('{"status":"unavailable"}')
        print('Terrain daylight unavailable.', file=sys.stderr)
        return 1
    print(canonical(report).decode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
