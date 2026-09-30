#!/usr/bin/env python3
"""Publish two native read-only BMS channels on each existing successful poll.

No Item command, poller change, freshness relaxation or provider transfer.
--check is read-only. --apply privately saves the preimage and restores only
our exact configuration on failure; concurrent edits are never overwritten.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh

POLLER = 'modbus:poller:discoverBms190:bmsMain'
TARGETS = {
    'modbus:data:discoverBms190:bmsMain:capRemainAh': ('88', 'BMS_Capacity_Remaining_Ah'),
    'modbus:data:discoverBms190:bmsMain:tempRaw': ('74', 'BMS_Temperature_Raw'),
}
CONSUMERS = {'hex_bms_soc_scale', 'hex_bms_ttd_smooth', 'hex_bms_aux_evidence'}
PARAM = 'updateUnchangedValuesEveryMillis'
BACKUP_ROOT = Path('/home/sat/.local/state/openhab-config-migration')


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def plan(thing):
    uid = thing.get('UID')
    require(uid in TARGETS and thing.get('editable') is True
            and thing.get('thingTypeUID') == 'modbus:data'
            and thing.get('bridgeUID') == POLLER, 'unexpected data Thing')
    config = thing.get('configuration', {})
    require(config.get('readStart') == TARGETS[uid][0]
            and config.get('readValueType') == 'uint32'
            and config.get('readTransform') in ('default', ['default'])
            and config.get('writeTransform') in ('default', ['default'])
            and all(config.get(k) in (None, '')
                    for k in ('writeStart', 'writeType', 'writeValueType')),
            'native read-only register configuration drift')
    require(type(config.get(PARAM)) is int and config[PARAM] in (0, 60000),
            'unexpected unchanged-update interval')
    desired = deepcopy(config)
    desired[PARAM] = 0
    return desired


def stable(thing):
    return {k: thing.get(k) for k in
            ('UID', 'editable', 'thingTypeUID', 'bridgeUID', 'configuration', 'channels')}


def inspect():
    things = {uid: oh.get('/things/' + uid) for uid in (*TARGETS, POLLER)}
    for uid, thing in things.items():
        require(thing.get('statusInfo', {}).get('status') == 'ONLINE',
                'source Thing not ONLINE')
        if uid in TARGETS:
            plan(thing)
    poller = things[POLLER]
    require(poller.get('configuration', {}).get('refresh') == 30000
            and poller['configuration'].get('start') == 64
            and poller['configuration'].get('length') == 34
            and poller['configuration'].get('type') == 'holding', 'poller configuration drift')
    links = [x for x in oh.get('/links') if x['itemName'] in
             {spec[1] for spec in TARGETS.values()}
             or any(x['channelUID'].startswith(uid + ':') for uid in TARGETS)]
    require(sorted((x['itemName'], x['channelUID']) for x in links) ==
            sorted((spec[1], uid + ':number') for uid, spec in TARGETS.items()),
            'native channel links drift')
    rules = [x for x in oh.get('/rules') if any(
        spec[1] in json.dumps(x) for spec in TARGETS.values())]
    require({x['uid'] for x in rules} == CONSUMERS, 'consumer inventory drift')
    aux = next(x for x in rules if x['uid'] == 'hex_bms_aux_evidence')
    scripts = [x.get('configuration', {}).get('script') for x in aux.get('actions', [])]
    require(scripts == [(ROOT / 'openhab/rules/bms-aux-evidence.js').read_text()],
            'auxiliary source collector drift')
    guard = {'poller': stable(poller), 'links': links,
             'rules': [{k: v for k, v in x.items() if k != 'status'} for x in rules]}
    return {uid: things[uid] for uid in TARGETS}, guard


def put(uid, config):
    require(uid in TARGETS, 'unapproved mutation target')
    req = Request(oh.BASE + '/things/' + uid + '/config', method='PUT',
                  data=json.dumps(config).encode(), headers={
                      'Authorization': 'Bearer ' + oh.token(),
                      'Content-Type': 'application/json'})
    with urlopen(req, timeout=15) as response:
        require(response.status in (200, 202, 204), 'configuration update refused')


def wait_online(uid, expected):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        thing = oh.get('/things/' + uid)
        require(thing.get('configuration') == expected, 'configuration readback mismatch')
        if thing.get('statusInfo', {}).get('status') == 'ONLINE':
            return thing
        time.sleep(2)
    raise RuntimeError('data Thing did not recover ONLINE')


def backup(originals, guard):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not BACKUP_ROOT.is_symlink() and BACKUP_ROOT.stat().st_uid == os.getuid()
            and BACKUP_ROOT.stat().st_mode & 0o077 == 0, 'unsafe backup directory')
    directory = Path(tempfile.mkdtemp(prefix='bms-aux-cadence-', dir=BACKUP_ROOT))
    body = json.dumps({'originals': originals, 'guard': guard}, sort_keys=True).encode()
    fd = os.open(directory / 'preimage.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    fd = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    require(sha256((directory / 'preimage.json').read_bytes()).digest() ==
            sha256(body).digest(), 'private backup mismatch')
    return directory


def apply(originals, guard):
    desired = {uid: plan(thing) for uid, thing in originals.items()}
    pending = [uid for uid in TARGETS if desired[uid] != originals[uid]['configuration']]
    if not pending:
        return {'status': 'already_configured', 'changed': []}
    directory = backup(originals, guard)
    current, current_guard = inspect()
    require(current_guard == guard and all(stable(current[uid]) == stable(originals[uid])
            for uid in TARGETS), 'preimage changed before application')
    attempted = []
    try:
        for uid in pending:
            attempted.append(uid)  # Include an ambiguous HTTP failure in rollback.
            put(uid, desired[uid])
            wait_online(uid, desired[uid])
        after, after_guard = inspect()
        require(after_guard == guard, 'poller/link/consumer changed during application')
        for uid in TARGETS:
            expected = {**stable(originals[uid]), 'configuration': desired[uid]}
            require(stable(after[uid]) == expected, 'unrelated data Thing change')
    except Exception:
        failed = []
        for uid in reversed(attempted):
            try:
                thing = oh.get('/things/' + uid)
                if stable(thing) == stable(originals[uid]):
                    continue
                require(stable(thing) == {**stable(originals[uid]),
                                         'configuration': desired[uid]},
                        'concurrent edit: do not overwrite')
                put(uid, originals[uid]['configuration'])
                wait_online(uid, originals[uid]['configuration'])
            except Exception:
                failed.append(uid)
        raise RuntimeError('application failed; rollback ' +
                           ('incomplete for ' + ','.join(failed) if failed else 'verified') +
                           '; private_backup=' + str(directory)) from None
    return {'status': 'applied', 'changed': pending, 'private_backup': str(directory),
            'poller_refresh_ms': 30000, 'freshness_ttl_changed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        originals, guard = inspect()
        result = apply(originals, guard) if args.apply else {
            'status': 'preflight_passed', 'current_intervals_ms': {
                uid: t['configuration'][PARAM] for uid, t in originals.items()},
            'proposed_interval_ms': 0, 'poller_refresh_ms': 30000}
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        # Never print HTTP response bodies, credentials or an arbitrary exception.
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__,
                          'reason': str(error) if type(error) is RuntimeError else 'request failed'}))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
