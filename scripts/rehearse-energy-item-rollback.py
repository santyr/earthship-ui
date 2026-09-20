#!/usr/bin/env python3
"""Attended observational Item file->managed->file rollback rehearsal only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path[:0] = ['/home/sat/earthship-ui/openhab/scripts', '/home/sat/Solar_PV/analytics/src']
import openhab_sanity_check as oh
from earthship_energy.db import parse_openhab_jdbc_config
import psycopg2


def main():
    name = 'Energy_Analytics_JSON'
    target = Path('/etc/openhab/items/energy-analytics.items')
    source = Path('/home/sat/earthship-ui/openhab/file-config/items/energy-analytics.items').read_bytes()
    assert not target.is_symlink() and target.read_bytes() == source
    expected = dict(name=name, type='String', label='Energy analytics summary', category='', tags=[], groupNames=[])

    def run(args):
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30).stdout.strip()

    def show(unit, prop):
        return run(['systemctl', '--user', 'show', unit, '-p', prop, '--value'])

    def get():
        try:
            return oh.get('/items/' + name + '?metadata=all')
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def wait(provider):
        for _ in range(100):
            item = get()
            if (provider is None and item is None) or (item is not None and item.get('editable') is provider):
                return item
            time.sleep(.2)
        raise RuntimeError('provider transition not observed')

    def valid(item):
        assert item is not None
        actual = {k: item.get(k) for k in expected}
        actual['category'] = actual['category'] or ''
        assert actual == expected
        assert not item.get('metadata')

    def request(method):
        req = Request(oh.BASE + '/items/' + name, method=method,
                      data=json.dumps(expected).encode() if method == 'PUT' else None,
                      headers={'Authorization': 'Bearer ' + oh.token(), 'Content-Type': 'application/json'})
        with urlopen(req, timeout=15) as response:
            assert response.status in (200, 201, 202, 204)

    def rules():
        return {r['uid']: {k: v for k, v in r.items() if k not in
                ('status', 'editable', 'configDescriptions', 'templateState')} for r in oh.get('/rules')}

    def restored(provider, state):
        item = wait(provider); valid(item)
        for _ in range(50):
            item = get()
            if item['state'] == state:
                return
            time.sleep(.2)
        raise RuntimeError('exact persisted state did not restore before publication')

    original = get(); valid(original); assert original['editable'] is False
    assert not [x for x in oh.get('/links') if x.get('itemName') == name]
    assert show('energy-ui-publish.timer', 'ActiveState') == 'active'
    protected = rules()
    os.umask(0o077)
    receipt = Path(tempfile.mkdtemp(prefix='energy-item-rollback-'))
    moved = receipt / 'energy-analytics.items'

    def save(filename, value):
        body = json.dumps(value, indent=2, default=str)
        patch = '*** Begin Patch\n*** Add File: ' + str(receipt / filename) + '\n'
        patch += ''.join('+' + line + '\n' for line in body.splitlines()) + '*** End Patch\n'
        subprocess.run(['apply_patch'], input=patch, text=True, capture_output=True, check=True)

    connection = psycopg2.connect(**parse_openhab_jdbc_config(
        '/var/lib/openhab/config/org/openhab/jdbc.config').connect_kwargs, connect_timeout=5)
    connection.set_session(readonly=True, autocommit=True)
    try:
        run(['systemctl', '--user', 'stop', 'energy-ui-publish.timer'])
        for _ in range(100):
            if show('energy-ui-publish.service', 'ActiveState') == 'inactive':
                break
            time.sleep(.2)
        else:
            raise RuntimeError('publisher did not stop')
        time.sleep(2)
        original = get(); valid(original); assert original['editable'] is False
        with connection.cursor() as cur:
            cur.execute("SET statement_timeout='5000ms'")
            cur.execute("SELECT itemid FROM public.items WHERE itemname=%s", (name,))
            assert cur.fetchall() == [(609,)]
            cur.execute("SELECT count(*),max(time),md5(string_agg(md5(value),'' ORDER BY time,value)) FROM public.item0609")
            history = cur.fetchone()
        save('before.json', {'item': original, 'history': history, 'rules': protected})
        print('private_receipt=' + str(receipt), flush=True)
        target.rename(moved); wait(None)
        request('PUT'); restored(True, original['state'])
        save('managed-restored.json', {'item': get(), 'restored_before_publication': True})
        request('DELETE'); wait(None)
        moved.rename(target); restored(False, original['state'])
        run(['systemctl', '--user', 'start', 'energy-ui-publish.service'])
        assert show('energy-ui-publish.service', 'Result') == 'success'
        item = get(); valid(item); assert item['editable'] is False
        assert json.loads(item['state'])['schema'] == 'earthship-energy-ui/v3'
        assert target.read_bytes() == source and rules() == protected
        with connection.cursor() as cur:
            cur.execute("SELECT itemid FROM public.items WHERE itemname=%s", (name,))
            assert cur.fetchall() == [(609,)]
            cur.execute("SELECT count(*),max(time),md5(string_agg(md5(value),'' ORDER BY time,value)) FROM public.item0609 WHERE time<=%s", (history[1],))
            assert cur.fetchone() == history
        save('verified.json', {'verified_at': datetime.now(timezone.utc).isoformat(),
             'both_providers_restored_before_publication': True, 'history_preserved': True,
             'rules_unchanged': True, 'file_sha256': hashlib.sha256(source).hexdigest()})
        print('rollback_and_return_verified=true', flush=True)
    finally:
        # Restore the original file provider if the managed leg failed.
        try:
            if moved.exists():
                current = get()
                if current is not None:
                    valid(current)
                    assert current['editable'] is True
                    request('DELETE'); wait(None)
                moved.rename(target); wait(False)
        finally:
            connection.close()
            run(['systemctl', '--user', 'start', 'energy-ui-publish.timer'])
            assert show('energy-ui-publish.timer', 'ActiveState') == 'active'
            print('publisher_timer_restored=true', flush=True)


if __name__ == '__main__':
    main()
