#!/usr/bin/env python3
"""Guarded, display-only Bitcoin Exec Thing provider transfer.

--check is read-only. --apply requires the release gate, retains private
managed-provider recovery data, preserves Item/link definitions and a fixed
JDBC price prefix, then requires a new real successful durable output receipt.
No OpenHAB restart, Item-definition mutation, direct database write or hardware
command exists. Normal binding-driven price/receipt persistence continues.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p = load('bitcoin_exec_preflight', 'preflight-bitcoin-exec-thing.py')
history = load('bitcoin_history_digest', 'bitcoin-price-history-digest.py')
backup_tools = load('openmeteo_thing_migration', 'migrate-openmeteo-things.py')
TARGET = p.TARGET
SOURCE_SHA256 = 'becb9ed6081f7a5780dc943a055217bed3907ec0bc55fc3793aa0ec401fff26a'
DELETE_PATH = '/things/' + quote(p.UID, safe='') + '?force=true'
BACKUP_ROOT = backup_tools.BACKUP_ROOT
FEED = Path('/etc/openhab/scripts/bitcoin.py')
WHITELIST = Path('/etc/openhab/misc/exec.whitelist')
RELEASE_READY = False


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def request(method, path, body=None):
    allowed = method == 'DELETE' and path == DELETE_PATH and body is None
    if method == 'POST' and path == '/things' and isinstance(body, bytes):
        definition = json.loads(body)
        allowed = (isinstance(definition, dict)
                   and set(definition) == {'UID', 'thingTypeUID', 'label', 'configuration'}
                   and definition == {'UID': p.UID, 'thingTypeUID': 'exec:command',
                                      'label': 'BTC_Price', 'configuration': p.CONFIG})
    require(allowed, 'Bitcoin Thing REST mutation outside exact scope')
    headers = {'Authorization': 'Bearer ' + p.oh.token()}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    try:
        with urlopen(Request(p.oh.BASE + path, method=method, data=body,
                             headers=headers), timeout=15) as response:
            require(response.status in (200, 201, 202, 204),
                    'Bitcoin Thing REST mutation refused')
    except HTTPError as error:
        raise RuntimeError('Bitcoin Thing REST HTTP ' + str(error.code)) from None


def get_thing():
    try:
        return p.oh.get('/things/' + p.UID + '?summary=false')
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def wait(predicate, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except (OSError, RuntimeError, KeyError, ValueError):
            pass
        time.sleep(1)
    return False


def item_definition(item):
    # Enriched 5.2.1 Item DTOs carry rolling state and update/change timestamps.
    # These are observations, not provider-owned definitions.
    return {key: value for key, value in item.items()
            if key not in {'state', 'lastState', 'lastStateChange', 'lastStateUpdate',
                           'transformedState', 'link', 'members'}}


def dependents():
    items = {name: item_definition(p.oh.get('/items/' + name + '?metadata=.*'))
             for name in p.LINKS}
    group = p.oh.get('/items/BTC_Price?metadata=.*')
    members = sorted(member['name'] for member in group.get('members', []))
    return {'items': items, 'group': item_definition(group), 'members': members}


def unchanged_dependents(original):
    current = dependents()
    return all(current[key] == original[key] for key in ('items', 'group', 'members'))


def withdrawal_items_equal(current, original):
    """Permit only derived readOnly=true disappearing at an absent provider.

    Final provider and rollback checks retain the full enriched definition.
    """
    normalized = deepcopy(current)
    for name in p.LINKS:
        before = original.get('items', {}).get(name, {}).get('stateDescription', {})
        after = normalized.get('items', {}).get(name, {}).get('stateDescription', {})
        if before.get('readOnly') is True and after.get('readOnly') is False:
            after['readOnly'] = True
    return all(normalized.get(key) == original.get(key)
               for key in ('items', 'group', 'members'))


def withdrawal_dependents(original):
    if get_thing() is not None:
        return False
    links = [link for link in p.oh.get('/links')
             if link.get('channelUID', '').startswith(p.UID + ':')]
    return (sorted(links, key=lambda link: link['itemName']) ==
            sorted(original['links'], key=lambda link: link['itemName'])
            and withdrawal_items_equal(dependents(), original))


def runtime_sources():
    p.validate_source(p.SOURCE)
    require(sha256(p.SOURCE.read_bytes()).hexdigest() == SOURCE_SHA256,
            'Bitcoin Thing source hash changed')
    body = FEED.read_bytes()
    require(body == (ROOT / 'openhab/scripts/bitcoin_price.sh').read_bytes(),
            'installed Bitcoin script differs from reviewed credential-free source')
    whitelist = WHITELIST.read_bytes()
    require(p.CONFIG['command'] in {line.strip() for line in whitelist.decode().splitlines()
                                   if line.strip() and not line.lstrip().startswith('#')},
            'existing Bitcoin command is not whitelisted')
    transform = Path('/etc/openhab/transform/bitcoin_output_receipt.js').read_bytes()
    require(transform == (ROOT / 'openhab/transform/bitcoin_output_receipt.js').read_bytes(),
            'installed Bitcoin receipt transform changed')
    return {'feed_sha256': sha256(body).hexdigest(),
            'whitelist_sha256': sha256(whitelist).hexdigest(),
            'receipt_transform_sha256': sha256(transform).hexdigest()}


def valid_receipt(raw, state, *, after, now):
    try:
        require(isinstance(raw, str) and len(raw.encode()) <= 1024,
                'receipt missing or oversized')
        payload = json.loads(raw)
        price, at = payload['price'], payload['receivedAt']
        return (set(payload) == {'version', 'field', 'receivedAt', 'price'}
                and type(payload['version']) is int and payload['version'] == 1
                and payload['field'] == 'bitcoin.usd'
                and type(at) is int
                and int(after.timestamp()*1000) < at <= int(now.timestamp()*1000)
                and int(now.timestamp()*1000)-at <= 90000
                and type(price) is int and 0 < price <= 9007199254740990
                and Decimal(str(state)).is_finite() and Decimal(str(state)) == price)
    except (KeyError, ValueError, TypeError, InvalidOperation, RuntimeError):
        return False


def natural_receipt_after(after):
    raw = p.oh.get('/items/BTC_Output_Receipt_JSON').get('state')
    price = p.oh.get('/items/BTC_USD_Price').get('state')
    return valid_receipt(raw, price, after=after, now=datetime.now(timezone.utc))


def durable_receipt_after(after):
    raw = p.oh.get('/items/BTC_Output_Receipt_JSON').get('state')
    price = p.oh.get('/items/BTC_USD_Price').get('state')
    now = datetime.now(timezone.utc)
    if not valid_receipt(raw, price, after=after, now=now):
        return False
    query = urlencode({'serviceId': 'jdbc', 'boundary': 'false', 'page': 0,
                       'pagelength': 20, 'starttime': after.isoformat(),
                       'endtime': now.isoformat()})
    data = p.oh.get('/persistence/items/BTC_Output_Receipt_JSON?' + query).get('data', [])
    if not isinstance(data, list) or len(data) > 20:
        return False
    for row in data:
        if (type(row.get('time')) is int and int(after.timestamp()*1000) < row['time']
                <= int(now.timestamp()*1000) and isinstance(row.get('state'), str)):
            try:
                if json.loads(row['state']) == json.loads(raw):
                    return True
            except ValueError:
                continue
    return False


def check():
    p.check()
    original = get_thing()
    links = p.oh.get('/links')
    p.validate(original, links)
    snapshot = {'thing': original, 'links': [link for link in links
                if link.get('channelUID', '').startswith(p.UID + ':')],
                **dependents(), 'runtime_sources': runtime_sources()}
    require(all(item.get('editable') is False for item in snapshot['items'].values()),
            'Bitcoin dependent Item is not file-owned')
    require(snapshot['members'] == ['BTC_Price_24h_PercentChange', 'BTC_USD_Price'],
            'Bitcoin Group membership changed')
    require(natural_receipt_after(datetime.now(timezone.utc)-timedelta(seconds=90)),
            'Bitcoin baseline lacks a fresh successful receipt')
    cutoff = datetime.now(timezone.utc)-timedelta(minutes=2)
    return {'snapshot': snapshot, 'history_prefix': history.digest_history(cutoff),
            'source_sha256': SOURCE_SHA256}


def backup(verified):
    info = BACKUP_ROOT.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700,
            'private Bitcoin backup root owner or mode unsafe')
    directory = Path(tempfile.mkdtemp(prefix='bitcoin-exec-', dir=BACKUP_ROOT))
    try:
        backup_tools.private_file(directory, 'rest-and-prefix.json',
                                  json.dumps(verified, sort_keys=True).encode())
        for path, name in [(backup_tools.THING_DB, 'thing-jsondb.json'),
                           (backup_tools.LINK_DB, 'link-jsondb.json')]:
            body = path.read_bytes()
            require(isinstance(json.loads(body), dict), 'managed registry backup unreadable')
            backup_tools.private_file(directory, name, body)
        descriptor = os.open(directory, os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        # Only the unique, incomplete directory just created by this call.
        # No provider has been withdrawn; complete backups are never pruned.
        shutil.rmtree(directory)
        raise
    return directory


def install_source():
    p.validate_source(p.SOURCE)
    fd, name = tempfile.mkstemp(prefix='.bitcoin-price-cutover-', suffix='.tmp', dir=TARGET.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(p.SOURCE_BYTES)
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
        os.link(temporary, TARGET, follow_symlinks=False)  # refuses overwrite atomically
        parent = os.open(TARGET.parent, os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        info = TARGET.lstat()
        return info.st_dev, info.st_ino
    finally:
        temporary.unlink(missing_ok=True)


def provider_ready(original, *, file_owned):
    current = get_thing()
    if not isinstance(current, dict):
        return False
    if current.get('editable') is not (not file_owned):
        return False
    try:
        p.validate({**current, 'editable': True}, p.oh.get('/links'))
        # Preserve all channel metadata, not only the seven identities/types.
        return p.definition(current) == p.definition(original)
    except RuntimeError:
        return False


def rollback_receipt_after(after):
    return natural_receipt_after(after) and durable_receipt_after(after)


def rollback(directory, original, installed_identity):
    if TARGET.exists() or TARGET.is_symlink():
        info = TARGET.lstat()
        require(not TARGET.is_symlink() and installed_identity == (info.st_dev, info.st_ino)
                and info.st_uid == os.getuid() and TARGET.read_bytes() == p.SOURCE_BYTES,
                'Bitcoin file ownership/source drift; manual rollback needed')
        moved = directory / 'withdrawn-file.things'
        require(not moved.exists(), 'rollback preimage exists; manual rollback needed')
        TARGET.rename(moved)
        require(wait(lambda: get_thing() is None, 60), 'file Bitcoin Thing did not unload')
    current = get_thing()
    if current is None:
        definition = {key: original[key] for key in ('UID', 'thingTypeUID', 'label', 'configuration')}
        request('POST', '/things', json.dumps(definition).encode())
    require(wait(lambda: provider_ready(original, file_owned=False), 120),
            'managed Bitcoin Thing rollback failed')


def main(apply):
    if apply:
        require(RELEASE_READY, 'Bitcoin Thing release gate is off')
    verified = check()
    prefix, original = verified['history_prefix'], verified['snapshot']
    if not apply:
        return {'status': 'preflight_passed', 'uid': p.UID, 'history_prefix': prefix,
                'source_sha256': SOURCE_SHA256, 'production_writes': 0,
                'release_ready': RELEASE_READY}
    directory = backup(verified)
    print('private_backup=' + str(directory), flush=True)
    changed = False
    installed_identity = None
    phase = 'baseline_recheck'
    try:
        require(provider_ready(original['thing'], file_owned=False)
                and unchanged_dependents(original)
                and runtime_sources() == original['runtime_sources'],
                'Bitcoin baseline changed after backup')
        require(history.digest_history(datetime.fromisoformat(prefix['before_utc'])) == prefix,
                'Bitcoin fixed prefix changed before handoff')
        changed = True  # a failed response may still have withdrawn the Thing
        phase = 'managed_withdrawal'
        request('DELETE', DELETE_PATH)
        require(wait(lambda: get_thing() is None, 30), 'managed Bitcoin Thing did not withdraw')
        phase = 'withdrawal_dependent_readback'
        require(withdrawal_dependents(original),
                'Bitcoin Item/Group/link changed at provider boundary')
        phase = 'file_installation'
        installed_identity = install_source()
        phase = 'file_metadata_readback'
        require(wait(lambda: provider_ready(original['thing'], file_owned=True), 90),
                'file Bitcoin Thing/channel/link readback failed')
        installed_at = datetime.now(timezone.utc)
        phase = 'new_real_receipt'
        require(wait(lambda: natural_receipt_after(installed_at), 120),
                'new real Bitcoin output receipt missing')
        phase = 'durable_real_receipt'
        require(wait(lambda: durable_receipt_after(installed_at), 30),
                'new real Bitcoin receipt did not persist')
        phase = 'dependent_definition_readback'
        require(unchanged_dependents(original)
                and runtime_sources() == original['runtime_sources'],
                'Bitcoin dependent definitions or source changed after handoff')
        phase = 'fixed_history_readback'
        require(history.digest_history(datetime.fromisoformat(prefix['before_utc'])) == prefix,
                'Bitcoin fixed prefix changed after handoff')
    except BaseException:
        print('handoff_failed_phase=' + phase, flush=True)
        if changed:
            rollback_started = datetime.now(timezone.utc)
            rollback(directory, original['thing'], installed_identity)
            require(unchanged_dependents(original), 'Bitcoin dependents changed during rollback')
            require(wait(lambda: rollback_receipt_after(rollback_started), 120),
                    'managed real polling recovery missing')
            require(history.digest_history(datetime.fromisoformat(prefix['before_utc'])) == prefix,
                    'Bitcoin prefix conflict requires manual recovery')
            print('managed_rollback_verified=true', flush=True)
        raise
    return {'status': 'file_provider_verified', 'uid': p.UID,
            'jdbc_item_id': 34, 'history_prefix_rows_preserved': prefix['rows'],
            'source_sha256': SOURCE_SHA256, 'new_real_durable_receipt': True,
            'backup': str(directory), 'openhab_restart': False}


if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-bitcoin-exec-thing.py --check|--apply')
    try:
        print(json.dumps(main(apply=sys.argv[1:] == ['--apply']), sort_keys=True))
    except Exception:
        raise SystemExit('Bitcoin Thing migration refused; inspect private backup and safe phase receipts') from None
