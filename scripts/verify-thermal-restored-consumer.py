#!/usr/bin/env python3
"""Installed-reader check against an explicitly disposable restored journal.

The connection defaults read-only and refuses production port/database names.
No schema write, actuator, registry recovery, training or relay connection.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys

import psycopg2
from psycopg2.extensions import parse_dsn


def verify(root, expected_revision, start, role):
    root = root.resolve()
    sys.path.insert(0, str(root))
    from thermal_intel import _code_revision
    from thermal_model.dataset import build_samples, dataset_manifest
    from thermal_model.journal import ActionJournal
    from thermal_model.schema import ACTION_KINDS
    for name, module in tuple(sys.modules.items()):
        if name == 'thermal_intel' or name == 'thermal_model' or name.startswith('thermal_model.'):
            if not Path(module.__file__).resolve().is_relative_to(root):
                raise ValueError('mixed consumer runtime roots')
    if _code_revision() != expected_revision:
        raise ValueError('consumer runtime preimage mismatch')
    params = parse_dsn(os.environ['THERMAL_RESTORE_PROBE_URL'])
    if (params.get('host') != '127.0.0.1' or params.get('dbname') != 'postgres'
            or not 1024 < int(params.get('port', 0)) < 65536 or int(params['port']) == 5432
            or params.get('user') != 'postgres' or not params.get('password')
            or re.fullmatch('[a-z_][a-z0-9_]*', role) is None
            or params.get('options') != '-c default_transaction_read_only=on -c role='+role):
        raise ValueError('restricted disposable connection required')
    dsn = os.environ['THERMAL_RESTORE_PROBE_URL']
    with psycopg2.connect(dsn, connect_timeout=3) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_user, current_setting(%s)', ('transaction_read_only',))
            if cursor.fetchone() != (role, 'on'):
                raise ValueError('read-only runtime role required')
    if start.utcoffset() is None or start.second or start.microsecond or start.minute % 5:
        raise ValueError('aware five-minute fixture start required')
    end = start+timedelta(hours=2)
    reader = ActionJournal(dsn)
    events = reader.effective_events(start, end)
    modes = reader.effective_modes(start, end)
    observed = {event.action: event.state for event in events}
    expected = {'vent': 'closed', 'indoor_shade': 'open', 'outdoor_shade': 'removed',
                'kiva': 'off', 'window': 'open', 'skylight': 'closed'}
    if len(events) != 6 or observed != expected or modes:
        raise ValueError('restored consumer lost or changed fixture observations')
    times = [start+i*timedelta(minutes=5) for i in range(25)]
    series = {role: [(at, value) for at in times] for role, value in
        {'air': 72., 'mass': 70., 'outdoor': 55., 'radiation': 0., 'glazing': 71.}.items()}
    supported = tuple(event for event in events if event.action in ACTION_KINDS)
    baseline = build_samples(series, supported, [], start, end)
    combined = build_samples(series, events, [], start, end)
    baseline_digest = dataset_manifest(baseline, supported, [])['canonical_rows_sha256']
    combined_digest = dataset_manifest(combined, events, [])['canonical_rows_sha256']
    if baseline != combined or baseline_digest != combined_digest:
        raise ValueError('restored observations changed legacy samples or support')
    if baseline.confirmed_action_rows != (start,) or combined.confirmed_action_rows != (start,):
        raise ValueError('restored observations changed legacy support')
    if _code_revision() != expected_revision:
        raise ValueError('consumer runtime changed during probe')
    return {'status': 'installed_consumer_qualified', 'runtime_revision': expected_revision,
        'connection_read_only': True, 'runtime_role_verified': True,
        'distinct_fixture_observations': len(events), 'legacy_samples_unchanged': True,
        'legacy_support_rows': len(combined.confirmed_action_rows),
        'sample_sha256': combined_digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--expected-runtime-revision', required=True)
    parser.add_argument('--fixture-start', required=True, type=datetime.fromisoformat)
    parser.add_argument('--runtime-role', required=True)
    args = parser.parse_args()
    try:
        result = verify(args.runtime_root, args.expected_runtime_revision,
                        args.fixture_start, args.runtime_role)
    except Exception as error:
        # This probe runs only against a disposable restored database. Surface
        # the invariant label for CI diagnosis without printing DSNs, payloads,
        # credentials, or household records.
        message = str(error)
        if len(message) > 240:
            message = message[:240]
        print(json.dumps({
            'status': 'withheld',
            'error_type': type(error).__name__,
            'error': message,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
