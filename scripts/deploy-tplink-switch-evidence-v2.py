#!/usr/bin/env python3
"""Guarded observational TP-Link evidence v1-to-v2 rule replacement.

Default mode is read-only preflight. --apply backs up the exact managed rule,
replaces only its script, and rolls back on a failed readback. It never commands
either switch. Natural v2 barrier and renewed reports are separate gates.
"""

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
SOURCE = ROOT / 'openhab/rules/tplink-switch-evidence.js'
UID = 'hex_tplink_switch_evidence'
OLD_SHA = 'e725970e0e47ee1c9108c8b1ab4203ea6568987379e5b27bd748defe772b3c1d'
NEW_SHA = '40b34d9b2afa3ce9451aecdf5b26aef3f46a85adda402cb6a0f7f6106f4466d9'
THINGS = ('tplinksmarthome:hs103:a34b4957dc', 'tplinksmarthome:hs103:08482dd378')
PRIVATE_ROOT = Path('/home/sat/.local/state/tplink-switch-evidence-release')
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
    raise RuntimeError('observational rule did not reach requested state')


def put(rule):
    request('/rules/' + UID, 'PUT', json.dumps(dto(rule)).encode(), 'application/json')


def backup(rule):
    if PRIVATE_ROOT.is_symlink():
        raise RuntimeError('private backup root must not be a symlink')
    PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if stat.S_IMODE(PRIVATE_ROOT.stat().st_mode) != 0o700:
        raise RuntimeError('private backup root must be mode 0700')
    directory = Path(tempfile.mkdtemp(prefix='v2-', dir=PRIVATE_ROOT))
    target = directory / 'original-rule.json'
    with target.open('x') as stream:
        json.dump(rule, stream, indent=2)
        stream.write('\n')
    if stat.S_IMODE(target.stat().st_mode) != 0o600:
        raise RuntimeError('private backup file must be mode 0600')
    return directory


def preflight():
    source = SOURCE.read_text()
    if digest(source) != NEW_SHA or 'sendCommand' in source:
        raise RuntimeError('candidate source differs from reviewed observational script')
    original = oh.get('/rules/' + UID)
    if (original.get('uid') != UID or len(original.get('actions', [])) != 1
            or len(original.get('triggers', [])) != 6
            or digest(original['actions'][0]['configuration']['script']) != OLD_SHA
            or original.get('status') != {'status': 'IDLE', 'statusDetail': 'NONE'}):
        raise RuntimeError('live observational rule differs from pinned baseline')
    for uid in THINGS:
        if oh.get('/things/' + uid).get('statusInfo') != {'status': 'ONLINE', 'statusDetail': 'NONE'}:
            raise RuntimeError('TP-Link source Thing is not ONLINE')
    return original, source


def apply(original, source):
    receipt = backup(original)
    print('private_backup=' + str(receipt), flush=True)
    replacement = copy.deepcopy(original)
    replacement['actions'][0]['configuration']['script'] = source
    disabled = False
    try:
        enable(False)
        disabled = True
        if dto(oh.get('/rules/' + UID)) != dto(original):
            raise RuntimeError('rule definition drifted after disable')
        put(replacement)
        live = oh.get('/rules/' + UID)
        if dto(live) != dto(replacement) or live['status'] != {'status': 'UNINITIALIZED', 'statusDetail': 'DISABLED'}:
            raise RuntimeError('disabled rule readback differs from candidate')
        enable(True)
        live = oh.get('/rules/' + UID)
        if dto(live) != dto(replacement) or digest(live['actions'][0]['configuration']['script']) != NEW_SHA:
            raise RuntimeError('enabled rule readback mismatch')
        print(json.dumps({'status': 'deployed_provisional', 'script_sha256': NEW_SHA}), flush=True)
    except Exception:
        if disabled:
            try:
                enable(False)
                put(original)
                enable(True)
                if dto(oh.get('/rules/' + UID)) != dto(original):
                    raise RuntimeError('rollback readback mismatch')
                print('rollback=verified', flush=True)
            except Exception as error:
                print('URGENT rollback failed: ' + str(error), file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='perform guarded production transfer')
    args = parser.parse_args()
    original, source = preflight()
    print(json.dumps({'status': 'preflight_ok', 'old_sha256': OLD_SHA,
                      'new_sha256': NEW_SHA, 'things': 'ONLINE'}), flush=True)
    if args.apply:
        apply(original, source)


if __name__ == '__main__':
    os.umask(0o077)
    main()
