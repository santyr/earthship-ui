#!/usr/bin/env python3
"""Networkless Astro Moon Thing provider/restart/rollback qualification.

Production REST access is GET-only. A clean isolated runtime contains only Moon
definitions, cached Astro/MAP bundles and an isolated API identity. No host
mounts, network, household rules, database, synthetic states or Item commands.
--check-history instead checks every original production JDBC prefix using two
read-only snapshots; it allocates no fixture and does not qualify a cutover.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import quote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


q = load('moon_clean_runtime', 'qualify-season-rule-provider.py')
runtime = q.runtime
definition = load('moon_neutral_thing', 'preflight-bitcoin-exec-thing.py').definition
UID = 'astro:moon:local'
LABEL = 'hex.astro.moon.qualification'
SOURCE = ROOT / 'openhab/file-config/things/astro-moon.things'
SOURCE_SHA = 'bc347fa716e7b959ceefc363b9e83b9d929da5354e1215ebef886d02f7b6310e'
ADDONS = Path('/var/lib/openhab/tmp/kar/openhab-addons-5.2.1/org/openhab/addons/bundles')
ASTRO = ADDONS / 'org.openhab.binding.astro/5.2.1/org.openhab.binding.astro-5.2.1.jar'
MAP = ADDONS / 'org.openhab.transform.map/5.2.1/org.openhab.transform.map-5.2.1.jar'
ASTRO_SHA = '1a3b8207ec49834022706359bff60ff2f4eaa1354d392c48850cb418de63e7db'
PROBE = 'Hex_Moon_Qualification_Ready'
TARGET = Path('/etc/openhab/things/astro-moon.things')
REGIONAL = {'language': 'en', 'region': 'US', 'timezone': 'America/Denver',
            'measurementSystem': 'US'}
ITEM_FIELDS = ('name', 'type', 'label', 'category', 'tags', 'groupNames', 'metadata',
               'unitSymbol', 'stateDescription', 'editable')
HISTORY_IDS = {
    'MoonPhaseicon': 60, 'Moon_Apogee_Date': 67, 'Moon_Apogee_Distance': 68,
    'Moon_Azimuth': 44, 'Moon_Distance_Date': 42, 'Moon_Distance_Distance': 43,
    'Moon_Eclipse_PartialElevation': 64, 'Moon_Eclipse_TotalElevation': 62,
    'Moon_FirstQuarter': 54, 'Moon_FullMoon': 56, 'Moon_MoonIllumination': 41,
    'Moon_MoonPhaseName': 59, 'Moon_NewMoon': 57, 'Moon_PartialMoonEclipse': 63,
    'Moon_Perigee_Date': 65, 'Moon_Perigee_Distance': 66, 'Moon_Phase_Age': 58,
    'Moon_Phase_AgeDegree': 39, 'Moon_Phase_AgePercent': 40,
    'Moon_Position_Elevation': 45, 'Moon_Rise_End': 51, 'Moon_Rise_Start': 52,
    'Moon_Set_End': 50, 'Moon_Set_Start': 53, 'Moon_ShadeLengthRatio': 69,
    'Moon_Sign': 70, 'Moon_ThirdQuarter': 55, 'Moon_TotalMoonEclipse': 61,
}
MAX_TABLE_HISTORY_BYTES = 32 * 1024**2
MAX_TOTAL_HISTORY_BYTES = 128 * 1024**2


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def item_definition(item):
    return {key: deepcopy(item.get(key)) for key in ITEM_FIELDS}


def dependent_definitions(items):
    """Full Item contracts plus complete semantic edges, not a Set's last point.

    Installed SemanticsMetadataProvider.processHierarchy iterates getMembers()
    and processMember overwrites hasPoint for each Point. That representative
    varies between JVMs; validate it, then compare the complete relation instead.
    All other metadata, units, tags, parent links and provider flags stay exact.
    """
    group = items.get('Moon', {})
    members = group.get('members', [])
    names = {row.get('name') for row in members if isinstance(row, dict)}
    expected = set(items) - {'Moon'}
    require(group.get('type') == 'Group' and names == expected
            and len(members) == len(names)
            and all('Moon' in items[name].get('groupNames', []) for name in names),
            'Moon semantic membership changed')
    points = {name for name in names if items[name].get('metadata', {}).get(
        'semantics', {}).get('value') == 'Point'}
    semantics = group.get('metadata', {}).get('semantics', {})
    require(semantics.get('value') == 'Equipment', 'Moon semantic equipment changed')
    require(semantics.get('editable') is False, 'Moon semantic provider changed')
    require(bool(points), 'Moon semantic points missing')
    require('hasPoint' in semantics.get('config', {}), 'Moon semantic representative absent')
    require(semantics.get('config', {}).get('hasPoint') in points,
            'Moon semantic representative changed')
    require(all(items[name]['metadata']['semantics'].get('config', {}).get(
        'isPointOf') == 'Moon' for name in points), 'Moon semantic parent changed')
    result = {name: item_definition(item) for name, item in items.items()}
    result['Moon']['members'] = sorted(names)
    result['Moon']['metadata']['semantics']['config']['hasPoint'] = sorted(points)
    return result


def difference_paths(before, after, prefix=''):
    """Definition names only; no configuration, credential or observation values."""
    if isinstance(before, dict) and isinstance(after, dict):
        paths = []
        for key in sorted(set(before) | set(after)):
            path = prefix + '.' + key if prefix else key
            if key not in before or key not in after:
                paths.append(path)
            else:
                paths.extend(difference_paths(before[key], after[key], path))
        return paths
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [path for i, (left, right) in enumerate(zip(before, after))
                for path in difference_paths(left, right, prefix + '.' + str(i))]
    return [] if before == after else [prefix]


def managed_item(item):
    return {key: deepcopy(item[key]) for key in (
        'name', 'type', 'label', 'category', 'tags', 'groupNames') if key in item}


def managed_thing(thing):
    # Legacy stored channels are not necessarily today's binding defaults.
    # An exact managed recovery must retain their full original descriptors.
    require(thing.get('UID') == UID, 'Moon recovery identity outside scope')
    result = {key: deepcopy(thing[key]) for key in (
        'UID', 'thingTypeUID', 'label', 'bridgeUID', 'location',
        'configuration', 'properties', 'channels') if key in thing}
    # Installed ChannelDTO has no linkedItems member. Links have their own
    # provider and are restored separately; preserve every writable descriptor.
    for channel in result.get('channels', []):
        channel.pop('linkedItems', None)
    return result


def link_path(link):
    require(isinstance(link.get('itemName'), str)
            and re.fullmatch(r'Moon[A-Za-z0-9_]*', link['itemName']) is not None
            and isinstance(link.get('channelUID'), str)
            and link['channelUID'].startswith(UID + ':'), 'Moon link outside isolated scope')
    return '/links/' + link['itemName'] + '/' + quote(link['channelUID'], safe='')


def restore_managed(rest, original):
    # ThingResource.create adds DTO channels to factory-created channels and
    # ThingHelper rejects duplicate UIDs. ThingResource.update replaces them.
    # This two-step path is isolated-only; no live recovery adapter is enabled.
    full = managed_thing(original)
    initial = {key: deepcopy(value) for key, value in full.items() if key != 'channels'}
    require(rest('POST', '/things', initial)[0] in (200, 201, 202),
            'isolated managed Moon creation refused')
    require(rest('PUT', '/things/' + UID, full)[0] == 200,
            'isolated original Moon descriptor restoration refused')


def native_update_after(log, after, now):
    """A new source-attributed binding event, never a held numeric state alone."""
    source = '(source: org.openhab.core.thing$astro:moon:local:phase#illumination)'
    for line in log.splitlines():
        if "Item 'Moon_MoonIllumination' changed" not in line or source not in line:
            continue
        try:
            at = datetime.strptime(line[:23], '%Y-%m-%d %H:%M:%S.%f').replace(
                tzinfo=ZoneInfo('America/Denver')).astimezone(timezone.utc)
        except ValueError:
            continue
        if after < at <= now:
            return True
    return False


def validate_container(info, marker):
    host = info['HostConfig']
    require(info['Config']['Labels'].get(LABEL) == marker
            and info['Config'].get('User') == '9001:9001'
            and host['NetworkMode'] == 'none' and not host['Privileged']
            and host['ReadonlyRootfs'] and not host.get('Binds')
            and not host.get('Devices') and not host.get('PortBindings')
            and host['Memory'] == host['MemorySwap'] == 1536 * 1024**2
            and host['NanoCpus'] == 1_000_000_000
            and info.get('AppArmorProfile') == 'docker-default',
            'isolated Moon containment mismatch')


def preflight():
    require(not SOURCE.is_symlink() and sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_SHA,
            'Moon source drift')
    require(not TARGET.exists() and not TARGET.is_symlink(), 'Moon target already present')
    regional = runtime.oh.get('/services/org.openhab.i18n/config')
    require(all(regional.get(key) == value for key, value in REGIONAL.items()),
            'Moon regional baseline changed')
    thing = runtime.oh.get('/things/' + UID)
    require(thing.get('editable') is True and thing.get('thingTypeUID') == 'astro:moon'
            and thing.get('label') == 'Moon'
            and thing.get('configuration') == {'geolocation': '38.3739919,-105.7744609', 'interval': 300}
            and type(thing['configuration']['interval']) is int
            and thing.get('statusInfo') == {'status': 'ONLINE', 'statusDetail': 'NONE'}
            and len(thing.get('channels', [])) == 34, 'live Moon baseline changed')
    links = [row for row in runtime.oh.get('/links')
             if row.get('channelUID', '').startswith(UID + ':')]
    require(len(links) == len({row['itemName'] for row in links}) == 28,
            'Moon dependent membership changed')
    items = {row['itemName']: runtime.oh.get('/items/' + row['itemName'] + '?metadata=.*')
             for row in links}
    items['Moon'] = runtime.oh.get('/items/Moon?metadata=.*')
    require({name for name, item in items.items() if item.get('editable') is False}
            == {'MoonPhaseicon', 'Moon_MoonPhaseName', 'Moon_MoonIllumination'},
            'Moon dependent providers changed')
    dependent_definitions(items)
    require(sha256(ASTRO.read_bytes()).hexdigest() == ASTRO_SHA, 'Astro binding drift')
    return thing, links, items


def aware_time(value):
    return isinstance(value, datetime) and value.utcoffset() is not None


class HistoryDigest:
    """Stream original COPY bytes; do not retain or print observation values."""
    def __init__(self, remaining=None):
        self.digest = sha256()
        self.size = 0
        self.remaining = MAX_TOTAL_HISTORY_BYTES if remaining is None else remaining

    def write(self, value):
        body = value.encode() if isinstance(value, str) else value
        self.size += len(body)
        require(self.size <= MAX_TABLE_HISTORY_BYTES, 'Moon history table bound exceeded')
        require(self.size <= self.remaining, 'Moon total history bound exceeded')
        self.digest.update(body)


def history_prefixes(db, *, before=None):
    """Pinned identities and ordered duplicate-preserving original prefixes.

    The second transaction fixes each original maximum, excluding genuine later
    appends. No renamed/remapped/aliased Item can acquire a different table, and
    absent history is explicitly refused rather than called recovered history.
    """
    if before is not None:
        require(set(before) == set(HISTORY_IDS)
                and all(row.get('id') == HISTORY_IDS[name]
                        and aware_time(row.get('cutoff')) for name, row in before.items()),
                'Moon original prefix identity or cutoff invalid')
    db.set_session(readonly=True, autocommit=False, isolation_level='REPEATABLE READ')
    result, total = {}, 0
    with db:
        with db.cursor() as cursor:
            cursor.execute('SHOW transaction_read_only')
            require(cursor.fetchone() == ('on',), 'Moon history transaction is not read-only')
            cursor.execute('SHOW transaction_isolation')
            require(cursor.fetchone() == ('repeatable read',),
                    'Moon history transaction is not a consistent snapshot')
            cursor.execute("SET LOCAL statement_timeout='20s'")
            cursor.execute("SET LOCAL lock_timeout='3s'")
            cursor.execute("SET LOCAL TIME ZONE 'UTC'")
            cursor.execute("SET LOCAL DateStyle='ISO, YMD'")
            cursor.execute('SELECT itemname,itemid FROM public.items '
                           'WHERE itemname=ANY(%s) OR itemid=ANY(%s) ORDER BY itemname',
                           (sorted(HISTORY_IDS), sorted(HISTORY_IDS.values())))
            # Database collation may order underscores/case differently from
            # Python; identity multiplicity is exact, but row order is not one.
            require(sorted(cursor.fetchall()) == sorted(HISTORY_IDS.items()),
                    'Moon JDBC identity missing, remapped, duplicated or aliased')
            for name, identity in sorted(HISTORY_IDS.items()):
                # Only hard-coded integer identities reach this SQL identifier.
                require(type(identity) is int and 0 < identity < 10000,
                        'Moon JDBC identity outside pinned scope')
                table = f'public.item{identity:04d}'
                where = '' if before is None else ' WHERE time<=%s'
                args = () if before is None else (before[name]['cutoff'],)
                cursor.execute('SELECT count(*),min(time),max(time) FROM ' + table + where, args)
                count, first, maximum = cursor.fetchone()
                require(type(count) is int and count > 0 and aware_time(first)
                        and aware_time(maximum) and first <= maximum,
                        'Moon original history empty or timestamp contract invalid')
                if before is not None:
                    require(maximum <= before[name]['cutoff'], 'Moon original prefix cutoff expanded')
                command = cursor.mogrify('COPY (SELECT time,value FROM ' + table
                                         + ' WHERE time<=%s ORDER BY time,value) TO STDOUT WITH CSV',
                                         (maximum,)).decode()
                writer = HistoryDigest(MAX_TOTAL_HISTORY_BYTES - total)
                cursor.copy_expert(command, writer)
                total += writer.size
                require(total <= MAX_TOTAL_HISTORY_BYTES, 'Moon total history bound exceeded')
                result[name] = {'id': identity, 'count': count, 'first': first,
                                'cutoff': maximum, 'sha256': writer.digest.hexdigest(),
                                'bytes': writer.size}
    return result


def check_history():
    original, links, items = preflight()
    require({row['itemName'] for row in links} == set(HISTORY_IDS),
            'Moon history linked scope changed')
    transport = load('moon_history_transport', 'migrate-astro-icon-items.py')
    settings = transport.parse_openhab_jdbc_config('/var/lib/openhab/config/org/openhab/jdbc.config')
    db = transport.psycopg2.connect(**settings.connect_kwargs, connect_timeout=5)
    try:
        before = history_prefixes(db)
        require(history_prefixes(db, before=before) == before, 'Moon original history prefix changed')
    finally:
        db.close()
    after, after_links, after_items = preflight()
    require(definition(original) == definition(after) and original['editable'] == after['editable']
            and sorted(links, key=lambda row: row['itemName'])
            == sorted(after_links, key=lambda row: row['itemName'])
            and dependent_definitions(items) == dependent_definitions(after_items),
            'Moon original definition, link or dependent changed during history audit')
    canonical = json.dumps(before, sort_keys=True, default=str, separators=(',', ':')).encode()
    print(json.dumps({'status': 'original_history_baseline_verified',
                      'assessed_at': datetime.now(timezone.utc).isoformat(),
                      'items': len(before), 'rows': sum(row['count'] for row in before.values()),
                      'bytes': sum(row['bytes'] for row in before.values()),
                      'prefixes_sha256': sha256(canonical).hexdigest(), 'prefixes': before,
                      'production_writes': 0, 'production_history_recovery': 'not_tested',
                      'provider_handoff': 'not_tested'}, sort_keys=True, default=str))


def command(args):
    require(args in ([], ['--check-history']),
            'no arbitrary target or production apply interface')
    if args:
        check_history()
    else:
        main()


def main():
    original, original_links, original_items = preflight()
    marker, container = secrets.token_hex(8), None
    try:
        supervisor = (
            'cp -a /openhab/dist/conf/. /openhab/conf/; '
            'cp -a /openhab/dist/userdata/. /openhab/userdata/; '
            'while [ ! -f /tmp/ready ]; do sleep 1; done; '
            'while true; do while [ ! -f /tmp/boot-permit ]; do sleep 1; done; '
            'rm /tmp/boot-permit; /openhab/start.sh server & jvm_child=$!; '
            'wait "$jvm_child"; touch /tmp/jvm-stopped; done')
        container = runtime.run([
            'docker', 'run', '-d', '--init', '--label', LABEL + '=' + marker,
            '--network', 'none', '--read-only', '--user', '9001:9001', '--cap-drop', 'ALL',
            '--memory', '1536m', '--memory-swap', '1536m', '--cpus', '1', '--pids-limit', '256',
            '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=64m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/conf:rw,nosuid,nodev,size=64m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/userdata:rw,exec,nosuid,nodev,size=512m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/addons:rw,nosuid,nodev,size=16m,uid=9001,gid=9001',
            '-e', 'EXTRA_JAVA_OPTS=-Xmx512m -XX:ActiveProcessorCount=1 '
                  '-Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
            '--entrypoint', '/bin/sh', runtime.IMAGE, '-c', supervisor,
        ]).decode().strip()
        validate_container(json.loads(runtime.run(['docker', 'inspect', container]))[0], marker)
        runtime.install(container, 'conf/services/runtime.cfg', ''.join(
            'org.openhab.i18n:' + key + '=' + value + '\n'
            for key, value in REGIONAL.items()).encode())
        runtime.install(container, 'conf/items/moon-ready.items', ('String ' + PROBE + '\n').encode())
        runtime.run(['docker', 'exec', container, 'touch', '/tmp/boot-permit', '/tmp/ready'])
        q.wait_for(lambda: q._startup_item(container, PROBE), seconds=240)
        print('isolated_core_ready=true', flush=True)
        time.sleep(20)  # Existing harness: settle the core's first feature transaction.
        client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                  '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
        runtime.install_bundles(container, [ASTRO, MAP])
        for name in ('org.openhab.binding.astro', 'org.openhab.transform.map'):
            def binding_ready():
                listing = runtime.run(client + ['bundle:list -s'], b'\n').decode()
                rows = [line for line in listing.splitlines() if name in line]
                if len(rows) != 1:
                    return False
                match = re.match(r'\s*(\d+)\s*[|│]\s*(\w+)\s*[|│]', rows[0])
                if match is None:
                    return False
                if match[2] == 'Resolved':
                    runtime.run(client + ['bundle:start ' + match[1]], b'\n')
                    return False
                return match[2] == 'Active'
            q.wait_for(binding_ready, seconds=120)
        print('isolated_astro_and_map_active=true', flush=True)
        runtime.run(client + ['openhab:users add qualification ' + secrets.token_hex(20)
                              + ' administrator'], b'\n')
        response = runtime.run(client + ["openhab:users addApiToken qualification qualification ''"], b'\n')
        tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', response.decode())
        require(len(tokens) == 1, 'isolated Moon token unavailable; output withheld')
        print('isolated_api_identity_ready=true', flush=True)

        def rest(method, path, body=None):
            require(method in ('GET', 'POST', 'PUT', 'DELETE'), 'unknown isolated method')
            args = ['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '8',
                    '-w', '\n%{http_code}', '-X', method,
                    '-H', 'Authorization: Bearer ' + tokens[0], '-H', 'Content-Type: application/json']
            if body is not None:
                args += ['--data-binary', '@-']
            args += ['http://127.0.0.1:8080/rest' + path]
            payload, code = runtime.run(args, json.dumps(body).encode() if body is not None else None).rsplit(b'\n', 1)
            if int(code) >= 400 and not (method == 'GET' and int(code) == 404):
                print(json.dumps({'isolated_http_method': method,
                                  'resource': path.split('/')[1],
                                  'status': int(code)}, sort_keys=True), flush=True)
            return int(code), json.loads(payload) if payload.startswith((b'{', b'[')) else None

        q.wait_for(lambda: rest('GET', '/thing-types/astro:moon')[0] == 200, seconds=90)
        require(rest('PUT', '/items/Moon', managed_item(original_items['Moon']))[0] in (200, 201),
                'isolated Moon Group refused')
        phase = datetime.now(timezone.utc)
        restore_managed(rest, original)
        for name, item in original_items.items():
            if name != 'Moon' and item.get('editable') is True:
                require(rest('PUT', '/items/' + name, managed_item(item))[0] in (200, 201),
                        'isolated Moon Item refused')
        runtime.install(container, 'conf/items/moon-phase-readings.items',
                        (ROOT / 'openhab/file-config/items/moon-phase-readings.items').read_bytes())
        icon = [line for line in (ROOT / 'openhab/file-config/items/astro-icons.items').read_text().splitlines()
                if line.startswith('String MoonPhaseicon ')]
        require(len(icon) == 1, 'Moon icon source changed')
        runtime.install(container, 'conf/items/moon-icon.items', (icon[0] + '\n').encode())
        runtime.install(container, 'conf/transform/astro.map', (ROOT / 'openhab/transform/astro.map').read_bytes())
        q.wait_for(lambda: all(rest('GET', '/items/' + name)[0] == 200 for name in (
            'MoonPhaseicon', 'Moon_MoonPhaseName', 'Moon_MoonIllumination')))
        for link in original_links:
            if link.get('editable') is True:
                path = link_path(link)
                require(rest('PUT', path, {key: link[key] for key in ('itemName', 'channelUID', 'configuration')})[0]
                        in (200, 201, 202, 204), 'isolated Moon link refused')

        # added(Point) recomputes that Point, not its parent Equipment. Our
        # Group-first REST setup can retain the initial empty Group metadata.
        # Initialize this isolated provider against the now-complete registry;
        # never write derived metadata or relax the relation checks.
        q.wait_for(lambda: len(rest('GET', '/items/Moon')[1].get('members', [])) == 28)
        listing = runtime.run(client + ['bundle:list -s'], b'\n').decode()
        rows = [line for line in listing.splitlines() if 'org.openhab.core.semantics' in line]
        require(len(rows) == 1, 'isolated semantics bundle not unique')
        match = re.match(r'\s*(\d+)\s*[|│]\s*(\w+)\s*[|│]', rows[0])
        require(match is not None and match[2] == 'Active', 'isolated semantics bundle not active')
        runtime.run(client + ['bundle:restart ' + match[1]], b'\n')
        print('isolated_semantics_reinitialized_after_fixture_registration=true', flush=True)

        def dependents():
            return dependent_definitions({
                name: rest('GET', '/items/' + name + '?metadata=.*')[1]
                for name in original_items})

        expected_items = dependent_definitions(original_items)
        expected_links = sorted(original_links, key=lambda row: row['itemName'])
        reported = {}

        def diagnose(category, fields=()):
            signature = (category, tuple(fields))
            if signature not in reported:
                reported[signature] = time.monotonic()
                print(json.dumps({'isolated_check': category, 'difference_paths': list(fields)[:60],
                                  'difference_count': len(fields)}, sort_keys=True), flush=True)
            elif fields and time.monotonic() - reported[signature] >= 30:
                # A stable definition mismatch is not a pending observation.
                # End the isolated attempt without another five-minute poll.
                raise RuntimeError('isolated definition mismatch persisted')
            return False

        def ready(editable, after):
            code, thing = rest('GET', '/things/' + UID)
            if code != 200 or not thing or thing.get('editable') is not editable:
                return diagnose('thing_registration_or_provider')
            if (thing.get('statusInfo') != {'status': 'ONLINE', 'statusDetail': 'NONE'}
                    or definition(thing) != definition(original)):
                return diagnose('thing_definition', difference_paths(definition(original), definition(thing)))
            code, links = rest('GET', '/links')
            selected = sorted([row for row in links if row.get('channelUID', '').startswith(UID + ':')],
                              key=lambda row: row['itemName'])
            if code != 200 or selected != expected_links:
                return diagnose('link_definition', difference_paths(expected_links, selected))
            try:
                actual_items = dependents()
            except RuntimeError as error:
                fields = {
                    'Moon semantic membership changed': 'members',
                    'Moon semantic equipment changed': 'equipment_type',
                    'Moon semantic provider changed': 'metadata_provider',
                    'Moon semantic points missing': 'points',
                    'Moon semantic representative absent': 'missing_representative',
                    'Moon semantic representative changed': 'representative',
                    'Moon semantic parent changed': 'point_parent',
                }
                if str(error) in fields:
                    return diagnose('item_semantics', (fields[str(error)],))
                raise
            if actual_items != expected_items:
                return diagnose('item_definition', difference_paths(expected_items, actual_items))
            code, illumination = rest('GET', '/items/Moon_MoonIllumination')
            try:
                if not (code == 200 and 0 <= float(illumination['state']) <= 1):
                    return diagnose('illumination_state_unavailable')
            except (KeyError, TypeError, ValueError):
                return diagnose('illumination_state_unavailable')
            log = runtime.run(['docker', 'exec', container, 'cat',
                               '/openhab/userdata/logs/events.log']).decode(errors='replace')
            return (True if native_update_after(log, after, datetime.now(timezone.utc))
                    else diagnose('new_source_attributed_update_pending'))

        q.wait_for(lambda: ready(True, phase), seconds=360)
        print('isolated_managed_moon_exact=true; channels=34; dependents=28', flush=True)
        require(rest('DELETE', '/things/' + UID + '?force=true')[0] in (200, 202, 204),
                'isolated managed Moon withdrawal refused')
        q.wait_for(lambda: rest('GET', '/things/' + UID)[0] == 404)
        phase = datetime.now(timezone.utc)
        runtime.install(container, 'conf/things/astro-moon.things', SOURCE.read_bytes())
        file_failed = False
        try:
            q.wait_for(lambda: ready(False, phase), seconds=360)
            print('isolated_file_moon_exact=true; all_original_dependents_preserved=true', flush=True)
            before = q.java_pids(container)
            require(len(before) == 1, 'one isolated JVM required')
            try:
                runtime.run(client + ['system:shutdown -f'], b'\n')
            except RuntimeError:
                pass
            q.wait_for(lambda: before[0] not in q.java_pids(container), seconds=60)
            q.wait_for(lambda: q._jvm_stopped(container), seconds=30)
            phase = datetime.now(timezone.utc)
            runtime.run(['docker', 'exec', container, 'touch', '/tmp/boot-permit'])
            q.wait_for(lambda: q._startup_item(container, PROBE), seconds=240)
            q.wait_for(lambda: ready(False, phase), seconds=360)
            require(len(q.java_pids(container)) == 1 and q.java_pids(container) != before,
                    'isolated Moon JVM did not restart')
            print('isolated_full_jvm_restart_exact=true', flush=True)
        except Exception:
            file_failed = True
            print('isolated_file_or_restart_gate_refused=true; checking_managed_recovery=true', flush=True)
        installed = runtime.run(['docker', 'exec', container, 'sha256sum',
                                 '/openhab/conf/things/astro-moon.things']).decode().split()[0]
        require(installed == SOURCE_SHA, 'isolated Moon withdrawal source drift')
        runtime.run(['docker', 'exec', container, 'rm', '/openhab/conf/things/astro-moon.things'])
        q.wait_for(lambda: rest('GET', '/things/' + UID)[0] == 404)
        phase = datetime.now(timezone.utc)
        restore_managed(rest, original)
        q.wait_for(lambda: ready(True, phase), seconds=360)
        print('isolated_managed_rollback_exact=true', flush=True)
        require(not file_failed, 'isolated file/restart failed despite verified managed recovery')
    finally:
        if container is not None:
            owner = runtime.run(['docker', 'inspect', '--format',
                                 '{{index .Config.Labels "' + LABEL + '"}}', container]).decode().strip()
            require(owner == marker, 'Moon cleanup ownership mismatch')
            runtime.run(['docker', 'rm', '-f', '-v', container], timeout=45)
            print('owned_moon_container_and_tmpfs_removed=true', flush=True)
    print('status=passed; production_writes=0; production_history_recovery=not_tested')


if __name__ == '__main__':
    try:
        command(sys.argv[1:])
    except (Exception, KeyboardInterrupt) as error:
        # Report code location only, never exception text, locals or subprocess
        # output: API authorization and private production reads remain opaque.
        locations = []
        trace = error.__traceback__
        while trace is not None:
            if trace.tb_frame.f_code.co_filename == __file__:
                locations.append({'function': trace.tb_frame.f_code.co_name,
                                  'line': trace.tb_lineno})
            trace = trace.tb_next
        print(json.dumps({'isolated_failure_type': type(error).__name__,
                          'probe_locations': locations}, sort_keys=True), flush=True)
        raise SystemExit('Moon isolated provider qualification failed; private diagnostics withheld') from None
