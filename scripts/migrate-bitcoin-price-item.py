#!/usr/bin/env python3
"""Attended Bitcoin price Item/link file transfer with private recovery data.

--check is read-only. --apply backs up Item34, preserves a fixed JDBC prefix,
and waits for a natural Exec receipt after file ownership. A failed provider
transfer rolls back the Item/link; database restore is deliberately manual.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('bitcoin_price_preflight',
    ROOT / 'scripts/preflight-bitcoin-price-item.py')
preflight = module_from_spec(spec)
spec.loader.exec_module(preflight)

oh = preflight.oh
SOURCE = preflight.SOURCE
TARGET = preflight.TARGET
ITEM = preflight.ITEM
CHANNEL = preflight.CHANNEL
SOURCE_SHA256 = preflight.SOURCE_SHA256
BACKUP_ROOT = Path('/home/sat/.local/state/openhab-config-migration')
ITEM_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.items.Item.json')
LINK_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.thing.link.ItemChannelLink.json')
RELEASE_READY = True  # Operator-approved attended Item/link cutover only.


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def same_number(left, right):
    try:
        a, b = Decimal(str(left)), Decimal(str(right))
        return a.is_finite() and b.is_finite() and a == b
    except (InvalidOperation, TypeError):
        return False


def get_item():
    try:
        return oh.get('/items/' + ITEM + '?metadata=.*')
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def links():
    return [entry for entry in oh.get('/links') if entry.get('itemName') == ITEM]


def members():
    return {entry['name'] for entry in oh.get('/items?recursive=false')
            if 'BTC_Price' in entry.get('groupNames', [])}


def group_unchanged():
    group = oh.get('/items/BTC_Price?metadata=.*')
    return (group.get('editable') is True and group.get('type') == 'Group'
            and group.get('label') == 'BTC Price'
            and group.get('metadata') == {
                'semantics': {'value': 'Equipment', 'editable': False}})


def exact_item(entry, *, file_owned):
    return (isinstance(entry, dict)
            and entry.get('editable') is (not file_owned)
            and entry.get('name') == ITEM and entry.get('type') == 'Number'
            and entry.get('label') == ('Bitcoin Price' if file_owned else '[%.0f ]')
            and (entry.get('category') or None) is None
            and entry.get('groupNames') == ['BTC_Price']
            and entry.get('tags') == [] and not entry.get('metadata')
            and (not file_owned or
                 (entry.get('stateDescription') or {}).get('pattern') == '%.0f USD')
            and preflight.finite_number(entry.get('state')))


def exact_link(entry, *, file_owned):
    return (entry.get('editable') is (not file_owned)
            and entry.get('itemName') == ITEM
            and entry.get('channelUID') == CHANNEL
            and not entry.get('configuration'))


def ready(*, file_owned):
    entry = get_item()
    found = links()
    return (exact_item(entry, file_owned=file_owned)
            and len(found) == 1 and exact_link(found[0], file_owned=file_owned)
            and members() == {ITEM, 'BTC_Price_24h_PercentChange'}
            and group_unchanged())


def absent():
    return get_item() is None and not links()


def wait(predicate, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except (OSError, RuntimeError, ValueError, KeyError):
            pass
        time.sleep(1)
    return False


def private_file(directory, name, body):
    path = directory / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def backup(original, original_link, prefix):
    root = BACKUP_ROOT.lstat()
    require(stat.S_ISDIR(root.st_mode) and root.st_uid == os.getuid()
            and stat.S_IMODE(root.st_mode) == 0o700,
            'private backup root owner or mode unsafe')
    directory = BACKUP_ROOT / ('bitcoin-price-'
        + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    directory.mkdir(mode=0o700)
    try:
        private_file(directory, 'rest-and-prefix.json', json.dumps({
            'item': original, 'link': original_link, 'history_prefix': prefix,
            'source_sha256': SOURCE_SHA256}, sort_keys=True).encode())
        private_file(directory, 'item-jsondb.json', ITEM_DB.read_bytes())
        private_file(directory, 'link-jsondb.json', LINK_DB.read_bytes())
        archive = directory / 'item0034.dump'
        descriptor = os.open(archive,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as output:
            result = subprocess.run(['sudo', '-n', '-u', 'postgres', 'pg_dump',
                '--format=custom', '--no-owner', '--no-privileges',
                '--table=public.item0034', '--dbname=openhab'],
                stdout=output, stderr=subprocess.PIPE, timeout=180)
            output.flush()
            os.fsync(output.fileno())
        require(result.returncode == 0 and archive.stat().st_size > 0,
                'private Bitcoin price table dump failed')
        verified = subprocess.run(['pg_restore', '--file=/dev/null', str(archive)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                  timeout=180)
        require(verified.returncode == 0, 'Bitcoin price table archive unreadable')
        digest = sha256()
        with archive.open('rb') as saved:
            for chunk in iter(lambda: saved.read(1024 * 1024), b''):
                digest.update(chunk)
        private_file(directory, 'archive-proof.json', json.dumps({
            'archive': 'item0034.dump', 'bytes': archive.stat().st_size,
            'sha256': digest.hexdigest(), 'pg_restore_stream_readable': True},
            sort_keys=True).encode())
        handle = os.open(directory, os.O_DIRECTORY)
        try:
            os.fsync(handle)
        finally:
            os.close(handle)
    except BaseException:
        # No provider mutation has happened yet. Remove only this newly created,
        # incomplete backup; a fully verified backup is never pruned here.
        shutil.rmtree(directory)
        raise
    return directory


def request(method, path, body=None):
    headers = {'Authorization': 'Bearer ' + oh.token()}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    try:
        with urlopen(Request(oh.BASE + path, method=method, data=body,
                             headers=headers), timeout=15) as response:
            require(response.status in (200, 201, 202, 204),
                    'Bitcoin price REST mutation refused')
    except HTTPError as error:
        raise RuntimeError('Bitcoin price ' + method + ' HTTP '
                           + str(error.code)) from None


def rollback(directory, original, original_link):
    if TARGET.exists() or TARGET.is_symlink():
        require(not TARGET.is_symlink() and sha256(TARGET.read_bytes()).hexdigest()
                == SOURCE_SHA256, 'Bitcoin price file changed; manual rollback needed')
        TARGET.rename(directory / 'failed-file.items')
        require(wait(absent, 60), 'Bitcoin file Item/link did not withdraw')
    if get_item() is None:
        definition = {key: original[key]
                      for key in ('name', 'type', 'label', 'category', 'tags', 'groupNames')
                      if key in original}
        request('PUT', '/items/' + ITEM, json.dumps(definition).encode())
    if not links():
        definition = {key: original_link[key]
                      for key in ('itemName', 'channelUID', 'configuration')}
        request('PUT', '/links/' + ITEM + '/' + quote(CHANNEL, safe=''),
                json.dumps(definition).encode())
    require(wait(lambda: ready(file_owned=False), 120),
            'managed Bitcoin price Item/link/Group rollback failed')


def natural_receipt_after(after):
    entry = get_item()
    if not exact_item(entry, file_owned=True):
        return False
    receipt = oh.get('/items/BTC_Output_Receipt_JSON').get('state')
    try:
        payload = json.loads(receipt)
        return (payload.get('version') == 1
                and payload.get('field') == 'bitcoin.usd'
                and type(payload.get('receivedAt')) is int
                and payload['receivedAt'] > int(after.timestamp() * 1000)
                and same_number(payload.get('price'), entry.get('state')))
    except (ValueError, TypeError):
        return False


def main(apply):
    verified = preflight.check()
    if not apply:
        print(json.dumps(verified, sort_keys=True))
        return
    require(RELEASE_READY, 'Bitcoin price live transfer is not release-qualified')
    original = get_item()
    found = links()
    require(exact_item(original, file_owned=False)
            and len(found) == 1 and exact_link(found[0], file_owned=False),
            'Bitcoin price changed after preflight')
    original_link = found[0]
    prefix = verified['history_prefix']
    directory = backup(original, original_link, prefix)
    print('private_backup=' + str(directory), flush=True)
    changed = False
    try:
        require(ready(file_owned=False), 'Bitcoin price managed source drifted')
        require(preflight.history.digest_history(
            datetime.fromisoformat(prefix['before_utc'])) == prefix,
            'Bitcoin historical prefix changed before transfer')
        changed = True
        request('DELETE', '/links/' + ITEM + '/' + quote(CHANNEL, safe=''))
        require(wait(lambda: not links(), 30), 'managed Bitcoin link did not withdraw')
        request('DELETE', '/items/' + ITEM)
        require(wait(absent, 30), 'managed Bitcoin Item did not withdraw')
        require(sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_SHA256,
                'Bitcoin price source changed during transfer')
        subprocess.run(['install', '-m', '0644', str(SOURCE), str(TARGET)],
                       check=True, timeout=15)
        require(sha256(TARGET.read_bytes()).hexdigest() == SOURCE_SHA256,
                'installed Bitcoin price source differs')
        require(wait(lambda: ready(file_owned=True), 90),
                'file Bitcoin price Item/link/Group failed')
        require(preflight.history.digest_history(
            datetime.fromisoformat(prefix['before_utc'])) == prefix,
            'Bitcoin historical prefix changed after transfer')
        installed_at = datetime.now(timezone.utc)
        require(wait(lambda: natural_receipt_after(installed_at), 120),
                'file-owned Bitcoin price did not receive a natural Exec update')
        require(oh.get('/rules/' + preflight.RULE).get('status') ==
                {'status': 'IDLE', 'statusDetail': 'NONE'},
                'Bitcoin percentage rule unhealthy after transfer')
    except BaseException:
        if changed:
            rollback(directory, original, original_link)
            require(preflight.history.digest_history(
                datetime.fromisoformat(prefix['before_utc'])) == prefix,
                'Bitcoin historical prefix changed during rollback')
            print('managed_rollback_verified=true', flush=True)
        raise
    print(json.dumps({'status': 'file_provider_verified', 'item': ITEM,
        'jdbc_item_id': 34, 'history_prefix_rows_preserved': prefix['rows'],
        'natural_exec_receipt_verified': True,
        'source_sha256': SOURCE_SHA256, 'backup': str(directory)},
        sort_keys=True), flush=True)


if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-bitcoin-price-item.py --check|--apply')
    main(apply=sys.argv[1:] == ['--apply'])
