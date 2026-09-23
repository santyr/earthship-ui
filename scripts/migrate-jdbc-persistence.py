#!/usr/bin/env python3
"""Attended, single-provider managed-to-file JDBC persistence handoff.

The provider-free interval is an unqualified collection gap. Never backfill it.
This script does not change connection settings, Items, rules, or strategies.
"""
import argparse
import hashlib
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402
from persistence_source import render  # noqa: E402

SOURCE = ROOT / 'openhab/file-config/persistence/jdbc.persist'
TARGET = Path('/etc/openhab/persistence/jdbc.persist')
RECEIPTS = Path('/home/sat/.local/state/earthship-ui/persistence-transfer')
PATH = '/persistence/jdbc'
INACTIVE_JOBS = ('forecast-json.service', 'forecast-intel.service',
                 'energy-forecast-snapshot.service', 'energy-daily.service',
                 'energy-ui-publish.service', 'thermal-model-train.service')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def request(method='GET', payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(oh.BASE + PATH, data=data, method=method,
                  headers={'Authorization': 'Bearer ' + oh.token(),
                           'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=10) as response:
            body = response.read()
            return response.status, json.loads(body) if method == 'GET' and body else None
    except HTTPError as error:
        if error.code == 404:
            return 404, None
        raise


def wait_provider(expected, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        status, body = request()
        if expected is None and status == 404:
            return
        if status == 200 and body == expected:
            return
        time.sleep(.25)
    raise RuntimeError('JDBC provider did not reach the exact expected state')


def history(item, start, end):
    query = urlencode({'serviceId': 'jdbc', 'starttime': start, 'endtime': end})
    result = oh.get('/persistence/items/' + item + '?' + query)
    if result.get('name') != item or not isinstance(result.get('data'), list):
        raise RuntimeError('unexpected JDBC history response for ' + item)
    return result['data']


def inactive_jobs():
    result = subprocess.run(['systemctl', '--user', 'is-active', *INACTIVE_JOBS],
                            capture_output=True, text=True, check=False)
    states = result.stdout.splitlines()
    if len(states) != len(INACTIVE_JOBS) or any(x != 'inactive' for x in states):
        raise RuntimeError('a forecast/energy/thermal job is active or not observable: '
                           + repr(dict(zip(INACTIVE_JOBS, states))))


def preflight():
    if TARGET.exists() or TARGET.is_symlink():
        raise RuntimeError('target file already exists; refuse provider overlap')
    status, original = request()
    if status != 200 or original.get('editable') is not True:
        raise RuntimeError('expected the managed JDBC provider')
    source = SOURCE.read_bytes()
    if source != render(original).encode():
        raise RuntimeError('source does not exactly render the live managed DTO')
    inactive_jobs()
    # Leave a settling margin for explicit writer events already in flight.
    end = datetime.now(timezone.utc) - timedelta(seconds=5)
    start = end - timedelta(minutes=5)
    fixed_end = end.isoformat()
    fixed_start = start.isoformat()
    before = {name: history(name, fixed_start, fixed_end)
              for name in ('BMS_SOC', 'Power_Evidence_JSON')}
    # BMS_SOC is intentionally change-only and may have no rows in this window.
    if not before['Power_Evidence_JSON']:
        raise RuntimeError('positive live power-history control is missing')
    if len(before['Power_Evidence_JSON']) > 500:
        raise RuntimeError('power-history control is unexpectedly large')
    return original, source, fixed_start, fixed_end, before


def save(directory, name, record):
    temporary = directory / (name + '.tmp')
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    os.chmod(temporary, 0o600)
    os.replace(temporary, directory / name)
    fd = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def install(source):
    fd, temporary = tempfile.mkstemp(prefix='.jdbc-stage-', suffix='.tmp',
                                    dir=TARGET.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(source)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        if TARGET.exists() or TARGET.is_symlink():
            raise RuntimeError('target appeared while staging file')
        os.replace(temporary, TARGET)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def restore_managed(original, source):
    if TARGET.exists() or TARGET.is_symlink():
        if TARGET.read_bytes() != source:
            raise RuntimeError('file differs from staged source; manual recovery required')
        TARGET.unlink()
    wait_provider(None)
    status, _ = request('PUT', original)
    if status != 201:
        raise RuntimeError('managed rollback creation returned HTTP ' + str(status))
    wait_provider(original)


def recover(receipt):
    receipt = receipt.resolve(strict=True)
    if receipt.parent != RECEIPTS or not receipt.is_dir():
        raise RuntimeError('recovery receipt must be an exact owned transfer directory')
    record = json.loads((receipt / 'receipt.json').read_text())
    if record.get('state') == 'verified_file_provider':
        raise RuntimeError('verified transfer is not an interrupted handoff')
    original = record['original']
    source = SOURCE.read_bytes()
    if hashlib.sha256(source).hexdigest() != record['source_sha256']:
        raise RuntimeError('source bytes changed since interrupted handoff')
    if render(original).encode() != source:
        raise RuntimeError('receipt DTO does not match source')
    with (RECEIPTS / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current_status, current = request()
        if current_status == 200 and current == original and not TARGET.exists():
            record.update(state='rolled_back_managed', collection_gap_end=stamp())
        elif current_status in (200, 404):
            if current_status == 200 and current != {**original, 'editable': False}:
                raise RuntimeError('unexpected provider state; refuse recovery')
            restore_managed(original, source)
            record.update(state='rolled_back_managed', collection_gap_end=stamp())
        else:
            raise RuntimeError('provider is not readable for recovery')
        save(receipt, 'receipt.json', record)
        print('managed_provider_restored=true', flush=True)


def apply():
    original, source, fixed_start, fixed_end, before = preflight()
    RECEIPTS.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(RECEIPTS, 0o700)
    with (RECEIPTS / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Revalidate under the lock. Never reuse a stale snapshot.
        original, source, fixed_start, fixed_end, before = preflight()
        receipt = RECEIPTS / ('jdbc-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        receipt.mkdir(mode=0o700)
        details = {'state': 'prepared', 'original': original,
                   'source_sha256': hashlib.sha256(source).hexdigest(),
                   'history_interval': [fixed_start, fixed_end], 'history_before': before,
                   'collection_continuity_claimed': False}
        save(receipt, 'receipt.json', details)
        print('private_receipt=' + str(receipt), flush=True)
        gap_start = stamp()
        details.update(state='provider_removal_started', collection_gap_start=gap_start)
        save(receipt, 'receipt.json', details)
        removed = False
        try:
            status, _ = request('DELETE')
            if status != 200:
                raise RuntimeError('managed provider deletion returned HTTP ' + str(status))
            removed = True
            wait_provider(None)
            details['provider_absent_observed_at'] = stamp()
            save(receipt, 'receipt.json', details)
            install(source)
            expected = {**original, 'editable': False}
            wait_provider(expected)
            details['file_provider_observed_at'] = stamp()
            after = {name: history(name, fixed_start, fixed_end) for name in before}
            if after != before:
                raise RuntimeError('pre-boundary JDBC history changed')
            details.update(state='verified_file_provider', history_preserved=True,
                           collection_gap_end=stamp(),
                           collection_gap_status='unqualified_natural_events')
            save(receipt, 'receipt.json', details)
            print('file_provider_verified=true', flush=True)
            print('collection_gap=' + gap_start + '/' + details['collection_gap_end'], flush=True)
        except Exception as error:
            details.update(state='rollback_attempted', error=str(error))
            save(receipt, 'receipt.json', details)
            try:
                current_status, _ = request()
            except Exception:
                current_status = None
            if removed or TARGET.exists() or current_status == 404:
                try:
                    restore_managed(original, source)
                    details.update(state='rolled_back_managed', collection_gap_end=stamp())
                    save(receipt, 'receipt.json', details)
                except Exception as rollback_error:
                    details.update(state='manual_recovery_required', rollback_error=str(rollback_error))
                    save(receipt, 'receipt.json', details)
            elif current_status is None:
                details.update(state='manual_recovery_required', rollback_error='provider state unreadable')
                save(receipt, 'receipt.json', details)
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='perform attended live provider transfer')
    parser.add_argument('--recover', type=Path, help='roll interrupted receipt back to managed')
    args = parser.parse_args()
    if args.apply and args.recover:
        parser.error('--apply and --recover are mutually exclusive')
    if args.recover:
        recover(args.recover)
    elif args.apply:
        apply()
    else:
        original, source, start, end, before = preflight()
        print('preflight=ready managed_provider=true source_exact=true '
              'jobs_inactive=true history_controls=' + ','.join(before))
