#!/usr/bin/env python3
"""Guarded observational runtime-input collector release; default is read-only.

The collector is not a control rule. On a failure after activation it is
disabled and left for diagnosis, never silently retried or rolled forward.
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
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402
from persistence_source import render  # noqa: E402

UID = 'hex_bms_runtime_input_evidence'
ITEM = 'BMS_Runtime_Input_Evidence_JSON'
SOURCE = ROOT / 'openhab/rules/bms-runtime-input-evidence.js'
ITEM_SOURCE = ROOT / 'openhab/file-config/items/bms-runtime-input-evidence.items'
JDBC_SOURCE = ROOT / 'openhab/file-config/persistence/jdbc.persist'
DEFINITION = ROOT / 'openhab/bms-runtime-input-evidence-resources.json'
LIVE_JDBC = Path('/etc/openhab/persistence/jdbc.persist')
LIVE_ITEM = Path('/etc/openhab/items/bms-runtime-input-evidence.items')
PRIVATE_ROOT = Path('/home/sat/.local/state/openhab-config-migration')
OLD_JDBC_SHA = 'fee8000e505b4a7b9af43e3a979f67475ba59c27efdd4a0029532dc07685fecc'
NEW_JDBC_SHA = '4b294cfb7b0e29cf97b5d52a854762d05d2a03260ad7c8603aee0f8772775737'
SOURCE_SHA = 'a2193c0fae81579da9eae671767a51be6a870556fa7249b25df9a754095afe34'
ITEM_SHA = 'e22c58eeac449389eb107b2eded9a04b05c8522ff989805def73601ddfbde83c'
PUMPS = ('SouthOutlet_Outlet2_Switch', 'East_Bed_Socket_Outlet_2_Power')
SOURCE_THINGS = (
    'modbus:data:schneiderBatterySunSpec:battery802Core:currentRawCentiA',
    'modbus:data:schneiderBatterySunSpec:battery802Core:voltageRawCentiV',
    'modbus:poller:schneiderBatterySunSpec:battery802Core',
    'modbus:tcp:schneiderBatterySunSpec',
    'modbus:data:discoverBms190:bmsMain:ttdMin',
    'modbus:data:discoverBms190:bmsMain:ttfMin',
    'modbus:poller:discoverBms190:bmsMain',
    'modbus:tcp:discoverBms190',
)
RULE_FIELDS = ('uid', 'name', 'description', 'tags', 'visibility', 'configuration',
               'triggers', 'conditions', 'actions')


def digest(body):
    return hashlib.sha256(body).hexdigest()


def absent(path):
    try:
        oh.get(path)
    except HTTPError as error:
        if error.code == 404:
            return True
        raise
    return False


def history():
    try:
        return oh.get('/persistence/items/' + ITEM + '?serviceId=jdbc').get('data', [])
    except HTTPError as error:
        if error.code == 404:
            return []
        raise


def request(method, path, body=None, content_type='application/json'):
    data = None if body is None else (body.encode() if isinstance(body, str) else json.dumps(body).encode())
    headers = {'Authorization': 'Bearer ' + oh.token(), 'Content-Type': content_type}
    with urlopen(Request(oh.BASE + path, data=data, method=method, headers=headers), timeout=15) as response:
        if response.status not in (200, 201, 202, 204):
            raise RuntimeError(f'{method} {path} HTTP {response.status}')


def wait_for(check, label, attempts=40, interval=.5):
    for _ in range(attempts):
        try:
            if check():
                return
        except HTTPError as error:
            if error.code != 404:
                raise
        time.sleep(interval)
    raise RuntimeError(label + ' readback timeout')


def rule_body(rule):
    return {key: copy.deepcopy(rule[key]) for key in RULE_FIELDS if key in rule}


def source_preflight():
    if digest(JDBC_SOURCE.read_bytes()) != NEW_JDBC_SHA \
            or digest(SOURCE.read_bytes()) != SOURCE_SHA \
            or digest(ITEM_SOURCE.read_bytes()) != ITEM_SHA:
        raise RuntimeError('reviewed source digest drift')
    descriptor = json.loads(DEFINITION.read_text())
    if descriptor['rule']['uid'] != UID or descriptor['rule']['enabled'] is not False \
            or descriptor['persistenceExclusion'] != '!' + ITEM \
            or len(descriptor['rule']['triggers']) != 6 or 'sendCommand' in SOURCE.read_text():
        raise RuntimeError('observational candidate contract drift')
    return descriptor


def preflight():
    descriptor = source_preflight()
    if LIVE_JDBC.is_symlink() or digest(LIVE_JDBC.read_bytes()) != OLD_JDBC_SHA:
        raise RuntimeError('live JDBC strategy preimage drift')
    if LIVE_ITEM.exists() or LIVE_ITEM.is_symlink() or not absent('/items/' + ITEM) \
            or not absent('/rules/' + UID) or history():
        raise RuntimeError('runtime input Item, rule or history already exists')
    for name in PUMPS:
        if oh.get('/items/' + name)['state'] != 'OFF':
            raise RuntimeError('pump state is not OFF')
    if oh.get('/items/BMS_Comms_Status')['state'] != 'OK':
        raise RuntimeError('BMS comms are not OK')
    for uid in SOURCE_THINGS:
        if oh.get('/things/' + uid).get('statusInfo') != {'status': 'ONLINE', 'statusDetail': 'NONE'}:
            raise RuntimeError('native source Thing is not ONLINE: ' + uid)
    expected = copy.deepcopy(oh.get('/persistence/jdbc'))
    if render(expected, allow_file=True).encode() != LIVE_JDBC.read_bytes():
        raise RuntimeError('live JDBC provider DTO/file mismatch')
    expected['configs'][0]['items'].append('!' + ITEM)
    expected['configs'][2]['items'].append(ITEM)
    if render(expected, allow_file=True).encode() != JDBC_SOURCE.read_bytes():
        raise RuntimeError('candidate JDBC strategy is not the exact additive change')
    return descriptor


def backup():
    if PRIVATE_ROOT.is_symlink():
        raise RuntimeError('private backup root is a symlink')
    PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if stat.S_IMODE(PRIVATE_ROOT.stat().st_mode) != 0o700:
        raise RuntimeError('private backup root is not 0700')
    directory = Path(tempfile.mkdtemp(prefix='bms-runtime-input-', dir=PRIVATE_ROOT))
    original = directory / 'jdbc.persist'
    with original.open('xb') as stream:
        stream.write(LIVE_JDBC.read_bytes())
        stream.flush(); os.fsync(stream.fileno())
    if digest(original.read_bytes()) != OLD_JDBC_SHA:
        raise RuntimeError('private backup readback mismatch')
    return directory


def install(source, target, expected_hash):
    if target.exists() and target.is_symlink():
        raise RuntimeError('destination is a symlink')
    body = source.read_bytes()
    if digest(body) != expected_hash:
        raise RuntimeError('install source changed')
    fd, temporary = tempfile.mkstemp(prefix='.hex-runtime-input-', dir=target.parent)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, target)
        if digest(target.read_bytes()) != expected_hash:
            raise RuntimeError('installed file readback mismatch')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def live_strategy_is(source):
    return render(oh.get('/persistence/jdbc'), allow_file=True).encode() == source.read_bytes()


def enabled(flag):
    request('POST', '/rules/' + UID + '/enable', str(flag).lower(), 'text/plain')
    expected = {'status': 'IDLE', 'statusDetail': 'NONE'} if flag else \
        {'status': 'UNINITIALIZED', 'statusDetail': 'DISABLED'}
    wait_for(lambda: oh.get('/rules/' + UID)['status'] == expected,
             'observational rule enable=' + str(flag))


def apply(descriptor):
    directory = backup()
    print('private_backup=' + str(directory), flush=True)
    item_installed = rule_created = rule_enabled = False
    try:
        install(JDBC_SOURCE, LIVE_JDBC, NEW_JDBC_SHA)
        wait_for(lambda: live_strategy_is(JDBC_SOURCE), 'JDBC candidate', attempts=80)
        item_installed = True
        install(ITEM_SOURCE, LIVE_ITEM, ITEM_SHA)
        wait_for(lambda: oh.get('/items/' + ITEM)['type'] == 'String', 'file-owned evidence Item', attempts=80)
        if history():
            raise RuntimeError('automatic JDBC rows appeared before rule activation')
        spec = descriptor['rule']
        skeleton = {'uid': UID, 'name': spec['name'], 'description': 'Observational native runtime receipts',
                    'tags': [], 'visibility': 'VISIBLE', 'configuration': {}, 'triggers': [],
                    'conditions': [], 'actions': [{'id': 'evidence', 'type': 'script.ScriptAction',
                      'configuration': {'type': 'application/javascript', 'script': SOURCE.read_text()}}]}
        rule_created = True
        request('POST', '/rules', skeleton)
        enabled(False)
        live = oh.get('/rules/' + UID)
        if live['triggers'] or digest(live['actions'][0]['configuration']['script'].encode()) != SOURCE_SHA:
            raise RuntimeError('disabled rule skeleton drift')
        desired = rule_body(live)
        desired['triggers'] = spec['triggers']
        request('PUT', '/rules/' + UID, desired)
        live = oh.get('/rules/' + UID)
        if rule_body(live) != desired or live['status'] != {'status': 'UNINITIALIZED', 'statusDetail': 'DISABLED'}:
            raise RuntimeError('disabled collector readback drift')
        rule_enabled = True
        enabled(True)
        if rule_body(oh.get('/rules/' + UID)) != desired:
            raise RuntimeError('enabled collector definition drift')
        print('observational_rule=enabled_provisional', flush=True)
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            live = oh.get('/items/' + ITEM)
            try:
                row = json.loads(live['state'])
            except (TypeError, ValueError):
                row = {}
            fields = row.get('fields', {})
            if row.get('basis') == 'native_runtime_inputs_v1' and all(
                fields.get(key, {}).get('status') == 'valid' for key in
                ('battery.dc_current_ca', 'battery.dc_voltage_cv', 'battery.ttd_min', 'battery.ttf_min')):
                persisted = history()
                if any(record['state'] == live['state'] for record in persisted):
                    if len(persisted) > 20:
                        raise RuntimeError('excessive runtime evidence writes during qualification')
                    print(json.dumps({'status': 'natural_receipt_verified', 'sequence': row['sequence'],
                                      'history_rows': len(persisted), 'streamEpoch': row['streamEpoch']}),
                          flush=True)
                    return
            time.sleep(2)
        raise RuntimeError('natural four-field receipt and JDBC row not verified')
    except Exception:
        if rule_created:
            try:
                enabled(False)
                print('observational_rule=disabled_after_failure', flush=True)
            except Exception:
                print('URGENT: observational rule disable failed', file=sys.stderr)
        if not rule_enabled:
            # Before activation, remove only this transaction's new Item/rule.
            if rule_created:
                try:
                    request('DELETE', '/rules/' + UID)
                except Exception:
                    print('URGENT: new disabled rule removal failed', file=sys.stderr)
            if item_installed and LIVE_ITEM.exists() and LIVE_ITEM.read_bytes() == ITEM_SOURCE.read_bytes():
                LIVE_ITEM.unlink()
            install(directory / 'jdbc.persist', LIVE_JDBC, OLD_JDBC_SHA)
            wait_for(lambda: live_strategy_is(directory / 'jdbc.persist'), 'original JDBC rollback', attempts=80)
            print('preactivation_rollback=verified', flush=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='perform guarded production installation')
    args = parser.parse_args()
    descriptor = preflight()
    print(json.dumps({'status': 'preflight_ok', 'candidate_rule': UID,
                      'old_jdbc_sha256': OLD_JDBC_SHA, 'new_jdbc_sha256': NEW_JDBC_SHA,
                      'source_sha256': SOURCE_SHA, 'pumps': 'OFF'}), flush=True)
    if args.apply:
        apply(descriptor)


if __name__ == '__main__':
    os.umask(0o077)
    main()
