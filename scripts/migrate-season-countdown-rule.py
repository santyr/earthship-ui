#!/usr/bin/env python3
"""Guarded, no-restart handoff of small display-only OpenHAB rules.

Default --check is read-only. --apply saves a private managed-rule backup,
withdraws that provider, installs the exact file rule, and rolls back on any
failed provider check. It never posts test Item values or commands hardware.
"""

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402

@dataclass(frozen=True)
class DisplayRule:
    uid: str
    script_sha: str
    source: Path
    source_sha: str
    target: Path
    triggers: tuple
    items: tuple
    outputs: tuple
    backup_prefix: str
    outputs_must_hold: bool = True


RULES = {
    'battery-icon': DisplayRule(
        uid='UpdateBatteryIcon',
        script_sha='834544eb8a9648a6c3082a8a135b3d22b5ef5ae0922a86fb9ee3e4f4fb110e2f',
        source=ROOT / 'openhab/file-config/automation/js/battery-icon.js',
        source_sha='bc6c0954b232902d4b5af444b6381cf5c8ea4af062aa5a12b8195de364729b45',
        target=Path('/etc/openhab/automation/js/battery-icon.js'),
        triggers=(('timer.GenericCronTrigger',
                   (('cronExpression', '0/30 * * * * ?'),)),),
        items=(('BMS_SOC', 'Number'), ('DCData_Current', 'Number:ElectricCurrent'),
               ('BatteryIcon', 'String'), ('BatteryChargingStatus', 'Switch')),
        outputs=('BatteryIcon', 'BatteryChargingStatus'),
        backup_prefix='battery-icon-rule-',
        outputs_must_hold=False,  # real charge transitions are not state corruption
    ),
    'season': DisplayRule(
        uid='update_days_until_season',
        script_sha='d43b3f993991966ade5d428bc4ff6af603a253a06f336ff93221cc22cc332311',
        source=ROOT / 'openhab/file-config/automation/js/update_days_until_season.js',
        source_sha='d101eff0c4acf86ad900637e28cc7b30c1cf1185c5b3bcd116bef65e2114ed36',
        target=Path('/etc/openhab/automation/js/update_days_until_season.js'),
        triggers=(('core.ItemStateChangeTrigger', (('itemName', 'Sun_TimeLeft'),)),),
        items=(('Sun_TimeLeft', 'Number:Time'), ('Sun_NextSeason', 'String'),
               ('DaysUntilNextSeason', 'String')),
        outputs=('DaysUntilNextSeason',),
        backup_prefix='season-rule-',
    ),
    'sky': DisplayRule(
        uid='sky-condition-calculator',
        script_sha='d99c01c15682b1cda7ed29d1255b877630ff1e329e08c12ba3ce26b59e11fd0c',
        source=ROOT / 'openhab/file-config/automation/js/sky-condition-calculator.js',
        source_sha='6921170816d665062ff934c7a3e1b371b6ed565d35c081ec89ff4338859b4320',
        target=Path('/etc/openhab/automation/js/sky-condition-calculator.js'),
        triggers=(
            ('core.ItemStateChangeTrigger', (('itemName', 'Sun_SunPhaseName'),)),
            ('core.ItemStateChangeTrigger', (('itemName', 'Sun_TotalRadiation'),)),
            ('core.ItemStateChangeTrigger', (('itemName', 'AmbientWeatherWS2902A_SolarRadiation'),)),
            ('core.ItemStateChangeTrigger', (('itemName', 'WeatherData_HealthStatus'),)),
            ('timer.GenericCronTrigger', (('cronExpression', '0 0/2 * * * ?'),)),
        ),
        items=(('Sun_SunPhaseName', 'String'), ('Sun_TotalRadiation', 'Number:Intensity'),
               ('AmbientWeatherWS2902A_SolarRadiation', 'Number:Intensity'),
               ('WeatherData_HealthStatus', 'String'),
               ('WeatherData_WH65B_AgeSeconds', 'Number'),
               ('SunPhaseIcon', 'String'), ('MoonPhaseicon', 'String'),
               ('SkyCondition', 'String'), ('SkyConditionIcon', 'String'),
               ('SkyCondition_LastEval', 'DateTime'),
               ('SkyCondition_Diagnostic', 'String')),
        outputs=('SkyCondition', 'SkyConditionIcon'),
        backup_prefix='sky-rule-',
    ),
    'extrema': DisplayRule(
        uid='temp-highlow-24h',
        script_sha='a499269f5aabf7a82de55f9fbc168d7c281c3155d07d91321a2259199b7072db',
        source=ROOT / 'openhab/file-config/automation/js/temperature-highlow-24h.js',
        source_sha='4c6c32a4847c93792f9748028ad8d53ac7116bc837a385544b7523fcd5c62297',
        target=Path('/etc/openhab/automation/js/temperature-highlow-24h.js'),
        triggers=(('timer.GenericCronTrigger',
                   (('cronExpression', '0 0/15 * * * ?'),)),),
        items=(('AmbientWeatherWS2902A_IndoorSensor_Temperature', 'Number'),
               ('AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', 'Number'),
               ('IndoorTemp_24h_Low', 'Number:Temperature'),
               ('IndoorTemp_24h_High', 'Number:Temperature'),
               ('OutdoorTemp_24h_Low', 'Number:Temperature'),
               ('OutdoorTemp_24h_High', 'Number:Temperature')),
        outputs=('IndoorTemp_24h_Low', 'IndoorTemp_24h_High',
                 'OutdoorTemp_24h_Low', 'OutdoorTemp_24h_High'),
        backup_prefix='extrema-rule-',
    ),
    'bitcoin': DisplayRule(
        uid='hex_btc_24h_change',
        script_sha='9e15eb8e7f4e3d3118f12295d7b09f82525ab52f41b951f8809097c98fc369bb',
        source=ROOT / 'openhab/file-config/automation/js/bitcoin-24h-change.js',
        source_sha='41893bdbd9eeefb60fab2ffa5bbe12c49ebc1c0f09e91176d285c02d9d719391',
        target=Path('/etc/openhab/automation/js/bitcoin-24h-change.js'),
        triggers=(('core.ItemStateUpdateTrigger',
                   (('itemName', 'BTC_USD_Price'),)),),
        items=(('BTC_USD_Price', 'Number'),
               ('BTC_Price_24h_PercentChange', 'Number')),
        outputs=('BTC_Price_24h_PercentChange',),
        backup_prefix='bitcoin-rule-',
        outputs_must_hold=False,  # natural price polls continue during handoff
    ),
}

