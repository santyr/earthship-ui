#!/usr/bin/env python3
"""Test live-like gForecast hot handoff with file-owned members, offline only.

Uses a disposable networkless OpenHAB. It deliberately reloads the three
member source files after a managed-Group REST deletion; it never writes to
production. Any membership gap or rollback failure is a release failure.
"""
import importlib.util
import json
from pathlib import Path
import secrets
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_group_fixture', ROOT / 'scripts/qualify-forecast-group-provider.py')
group = importlib.util.module_from_spec(spec)
spec.loader.exec_module(group)
aqi = group.aqi

LABEL = 'hex.forecast.group.hot.qualification'
MEMBER_SOURCES = tuple(ROOT / 'openhab/file-config/items' / name for name in (
    'openmeteo-forecast-temperature.items',
    'openmeteo-forecast-meteorology.items',
    'openmeteo-forecast-daily.items',
))


def request(container, method, path, header, payload=None):
    args = ['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '8',
            '-o', '/dev/null', '-w', '%{http_code}', '-X', method,
            '-H', '@/tmp/forecast-group-auth']
    if payload is not None:
        args.extend(['-H', 'Content-Type: application/json', '--data-binary', '@-'])
    args.append('http://127.0.0.1:8080/rest' + path)
    result = aqi.run(args, json.dumps(payload).encode() if payload is not None else None,
                     timeout=12)
    if result.stdout.decode().strip() not in ('200', '201', '202', '204'):
        raise RuntimeError('isolated Group ' + method + ' refused')


def members(container, header):
    code, items = aqi.isolated_get(container, '/items?recursive=false', header)
    if code != 200 or not isinstance(items, list):
        raise RuntimeError('isolated Item list unavailable')
    return {row['name'] for row in items
            if group.GROUP in row.get('groupNames', [])}


def wait_members(container, header, expected, seconds=100):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if members(container, header) == expected:
                return True
        except RuntimeError:
            pass
        time.sleep(2)
    return False


