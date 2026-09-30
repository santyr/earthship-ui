#!/usr/bin/env python3
"""Exercise Astro calculations only in a fresh, networkless OpenHAB 5.2.1.

Copies no production registry, credential or private recovery archive. Reads
only the live Sun Thing's location/settings to construct an isolated fixture.
"""

from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import secrets
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('display_runtime_qualification',
    ROOT / 'scripts/qualify-season-rule-provider.py')
display = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = display
spec.loader.exec_module(display)
runtime = display.runtime
ASTRO = runtime.ADDON.parents[2] / 'org.openhab.binding.astro/5.2.1/org.openhab.binding.astro-5.2.1.jar'
LABEL = 'hex.astro.forecast.actions'
ITEM = 'Astro_Qualification_Result'
THING = 'astro:sun:qualification'
RULE = 'isolated_astro_forecast_actions'
DAYS = ('2026-09-30', '2026-10-01', '2026-03-08', '2026-11-01',
        '2026-03-20', '2026-06-21', '2026-12-21')
ZONE = ZoneInfo('America/Denver')
PHASE = 'preflight'


def ready_rule(rest):
    try:
        rule = rest('GET', '/rules/' + RULE)
    except RuntimeError:
        return None  # File-provider registration may briefly return 404.
    return rule if isinstance(rule, dict) and rule.get('uid') == RULE and rule.get('editable') is False and rule.get('status') == {
        'status': 'IDLE', 'statusDetail': 'NONE'} else None


def fixture_source():
    return '''const {rules, actions, items} = require('openhab');
rules.JSRule({id: '%s', name: 'Isolated Astro forecast calculations',
  triggers: [], execute: () => {
    const sun = actions.get('astro', '%s');
    if (!sun) throw new Error('isolated Astro actions unavailable');
    const LocalDate = Java.type('java.time.LocalDate');
    const ZoneId = Java.type('java.time.ZoneId');
    const zone = ZoneId.of('America/Denver');
    const results = %s.map(day => {
      const noon = LocalDate.parse(day).atTime(12, 0).atZone(zone);
      const midnight = LocalDate.parse(day).atStartOfDay(zone);
      const event = (phase, moment) =>
        sun.getEventTime(phase, noon, moment).toInstant().toString();
      return {day, daylightStart: event('DAYLIGHT', 'START'),
        daylightEnd: event('DAYLIGHT', 'END'), sunriseStart: event('SUN_RISE', 'START'),
        sunriseEnd: event('SUN_RISE', 'END'), sunsetStart: event('SUN_SET', 'START'),
        sunsetEnd: event('SUN_SET', 'END'),
        noonElevation: String(sun.getElevation(noon)),
        noonAzimuth: String(sun.getAzimuth(noon)),
        noonRadiation: String(sun.getTotalRadiation(noon)),
        midnightRadiation: String(sun.getTotalRadiation(midnight))};
    });
    items.getItem('%s').postUpdate(JSON.stringify(results));
  }
});
''' % (RULE, THING, json.dumps(DAYS), ITEM)


