#!/usr/bin/env python3
"""Attended four-Item provider transfer. No telemetry writes or rule execution."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from decimal import Decimal
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'openhab/scripts'), '/home/sat/Solar_PV/analytics/src']
import openhab_sanity_check as oh
from extrema_item_source import NAMES, render
from earthship_energy.db import parse_openhab_jdbc_config
import psycopg2

SOURCE = ROOT / 'openhab/file-config/items/temperature-extrema.items'
TARGET = Path('/etc/openhab/items/temperature-extrema.items')
RULE = 'temp-highlow-24h'
IDS = {'IndoorTemp_24h_Low': 178, 'IndoorTemp_24h_High': 179,
       'OutdoorTemp_24h_Low': 180, 'OutdoorTemp_24h_High': 181}
FIELDS = ('name', 'type', 'label', 'category', 'groupNames', 'tags')


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def quantity(value):
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)) (°[FC])', str(value))
    if not match:
        raise ValueError('finite explicit temperature quantity required')
    return Decimal(match[1]), match[2]


def item(name):
    try:
        return oh.get('/items/' + name + '?metadata=.*')
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def request(path, method, value=None):
    data = json.dumps(value).encode() if value is not None else None
    content = 'application/json'
    if isinstance(value, bool):
        data = str(value).lower().encode(); content = 'text/plain'
    with urlopen(Request(oh.BASE + path, data=data, method=method,
        headers={'Authorization': 'Bearer ' + oh.token(), 'Content-Type': content}), timeout=15) as response:
        require(response.status in (200, 201, 202, 204), 'REST mutation failed')


def validate(actual, original, provider):
    require(actual is not None and actual.get('editable') is provider, 'wrong provider')
    for field in (*FIELDS, 'metadata', 'stateDescription'):
        left, right = actual.get(field), original.get(field)
        if field in ('tags', 'groupNames'):
            left, right = sorted(left or []), sorted(right or [])
        require(left == right, 'definition mismatch: ' + original['name'] + ':' + field)


def wait(name, provider, original=None):
    last_error = None
    for _ in range(100):
        actual = item(name)
        if provider is None and actual is None:
            return
        if actual is not None and actual.get('editable') is provider:
            try:
                validate(actual, original, provider)
                if quantity(actual.get('state')) == quantity(original['state']):
                    return
            except (ValueError, RuntimeError) as error:
                last_error = error
        time.sleep(.2)
    raise RuntimeError('provider/state/unit recovery timeout: ' + name) from last_error


def rules():
    return {r['uid']: {k: v for k, v in r.items() if k not in
        ('status', 'editable', 'configDescriptions', 'templateState')} for r in oh.get('/rules')}


def main():
    require(not TARGET.exists() and not TARGET.is_symlink(), 'target already exists')
    source = SOURCE.read_bytes()
    originals = {name: item(name) for name in NAMES}
    links = oh.get('/links'); before_rules = rules()
    require(render(list(originals.values()), links).encode() == source, 'source/live drift')
    require(oh.get('/rules/' + RULE)['status'] == {'status': 'IDLE', 'statusDetail': 'NONE'}, 'writer not idle')
    for original in originals.values():
        quantity(original['state'])
    os.umask(0o077)
    receipt = Path(tempfile.mkdtemp(prefix='temperature-extrema-transfer-'))
    print('private_receipt=' + str(receipt), flush=True)

    def save(name, data):
        body = json.dumps(data, indent=2, default=str) + '\n'
        patch = '*** Begin Patch\n*** Add File: ' + str(receipt / name) + '\n'
        patch += ''.join('+' + line + '\n' for line in body.splitlines()) + '*** End Patch\n'
        subprocess.run(['apply_patch'], input=patch, text=True, check=True, capture_output=True)

    db = psycopg2.connect(**parse_openhab_jdbc_config('/var/lib/openhab/config/org/openhab/jdbc.config').connect_kwargs,
                          connect_timeout=5)
    db.set_session(readonly=True, autocommit=True)

    def history(name, cutoff=None):
        with db.cursor() as cursor:
            cursor.execute("SET statement_timeout='10s'")
            cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s', (name,))
            require(cursor.fetchall() == [(IDS[name],)], 'JDBC identity drift')
            cursor.execute("SELECT count(*),max(time),md5(string_agg(md5(time::text || ':' || value::text),'' ORDER BY time,value)) FROM public.item"
                + format(IDS[name], '04d') + (' WHERE time<=%s' if cutoff else ''), (cutoff,) if cutoff else ())
            return cursor.fetchone()

    removed = False; paused = False; succeeded = False; recovered = False
    try:
        save('before.json', {'items': originals, 'rules': before_rules, 'links': links})
        paused = True
        request('/rules/' + RULE + '/enable', 'POST', False)
        for _ in range(100):
            if oh.get('/rules/' + RULE)['status'] == {'status': 'UNINITIALIZED', 'statusDetail': 'DISABLED'}:
                break
            time.sleep(.2)
        else:
            raise RuntimeError('writer did not disable')
        originals = {name: item(name) for name in NAMES}
        require(render(list(originals.values()), oh.get('/links')).encode() == source, 'paused definition drift')
        before = {name: history(name) for name in NAMES}
        for name, original in originals.items():
            require(before[name][0] > 0, 'no persisted recovery state')
            value, unit = quantity(original['state'])
            require(unit == '°F', 'unreviewed temperature unit')
            with db.cursor() as cursor:
                cursor.execute('SELECT value::text FROM public.item' + format(IDS[name], '04d') + ' ORDER BY time DESC LIMIT 1')
                require(Decimal(cursor.fetchone()[0]) == value, 'latest state not persisted')
        save('paused.json', {'items': originals, 'history': before})
        require(SOURCE.read_bytes() == source and rules() == before_rules and oh.get('/links') == links, 'pre-delete drift')

        def remove_managed():
            nonlocal removed
            for name in NAMES:
                validate(item(name), originals[name], True)
                removed = True
                request('/items/' + name, 'DELETE'); wait(name, None)

        def verify(provider):
            for name in NAMES:
                wait(name, provider, originals[name])

        remove_managed()
        subprocess.run(['install', '-m', '644', str(SOURCE), str(TARGET)], check=True)
        verify(False)
        require(TARGET.read_bytes() == source, 'installed source mismatch')
        TARGET.rename(receipt / 'rollback.items')
        for name in NAMES:
            wait(name, None)
            request('/items/' + name, 'PUT', {k: originals[name][k] for k in FIELDS})
        verify(True)
        remove_managed()
        (receipt / 'rollback.items').rename(TARGET)
        verify(False)
        require(all(history(name, before[name][1]) == before[name] for name in NAMES), 'history changed')
        require(rules() == before_rules and oh.get('/links') == links, 'rules or links changed')
        save('verified.json', {'file_provider': True, 'same_unit_state_restored': True,
            'managed_rollback_and_return_verified': True, 'history_and_definitions_preserved': True})
        succeeded = True
    finally:
        try:
            if removed and not succeeded:
                if TARGET.exists():
                    require(not TARGET.is_symlink() and TARGET.read_bytes() == source, 'refusing unknown target rollback')
                    TARGET.rename(receipt / 'failed.items')
                    for name in NAMES:
                        wait(name, None)
                for name in NAMES:
                    if item(name) is None:
                        request('/items/' + name, 'PUT', {k: originals[name][k] for k in FIELDS})
                    wait(name, True, originals[name])
                recovered = True
                save('recovered.json', {'original_managed_provider_and_states_restored': True})
        finally:
            db.close()
            if paused and (succeeded or recovered or not removed):
                request('/rules/' + RULE + '/enable', 'POST', True)
                require(oh.get('/rules/' + RULE)['status']['status'] in ('IDLE', 'RUNNING'), 'writer did not recover')
            elif paused:
                print('RECOVERY_INCOMPLETE: writer deliberately remains disabled; inspect private receipt', flush=True)
    print('four_item_transfer_and_rollback_verified=true; writer_enabled=true', flush=True)


if __name__ == '__main__':
    if sys.argv[1:] != ['--execute-approved']:
        raise SystemExit('Attended execution requires --execute-approved')
    main()
