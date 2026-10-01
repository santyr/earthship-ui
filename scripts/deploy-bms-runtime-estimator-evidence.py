#!/usr/bin/env python3
"""Exact managed display-estimator update; default read-only, live gate closed.

Only one rule PUT is allowed (or its exact rollback). No Item writes, runnow,
enable/disable, control commands, database writes, provider transfer or restart.
"""
import argparse
from contextlib import contextmanager
import fcntl
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('estimator_transport',
    ROOT / 'scripts/deploy-bms-runtime-input-evidence.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
UID = 'hex_bms_ttd_smooth'
OLD_SHA = '8698b16a5e07a5fde653c6e74219886f78c2b6ec7740e5a8a8608c32c205a794'
NEW_SHA = '8b0e6533517c1ded06b1dd1e7c64b5cf9eb7a3ff3792d05a44ce3e4e5fc6e168'
DESCRIPTOR_SHA = '3031e528bb002dd4c0741b3da65a243624bf33f321c05e865b117eda17c9e458'
COLLECTOR_SHA = '621f4ac7416de35e1b68f87f7d0ed4096c729319cad08e5b71bc95b1b0062c80'
SOURCE = ROOT / 'openhab/rules/bms-runtime-estimator-evidence.js'
DESCRIPTOR = ROOT / 'openhab/bms-runtime-estimator-evidence-resources.json'
PRIVATE_ROOT = common.PRIVATE_ROOT
RELEASE_READY = False
QUALIFIED_RUNTIME_VERSION = '5.2.1'
OLD_TRIGGERS = [{'id': '1', 'configuration': {'itemName': 'BMS_TimeToDischarge_Min'},
                 'type': 'core.ItemStateUpdateTrigger'}]
OUTPUTS = {'BMS_Runtime_Basis': 'String', 'BMS_TimeToDischarge_Smoothed': 'Number',
           'BMS_TimeToFull_Smoothed': 'Number'}
PROTECTED = ('hex_southoutlet_cycle', 'hex_schneider_safety', 'hex_bms_soc_scale',
             'hex_bms_comms_watchdog', 'hex_bms_runtime_input_evidence')


class GuardFailure(RuntimeError):
    """Only fixed, source-defined refusal reasons may be shown to the operator."""


def require(value, reason):
    if not value: raise GuardFailure(reason)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def descriptor():
    require(not DESCRIPTOR.is_symlink() and sha256(DESCRIPTOR.read_bytes()).hexdigest() == DESCRIPTOR_SHA,
            'candidate descriptor drift')
    return json.loads(DESCRIPTOR.read_text())


def plan(rule, source, description):
    require(digest(description) == digest(descriptor()), 'candidate descriptor drift')
    actions = rule.get('actions', [])
    require(rule.get('uid') == UID and rule.get('editable') is True
            and rule.get('conditions') == [] and rule.get('configuration', {}) == {}
            and rule.get('triggers') == OLD_TRIGGERS and len(actions) == 1
            and actions[0].get('id') == '2' and actions[0].get('type') == 'script.ScriptAction'
            and actions[0].get('inputs', {}) == {}
            and set(actions[0].get('configuration', {})) == {'type', 'script'}
            and actions[0]['configuration']['type'] == 'application/javascript'
            and sha256(actions[0]['configuration']['script'].encode()).hexdigest() == OLD_SHA,
            'managed estimator baseline drift')
    require(sha256(source.encode()).hexdigest() == NEW_SHA and 'sendCommand' not in source,
            'candidate source drift')
    desired = common.rule_body(rule)
    desired['triggers'] = description['triggers']
    desired['actions'][0]['configuration']['script'] = source
    return desired


def native_field(raw, now, basis, key, ttl, property, low, high):
    """Match original-observation qualification, not a changed Item timestamp."""
    try:
        if not isinstance(raw, str) or len(raw) > 8192: return False
        def unique(pairs):
            result = {}
            for k, v in pairs:
                if k in result: raise ValueError('duplicate receipt field')
                result[k] = v
            return result
        r = json.loads(raw, object_pairs_hook=unique)
        if (not isinstance(r, dict) or type(r.get('version')) is not int or r['version'] != 1
                or (basis is not None and r.get('basis') != basis)
                or not isinstance(r.get('streamEpoch'), str)
                or str(UUID(r['streamEpoch'])) != r['streamEpoch']
                or type(r.get('sequence')) is not int or r['sequence'] <= 0
                or type(r.get('recordedAt')) is not int
                or not 0 < r['recordedAt'] <= now or now-r['recordedAt'] > 180000): return False
        f = r['fields'][key]
        return (f.get('status') == 'valid' and f.get('reason') == 'ok'
                and all(type(f.get(k)) is int for k in ('observedAt', 'validUntil', property))
                and 0 < f['observedAt'] <= r['recordedAt']
                and f['validUntil'] == f['observedAt'] + ttl and now < f['validUntil']
                and low <= f[property] <= high)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return False


def guard_digest():
    rules = common.oh.get('/rules')
    indexed = {row['uid']: row for row in rules}
    for uid in PROTECTED:
        require(indexed.get(uid, {}).get('status', {}).get('status') in ('IDLE', 'RUNNING')
                and indexed[uid]['status'].get('statusDetail') == 'NONE', 'protected rule unhealthy')
    collector = indexed['hex_bms_runtime_input_evidence'].get('actions', [])
    require(len(collector) == 1 and sha256(collector[0]['configuration']['script'].encode()).hexdigest()
            == COLLECTOR_SHA, 'observation-preserving collector drift')
    things = []
    for uid in common.SOURCE_THINGS:
        row = common.oh.get('/things/' + uid)
        require(row.get('statusInfo', {}).get('status') == 'ONLINE', 'native runtime source offline')
        things.append({k: row.get(k) for k in
                       ('UID', 'editable', 'thingTypeUID', 'bridgeUID', 'configuration', 'channels')})
    items = []
    for name in (*descriptor()['requiresValidItems'], *OUTPUTS):
        row = common.oh.get('/items/' + name)
        require(row.get('type') == OUTPUTS.get(name, 'String'), 'runtime Item type drift')
        items.append({k: row.get(k) for k in
                      ('name', 'type', 'editable', 'label', 'category', 'groupNames', 'tags',
                       'unit', 'stateDescription', 'metadata')})
    return digest({'rules': sorted((common.rule_body(r) for r in rules if r['uid'] != UID),
                                   key=lambda r: r['uid']),
                   'things': things, 'items': items,
                   'links': sorted(common.oh.get('/links'), key=lambda r: (r['itemName'], r['channelUID'])),
                   'jdbc': common.oh.get('/persistence/jdbc')})


def inspect():
    require(not SOURCE.is_symlink(), 'candidate source symlink')
    require(common.oh.get('/').get('runtimeInfo', {}).get('version') == QUALIFIED_RUNTIME_VERSION,
            'runtime differs from qualified JVM version')
    row = common.oh.get('/rules/' + UID)
    desired = plan(row, SOURCE.read_text(), descriptor())
    require(row.get('status', {}).get('status') in ('IDLE', 'RUNNING')
            and row['status'].get('statusDetail') == 'NONE', 'estimator unhealthy or disabled')
    for name in common.PUMPS:
        require(common.oh.get('/items/' + name)['state'] == 'OFF', 'pump not OFF')
    require(common.oh.get('/items/BMS_Comms_Status')['state'] == 'OK', 'BMS comms not OK')
    states = {name: common.oh.get('/items/' + name)['state'] for name in descriptor()['requiresValidItems']}
    now = time.time(); now_ms = int(now * 1000)
    require(common.oh.atomic_soc_freshness(states['BMS_SOC_Evidence_JSON'], now) is None,
            'original SoC evidence not fresh')
    require(common.oh.qualified_runtime_current(states['BMS_Runtime_Input_Evidence_JSON'], now) is not None,
            'original current evidence not fresh')
    for name, basis, key, ttl, prop, low, high in [
        ('BMS_Aux_Evidence_JSON', 'discover_bms_190_native_aux_v1', 'battery.remaining_ah', 120000, 'value', 0, 450),
        ('BMS_Runtime_Input_Evidence_JSON', 'native_runtime_inputs_v1', 'battery.dc_voltage_cv', 90000, 'value', 4000, 6500),
        ('Inverter_AC_Evidence_JSON', 'inverter_output', 'inverter.ac_output_w', 30000, 'watts', 0, 20000),
        ('Power_Evidence_JSON', None, 'pv.input_power_w', 120000, 'watts', 0, 4294967294),
    ]:
        require(native_field(states[name], now_ms, basis, key, ttl, prop, low, high),
                'required original runtime field not fresh')
    return common.rule_body(row), desired, guard_digest()


def private_root():
    require(not PRIVATE_ROOT.is_symlink(), 'private backup root symlink')
    PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = PRIVATE_ROOT.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'private backup root unsafe')


