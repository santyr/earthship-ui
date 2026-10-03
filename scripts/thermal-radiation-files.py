#!/usr/bin/env python3
"""Receipt-bound, six-file current-radiation rollout using the tested file adapter.

Prepare writes only a private recovery point. Apply/restore require an explicit
flag, idle jobs and a clear natural timer window. No job, timer or control starts.
"""
import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('radiation_rollout_qualifier',
    ROOT/'scripts/qualify-thermal-radiation-runtime.py')
q = importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
OLD = '7316fa8b1e408544463b3f44e64772e56c7f36b57a9d6325ccca3353bea03af5'
NEW = 'c732feed23f4a9dd323a85a77dec9872d821c626d6619a642548dc7b752baaac'
LIVE = Path('/home/sat/openhab/scripts')
STATE = Path('/home/sat/.local/state/thermal-intel')
RECEIPTS = STATE/'deploy-receipts'
UNIT = Path('/home/sat/.config/systemd/user/thermal-model-shadow.service.d/qualified-radiation.conf')
UNIT_SOURCE = 'deploy/thermal-model-shadow.service.d/qualified-radiation.conf'
CODE_ORDER = ('weather_radiation_evidence.py', 'weather_radiation_config.py',
              'weather_radiation_reader.py', 'weather_radiation_history.py',
              'thermal_radiation_runtime.py', 'thermal_intel.py')
CONFIGS = tuple(Path('/home/sat/.config/hex')/name for name in (
    'openhab.env', 'weather-temperature-db.json', 'weather-temperature-policy.json',
    'energy-power-reader.jdbc', 'weather-radiation-policy.json')) + (
    Path('/home/sat/.config/systemd/user/thermal-model-shadow.service'),
    UNIT.parent/'qualified-temperature.conf', UNIT.parent/'forcing-capture.conf',
    STATE/'models/accepted.json',)
RAD_ENV = dict(THERMAL_RADIATION_SHADOW_QUALIFIED_ENABLE='1',
    THERMAL_RADIATION_DB_CONFIG='/home/sat/.config/hex/energy-power-reader.jdbc',
    THERMAL_RADIATION_POLICY='/home/sat/.config/hex/weather-radiation-policy.json',
    THERMAL_RADIATION_EVIDENCE_CUTOVER='2026-10-02T20:00:09.206165+00:00')


def systemctl(*args):
    result = subprocess.run(['systemctl', '--user', *args], text=True, capture_output=True,
                            check=True, timeout=15)
    return result.stdout.strip()


def _seconds(value):
    units = {'d':86400, 'h':3600, 'min':60, 'ms':.001, 'us':.000001, 's':1}
    pairs = re.findall(r'(\d+(?:\.\d+)?)(min|ms|us|d|h|s)', value)
    if not pairs or ''.join(number+unit for number, unit in pairs) != value.replace(' ', ''):
        raise ValueError('finite monotonic timer deadline required')
    return sum(float(number)*units[unit] for number, unit in pairs)


def idle_window():
    for unit in ('thermal-model-shadow.service', 'thermal-model-train.service'):
        state = dict(line.split('=', 1) for line in systemctl('show', '-p', 'ActiveState',
                    '-p', 'MainPID', unit).splitlines())
        if state != {'ActiveState':'inactive', 'MainPID':'0'}:
            raise ValueError('idle thermal jobs required')
    if systemctl('show', '-p', 'ActiveState', '--value', 'thermal-model-shadow.timer') != 'active':
        raise ValueError('existing natural shadow timer must remain active')
    deadline = systemctl('show', '-p', 'NextElapseUSecMonotonic', '--value', 'thermal-model-shadow.timer')
    if _seconds(deadline)-time.monotonic() < 90:
        raise ValueError('natural shadow timer window is too close')


def manifest():
    unchanged = [name for name in (*q.bundle.LEGACY_RUNTIME_PATHS, q.CAPTURE_HELPER)
                 if name != 'thermal_intel.py']
    return tuple(dict(source='openhab/scripts/'+name, target=str(LIVE/name),
                      phase='verify', mode=0o644) for name in unchanged) + tuple(
        dict(source='openhab/scripts/'+name, target=str(LIVE/name), phase='code',
             mode=0o755 if name == 'thermal_intel.py' else 0o644) for name in CODE_ORDER) + (
        dict(source=UNIT_SOURCE, target=str(UNIT), phase='unit', mode=0o644),)


def _revision(root):
    before = q.bundle._read(root/'thermal_intel.py')
    paths = q.bundle._paths(before)
    return q._revision({name: before if name=='thermal_intel.py' else q.bundle._read(root/name)
                        for name in paths}, paths)


def _state(receipt):
    data = json.loads(q.bundle._read(receipt/'qualification.json', private=True))
    keys = {'version','old_revision','new_revision','configs','source_sha256','status'}
    if (set(data) not in (keys, keys | {'natural_publication_sha256'})
            or type(data['version']) is not int or data['version'] != 1
            or data['status'] not in {'prepared','installed_waiting_natural_publication',
                                     'installed_natural_publication_verified','rolled_back'}
            or data['old_revision'] != OLD or data['new_revision'] != NEW
            or set(data['configs']) != {str(path) for path in CONFIGS}
            or set(data['source_sha256']) != set(CODE_ORDER) | {UNIT_SOURCE}):
        raise ValueError('exact private rollout qualification required')
    pin = data.get('natural_publication_sha256')
    if data['status'] == 'installed_natural_publication_verified' and pin is None:
        raise ValueError('durable natural publication proof required')
    if pin is not None:
        if (data['status'] not in {'installed_natural_publication_verified','rolled_back'}
                or not isinstance(pin,str) or re.fullmatch('[0-9a-f]{64}',pin) is None
                or sha256(q.bundle._read(receipt/'natural-publication.json',private=True)).hexdigest()!=pin):
            raise ValueError('unchanged private natural publication proof required')
    for path, digest in data['configs'].items():
        if sha256(q.bundle._read(Path(path))).hexdigest() != digest:
            raise ValueError('unchanged configuration and accepted artifact required')
    if _revision(receipt/'source/openhab/scripts') != NEW:
        raise ValueError('frozen candidate source changed')
    for name, digest in data['source_sha256'].items():
        path = receipt/'source'/(name if name == UNIT_SOURCE else 'openhab/scripts/'+name)
        if sha256(q.bundle._read(path)).hexdigest() != digest:
            raise ValueError('frozen rollout source changed')
    return data


