#!/usr/bin/env python3
"""Run the unchanged protected Transaction only inside the disposable provider."""
import os
import sys
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('isolated_protected_sky_release',
    Path(__file__).with_name('deploy-sky-control-input.py'))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

from dataclasses import replace
import json
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path('/openhab/userdata/sky-transaction')


def guard(get, original):
    current = get('/rules/' + release.sky.UID)
    release.engine.require(release.engine.managed_rule_ok(current, original)
        and all(current.get(k) == original.get(k) for k in release.RULE_FIELDS),
        'isolated consumer changed or unhealthy')
    release.engine.require(not get('/links'), 'isolated device links must be absent')
    release.engine.require(all(get('/items/' + n)['state'] == 'OFF'
                               for n in release.sky.PUMPS), 'isolated pump not OFF')


def main(phase):
    release.engine.require(phase in ('apply', 'restore'), 'unknown transaction phase')
    release.engine.require(os.getuid() == 9001 and Path('/.dockerenv').is_file()
        and (ROOT / 'permit').is_file(), 'inspected isolated container required')
    packet = json.load(sys.stdin)  # Ephemeral token arrives by stdin, never argv/disk/stdout.
    token, original, consumer = packet['token'], packet['original'], packet['consumer']
    config = replace(release.CONFIG,
        target=Path('/openhab/conf/automation/js/sky-condition-calculator.js'))
    release.engine.require(release.engine.digest(config.source.read_bytes()) == config.source_sha,
                           'isolated candidate source drift')

    def rest(method, path, body=None):
        req = Request('http://127.0.0.1:8080/rest' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
            method=method)
        try:
            with urlopen(req, timeout=8) as response:
                data = response.read()
                return response.status, json.loads(data) if data else None
        except HTTPError as error:
            if error.code == 404: return 404, None
            raise RuntimeError('isolated REST HTTP ' + str(error.code)) from None

    def get(path):
        status, result = rest('GET', path)
        release.engine.require(status == 200, 'isolated read unavailable')
        return result

    def read(config):
        status, row = rest('GET', '/rules/' + config.uid)
        release.engine.require(status in (200, 404), 'isolated rule read failed')
        return row if status == 200 else None

    fault = [False]
    def wait(predicate, config):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            row = read(config)
            if predicate(row):
                if fault[0] and row and row.get('editable') is False:
                    fault[0] = False
                    raise RuntimeError('synthetic first file readback failure')
                return row
            time.sleep(1)
        raise RuntimeError('isolated protected provider timeout')

    provider = SimpleNamespace(rule_or_none=read,
        request=lambda method, path, body=None: rest(method, path, body)[0],
        wait_rule=wait, oh=SimpleNamespace(get=get))
    receipt = Path('/openhab/conf/sky-transaction-recovery')
    state_path = ROOT / 'owned-state.json'
    if phase == 'apply':
        receipt.mkdir(mode=0o700)
        before = {r['uid']: {k:r[k] for k in release.RULE_FIELDS if k in r}
                  for r in get('/rules') if r['uid'] != config.uid}
    else:
        release.engine.require(state_path.is_file() and not state_path.is_symlink(),
                               'isolated ownership receipt required')
        saved = json.loads(state_path.read_text())
        release.engine.require(saved['original'] == original, 'isolated managed preimage drift')
        before = saved['continuity']

    def guarded():
        guard(get, consumer)
        actual = {r['uid']: {k:r[k] for k in release.RULE_FIELDS if k in r}
                  for r in get('/rules') if r['uid'] != config.uid}
        release.engine.require(actual == before, 'isolated unrelated definition drift')

    guarded()
    if phase == 'apply':
        # Prove that a real registered file followed by failed readback restores
        # the exact original managed provider through the real transaction.
        tx = release.Transaction(original, receipt, guarded, config=config, provider=provider)
        fault[0] = True
        try:
            tx.apply()
        except RuntimeError as error:
            if str(error) != 'synthetic first file readback failure': raise
        else:
            raise RuntimeError('isolated rollback fault did not execute')
        release.engine.require(tx.managed_original(read(config)) and not config.target.exists(),
                               'isolated fault rollback mismatch')
        print('isolated_exact_fault_rollback=true', flush=True)
        tx.apply()  # Same object retains unique withdrawal numbering.
        with state_path.open('x') as stream:
            json.dump(dict(original=original, continuity=before,
                           owned_identity=tx.owned_identity, withdrawals=tx.withdrawals), stream)
        state_path.chmod(0o600)
        print('isolated_exact_file_managed_file=true', flush=True)
    else:
        tx = release.Transaction(original, receipt, guarded, config=config, provider=provider)
        tx.owned_identity = tuple(saved['owned_identity'])
        tx.withdrawals = saved['withdrawals']
        tx.to_managed()
        release.engine.require(tx.managed_original(read(config)) and not config.target.exists(),
                               'isolated final managed rollback mismatch')
        print('isolated_exact_post_restart_managed_rollback=true', flush=True)
    guarded()


if __name__ == '__main__':
    os.umask(0o077)
    main(sys.argv[1])