def validate(rows):
    if not isinstance(rows, list) or len(rows) != len(DAYS):
        raise ValueError('exact bounded Astro date fixtures required')
    result = []
    for row, day in zip(rows, DAYS):
        if not isinstance(row, dict) or set(row) != {'day', 'daylightStart', 'daylightEnd',
                'sunriseStart', 'sunriseEnd', 'sunsetStart', 'sunsetEnd',
                'noonElevation', 'noonAzimuth', 'noonRadiation', 'midnightRadiation'} or row['day'] != day:
            raise ValueError('Astro fixture identity mismatch')
        events = {key: datetime.fromisoformat(row[key].replace('Z', '+00:00'))
                  for key in ('daylightStart', 'daylightEnd', 'sunriseStart',
                              'sunriseEnd', 'sunsetStart', 'sunsetEnd')}
        if any(at.tzinfo is None or at.astimezone(ZONE).date().isoformat() != day
               for at in events.values()):
            raise ValueError('Astro event date/zone mismatch')
        if not (events['sunriseStart'] < events['sunriseEnd'] == events['daylightStart']
                < events['daylightEnd'] == events['sunsetStart'] < events['sunsetEnd']):
            raise ValueError('Astro daylight event definitions differ')
        daylight = (events['daylightEnd'] - events['daylightStart']).total_seconds()
        quantities = {}
        for key, unit in (('noonElevation', '°'), ('noonAzimuth', '°'),
                          ('noonRadiation', 'W/m²'), ('midnightRadiation', 'W/m²')):
            raw = row[key]
            match = re.fullmatch(r'(-?\d+(?:\.\d+)?) ' + re.escape(unit), raw) if isinstance(raw, str) else None
            if match is None:
                raise ValueError('Astro quantity units differ')
            quantities[key] = float(match.group(1))
        if (not 0 < daylight < 86400 or not -90 <= quantities['noonElevation'] <= 90
                or not 0 <= quantities['noonAzimuth'] < 360
                or not 0 < quantities['noonRadiation'] < 1500
                or quantities['midnightRadiation'] != 0):
            raise ValueError('Astro quantity sanity failure')
        result.append({'day': day, 'daylight_seconds': daylight,
                       'sunrise_at': events['sunriseStart'].isoformat(),
                       'sunset_at': events['sunsetStart'].isoformat(),
                       'noon_elevation_degrees': quantities['noonElevation'],
                       'noon_azimuth_degrees': quantities['noonAzimuth'],
                       'noon_radiation_wm2': quantities['noonRadiation']})
    by_day = {row['day']: row for row in result}
    if not by_day['2026-12-21']['daylight_seconds'] < by_day['2026-06-21']['daylight_seconds']:
        raise ValueError('Astro winter/summer ordering failure')
    return result


