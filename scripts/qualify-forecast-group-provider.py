#!/usr/bin/env python3
"""Rehearse gForecast file ownership and managed rollback in isolation.

The Group is the JDBC forecast-series selector. The restored private registry
and its members stay in an owned networkless OpenHAB container. Production is
read-only; this does not yet qualify a live Group transfer.
"""
import importlib.util
import json
from pathlib import Path
import secrets
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'aqi_provider_fixture', ROOT / 'scripts/qualify-openmeteo-aqi-item.py')
aqi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aqi)

SOURCE = ROOT / 'openhab/file-config/items/forecast-group.items'
GROUP = 'gForecast'
FIELDS = ('name', 'type', 'label', 'category', 'tags', 'groupNames')
LABEL = 'hex.forecast.group.qualification'


def matches(container, header, original, members, *, file_owned):
    code, group = aqi.isolated_get(container, '/items/' + GROUP + '?metadata=.*', header)
    if code != 200 or not isinstance(group, dict) or group.get('editable') is not (not file_owned):
        return False
    if any(group.get(field) != original.get(field) for field in FIELDS):
        return False
    code, items = aqi.isolated_get(container, '/items?recursive=false', header)
    if code != 200 or not isinstance(items, list):
        return False
    found = {row['name'] for row in items if GROUP in row.get('groupNames', [])}
    return found == members


def wait(container, header, original, members, *, file_owned, seconds=240):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if matches(container, header, original, members, file_owned=file_owned):
            return True
        time.sleep(3)
    return False


