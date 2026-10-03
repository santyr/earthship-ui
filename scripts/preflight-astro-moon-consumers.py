#!/usr/bin/env python3
"""GET-only drift check for the named Moon consumer/shared-binding review.

This is not automatic dependency closure, migration authority, or a protected
control qualification. No apply path, backup, command, SQL or service operation.
Print hashes only; executable rule bodies and configuration stay in memory.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402

MANAGED_SCRIPTS = {
    'sky-condition-calculator': 'd99c01c15682b1cda7ed29d1255b877630ff1e329e08c12ba3ce26b59e11fd0c',
    'hex_southoutlet_cycle': 'e697e2626a5e1ab4e4d079612c4b85d16dd79178a4ff80a5208b4bb108970d18',
    'hex_night_load_override': 'e7aed419e81f6772ef26cb48e788e6eef33b47ebb1cd27d664425a772831d793',
}
CANONICAL_MANAGED = {
    'hex_southoutlet_cycle': 'openhab/rules/southoutlet-cycle-current.js',
    'hex_night_load_override': 'openhab/rules/night-load-owner.js',
}
FILE_RULES = {
    'hex_astro_forecast_context': ('astro-forecast-context.js', 'f8f78077a802934754cb171e86dba3fff02b313cab7632ae02463bf733b8d3d4'),
    'hex_bedroom_temperature': ('bedroom-temperature.js', '44cf18e9de018d797d6096adc82eee0aee8221c084290f133cc166b8f2871ce9'),
    'hex_btc_24h_change': ('bitcoin-24h-change.js', '41893bdbd9eeefb60fab2ffa5bbe12c49ebc1c0f09e91176d285c02d9d719391'),
    'temp-highlow-24h': ('temperature-highlow-24h.js', '4c6c32a4847c93792f9748028ad8d53ac7116bc837a385544b7523fcd5c62297'),
    'update_days_until_season': ('update_days_until_season.js', 'd101eff0c4acf86ad900637e28cc7b30c1cf1185c5b3bcd116bef65e2114ed36'),
}
INSTALLED_JS = Path('/etc/openhab/automation/js')
FILE_PINS = (
    (Path('/etc/openhab/transform/astro.map'), '54b74cc4a17a96890e5d4594321516c40afa4832742da55ef26e3f6c64dc04c4',
     'openhab/transform/astro.map'),
    (Path('/var/lib/openhab/tmp/kar/openhab-addons-5.2.1/org/openhab/addons/bundles/org.openhab.binding.astro/5.2.1/org.openhab.binding.astro-5.2.1.jar'),
     '1a3b8207ec49834022706359bff60ff2f4eaa1354d392c48850cb418de63e7db', None),
    (Path('/usr/share/openhab/runtime/system/org/openhab/core/bundles/org.openhab.core.thing/5.2.1/org.openhab.core.thing-5.2.1.jar'),
     '1a0892c0faf8a6f6acd6efd17131dadbead6453ae6c5a13baa1a2a9dd4ea7572', None),
    (Path('/usr/share/openhab/runtime/system/org/openhab/core/bundles/org.openhab.core/5.2.1/org.openhab.core-5.2.1.jar'),
     '68e37d9c0eaf2343603082b12f460523f328f6f02efbe9a99b19502fb44f78ed', None),
)


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file_pin(path, expected, canonical=None):
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 16 * 1024**2,
            'reviewed source shape changed')
    body = path.read_bytes()
    require(sha256(body).hexdigest() == expected, 'reviewed source changed')
    if canonical is not None:
        source = ROOT / canonical
        require(not source.is_symlink() and source.is_file() and source.read_bytes() == body,
                'canonical source differs')
    return expected


def rule_graph(rows):
    require(isinstance(rows, list) and all(isinstance(row, dict) and isinstance(row.get('uid'), str)
                                        for row in rows), 'rule inventory incomplete')
    require(len({row['uid'] for row in rows}) == len(rows), 'duplicate rule identity')
    result = deepcopy(rows)
    for row in result:
        # The live status is execution state, not an executable definition.
        # Preserve every other field, including unknown future fields.
        row.pop('status', None)
    return sorted(result, key=lambda row: row['uid'])


def verify_rules(rows):
    by_id = {row['uid']: row for row in rule_graph(rows)}
    for uid, expected in MANAGED_SCRIPTS.items():
        row = by_id.get(uid, {})
        actions = row.get('actions', [])
        require(row.get('editable') is True and len(actions) == 1,
                'reviewed managed provider changed')
        require(actions[0].get('type') == 'script.ScriptAction'
                and actions[0].get('configuration', {}).get('type') == 'application/javascript',
                'reviewed managed action language changed')
        script = actions[0].get('configuration', {}).get('script')
        require(isinstance(script, str) and sha256(script.encode()).hexdigest() == expected,
                'reviewed managed action changed')
        if uid in CANONICAL_MANAGED:
            file_pin(ROOT / CANONICAL_MANAGED[uid], expected)
    for uid in FILE_RULES:
        row = by_id.get(uid, {})
        require(row.get('editable') is False and len(row.get('actions', [])) == 1
                and row['actions'][0].get('type') == 'jsr223.ScriptedAction',
                'reviewed file provider changed')


def sun_definition(row):
    require(isinstance(row, dict) and row.get('UID') == 'astro:sun:local'
            and row.get('thingTypeUID') == 'astro:sun'
            and row.get('editable') is True
            and row.get('statusInfo') == {'status': 'ONLINE', 'statusDetail': 'NONE'},
            'shared Sun baseline changed or unavailable')
    return row


def check(get=None):
    get = get or oh.get
    before = rule_graph(get('/rules'))
    sun = sun_definition(get('/things/astro:sun:local'))
    verify_rules(before)
    pins = dict(MANAGED_SCRIPTS)
    for uid, (name, expected) in FILE_RULES.items():
        pins[uid] = file_pin(INSTALLED_JS / name, expected,
                            'openhab/file-config/automation/js/' + name)
    for path, expected, canonical in FILE_PINS:
        pins[str(path)] = file_pin(path, expected, canonical)
    require(rule_graph(get('/rules')) == before, 'rule definitions changed during check')
    require(sun_definition(get('/things/astro:sun:local')) == sun,
            'Sun definitions changed during check')
    return {'scope': 'named_moon_consumer_source_drift_check', 'status': 'passed',
            'rule_count': len(before), 'rule_graph_sha256': digest(before),
            'source_pins_sha256': digest(pins), 'sun_definition_sha256': digest(sun),
            'reviewed_managed_scripts': sorted(MANAGED_SCRIPTS),
            'reviewed_file_rules': sorted(FILE_RULES), 'source_pins': pins,
            'all_consumer_closure': False, 'atomic_snapshot': False,
            'production_writes': 0, 'apply_available': False}


def command(args):
    require(args == [], 'no apply or arbitrary target interface')
    return check()


if __name__ == '__main__':
    try:
        print(json.dumps(command(sys.argv[1:]), sort_keys=True))
    except Exception:
        raise SystemExit('Moon consumer preflight refused; no production writes; private diagnostics withheld') from None