def main():
    global PHASE
    if sys.argv[1:]:
        raise ValueError('no production action or arbitrary target arguments accepted')
    live = runtime.oh.get('/things/astro:sun:local')
    if live.get('statusInfo', {}).get('status') != 'ONLINE' or live.get('thingTypeUID') != 'astro:sun':
        raise ValueError('live Astro settings unavailable')
    configuration = live['configuration']
    if not isinstance(configuration.get('geolocation'), str):
        raise ValueError('explicit Sun location required')
    bundles = sorted(runtime.GRAAL.glob('org.graalvm.*/25.0.1/*.jar'))
    if len(bundles) != 22 or not runtime.ADDON.is_file() or not ASTRO.is_file():
        raise ValueError('cached pinned runtime unavailable')
    marker = secrets.token_hex(8)
    container = None
    try:
        PHASE = 'create_isolated_runtime'
        container = runtime.run(['docker', 'run', '-d', '--init', '--label', LABEL + '=' + marker,
            '--network', 'none', '--read-only', '--user', '9001:9001', '--cap-drop', 'ALL',
            '--memory', '2048m', '--memory-swap', '2048m', '--cpus', '2', '--pids-limit', '256',
            '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=64m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/conf:rw,nosuid,nodev,size=64m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/userdata:rw,exec,nosuid,nodev,size=512m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/addons:rw,nosuid,nodev,size=160m,uid=9001,gid=9001',
            '-e', 'EXTRA_JAVA_OPTS=-Xmx512m -Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
            '--entrypoint', '/bin/sh', runtime.IMAGE, '-c',
            'cp -a /openhab/dist/conf/. /openhab/conf/; cp -a /openhab/dist/userdata/. /openhab/userdata/; '
            'while [ ! -f /tmp/ready ]; do sleep 1; done; exec /openhab/start.sh server']).decode().strip()
        info = json.loads(runtime.run(['docker', 'inspect', container]))[0]
        host = info['HostConfig']
        if (info['Config']['Labels'].get(LABEL) != marker or host['NetworkMode'] != 'none'
                or host['Privileged'] or host.get('Binds') or host.get('Devices')
                or host.get('PortBindings') or info['AppArmorProfile'] != 'docker-default'):
            raise ValueError('isolation policy mismatch')
        runtime.install(container, 'conf/items/astro-qualification.items', ('String ' + ITEM + '\n').encode())
        runtime.install_bundles(container, bundles + [ASTRO])
        runtime.run(['docker', 'exec', container, 'touch', '/tmp/ready'])
        PHASE = 'runtime_boot'
        display.wait_for(lambda: display._startup_item(container, ITEM), seconds=240)
        client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                  '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
        display.wait_for(lambda: display._active_bundle(client, 'org.graalvm.js.js-language'), seconds=90)
        display.wait_for(lambda: display._active_bundle(client, 'org.openhab.binding.astro'), seconds=90)
        runtime.install_bundles(container, [runtime.ADDON])
        display.wait_for(lambda: display._active_bundle(client, 'org.openhab.automation.jsscripting'), seconds=90)
        PHASE = 'isolated_api_user'
        runtime.run(client + ['openhab:users add qualification ' + secrets.token_hex(20) + ' administrator'], b'\n')
        output = runtime.run(client + ["openhab:users addApiToken qualification qualification ''"], b'\n').decode()
        tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', output)
        if len(tokens) != 1:
            raise ValueError('isolated API token unavailable')
        def rest(method, path, body=None):
            args = ['docker', 'exec', '-i', container, 'curl', '-fsS', '--max-time', '8',
                    '-X', method, '-H', 'Authorization: Bearer ' + tokens[0],
                    '-H', 'Content-Type: application/json']
            if body is not None: args += ['--data-binary', '@-']
            raw = runtime.run(args + ['http://127.0.0.1:8080/rest' + path],
                              json.dumps(body).encode() if body is not None else None)
            return json.loads(raw) if raw.strip() else None
        PHASE = 'isolated_thing'
        rest('POST', '/things', {'UID': THING, 'thingTypeUID': 'astro:sun',
             'label': 'Isolated Sun calculation fixture', 'configuration': configuration})
        display.wait_for(lambda: rest('GET', '/things/' + THING).get('statusInfo', {}).get('status') == 'ONLINE')
        runtime.run(['docker', 'exec', container, 'mkdir', '-p', '/openhab/conf/automation/js'])
        source = fixture_source().encode()
        runtime.install(container, 'conf/automation/js/astro-forecast-qualification.js', source)
        PHASE = 'isolated_rule_readiness'
        display.wait_for(lambda: ready_rule(rest), seconds=120)
        PHASE = 'isolated_action_execution'
        rest('POST', '/rules/' + RULE + '/runnow')
        def result():
            state = rest('GET', '/items/' + ITEM)['state']
            return json.loads(state) if state not in ('NULL', 'UNDEF') else None
        rows = display.wait_for(result, seconds=90)
        PHASE = 'result_validation'
        rows = validate(rows)
        print(json.dumps({'status': 'qualified_isolated_actions', 'production_writes': 0,
            'fixture_source_sha256': sha256(source).hexdigest(),
            'astro_bundle_sha256': sha256(ASTRO.read_bytes()).hexdigest(),
            'dates': rows, 'live_action_executed': False}, sort_keys=True), flush=True)
    finally:
        if container is not None:
            owner = runtime.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "' + LABEL + '"}}', container]).decode().strip()
            if owner == marker:
                runtime.run(['docker', 'rm', '-f', '-v', container], timeout=45)
                print('owned_isolated_container_removed=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'qualification_failed', 'phase': PHASE,
                          'error_class': type(error).__name__, 'diagnostics_withheld': True}), file=sys.stderr)
        raise SystemExit(1) from None