def wait_group_absent(container, header, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if aqi.isolated_get(container, '/items/' + group.GROUP, header)[0] == 404:
            return True
        time.sleep(2)
    return False


def reload_members(container, marker):
    for source in MEMBER_SOURCES:
        aqi.install_bytes(container, '/openhab/conf/items', source.name,
                          source.read_bytes() + ('\n// isolated member reload ' + marker + '\n').encode())


def main():
    original = aqi.oh.get('/items/' + group.GROUP + '?metadata=.*')
    expected = {row['name'] for row in aqi.oh.get('/items?recursive=false')
                if group.GROUP in row.get('groupNames', [])}
    if len(expected) != 10 or original.get('editable') is not True:
        raise RuntimeError('live Group/member preflight changed')
    sources = {source.name: source.read_bytes() for source in MEMBER_SOURCES}
    for name, body in sources.items():
        if body.count(b'(gForecast)') not in (3, 4):
            raise RuntimeError('unexpected member source cardinality: ' + name)
    marker = secrets.token_hex(8)
    container = None
    try:
        container = aqi.run(['docker', 'run', '-d', '--label', LABEL + '=' + marker,
            '--network', 'none', '--hostname', 'localhost', '--cap-drop', 'ALL',
            '--pids-limit', '384', '--memory', '4g',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
            '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
            '--entrypoint', '/bin/sh', aqi.IMAGE, '-c',
            'while [ ! -f /openhab/conf/items/.forecast-group-hot-ready ]; do sleep 1; done; '
            'exec /openhab/start.sh server']).stdout.decode().strip()
        owner = aqi.run(['docker', 'inspect', '--format',
            '{{index .Config.Labels "' + LABEL + '"}}', container]).stdout.decode().strip()
        if owner != marker:
            raise RuntimeError('isolated container ownership mismatch')
        for scope in ('conf', 'userdata'):
            aqi.restore(container, scope)
        items = aqi.snapshot_registry('org.openhab.core.items.Item.json')
        links = aqi.snapshot_registry('org.openhab.core.thing.link.ItemChannelLink.json')
        if group.GROUP not in items or not expected.issubset(items):
            raise RuntimeError('restored Group/member registry incomplete')
        for name in expected:
            del items[name]
            keys = [key for key in links if key.startswith(name + ' -> ')]
            if len(keys) != 1:
                raise RuntimeError('restored member link count changed: ' + name)
            del links[keys[0]]
        aqi.install_bytes(container, '/openhab/userdata/jsondb',
            'org.openhab.core.items.Item.json',
            json.dumps(items, separators=(',', ':')).encode())
        aqi.install_bytes(container, '/openhab/userdata/jsondb',
            'org.openhab.core.thing.link.ItemChannelLink.json',
            json.dumps(links, separators=(',', ':')).encode())
        if aqi.BINDING is not None:
            aqi.install_bytes(container, '/openhab/addons', 'openmeteo.jar',
                              aqi.BINDING.read_bytes())
        for name, body in sources.items():
            aqi.install_bytes(container, '/openhab/conf/items', name, body)
        aqi.install_bytes(container, '/openhab/conf/items',
                          '.forecast-group-hot-ready', b'')
        header = ('Authorization: Bearer ' + aqi.oh.token() + '\n').encode()
        if not group.wait(container, header, original, expected, file_owned=False):
            raise RuntimeError('managed Group/file-owned member baseline failed')
        print('managed_group_file_member_baseline=true', flush=True)
        aqi.install_bytes(container, '/tmp', 'forecast-group-auth', header,
                          mode=0o600)
        request(container, 'DELETE', '/items/' + group.GROUP, header)
        if not wait_group_absent(container, header):
            raise RuntimeError('managed Group did not withdraw')
        after_delete = members(container, header)
        print('members_after_managed_group_delete=' + str(len(after_delete)), flush=True)
        if after_delete not in (set(), expected):
            raise RuntimeError('managed Group deletion left partial membership')
        aqi.install_bytes(container, '/openhab/conf/items',
                          group.SOURCE.name, group.SOURCE.read_bytes())
        if after_delete == expected:
            if not group.wait(container, header, original, expected,
                              file_owned=True, seconds=100):
                raise RuntimeError('file Group did not preserve file-owned members')
            print('hot_file_group_preserved_members_without_reload=true', flush=True)
        else:
            if not wait_members(container, header, set(), seconds=15):
                raise RuntimeError('Group creation left partial membership')
        reload_members(container, 'forward')
        if not group.wait(container, header, original, expected,
                          file_owned=True, seconds=100):
            raise RuntimeError('member file reload did not restore Group membership')
        print('hot_file_group_member_reload_verified=true', flush=True)
        aqi.run(['docker', 'restart', container], timeout=90)
        if not group.wait(container, header, original, expected, file_owned=True):
            raise RuntimeError('restart lost hot-restored Group membership')
        print('full_restart_group_members_verified=true', flush=True)
        aqi.run(['docker', 'exec', container, 'rm',
                 '/openhab/conf/items/' + group.SOURCE.name])
        if not wait_group_absent(container, header):
            raise RuntimeError('file Group did not withdraw')
        after_withdraw = members(container, header)
        print('members_after_file_group_withdrawal=' + str(len(after_withdraw)), flush=True)
        if after_withdraw not in (set(), expected):
            raise RuntimeError('file Group withdrawal left partial membership')
        # /tmp is a container tmpfs and is cleared by the restart above.
        aqi.install_bytes(container, '/tmp', 'forecast-group-auth', header,
                          mode=0o600)
        request(container, 'PUT', '/items/' + group.GROUP, header,
                aqi.managed_item_dto(original))
        reload_members(container, 'rollback')
        if not group.wait(container, header, original, expected,
                          file_owned=False, seconds=100):
            raise RuntimeError('hot managed rollback lost Group membership')
        print('hot_managed_rollback_members_verified=true', flush=True)
    finally:
        if container is not None:
            owner = aqi.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "' + LABEL + '"}}', container],
                check=False).stdout.decode().strip()
            if owner == marker:
                aqi.run(['docker', 'rm', '-f', '-v', container], timeout=90)
                print('owned_isolated_container_removed=true', flush=True)
    print('status=passed; production_writes=0; jdbc_and_event_gap=not_tested')


if __name__ == '__main__':
    main()