RULE = RULES['season'].uid  # Historical import compatibility for focused tests.
RELEASE_READY = {'season': False, 'sky': False, 'extrema': False, 'bitcoin': False,
                 'battery-icon': False}
# Completed display handoffs stay closed; a future transfer needs its own gate.
# SkyCondition gates greywater eligibility; its cutover remains held.
BACKUP_ROOT = Path('/home/sat/.local/state')
FIELDS = ('uid', 'name', 'description', 'tags', 'triggers', 'conditions', 'actions')


def trigger_contract(rule):
    return tuple((trigger.get('type'), tuple(sorted(trigger.get('configuration', {}).items())))
                 for trigger in rule.get('triggers', []))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def request(method, path, body=None):
    data = json.dumps(body, separators=(',', ':')).encode() if body is not None else None
    req = Request(oh.BASE + path, method=method, data=data,
                  headers={'Authorization': 'Bearer ' + oh.token(),
                           'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=12) as response:
            return response.status
    except HTTPError as error:
        raise RuntimeError('OpenHAB ' + method + ' HTTP ' + str(error.code)) from None


def rule_or_none(config=RULES['season']):
    try:
        return oh.get('/rules/' + config.uid)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def wait_rule(predicate, config=RULES['season'], *, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        current = rule_or_none(config)
        if predicate(current):
            return current
        time.sleep(1)
    raise RuntimeError('display rule provider timeout')


def file_rule_ok(row, config=RULES['season']):
    return (isinstance(row, dict) and row.get('uid') == config.uid
            and row.get('editable') is False
            and row.get('status') in ({'status': 'IDLE', 'statusDetail': 'NONE'},
                                      {'status': 'RUNNING', 'statusDetail': 'NONE'})
            and trigger_contract(row) == config.triggers)


def managed_rule_ok(row, original):
    return (isinstance(row, dict) and row.get('editable') is True
            and all(row.get(field) == original.get(field) for field in FIELDS)
            and row.get('status') in ({'status': 'IDLE', 'statusDetail': 'NONE'},
                                      {'status': 'RUNNING', 'statusDetail': 'NONE'}))


def preflight(config=RULES['season']):
    require(not config.target.exists() and not config.target.is_symlink(),
            'display rule target exists')
    require(digest(config.source.read_bytes()) == config.source_sha,
            'display rule source changed')
    service = subprocess.run(['systemctl', 'is-active', 'openhab.service'],
                             check=True, text=True, capture_output=True, timeout=5)
    require(service.stdout.strip() == 'active', 'OpenHAB is not active')
    original = rule_or_none(config)
    require(original is not None and original.get('uid') == config.uid
            and original.get('editable') is True
            and original.get('status') == {'status': 'IDLE', 'statusDetail': 'NONE'}
            and trigger_contract(original) == config.triggers
            and not original.get('conditions')
            and len(original.get('actions', [])) == 1,
            'managed display rule changed or unhealthy')
    require(digest(original['actions'][0]['configuration']['script'].encode()) == config.script_sha,
            'managed display script changed')
    for name, type_name in config.items:
        item = oh.get('/items/' + name)
        require(item.get('type') == type_name and item.get('state') not in
                (None, 'NULL', 'UNDEF'), 'display Item unavailable: ' + name)
    require(sum(rule.get('uid') == config.uid for rule in oh.get('/rules')) == 1,
            'display rule identity is not unique')
    return original, {name: oh.get('/items/' + name)['state'] for name in config.outputs}


def backup(original, config=RULES['season']):
    directory = Path(tempfile.mkdtemp(prefix=config.backup_prefix, dir=BACKUP_ROOT))
    os.chmod(directory, 0o700)
    body = json.dumps(original, sort_keys=True, separators=(',', ':')).encode()
    path = directory / 'managed-rule.json'
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(body)
        output.flush()
        os.fsync(output.fileno())
    require(digest(path.read_bytes()) == digest(body), 'managed backup differs')
    return directory


def install(config=RULES['season']):
    fd, name = tempfile.mkstemp(prefix='.' + config.backup_prefix,
                               suffix='.js', dir=config.target.parent)
    staged = Path(name)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, 'wb') as output:
            output.write(config.source.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        require(digest(staged.read_bytes()) == config.source_sha,
                'staged display source differs')
        os.replace(staged, config.target)
        require(digest(config.target.read_bytes()) == config.source_sha,
                'installed display source differs')
    finally:
        if staged.exists():
            staged.unlink()


def output_states(config):
    return {name: oh.get('/items/' + name)['state'] for name in config.outputs}


def apply(original, old_state, config=RULES['season']):
    directory = backup(original, config)
    print('private_backup=' + str(directory), flush=True)
    changed = success = False
    try:
        require(rule_or_none(config) == original, 'managed rule changed during backup')
        if config.outputs_must_hold:
            require(output_states(config) == old_state,
                    'display output changed during backup')
        changed = True
        require(request('DELETE', '/rules/' + config.uid) in (200, 204),
                'managed display withdrawal refused')
        wait_rule(lambda row: row is None, config)
        install(config)
        wait_rule(lambda row: file_rule_ok(row, config), config)
        require(sum(rule.get('uid') == config.uid for rule in oh.get('/rules')) == 1,
                'display rule duplicated after file install')
        if config.outputs_must_hold:
            require(output_states(config) == old_state,
                    'display state changed during handoff')
        success = True
        print('status=file_provider_provisional; natural_update_pending=true', flush=True)
    finally:
        if changed and not success:
            if config.target.exists():
                require(not config.target.is_symlink()
                        and digest(config.target.read_bytes()) == config.source_sha,
                        'unexpected display file target; manual rollback required')
                config.target.rename(directory / 'failed-candidate.js')
                wait_rule(lambda row: row is None, config)
            current = rule_or_none(config)
            if current is None:
                payload = {field: original[field] for field in FIELDS if field in original}
                require(request('POST', '/rules', payload) == 201,
                        'managed display rollback refused')
            elif not managed_rule_ok(current, original):
                raise RuntimeError('unknown display provider during rollback')
            wait_rule(lambda row: managed_rule_ok(row, original), config)
            if config.outputs_must_hold:
                require(output_states(config) == old_state,
                        'display output changed during rollback')
            print('managed_display_rollback_verified=true', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=tuple(RULES), default='season')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check', action='store_true')
    action.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply and not RELEASE_READY[args.kind]:
        raise SystemExit(args.kind + ' control-input cutover is not release-qualified')
    config = RULES[args.kind]
    original, state = preflight(config)
    if args.check:
        print(config.uid + '_preflight=passed; provider=managed; writes=0')
        return
    apply(original, state, config)


if __name__ == '__main__':
    main()
