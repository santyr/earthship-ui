#!/usr/bin/env python3
"""Qualify only the radiation delta against a pinned installed thermal runtime.

Copies/replays and guarded file transactions occur only in an owned temporary
directory. No production installation, service, configuration or journal write.
"""
import argparse
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DELTA = ('thermal_intel.py', 'thermal_radiation_runtime.py',
         'weather_radiation_reader.py', 'weather_radiation_history.py',
         'weather_radiation_evidence.py', 'weather_radiation_config.py')
CAPTURE_HELPER = 'thermal_model/forcing_capture.py'


def _module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


bundle = _module('radiation_qualifier_bundle', 'thermal-replay-bundle.py')
files = _module('radiation_qualifier_files', 'thermal-model-files.py')


def _revision(values, paths):
    return bundle._revision(paths, {'code/'+name: values[name] for name in paths})


def _write_tree(root, values):
    for name, data in values.items():
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(data)
        path.chmod(0o600)


def _replay(runtime, capture, revision):
    completed = subprocess.run([sys.executable, str(ROOT/'scripts/replay-thermal-forcing.py'),
        '--runtime-root', str(runtime), '--capture', str(capture),
        '--expected-runtime-revision', revision], text=True, capture_output=True,
        timeout=45, check=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    if len(completed.stdout.encode()) > 16384:
        raise ValueError('bounded replay result required')
    result = json.loads(completed.stdout)
    if (result.get('scope') != 'read_only_exact_thermal_replay'
            or result.get('exact_as_issued') is not True
            or result.get('runtime_manifest_revision') != revision
            or result.get('counterfactual_is_action_evidence') is not False):
        raise ValueError('exact source-bound replay required')
    for key in ('capture_output_sha256', 'artifact_code_revision'):
        if not isinstance(result.get(key), str) or not re.fullmatch('[0-9a-f]{64}', result[key]):
            raise ValueError('original replay identity required')
    return {key: result[key] for key in ('capture_output_sha256', 'artifact_code_revision')}


def _current_inputs(runtime):
    """Optional process-local read of actual inputs; never a model publication."""
    code = '''
from datetime import datetime, timezone
import json, os, sys
sys.path.insert(0, sys.argv[1])
from thermal_intel import _current_states
from thermal_temperature_runtime import validate_shadow_receipt_expiry
from thermal_radiation_runtime import validate_shadow_radiation_expiry
try:
    if (os.environ.get('THERMAL_TEMP_SHADOW_QUALIFIED_ENABLE') != '1'
            or os.environ.get('THERMAL_RADIATION_SHADOW_QUALIFIED_ENABLE') != '1'):
        raise ValueError('explicit receipt-only input gates required')
    at = datetime.now(timezone.utc)
    current = _current_states(at)
    checked = datetime.now(timezone.utc)
    for role in ('air', 'mass', 'outdoor'):
        if 'validUntil' not in current[role]:
            raise ValueError('receipt-only temperatures required')
    validate_shadow_receipt_expiry(current, checked)
    validate_shadow_radiation_expiry(current, checked)
    receipt = current['radiation']['sourceEvidence']
    print(json.dumps(dict(scope='read_only_actual_thermal_inputs',
        checked_at=checked.isoformat(), temperature_roles=['air','mass','outdoor'],
        radiation=dict(native_age_seconds=(checked-current['radiation']['at']).total_seconds(),
            irradiance_proxy_w_m2=current['radiation']['value'],
            valid_until=receipt['validUntil'].isoformat(), snapshot_sha256=receipt['snapshotSha256'],
            fault_visibility=receipt['fault_visibility'])), sort_keys=True))
except Exception:
    raise SystemExit(1) from None
'''
    result = subprocess.run([sys.executable, '-c', code, str(runtime)], capture_output=True,
        text=True, timeout=150, check=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    if len(result.stdout.encode()) > 4096:
        raise ValueError('bounded current-input result required')
    value = json.loads(result.stdout)
    if (not isinstance(value, dict) or set(value) != {'scope','checked_at','temperature_roles','radiation'}
            or value['scope'] != 'read_only_actual_thermal_inputs'
            or value['temperature_roles'] != ['air','mass','outdoor']
            or value['radiation'].get('fault_visibility') != 'verified'):
        raise ValueError('qualified actual thermal inputs required')
    return value


def qualify(*, repo_root, installed_root, expected_revision, captures, replay_runner=_replay,
            check_current=False, current_reader=None):
    if not isinstance(expected_revision, str) or not re.fullmatch('[0-9a-f]{64}', expected_revision):
        raise ValueError('full installed runtime pin required')
    repo_root, installed_root = Path(repo_root), Path(installed_root)
    for root in (repo_root, installed_root):
        if not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir():
            raise ValueError('explicit canonical source roots required')
    if not isinstance(captures, (tuple, list)) or not 1 <= len(captures) <= 3:
        raise ValueError('one to three original captures required')
    captures = [Path(path) for path in captures]
    if len(set(captures)) != len(captures):
        raise ValueError('distinct original captures required')
    # Each capture must stay private and byte-identical during qualification.
    originals = {path: bundle._read(path, private=True, max_size=256000) for path in captures}
    before = bundle._read(installed_root/'thermal_intel.py')
    old_paths = bundle._paths(before)
    if old_paths != bundle.LEGACY_RUNTIME_PATHS:
        raise ValueError('original installed thermal inventory required')
    baseline = {name: before if name == DELTA[0] else bundle._read(installed_root/name)
                for name in (*old_paths, CAPTURE_HELPER)}
    if _revision(baseline, old_paths) != expected_revision:
        raise ValueError('installed runtime changed from reviewed pin')
    if any((installed_root/name).exists() or (installed_root/name).is_symlink() for name in DELTA[1:]):
        raise ValueError('new radiation destinations must be absent')
    delta = {name: bundle._read(repo_root/'openhab/scripts'/name) for name in DELTA}
    candidate = {**baseline, **delta}
    paths = bundle._paths(candidate['thermal_intel.py'])
    if paths != bundle.RADIATION_RUNTIME_PATHS or set(candidate) != set(paths) | {CAPTURE_HELPER}:
        raise ValueError('exact radiation runtime inventory required')
    candidate_revision = _revision(candidate, paths)
    replays = []
    current_inputs = None
    with tempfile.TemporaryDirectory(prefix='earthship-thermal-radiation-') as temporary:
        root = Path(temporary); root.chmod(0o700)
        prior_root, candidate_root = root/'prior', root/'candidate/openhab/scripts'
        target_root = root/'target'
        _write_tree(prior_root, baseline)
        _write_tree(candidate_root, candidate)
        _write_tree(target_root, baseline)
        manifest = tuple(dict(source='openhab/scripts/'+name, target=str(target_root/name),
                              phase='code' if name in DELTA else 'verify', mode=0o600)
                         for name in (*paths, CAPTURE_HELPER))
        receipt = root/'receipt'
        files.capture_backup(root/'candidate', receipt, manifest=manifest)
        for capture in captures:
            prior = replay_runner(prior_root, capture, expected_revision)
            new = replay_runner(candidate_root, capture, candidate_revision)
            if prior != new:
                raise ValueError('radiation delta changed original replay identity')
            replays.append(dict(capture=capture.name, **new))
        if check_current:
            current_inputs = (_current_inputs if current_reader is None else current_reader)(candidate_root)
        # Interrupt after introducing new files; the existing transaction must
        # restore old entrypoint bytes and remove every newly introduced file.
        interrupted = False
        def fail(event, index):
            nonlocal interrupted
            if event == 'before-parent-fsync' and index == 3:
                interrupted = True
                raise RuntimeError('isolated radiation transaction interruption')
        try:
            files.install_phase(root/'candidate', receipt, 'code', manifest=manifest, fault=fail)
        except RuntimeError as error:
            if str(error) != 'isolated radiation transaction interruption':
                raise
        if not interrupted:
            raise ValueError('interrupted rollback was not exercised')
        _assert_original(target_root, baseline)
        files.install_phase(root/'candidate', receipt, 'code', manifest=manifest)
        if not files.verify_phase(root/'candidate', receipt, 'code', manifest=manifest):
            raise ValueError('candidate file verification failed')
        for capture, original in zip(captures, replays):
            replayed = replay_runner(target_root, capture, candidate_revision)
            if replayed != {key: original[key] for key in replayed}:
                raise ValueError('installed isolated candidate replay changed')
        files.restore(root/'candidate', receipt, manifest=manifest)
        _assert_original(target_root, baseline)
        if _revision({name: bundle._read(target_root/name) for name in old_paths}, old_paths) != expected_revision:
            raise ValueError('restored installed revision mismatch')
    # Guard the actual sources and captures; no production install has occurred.
    for name, data in baseline.items():
        if bundle._read(installed_root/name) != data:
            raise ValueError('installed source changed during qualification')
    for name, data in delta.items():
        if bundle._read(repo_root/'openhab/scripts'/name) != data:
            raise ValueError('candidate source changed during qualification')
    if any(bundle._read(path, private=True, max_size=256000) != raw for path, raw in originals.items()):
        raise ValueError('original capture changed during qualification')
    result = dict(scope='isolated_exact_installed_radiation_delta', installed_revision=expected_revision,
        candidate_revision=candidate_revision, delta_sha256={name: sha256(data).hexdigest() for name, data in delta.items()},
        preserved_files=len(baseline)-1, replays=replays, interrupted_rollback=True,
        candidate_install_restore=True, production_writes=0, controls_enabled=False)
    if current_inputs is not None:
        result['current_inputs'] = current_inputs
    return result


def _assert_original(root, baseline):
    if any(bundle._read(root/name) != data for name, data in baseline.items()):
        raise ValueError('original runtime restoration failed')
    if any((root/name).exists() or (root/name).is_symlink() for name in DELTA[1:]):
        raise ValueError('new radiation files remained after rollback')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', required=True, type=Path)
    parser.add_argument('--installed-root', required=True, type=Path)
    parser.add_argument('--expected-runtime-revision', required=True)
    parser.add_argument('--capture', action='append', required=True, type=Path)
    parser.add_argument('--check-current-inputs', action='store_true',
                        help='explicit read-only current receipt probe using process-local private configuration')
    args = parser.parse_args(argv)
    try:
        result = qualify(repo_root=args.repo_root, installed_root=args.installed_root,
            expected_revision=args.expected_runtime_revision, captures=args.capture,
            check_current=args.check_current_inputs)
        print(json.dumps(result, sort_keys=True, separators=(',', ':')))
        return 0
    except Exception:
        print('isolated thermal radiation qualification unavailable', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
