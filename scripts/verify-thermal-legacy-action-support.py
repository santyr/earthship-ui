#!/usr/bin/env python3
"""Read-only fixture check of one explicitly selected installed thermal tree.

No journal connection, training, model save/quarantine, publication or command.
Checks the installed artifact validator directly, never registry recovery.
"""
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib
import json
from pathlib import Path
import sys


def verify(root, expected_sha256, accepted=None):
    root = root.resolve()
    target = root / 'thermal_model/dataset.py'
    if target.is_symlink() or sha256(target.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('dataset preimage mismatch')
    sys.path.insert(0, str(root))
    dataset = importlib.import_module('thermal_model.dataset')
    schema = importlib.import_module('thermal_model.schema')
    intel = importlib.import_module('thermal_intel')
    for name, module in tuple(sys.modules.items()):
        if name == 'thermal_intel' or name == 'thermal_model' or name.startswith('thermal_model.'):
            if not Path(module.__file__).resolve().is_relative_to(root):
                raise ValueError('mixed installed thermal roots')
    start = datetime(2026, 8, 13, 6, tzinfo=timezone.utc)
    end = start+timedelta(hours=2)
    times = [start+i*timedelta(minutes=5) for i in range(25)]
    series = {role: [(at, value) for at in times] for role, value in
              {'air': 72., 'mass': 70., 'outdoor': 55., 'radiation': 0., 'glazing': 71.}.items()}
    def event(name, state, at):
        return schema.ActionEvent('fixture-'+name, 'fixture-receipt-'+name,
            at, at, name, state, 'nostr_confirmed', 1.)
    legacy = [event(name, state, start) for name, state in
        (('vent', 'closed'), ('indoor_shade', 'open'), ('outdoor_shade', 'removed'), ('kiva', 'off'))]
    observations = [event('window', 'open', start+timedelta(minutes=5)),
                    event('skylight', 'closed', start+timedelta(minutes=10))]
    baseline = dataset.build_samples(series, legacy, [], start, end)
    combined = dataset.build_samples(series, legacy+observations, [], start, end)
    only_new = dataset.build_samples(series, observations, [], start, end)
    legacy_digest = dataset.dataset_manifest(baseline, legacy, [])['canonical_rows_sha256']
    combined_digest = dataset.dataset_manifest(combined, legacy+observations, [])['canonical_rows_sha256']
    if legacy_digest != combined_digest or baseline != combined:
        raise ValueError('unsupported observations changed legacy forcing')
    if any(row.vent_open is not None for row in only_new):
        raise ValueError('unsupported observations became vent forcing')
    safe = (baseline.confirmed_action_rows == combined.confirmed_action_rows == (start,)
            and only_new.confirmed_action_rows == ())
    result = {'status': 'safe' if safe else 'unsafe_action_support',
        'dataset_sha256': expected_sha256, 'runtime_revision': intel._code_revision(),
        'legacy_fixture_sha256': legacy_digest, 'legacy_forcing_unchanged': True,
        'baseline_support_rows': len(baseline.confirmed_action_rows),
        'combined_support_rows': len(combined.confirmed_action_rows),
        'unsupported_only_support_rows': len(only_new.confirmed_action_rows)}
    if accepted is not None:
        if accepted.is_symlink():
            raise ValueError('accepted artifact symlink refused')
        raw = accepted.read_bytes()
        artifacts = importlib.import_module('thermal_model.artifacts')
        model = artifacts._artifact_from_payload(json.loads(raw))
        artifacts.validate_artifact(model, require_eligible=True)
        result.update(accepted_artifact_sha256=sha256(raw).hexdigest(),
                      accepted_training_revision=model.code_revision,
                      accepted_artifact_valid=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scripts-root', required=True, type=Path)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--accepted', type=Path)
    parser.add_argument('--require-safe', action='store_true')
    args = parser.parse_args()
    try:
        result = verify(args.scripts_root, args.expected_sha256, args.accepted)
        print(json.dumps(result, sort_keys=True))
        return 2 if args.require_safe and result['status'] != 'safe' else 0
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