def _save_state(receipt, data):
    q.files._atomic_write_private(receipt/'qualification.json',
        (json.dumps(data, sort_keys=True, separators=(',', ':'))+'\n').encode(), 0o600, parent_mode=0o700)


def prepare(receipt):
    idle_window()
    if receipt.exists() or receipt.is_symlink() or UNIT.exists() or UNIT.is_symlink():
        raise ValueError('new private receipt and absent radiation drop-in required')
    if _revision(LIVE) != OLD or any((LIVE/name).exists() or (LIVE/name).is_symlink() for name in CODE_ORDER[:-1]):
        raise ValueError('reviewed original installed runtime required')
    baseline = {name:q.bundle._read(LIVE/name) for name in (*q.bundle.LEGACY_RUNTIME_PATHS, q.CAPTURE_HELPER)}
    delta = {name:q.bundle._read(ROOT/'openhab/scripts'/name) for name in CODE_ORDER}
    candidate = {**baseline, **delta}
    if q._revision(candidate, q.bundle.RADIATION_RUNTIME_PATHS) != NEW:
        raise ValueError('qualified six-file candidate required')
    configs = {str(path):q.bundle._read(path) for path in CONFIGS}
    dropin = q.bundle._read(ROOT/UNIT_SOURCE)
    q.files.secure_directory(receipt, 0o700, create=True, enforce_mode=True)
    q._write_tree(receipt/'source/openhab/scripts', candidate)
    q._write_tree(receipt/'source', {UNIT_SOURCE:dropin})
    for index, raw in enumerate(configs.values()):
        q.files._atomic_write_private(receipt/'configuration'/f'{index:02d}.bin', raw, 0o600, parent_mode=0o700)
    data = dict(version=1, old_revision=OLD, new_revision=NEW, status='prepared',
        configs={path:sha256(raw).hexdigest() for path,raw in configs.items()},
        source_sha256={**{name:sha256(raw).hexdigest() for name,raw in delta.items()},
                       UNIT_SOURCE:sha256(dropin).hexdigest()})
    _save_state(receipt, data)
    q.files.capture_backup(receipt/'source', receipt/'files', manifest=manifest())
    _state(receipt)
    return dict(status='prepared', receipt=str(receipt), candidate_revision=NEW, production_writes=0)


def apply(receipt):
    data = _state(receipt)
    idle_window()
    if data['status'] != 'prepared' or _revision(LIVE) != OLD:
        raise ValueError('unchanged prepared original runtime required')
    # Require fresh actual candidate inputs before crossing the production gate.
    current = q._current_inputs(receipt/'source/openhab/scripts')
    idle_window()
    try:
        q.files.install_phase(receipt/'source', receipt/'files', 'code', manifest=manifest())
        q.files.install_phase(receipt/'source', receipt/'files', 'unit', manifest=manifest())
        systemctl('daemon-reload')
        env = {key:value for entry in shlex.split(systemctl('show', '-p', 'Environment', '--value',
            'thermal-model-shadow.service')) if '=' in entry for key,value in [entry.split('=',1)] if key in RAD_ENV}
        if env != RAD_ENV or _revision(LIVE) != NEW:
            raise ValueError('installed source and current-input configuration mismatch')
        _state(receipt)
        data['status'] = 'installed_waiting_natural_publication'
        _save_state(receipt, data)
    except BaseException:
        q.files.restore(receipt/'source', receipt/'files', manifest=manifest())
        systemctl('daemon-reload')
        data['status'] = 'rolled_back'
        _save_state(receipt, data)
        raise
    return dict(status=data['status'], receipt=str(receipt), candidate_revision=NEW,
                current_inputs=current, controls_enabled=False, learning_enabled=False)


def restore(receipt):
    data = _state(receipt)
    idle_window()
    q.files.restore(receipt/'source', receipt/'files', manifest=manifest())
    systemctl('daemon-reload')
    if _revision(LIVE) != OLD or UNIT.exists():
        raise ValueError('original runtime rollback verification failed')
    data['status']='rolled_back'; _save_state(receipt, data)
    return dict(status='rolled_back', receipt=str(receipt), restored_revision=OLD)


def recover(receipt):
    _state(receipt)
    idle_window()
    q.files.recover(receipt/'source', receipt/'files', manifest=manifest())
    return restore(receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare','apply','restore','recover'))
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--allow-apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        receipt = args.receipt
        if (receipt.parent != RECEIPTS or not re.fullmatch(r'radiation-current-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}', receipt.name)
                or receipt.parent.resolve(strict=True) != RECEIPTS):
            raise ValueError('exact private rollout receipt required')
        if args.operation != 'prepare' and not args.allow_apply:
            raise ValueError('explicit rollout write gate required')
        result = dict(prepare=prepare, apply=apply, restore=restore, recover=recover)[args.operation](receipt)
        print(json.dumps(result, sort_keys=True, separators=(',', ':')))
        return 0
    except Exception:
        print('guarded thermal radiation operation unavailable; inspect private receipt', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