@contextmanager
def apply_lock():
    private_root()
    fd = os.open(PRIVATE_ROOT / 'bms-estimator.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) == 0o600, 'private estimator lock unsafe')
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('another estimator handoff owns the lock') from None
        yield
    finally:
        os.close(fd)


def save_backup(original, guard):
    private_root()
    directory = Path(tempfile.mkdtemp(prefix='bms-estimator-evidence-', dir=PRIVATE_ROOT))
    body = json.dumps({'original': original, 'guard_sha256': guard,
                       'candidate_sha256': NEW_SHA, 'descriptor_sha256': DESCRIPTOR_SHA}, sort_keys=True).encode()
    fd = os.open(directory / 'preimage.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(body); stream.flush(); os.fsync(stream.fileno())
    for path in (directory, PRIVATE_ROOT):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)
    require((directory / 'preimage.json').read_bytes() == body, 'private backup readback failed')
    return directory


def read_definition():
    return common.rule_body(common.oh.get('/rules/' + UID))


def put_definition(body):
    actions = body.get('actions', [])
    require(body.get('uid') == UID and body.get('conditions') == []
            and body.get('configuration', {}) == {} and len(actions) == 1
            and actions[0].get('id') == '2' and actions[0].get('type') == 'script.ScriptAction'
            and actions[0].get('inputs', {}) == {}
            and set(actions[0].get('configuration', {})) == {'type', 'script'}
            and actions[0]['configuration']['type'] == 'application/javascript',
            'mutation outside pinned estimator scope')
    source_sha = sha256(actions[0]['configuration']['script'].encode()).hexdigest()
    require((source_sha == OLD_SHA and body.get('triggers') == OLD_TRIGGERS)
            or (source_sha == NEW_SHA and body.get('triggers') == descriptor()['triggers']),
            'mutation outside pinned estimator scope')
    common.request('PUT', '/rules/' + UID, body)


def verify_ready(expected):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        row = common.oh.get('/rules/' + UID)
        require(common.rule_body(row) == expected, 'definition readback drift')
        if row.get('status') == {'status': 'IDLE', 'statusDetail': 'NONE'}: return
        time.sleep(.5)
    raise RuntimeError('estimator readiness timed out')


class ApplyFailure(RuntimeError):
    def __init__(self, status, backup):
        self.status = status; self.backup = str(backup)
        super().__init__(status)


def apply(original, desired, guard, *, attended=False):
    require(RELEASE_READY, 'estimator live release gate is off')
    require(attended, 'attended operation required')
    with apply_lock():
        backup = save_backup(original, guard)
        require(inspect() == (original, desired, guard), 'preimage changed before mutation')
        require(read_definition() == original, 'target changed immediately before PUT')
        try:
            put_definition(desired)
            verify_ready(desired)
            require(guard_digest() == guard, 'unrelated configuration changed')
        except Exception:
            try:
                current = read_definition()
                if current != original:
                    require(current == desired, 'concurrent edit: rollback refused')
                    put_definition(original)
                verify_ready(original)
            except Exception:
                raise ApplyFailure('apply_failed_rollback_unverified', backup) from None
            raise ApplyFailure('apply_failed_rollback_verified', backup) from None
        return {'status': 'definition_updated_natural_evidence_pending', 'private_backup': str(backup),
                'candidate_sha256': NEW_SHA, 'control_commands': 0, 'restart': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true'); group.add_argument('--apply', action='store_true')
    parser.add_argument('--attended', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.apply:
            require(RELEASE_READY, 'estimator live release gate is off')
            require(args.attended, 'attended operation required')
        else:
            require(not args.attended, 'attendance is only valid for apply')
        original, desired, guard = inspect()
        result = apply(original, desired, guard, attended=args.attended) if args.apply else {
            'status': 'preflight_passed', 'preimage_sha256': OLD_SHA,
            'candidate_sha256': NEW_SHA, 'guard_sha256': guard,
            'release_ready': RELEASE_READY, 'production_writes': 0}
        print(json.dumps(result, sort_keys=True))
        return 0
    except ApplyFailure as error:
        print(json.dumps({'status': error.status, 'private_backup': error.backup}))
    except GuardFailure as error:
        print(json.dumps({'status': 'refused', 'reason': str(error)}))
    except Exception as error:
        # Never emit private input bodies, arbitrary server errors or tokens.
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
