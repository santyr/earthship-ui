#!/usr/bin/env python3
"""Attended, exact-baseline greywater rule repair with private rollback."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'openhab/scripts'))
import openhab_sanity_check as oh

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'openhab/rules/southoutlet-cycle-current.js'
UID = 'hex_southoutlet_cycle'
OLD_SHA = 'de49ccfafbdf1263da6691d653c4bd6dde7c607f7d33f934c9abc17431eebe09'
NEW_SHA = '358c5c1131b731ee944c7cd45769cbc29b191fe42d28186d5020345fed1ff0ab'
PUMPS = ('SouthOutlet_Outlet2_Switch', 'East_Bed_Socket_Outlet_2_Power')
PRIVATE_ROOT = Path('/home/sat/.local/state/greywater-rule-release')
DTO_KEYS = ('uid', 'name', 'description', 'tags', 'visibility', 'configuration',
            'triggers', 'conditions', 'actions')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def dto(rule):
    result = {key: copy.deepcopy(rule[key]) for key in DTO_KEYS if key in rule}
    result.setdefault('description', '')
    result.setdefault('tags', [])
    result.setdefault('visibility', 'VISIBLE')
    result.setdefault('configuration', {})
    result.setdefault('triggers', [])
    result.setdefault('conditions', [])
    return result


def request(path, method, payload, content_type):
    headers = {'Authorization': 'Bearer ' + oh.token(), 'Content-Type': content_type}
    with urlopen(Request(oh.BASE + path, data=payload, method=method, headers=headers), timeout=15) as response:
        if response.status not in (200, 201, 202, 204):
            raise RuntimeError(f'{method} {path} returned HTTP {response.status}')


def enable(flag):
    request('/rules/' + UID + '/enable', 'POST', str(flag).lower().encode(), 'text/plain')
    expected = ('IDLE', 'NONE') if flag else ('UNINITIALIZED', 'DISABLED')
    for _ in range(40):
        status = oh.get('/rules/' + UID)['status']
        if (status['status'], status['statusDetail']) == expected:
            return
        time.sleep(.25)
    raise RuntimeError('rule did not reach requested enabled state')


def put(rule):
    request('/rules/' + UID, 'PUT', json.dumps(dto(rule)).encode(), 'application/json')


def pumps_off():
    states = {name: oh.get('/items/' + name)['state'] for name in PUMPS}
    if any(value != 'OFF' for value in states.values()):
        raise RuntimeError('both pump Items must be explicitly OFF')


def backup(rule):
    PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if stat.S_IMODE(PRIVATE_ROOT.stat().st_mode) != 0o700:
        raise RuntimeError('private backup root must be mode 0700')
    directory = Path(tempfile.mkdtemp(prefix='timer-guard-', dir=PRIVATE_ROOT))
    target = directory / 'original-rule.json'
    with target.open('x') as stream:
        json.dump(rule, stream, indent=2)
        stream.write('\n')
    if stat.S_IMODE(target.stat().st_mode) != 0o600:
        raise RuntimeError('private backup file must be mode 0600')
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='perform guarded production transfer')
    args = parser.parse_args()
    source = SOURCE.read_text()
    if digest(source) != NEW_SHA:
        raise RuntimeError('source differs from reviewed candidate')
    original = oh.get('/rules/' + UID)
    if original['uid'] != UID or len(original['actions']) != 1:
        raise RuntimeError('unreviewed live rule shape')
    if digest(original['actions'][0]['configuration']['script']) != OLD_SHA:
        raise RuntimeError('live script differs from pinned baseline')
    if original['status'] != {'status': 'IDLE', 'statusDetail': 'NONE'}:
        raise RuntimeError('rule must be idle and enabled')
    pumps_off()
    status = oh.get('/items/SouthOutlet_AutoStatus')['state']
    if status.startswith(('reason=cycle_active', 'reason=cycle_started')):
        raise RuntimeError('rule reports a running cycle')
    print(json.dumps({'status': 'preflight_ok', 'old_sha256': OLD_SHA,
                      'new_sha256': NEW_SHA, 'both_pumps': 'OFF'}), flush=True)
    if not args.apply:
        return
    receipt = backup(original)
    print('private_backup=' + str(receipt), flush=True)
    replacement = copy.deepcopy(original)
    replacement['actions'][0]['configuration']['script'] = source
    disabled = False
    try:
        enable(False)
        disabled = True
        pumps_off()
        if dto(oh.get('/rules/' + UID)) != dto(original):
            raise RuntimeError('rule definition drifted after disable')
        put(replacement)
        live = oh.get('/rules/' + UID)
        if dto(live) != dto(replacement) or live['status'] != {'status': 'UNINITIALIZED', 'statusDetail': 'DISABLED'}:
            raise RuntimeError('disabled rule readback differs from reviewed candidate')
        enable(True)
        live = oh.get('/rules/' + UID)
        pumps_off()
        if dto(live) != dto(replacement) or digest(live['actions'][0]['configuration']['script']) != NEW_SHA:
            raise RuntimeError('enabled rule readback mismatch')
        print(json.dumps({'status': 'deployed', 'script_sha256': NEW_SHA,
                          'both_pumps': 'OFF'}), flush=True)
    except Exception:
        if disabled:
            try:
                enable(False)
                pumps_off()
                put(original)
                enable(True)
                if dto(oh.get('/rules/' + UID)) != dto(original):
                    raise RuntimeError('rollback readback mismatch')
                print('rollback=verified', flush=True)
            except Exception as rollback_error:
                print('URGENT rollback failed: ' + str(rollback_error), file=sys.stderr)
        raise


if __name__ == '__main__':
    os.umask(0o077)
    main()
