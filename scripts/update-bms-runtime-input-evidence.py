#!/usr/bin/env python3
"""Exact observational collector update; default read-only and release gated.

Never changes Items, Things, links, persistence configuration or control rules.
The initial-install adapter remains pinned to its historical source preimage.
"""
import argparse
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runtime_input_install',
    ROOT / 'scripts/deploy-bms-runtime-input-evidence.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
UID = common.UID
OLD_SHA = common.SOURCE_SHA
NEW_SHA = '621f4ac7416de35e1b68f87f7d0ed4096c729319cad08e5b71bc95b1b0062c80'
RELEASE_ENABLED = True  # September 30 pinned original-event/JDBC fixture passed.


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def plan(rule, source):
    descriptor = json.loads(common.DEFINITION.read_text())
    actions = rule.get('actions', [])
    require(rule.get('uid') == UID and rule.get('editable') is True
        and rule.get('conditions') == [] and len(actions) == 1
        and actions[0].get('type') == 'script.ScriptAction'
        and actions[0].get('configuration', {}).get('type') == 'application/javascript'
        and rule.get('triggers') == descriptor['rule']['triggers'],
        'collector definition drift')
    original = actions[0]['configuration'].get('script', '')
    require(sha256(original.encode()).hexdigest() == OLD_SHA, 'collector source preimage drift')
    require(sha256(source.encode()).hexdigest() == NEW_SHA and 'sendCommand' not in source,
        'candidate source drift')
    desired = common.rule_body(rule)
    desired['actions'][0]['configuration']['script'] = source
    return desired


def inspect():
    rule = common.oh.get('/rules/' + UID)
    desired = plan(rule, common.SOURCE.read_text())
    require(rule.get('status', {}).get('status') == 'IDLE', 'collector is not enabled and idle')
    require(not common.LIVE_ITEM.is_symlink()
        and sha256(common.LIVE_ITEM.read_bytes()).hexdigest() == common.ITEM_SHA,
        'file-owned evidence Item drift')
    item = common.oh.get('/items/' + common.ITEM)
    require(item.get('type') == 'String' and item.get('editable') is False,
        'evidence Item provider drift')
    guard = guard_digest()
    return common.rule_body(rule), desired, guard


def guard_digest():
    # Status/state naturally change. Protect static definitions, not telemetry.
    rules = sorted((common.rule_body(row) for row in common.oh.get('/rules')
                    if row['uid'] != UID), key=lambda row: row['uid'])
    things = []
    for uid in common.SOURCE_THINGS:
        row = common.oh.get('/things/' + uid)
        require(row.get('statusInfo', {}).get('status') == 'ONLINE', 'native source is not online')
        things.append({key: row.get(key) for key in
            ('UID', 'editable', 'thingTypeUID', 'bridgeUID', 'configuration', 'channels')})
    links = sorted(common.oh.get('/links'), key=lambda row: (row['itemName'], row['channelUID']))
    return digest({'rules': rules, 'things': things, 'links': links,
        'jdbc': common.oh.get('/persistence/jdbc')})


def save_backup(original, guard):
    directory_root = common.PRIVATE_ROOT
    require(not directory_root.is_symlink(), 'unsafe private backup root')
    directory_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(directory_root.stat().st_uid == os.getuid()
        and directory_root.stat().st_mode & 0o077 == 0, 'unsafe private backup root')
    directory = Path(tempfile.mkdtemp(prefix='bms-runtime-observation-update-', dir=directory_root))
    payload = {'original': original, 'guard_sha256': guard, 'candidate_sha256': NEW_SHA}
    body = json.dumps(payload, sort_keys=True).encode()
    fd = os.open(directory / 'preimage.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(body); stream.flush(); os.fsync(stream.fileno())
    require((directory / 'preimage.json').read_bytes() == body, 'private backup readback failed')
    return directory


def read_definition():
    return common.rule_body(common.oh.get('/rules/' + UID))


def put_definition(body):
    require(body.get('uid') == UID, 'mutation outside collector scope')
    common.request('PUT', '/rules/' + UID, body)


def verify_ready(expected):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        row = common.oh.get('/rules/' + UID)
        require(common.rule_body(row) == expected, 'updated definition readback failed')
        if row.get('status', {}).get('status') == 'IDLE':
            return
        time.sleep(.5)
    raise RuntimeError('updated collector readiness timed out')


def apply(original, desired, guard):
    require(RELEASE_ENABLED, 'collector release gate is off')
    backup = save_backup(original, guard)
    before, next_desired, next_guard = inspect()
    require((before, next_desired, next_guard) == (original, desired, guard),
        'preimage changed before application')
    try:
        # Include ambiguous HTTP failures in the exact-definition rollback.
        put_definition(desired)
        verify_ready(desired)
        require(guard_digest() == guard, 'unrelated configuration changed during update')
    except Exception:
        try:
            current = read_definition()
            if current != original:
                require(current == desired, 'concurrent collector edit: rollback refused')
                put_definition(original)
            verify_ready(original)
        except Exception:
            raise RuntimeError('update failed; rollback unverified; private_backup=' + str(backup)) from None
        raise RuntimeError('update failed; rollback verified; private_backup=' + str(backup)) from None
    return {'status': 'definition_updated_natural_evidence_pending', 'private_backup': str(backup),
        'collector_sha256': NEW_SHA, 'estimator_changed': False, 'control_writes': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        original, desired, guard = inspect()
        result = apply(original, desired, guard) if args.apply else {
            'status': 'preflight_passed', 'preimage_sha256': OLD_SHA,
            'candidate_sha256': NEW_SHA, 'guard_sha256': guard,
            'release_enabled': RELEASE_ENABLED, 'production_writes': 0}
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        # Do not emit arbitrary exceptions, server bodies, tokens or DSNs.
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
