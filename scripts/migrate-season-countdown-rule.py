#!/usr/bin/env python3
"""Guarded, no-restart handoff of the display-only season countdown rule.

Default --check is read-only. --apply saves a private managed-rule backup,
withdraws that provider, installs the exact file rule, and rolls back on any
failed provider check. It never posts test Item values or commands hardware.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402

RULE = 'update_days_until_season'
SCRIPT_SHA = 'd43b3f993991966ade5d428bc4ff6af603a253a06f336ff93221cc22cc332311'
SOURCE = ROOT / 'openhab/file-config/automation/js/update_days_until_season.js'
SOURCE_SHA = 'd101eff0c4acf86ad900637e28cc7b30c1cf1185c5b3bcd116bef65e2114ed36'
TARGET = Path('/etc/openhab/automation/js/update_days_until_season.js')
BACKUP_ROOT = Path('/home/sat/.local/state')
FIELDS = ('uid', 'name', 'description', 'tags', 'triggers', 'conditions', 'actions')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def request(method, path, body=None):
    data = json.dumps(body, separators=(',', ':')).encode() if body is not None else None
    req = Request(oh.BASE + path, method=method, data=data,
                  headers={'Authorization': 'Bearer ' + oh.token(),
                           'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=12) as response:
            return response.status
    except HTTPError as error:
        raise RuntimeError('OpenHAB ' + method + ' HTTP ' + str(error.code)) from None


def rule_or_none():
    try:
        return oh.get('/rules/' + RULE)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def wait_rule(predicate, *, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        current = rule_or_none()
        if predicate(current):
            return current
        time.sleep(1)
    raise RuntimeError('season rule provider timeout')


def file_rule_ok(row):
    return (isinstance(row, dict) and row.get('uid') == RULE
            and row.get('editable') is False
            and row.get('status') in ({'status': 'IDLE', 'statusDetail': 'NONE'},
                                      {'status': 'RUNNING', 'statusDetail': 'NONE'})
            and len(row.get('triggers', [])) == 1
            and row['triggers'][0].get('type') == 'core.ItemStateChangeTrigger'
            and row['triggers'][0].get('configuration', {}).get('itemName') == 'Sun_TimeLeft')


def managed_rule_ok(row, original):
    return (isinstance(row, dict) and row.get('editable') is True
            and all(row.get(field) == original.get(field) for field in FIELDS)
            and row.get('status') in ({'status': 'IDLE', 'statusDetail': 'NONE'},
                                      {'status': 'RUNNING', 'statusDetail': 'NONE'}))


def preflight():
    require(not TARGET.exists() and not TARGET.is_symlink(), 'season rule target exists')
    require(digest(SOURCE.read_bytes()) == SOURCE_SHA, 'season rule source changed')
    service = subprocess.run(['systemctl', 'is-active', 'openhab.service'],
                             check=True, text=True, capture_output=True, timeout=5)
    require(service.stdout.strip() == 'active', 'OpenHAB is not active')
    original = rule_or_none()
    require(original is not None and original.get('uid') == RULE
            and original.get('editable') is True
            and original.get('status') == {'status': 'IDLE', 'statusDetail': 'NONE'}
            and len(original.get('triggers', [])) == 1
            and original['triggers'][0].get('type') == 'core.ItemStateChangeTrigger'
            and original['triggers'][0].get('configuration', {}).get('itemName') == 'Sun_TimeLeft'
            and not original.get('conditions')
            and len(original.get('actions', [])) == 1,
            'managed season rule changed or unhealthy')
    require(digest(original['actions'][0]['configuration']['script'].encode()) == SCRIPT_SHA,
            'managed season script changed')
    for name, type_name in (('Sun_TimeLeft', 'Number:Time'),
                            ('Sun_NextSeason', 'String'),
                            ('DaysUntilNextSeason', 'String')):
        item = oh.get('/items/' + name)
        require(item.get('type') == type_name and item.get('state') not in
                (None, 'NULL', 'UNDEF'), 'season display Item unavailable: ' + name)
    require(sum(rule.get('uid') == RULE for rule in oh.get('/rules')) == 1,
            'season rule identity is not unique')
    return original, oh.get('/items/DaysUntilNextSeason')['state']


def backup(original):
    directory = Path(tempfile.mkdtemp(prefix='season-rule-', dir=BACKUP_ROOT))
    os.chmod(directory, 0o700)
    body = json.dumps(original, sort_keys=True, separators=(',', ':')).encode()
    path = directory / 'managed-rule.json'
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(body)
        output.flush()
        os.fsync(output.fileno())
    require(digest(path.read_bytes()) == digest(body), 'managed backup differs')
    return directory


def install():
    fd, name = tempfile.mkstemp(prefix='.season-rule-', suffix='.js', dir=TARGET.parent)
    staged = Path(name)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, 'wb') as output:
            output.write(SOURCE.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        require(digest(staged.read_bytes()) == SOURCE_SHA, 'staged season source differs')
        os.replace(staged, TARGET)
        require(digest(TARGET.read_bytes()) == SOURCE_SHA, 'installed season source differs')
    finally:
        if staged.exists():
            staged.unlink()


def apply(original, old_state):
    directory = backup(original)
    print('private_backup=' + str(directory), flush=True)
    changed = success = False
    try:
        require(rule_or_none() == original, 'managed rule changed during backup')
        require(oh.get('/items/DaysUntilNextSeason')['state'] == old_state,
                'season output changed during backup')
        changed = True
        require(request('DELETE', '/rules/' + RULE) in (200, 204),
                'managed season withdrawal refused')
        wait_rule(lambda row: row is None)
        install()
        wait_rule(file_rule_ok)
        require(sum(rule.get('uid') == RULE for rule in oh.get('/rules')) == 1,
                'season rule duplicated after file install')
        require(oh.get('/items/DaysUntilNextSeason')['state'] == old_state,
                'season display state changed during handoff')
        success = True
        print('status=file_provider_provisional; natural_update_pending=true', flush=True)
    finally:
        if changed and not success:
            if TARGET.exists():
                require(not TARGET.is_symlink() and digest(TARGET.read_bytes()) == SOURCE_SHA,
                        'unexpected season file target; manual rollback required')
                TARGET.rename(directory / 'failed-candidate.js')
                wait_rule(lambda row: row is None)
            current = rule_or_none()
            if current is None:
                payload = {field: original[field] for field in FIELDS if field in original}
                require(request('POST', '/rules', payload) == 201,
                        'managed season rollback refused')
            elif not managed_rule_ok(current, original):
                raise RuntimeError('unknown season provider during rollback')
            wait_rule(lambda row: managed_rule_ok(row, original))
            require(oh.get('/items/DaysUntilNextSeason')['state'] == old_state,
                    'season output changed during rollback')
            print('managed_season_rollback_verified=true', flush=True)


def main():
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-season-countdown-rule.py --check|--apply')
    original, state = preflight()
    if sys.argv[1:] == ['--check']:
        print('season_rule_preflight=passed; provider=managed; writes=0')
        return
    apply(original, state)


if __name__ == '__main__':
    main()
