#!/usr/bin/env python3
"""Networkless OpenMeteo file-provider rehearsal from a private restore snapshot."""
import io
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tarfile
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import forecast_intel as live  # noqa: E402
from openmeteo_config import mismatch_keys  # noqa: E402

SNAPSHOT = Path('/home/sat/backups/earthship-energy/runtime-recovery-1x76m17d')
IMAGE = 'openhab/openhab@sha256:bfd4a60e90da18cf917a9004bbc22354fc818825f3c6f0351e471a2e938d6c3c'
BINDING = Path('/var/lib/openhab/marketplace/bundles/165191/com.obones.binding.openmeteo-0.5.0.jar')
UIDS = {'openmeteo:openmeteo:local', 'openmeteo:forecast:local:site',
        'openmeteo:air-quality:local:aq'}


def run(args, *, data=None, check=True, timeout=30):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('isolated command failed: ' + args[0] + ' ' + args[1])
    return result


def stream_bytes(container, directory, name, body, *, mode=0o644):
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode='w') as archive:
        member = tarfile.TarInfo(name)
        member.size = len(body)
        member.mode = mode
        archive.addfile(member, io.BytesIO(body))
    run(['docker', 'exec', '-i', container, 'tar', '--no-same-owner',
         '--no-same-permissions', '-xf', '-', '-C', directory],
        data=archive_bytes.getvalue(), timeout=50)


def copy_bytes_to_stopped(container, directory, name, body):
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode='w') as archive:
        member = tarfile.TarInfo(name)
        member.size = len(body)
        member.mode = 0o644
        archive.addfile(member, io.BytesIO(body))
    run(['docker', 'cp', '-', container + ':' + directory],
        data=archive_bytes.getvalue(), timeout=50)


def restore_archive(container, name):
    with (SNAPSHOT / (name + '.tar')).open('rb') as archive:
        result = subprocess.run(
            ['docker', 'exec', '-i', container, 'tar', '--no-same-owner',
             '--no-same-permissions', '-xf', '-', '-C', '/openhab/' + name],
            stdin=archive, capture_output=True, timeout=110,
        )
        if result.returncode:
            raise RuntimeError('isolated snapshot restore failed: ' + name)


def selected_things(response):
    return {thing['UID']: thing for thing in response if thing.get('UID') in UIDS}


def supported_config_matches(current, original):
    mismatches = {}
    for uid in UIDS:
        metadata = live.oh_get('/thing-types/' + original[uid]['thingTypeUID'])
        mismatches[uid] = mismatch_keys(current[uid], original[uid], metadata)
    return mismatches


def compare_registry(container, live_things, live_links, auth_header,
                     *, expect_file_owned=True, timeout_seconds=300):
    deadline = time.monotonic() + timeout_seconds
    codes = []
    comparison = None
    while time.monotonic() < deadline:
        response = run([
            'docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '6',
            '-w', '\nCODE:%{http_code}', '-H', '@-',
            'http://127.0.0.1:8080/rest/things?summary=false',
        ], data=auth_header, check=False, timeout=10)
        raw = response.stdout.decode(errors='replace')
        code = raw.rsplit('CODE:', 1)[-1].strip() if 'CODE:' in raw else 'none'
        if code not in codes:
            codes.append(code)
        if code == '200':
            things = selected_things(json.loads(raw.rsplit('\nCODE:', 1)[0]))
            if len(things) == 3 and all(thing.get('channels') for thing in things.values()):
                link_response = run([
                    'docker', 'exec', '-i', container, 'curl', '-fsS', '--max-time', '6',
                    '-H', '@-', 'http://127.0.0.1:8080/rest/links',
                ], data=auth_header, check=False, timeout=10)
                links = ({(link['itemName'], link['channelUID'])
                          for link in json.loads(link_response.stdout)}
                         if link_response.returncode == 0 else set())
                config_mismatches = supported_config_matches(things, live_things)
                comparison = {
                    'file_owned': {uid: thing.get('editable') is False
                                   for uid, thing in things.items()},
                    'channel_count': {uid: len(thing['channels'])
                                      for uid, thing in things.items()},
                    'channel_sets_match_live': {
                        uid: {channel['uid'] for channel in thing['channels']}
                        == {channel['uid'] for channel in live_things[uid]['channels']}
                        for uid, thing in things.items()},
                    'supported_config_matches_live': {
                        uid: not keys for uid, keys in config_mismatches.items()},
                    'supported_config_mismatch_keys': config_mismatches,
                    'live_link_count': len(live_links),
                    'isolated_links_preserved': len(live_links & links),
                }
                if comparison['isolated_links_preserved'] == len(live_links):
                    break
        time.sleep(5)
    passed = (comparison is not None and all(
                  value is expect_file_owned for value in comparison['file_owned'].values())
              and all(comparison['channel_sets_match_live'].values())
              and all(comparison['supported_config_matches_live'].values())
              and comparison['isolated_links_preserved'] == len(live_links))
    return {'status': 'verified' if passed else 'incomplete',
            'http_codes': codes, 'result': comparison}