def main():
    source = SOURCE.read_bytes()
    if source.count(b'Group gForecast "Forecast Items" ["forecast"]') != 1:
        raise RuntimeError('prepared forecast Group source changed')
    original = aqi.oh.get('/items/' + GROUP + '?metadata=.*')
    if (original.get('editable') is not True or original.get('type') != 'Group'
            or original.get('label') != 'Forecast Items'
            or original.get('tags') != ['forecast']
            or original.get('groupNames') != [] or original.get('metadata')):
        raise RuntimeError('live managed forecast Group preflight changed')
    members = {row['name'] for row in aqi.oh.get('/items?recursive=false')
               if GROUP in row.get('groupNames', [])}
    if len(members) != 10:
        raise RuntimeError('live forecast Group membership changed')
    marker = secrets.token_hex(8)
    container = None
    try:
        container = aqi.run(['docker', 'run', '-d', '--label', LABEL + '=' + marker,
            '--network', 'none', '--hostname', 'localhost', '--cap-drop', 'ALL',
            '--pids-limit', '384', '--memory', '4g',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
            '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
            '--entrypoint', '/bin/sh', aqi.IMAGE, '-c',
            'while [ ! -f /openhab/conf/items/' + SOURCE.name + ' ]; do sleep 1; done; '
            'exec /openhab/start.sh server']).stdout.decode().strip()
        owner = aqi.run(['docker', 'inspect', '--format',
            '{{index .Config.Labels "' + LABEL + '"}}', container]).stdout.decode().strip()
        if owner != marker:
            raise RuntimeError('isolated forecast Group container ownership mismatch')
        for scope in ('conf', 'userdata'):
            aqi.restore(container, scope)
        items = aqi.snapshot_registry('org.openhab.core.items.Item.json')
        if GROUP not in items:
            raise RuntimeError('restored registry lacks managed forecast Group')
        del items[GROUP]
        aqi.install_bytes(container, '/openhab/userdata/jsondb',
            'org.openhab.core.items.Item.json',
            json.dumps(items, separators=(',', ':')).encode())
        header = ('Authorization: Bearer ' + aqi.oh.token() + '\n').encode()
        aqi.install_bytes(container, '/openhab/conf/items', SOURCE.name, source)
        if not wait(container, header, original, members, file_owned=True):
            raise RuntimeError('file Group or member references did not match')
        print('file_group_and_members_verified=true', flush=True)
        aqi.run(['docker', 'restart', container], timeout=90)
        if not wait(container, header, original, members, file_owned=True):
            raise RuntimeError('full restart lost file Group or members')
        print('full_restart_group_and_members_verified=true', flush=True)
        aqi.run(['docker', 'exec', container, 'rm',
            '/openhab/conf/items/' + SOURCE.name])
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if aqi.isolated_get(container, '/items/' + GROUP, header)[0] == 404:
                break
            time.sleep(3)
        else:
            raise RuntimeError('file Group did not withdraw')
        aqi.install_bytes(container, '/tmp', 'forecast-auth-header', header,
                          mode=0o600)
        payload = json.dumps(aqi.managed_item_dto(original)).encode()
        response = aqi.run(['docker', 'exec', '-i', container, 'curl', '-sS',
            '--max-time', '8', '-o', '/dev/null', '-w', '%{http_code}', '-X', 'PUT',
            '-H', '@/tmp/forecast-auth-header', '-H', 'Content-Type: application/json',
            '--data-binary', '@-',
            'http://127.0.0.1:8080/rest/items/' + GROUP], payload, timeout=12)
        if response.stdout.decode().strip() not in ('200', '201', '202', '204'):
            raise RuntimeError('isolated managed Group restore refused')
        if not wait(container, header, original, members,
                    file_owned=False, seconds=90):
            raise RuntimeError('managed Group rollback or member references drifted')
        print('managed_group_rollback_and_members_verified=true', flush=True)
        # A running OpenHAB may treat REST deletion differently from removing
        # its JSONDB record before boot. Rehearse that exact live-like handoff.
        deleted = aqi.run(['docker', 'exec', container, 'curl', '-sS',
            '--max-time', '8', '-o', '/dev/null', '-w', '%{http_code}', '-X', 'DELETE',
            '-H', '@/tmp/forecast-auth-header',
            'http://127.0.0.1:8080/rest/items/' + GROUP], timeout=12)
        if deleted.stdout.decode().strip() not in ('200', '202', '204'):
            raise RuntimeError('isolated live-like managed Group deletion refused')
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if aqi.isolated_get(container, '/items/' + GROUP, header)[0] == 404:
                break
            time.sleep(3)
        else:
            raise RuntimeError('managed Group did not withdraw for live-like handoff')
        aqi.install_bytes(container, '/openhab/conf/items', SOURCE.name, source)
        if not wait(container, header, original, members,
                    file_owned=True, seconds=90):
            group_code, group = aqi.isolated_get(
                container, '/items/' + GROUP + '?metadata=.*', header)
            item_code, current_items = aqi.isolated_get(
                container, '/items?recursive=false', header)
            current_members = ({row['name'] for row in current_items
                                if GROUP in row.get('groupNames', [])}
                               if item_code == 200 and isinstance(current_items, list)
                               else set())
            print('live_like_handoff_diagnostic=' + json.dumps({
                'group_code': group_code,
                'file_owned': group.get('editable') is False if isinstance(group, dict) else None,
                'member_count': len(current_members),
                'original_member_count': len(members),
            }, sort_keys=True), flush=True)
            raise RuntimeError('live-like file Group handoff lost definition or member references')
        print('live_like_rest_to_file_group_and_members_verified=true', flush=True)
        aqi.run(['docker', 'exec', container, 'rm',
            '/openhab/conf/items/' + SOURCE.name])
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if aqi.isolated_get(container, '/items/' + GROUP, header)[0] == 404:
                break
            time.sleep(3)
        else:
            raise RuntimeError('live-like file Group did not withdraw')
        restored = aqi.run(['docker', 'exec', '-i', container, 'curl', '-sS',
            '--max-time', '8', '-o', '/dev/null', '-w', '%{http_code}', '-X', 'PUT',
            '-H', '@/tmp/forecast-auth-header', '-H', 'Content-Type: application/json',
            '--data-binary', '@-',
            'http://127.0.0.1:8080/rest/items/' + GROUP], payload, timeout=12)
        if restored.stdout.decode().strip() not in ('200', '201', '202', '204'):
            raise RuntimeError('isolated final managed Group restore refused')
        if not wait(container, header, original, members,
                    file_owned=False, seconds=90):
            raise RuntimeError('live-like Group rollback lost member references')
        print('live_like_final_managed_rollback_verified=true', flush=True)
    finally:
        if container is not None:
            owner = aqi.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "' + LABEL + '"}}', container],
                check=False).stdout.decode().strip()
            if owner == marker:
                aqi.run(['docker', 'rm', '-f', '-v', container], timeout=90)
                print('owned_isolated_container_removed=true', flush=True)
    print('status=passed; production_writes=0; live_group_transfer=not_tested')


if __name__ == '__main__':
    main()
