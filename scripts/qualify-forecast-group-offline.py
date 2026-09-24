#!/usr/bin/env python3
"""Rehearse a stopped-OpenHAB gForecast JSONDB-to-file handoff in isolation.

No production writes. The restored private registry stays in an owned,
networkless container and a mode-0700 temporary directory. A REST deletion is
never used because it removes the ten member references.
"""
import importlib.util
import json
from pathlib import Path
import secrets
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_group_provider', ROOT / 'scripts/qualify-forecast-group-provider.py')
group = importlib.util.module_from_spec(spec)
spec.loader.exec_module(group)
aqi = group.aqi

LABEL = 'hex.forecast.group.offline.qualification'
REGISTRY = '/openhab/userdata/jsondb/org.openhab.core.items.Item.json'
SOURCE = group.SOURCE
TARGET = '/openhab/conf/items/' + SOURCE.name


def copy_out(container, source, destination):
    result = aqi.run(['docker', 'cp', container + ':' + source, str(destination)],
                     check=False, timeout=30)
    if result.returncode:
        raise RuntimeError('isolated stopped-container copy-out failed: '
                           + result.stderr.decode(errors='replace').strip())


def copy_in(container, source, destination):
    result = aqi.run(['docker', 'cp', str(source), container + ':' + destination],
                     check=False, timeout=30)
    if result.returncode:
        raise RuntimeError('isolated stopped-container copy-in failed: '
                           + result.stderr.decode(errors='replace').strip())


def edit_stopped_registry(container, temporary, *, remove, original):
    path = temporary / 'items.json'
    copy_out(container, REGISTRY, path)
    items = json.loads(path.read_text())
    if remove:
        if items.get(group.GROUP) != original:
            raise RuntimeError('stopped managed Group record drifted')
        del items[group.GROUP]
    else:
        if group.GROUP in items:
            raise RuntimeError('stopped registry already has forecast Group')
        items[group.GROUP] = original
    path.write_text(json.dumps(items, separators=(',', ':')))
    copy_in(container, path, REGISTRY)


def main():
    source = SOURCE.read_bytes()
    if source.count(b'Group gForecast "Forecast Items" ["forecast"]') != 1:
        raise RuntimeError('prepared forecast Group source changed')
    original = aqi.oh.get('/items/gForecast?metadata=.*')
    if (original.get('editable') is not True or original.get('type') != 'Group'
            or original.get('label') != 'Forecast Items'
            or original.get('tags') != ['forecast']
            or original.get('groupNames') != [] or original.get('metadata')):
        raise RuntimeError('live managed forecast Group preflight changed')
    members = {row['name'] for row in aqi.oh.get('/items?recursive=false')
               if group.GROUP in row.get('groupNames', [])}
    if len(members) != 10:
        raise RuntimeError('live forecast Group membership changed')
    original_record = aqi.snapshot_registry('org.openhab.core.items.Item.json')[group.GROUP]
    marker = secrets.token_hex(8)
    container = None
    # Snap Docker has a private /tmp mount; use a 0700 workspace directory that
    # is visible to its confined CLI, and remove it when the rehearsal ends.
    with tempfile.TemporaryDirectory(prefix='forecast-group-offline-', dir=ROOT) as temp:
        temporary = Path(temp)
        try:
            container = aqi.run([
                'docker', 'run', '-d', '--label', LABEL + '=' + marker,
                '--network', 'none', '--hostname', 'localhost', '--cap-drop', 'ALL',
                '--pids-limit', '384', '--memory', '4g',
                '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
                '--entrypoint', '/bin/sh', aqi.IMAGE, '-c',
                'while [ ! -f /openhab/conf/items/.forecast-group-offline-ready ]; '
                'do sleep 1; done; exec /openhab/start.sh server',
            ], timeout=45).stdout.decode().strip()
            owner = aqi.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "' + LABEL + '"}}', container]
                ).stdout.decode().strip()
            if owner != marker:
                raise RuntimeError('isolated container ownership mismatch')
            for scope in ('conf', 'userdata'):
                aqi.restore(container, scope)
            aqi.install_bytes(container, '/openhab/conf/items',
                              '.forecast-group-offline-ready', b'')
            header = ('Authorization: Bearer ' + aqi.oh.token() + '\n').encode()
            if not group.wait(container, header, original, members, file_owned=False):
                raise RuntimeError('managed Group baseline or members failed')
            print('managed_baseline_members_verified=true', flush=True)

            aqi.run(['docker', 'stop', '-t', '30', container], timeout=45)
            edit_stopped_registry(container, temporary, remove=True,
                                  original=original_record)
            source_path = temporary / SOURCE.name
            source_path.write_bytes(source)
            copy_in(container, source_path, TARGET)
            aqi.run(['docker', 'start', container], timeout=45)
            if not group.wait(container, header, original, members, file_owned=True):
                raise RuntimeError('offline handoff lost Group or member references')
            print('offline_handoff_members_verified=true', flush=True)
            aqi.run(['docker', 'restart', container], timeout=90)
            if not group.wait(container, header, original, members, file_owned=True):
                raise RuntimeError('full restart lost file Group or members')
            print('full_restart_members_verified=true', flush=True)

            aqi.run(['docker', 'stop', '-t', '30', container], timeout=45)
            edit_stopped_registry(container, temporary, remove=False,
                                  original=original_record)
            source_path.write_bytes(b'')
            copy_in(container, source_path, TARGET)
            aqi.run(['docker', 'start', container], timeout=45)
            if not group.wait(container, header, original, members, file_owned=False):
                raise RuntimeError('offline rollback lost Group or member references')
            print('offline_rollback_members_verified=true', flush=True)
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