def main():
    marker = secrets.token_hex(8)
    name = 'hex-openmeteo-restore-' + marker[:8]
    container = None
    try:
        container = run([
            'docker', 'run', '-d', '--name', name,
            '--label', 'hex.openmeteo.restore=' + marker,
            '--network', 'none', '--hostname', 'localhost', '--cap-drop', 'ALL',
            '--pids-limit', '384', '--memory', '4g',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
            '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
            '--entrypoint', '/bin/sh', IMAGE, '-c',
            'while [ ! -f /openhab/conf/things/openmeteo.things ]; do sleep 1; done; '
            'exec /openhab/start.sh server',
        ], timeout=45).stdout.decode().strip()
        owner = run(['docker', 'inspect', '--format',
                     '{{index .Config.Labels "hex.openmeteo.restore"}}',
                     container]).stdout.decode().strip()
        if owner != marker:
            raise RuntimeError('isolated container ownership mismatch')

        for scope in ('conf', 'userdata'):
            restore_archive(container, scope)
        with tarfile.open(SNAPSHOT / 'userdata.tar') as archive:
            original_jsondb = archive.extractfile(
                './jsondb/org.openhab.core.thing.Thing.json').read()
            definitions = json.loads(original_jsondb)
        if not UIDS <= set(definitions):
            raise RuntimeError('snapshot missing managed OpenMeteo Things')
        for uid in UIDS:
            del definitions[uid]
        stream_bytes(container, '/openhab/userdata/jsondb',
                     'org.openhab.core.thing.Thing.json',
                     json.dumps(definitions, separators=(',', ':')).encode())
        stream_bytes(container, '/openhab/addons', 'openmeteo.jar', BINDING.read_bytes())
        run(['docker', 'cp', str(ROOT / 'openhab/file-config/things/openmeteo.things'),
             container + ':/openhab/conf/things/openmeteo.things'])

        live_things = selected_things(live.oh_get('/things?summary=false'))
        live_links = {(link['itemName'], link['channelUID']) for link in live.oh_get('/links')
                      if any(link.get('channelUID', '').startswith(uid + ':') for uid in UIDS)}
        auth_header = ('Authorization: Bearer ' + live.token() + '\n').encode()
        first = compare_registry(container, live_things, live_links, auth_header)
        print(json.dumps({'phase': 'first_boot', **first}, sort_keys=True), flush=True)
        if first['status'] != 'verified':
            return 2
        run(['docker', 'restart', container], timeout=80)
        restarted = compare_registry(container, live_things, live_links, auth_header)
        print(json.dumps({'phase': 'restart', **restarted}, sort_keys=True), flush=True)
        if restarted['status'] != 'verified':
            return 2
        run(['docker', 'stop', container], timeout=80)
        copy_bytes_to_stopped(container, '/openhab/conf/things',
                              'openmeteo.things', b'')
        copy_bytes_to_stopped(container, '/openhab/userdata/jsondb',
                              'org.openhab.core.thing.Thing.json', original_jsondb)
        run(['docker', 'start', container], timeout=45)
        rollback = compare_registry(container, live_things, live_links, auth_header,
                                    expect_file_owned=False)
        print(json.dumps({'phase': 'managed_restore', **rollback}, sort_keys=True),
              flush=True)
        if rollback['status'] != 'verified':
            return 2
        for uid in ('openmeteo:forecast:local:site',
                    'openmeteo:air-quality:local:aq', 'openmeteo:openmeteo:local'):
            response = run([
                'docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '8',
                '-w', '\nCODE:%{http_code}', '-X', 'DELETE', '-H', '@-',
                'http://127.0.0.1:8080/rest/things/' + quote(uid, safe='') +
                '?force=true',
            ], data=auth_header, check=False, timeout=12)
            code = response.stdout.decode(errors='replace').rsplit('CODE:', 1)[-1].strip()
            if code not in {'200', '202', '204'}:
                raise RuntimeError('isolated managed Thing deletion refused: ' + uid)
        link_response = run([
            'docker', 'exec', '-i', container, 'curl', '-fsS', '--max-time', '8',
            '-H', '@-', 'http://127.0.0.1:8080/rest/links',
        ], data=auth_header, timeout=12)
        links_after_delete = {(link['itemName'], link['channelUID'])
                              for link in json.loads(link_response.stdout)}
        thing_response = run([
            'docker', 'exec', '-i', container, 'curl', '-fsS', '--max-time', '8',
            '-H', '@-', 'http://127.0.0.1:8080/rest/things?summary=false',
        ], data=auth_header, timeout=12)
        things_after_delete = selected_things(json.loads(thing_response.stdout))
        print(json.dumps({'phase': 'managed_deleted',
                          'remaining_openmeteo_links': len(live_links & links_after_delete),
                          'remaining_thing_ids': sorted(things_after_delete),
                          'remaining_editable': {uid: thing.get('editable')
                                                 for uid, thing in things_after_delete.items()}},
                         sort_keys=True), flush=True)
        run(['docker', 'exec', container, 'rm',
             '/openhab/conf/things/openmeteo.things'])
        run(['docker', 'cp', str(ROOT / 'openhab/file-config/things/openmeteo.things'),
             container + ':/openhab/conf/things/openmeteo-cutover.things'])
        transition = compare_registry(container, live_things, live_links, auth_header,
                                      timeout_seconds=90)
        print(json.dumps({'phase': 'rest_like_file_transition', **transition},
                         sort_keys=True), flush=True)
        if transition['status'] != 'verified':
            return 2
        run(['docker', 'exec', container, 'rm',
             '/openhab/conf/things/openmeteo-cutover.things'])
        absent = False
        for _ in range(18):
            response = run([
                'docker', 'exec', '-i', container, 'curl', '-fsS', '--max-time', '6',
                '-H', '@-', 'http://127.0.0.1:8080/rest/things?summary=false',
            ], data=auth_header, check=False, timeout=10)
            if response.returncode == 0 and not selected_things(json.loads(response.stdout)):
                absent = True
                break
            time.sleep(5)
        print(json.dumps({'phase': 'file_removed', 'thing_ids_absent': absent}),
              flush=True)
        if not absent:
            return 2
        stream_bytes(container, '/tmp', 'auth-header', auth_header, mode=0o600)
        for uid in ('openmeteo:openmeteo:local',
                    'openmeteo:forecast:local:site',
                    'openmeteo:air-quality:local:aq'):
            thing = live_things[uid]
            body = {key: thing[key] for key in ('UID', 'thingTypeUID', 'label',
                                                'configuration')}
            if thing.get('bridgeUID'):
                body['bridgeUID'] = thing['bridgeUID']
            stream_bytes(container, '/tmp', 'thing-create.json',
                         json.dumps(body, separators=(',', ':')).encode(), mode=0o600)
            response = run([
                'docker', 'exec', container, 'curl', '-sS', '--max-time', '10',
                '-w', '\nCODE:%{http_code}', '-X', 'POST', '-H', '@/tmp/auth-header',
                '-H', 'Content-Type: application/json',
                '--data-binary', '@/tmp/thing-create.json',
                'http://127.0.0.1:8080/rest/things',
            ], check=False, timeout=14)
            code = response.stdout.decode(errors='replace').rsplit('CODE:', 1)[-1].strip()
            if code not in {'200', '201', '202'}:
                print(json.dumps({'phase': 'managed_recreate', 'uid': uid,
                                  'http_code': code}), flush=True)
                return 2
        reverse = compare_registry(container, live_things, live_links, auth_header,
                                   expect_file_owned=False, timeout_seconds=90)
        print(json.dumps({'phase': 'rest_like_managed_rollback', **reverse},
                         sort_keys=True), flush=True)
        return 0 if reverse['status'] == 'verified' else 2
    finally:
        if container:
            owner = run(['docker', 'inspect', '--format',
                         '{{index .Config.Labels "hex.openmeteo.restore"}}',
                         container], check=False).stdout.decode().strip()
            if owner != marker:
                raise RuntimeError('refusing to remove unowned isolated container')
            run(['docker', 'rm', '-f', '-v', container], check=False, timeout=50)
            print('owned_test_container_removed=true', flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
