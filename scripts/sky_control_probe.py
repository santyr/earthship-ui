"""Synthetic, networkless-container-only sky/pump recovery probes.

No live REST client, production writes, device links or persistent scheduler.
Callbacks must come from qualify-season-rule-provider's inspected container.
This qualifies specific recovery paths, not whole-installation control safety.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re

UID = 'hex_southoutlet_cycle'
ACTION_SHA = 'e697e2626a5e1ab4e4d079612c4b85d16dd79178a4ff80a5208b4bb108970d18'
DURABLE_ACTION_SHA = '4c34780e544d80af8eb36d047a949fa30e0198bb50fa57650285052db3c52d9b'
TRIGGERS = (
    ('core.ItemCommandTrigger', (('itemName', 'SouthOutlet_ManualRequest'),)),
    ('timer.GenericCronTrigger', (('cronExpression', '0 * * * * ?'),)),
)
PUMPS = ('SouthOutlet_Outlet2_Switch', 'East_Bed_Socket_Outlet_2_Power')
ITEMS = b'''Number DCData_Voltage
Number BMS_SOC
String BMS_SOC_Evidence_JSON
String BMS_Comms_Status
Number SouthOutlet_LowSocCutoff
Switch SouthOutlet_Outlet2_Switch
Switch East_Bed_Socket_Outlet_2_Power
DateTime SouthOutlet_LastAutoRun
DateTime SouthOutlet_LastCycleStart
String SouthOutlet_AutoStatus
Number Sun_Position_Elevation
String SouthOutlet_ManualRequest
String SouthOutlet_ManualResult
String SouthOutlet_LastCycle
'''


def control_payload(rule, source, *, consumer_revision='original'):
    # Keep the original deployment adapter's baseline unchanged. Qualification
    # of the attended repair must explicitly select its separately reviewed pin.
    if consumer_revision == 'original':
        expected = ACTION_SHA
    elif consumer_revision == 'durable-recovery':
        expected = DURABLE_ACTION_SHA
    else:
        raise RuntimeError('reviewed sky-consumer revision required')
    triggers = tuple((x.get('type'), tuple(sorted(x.get('configuration', {}).items())))
                     for x in rule.get('triggers', []))
    actions = rule.get('actions', [])
    if (rule.get('uid') != UID or rule.get('editable') is not True
            or rule.get('status') != {'status': 'IDLE', 'statusDetail': 'NONE'}
            or triggers != TRIGGERS or rule.get('conditions')
            or len(actions) != 1 or actions[0].get('type') != 'script.ScriptAction'
            or actions[0].get('configuration', {}).get('type') != 'application/javascript'
            or sha256(actions[0]['configuration']['script'].encode()).hexdigest() != expected
            or sha256(source).hexdigest() != expected):
        raise RuntimeError('exact current sky-consumer source/provider required')
    return {key: rule[key] for key in
            ('uid', 'name', 'description', 'tags', 'triggers', 'conditions', 'actions')
            if key in rule}


def soc_receipt(at, *, expired):
    now = int(at.timestamp() * 1000)
    observed = now - (300000 if expired else 1000)
    return {'version': 1, 'streamEpoch': 'aa1f3b9e-147b-4ac0-a69d-1287831fc19c',
            'recordedAt': observed, 'status': 'valid', 'reason': 'ok',
            'observedAt': observed, 'scaleObservedAt': observed,
            'validUntil': observed + 120000, 'soc': 95}


def on_command_seen(logs, name):
    return bool(re.search(r"Item '" + re.escape(name) + r"' received command ON(?:\s|$)", logs))


def require_no_on_commands(logs):
    if any(on_command_seen(logs, name) for name in PUMPS):
        raise RuntimeError('isolated fail-closed probe emitted a pump ON command')


def refusal_matches(states, reason):
    return (all(states.get(name) == 'OFF' for name in PUMPS)
            and states.get('SouthOutlet_AutoStatus', '').split(',', 1)[0] == 'reason=' + reason)


def fixture_state_matches(name, actual, expected):
    if name == 'SouthOutlet_LastCycleStart':
        try:
            return datetime.fromisoformat(actual.split('[', 1)[0]) == datetime.fromisoformat(expected)
        except (ValueError, TypeError):
            return False
    return actual == expected


def run_probe(rest, logs, wait_for, *, phase):
    """Exercise exact action through isolated REST; all inputs are synthetic."""
    def seed(values):
        for name, value in values.items():
            if rest('PUT', '/items/' + name + '/state', str(value),
                    content_type='text/plain')[0] not in (200, 202):
                raise RuntimeError('isolated control fixture update failed')
        wait_for(lambda: all(fixture_state_matches(name, rest('GET', '/items/' + name)[1].get('state'), str(value))
                             for name, value in values.items()), seconds=20)

    def states():
        return {name: rest('GET', '/items/' + name)[1]['state']
                for name in (*PUMPS, 'SouthOutlet_AutoStatus')}

    def execute(uid):
        if rest('POST', '/rules/' + uid + '/runnow', {})[0] not in (200, 202, 204):
            raise RuntimeError('isolated control execution failed')

    # High held SoC and CLEAR sky must never substitute for fresh source evidence.
    seed({'DCData_Voltage': '53.6', 'BMS_SOC': '100', 'BMS_Comms_Status': 'OK',
          'SouthOutlet_LowSocCutoff': '45', 'Sun_Position_Elevation': '37.3',
          **{name: 'OFF' for name in PUMPS}})
    seed({'Sun_SunPhaseName': 'DAY', 'Sun_TotalRadiation': '100',
          'AmbientWeatherWS2902A_SolarRadiation': '100', 'WeatherData_HealthStatus': 'OK',
          'WeatherData_WH65B_AgeSeconds': '30'})
    execute('sky-condition-calculator')
    wait_for(lambda: rest('GET', '/items/SkyCondition')[1]['state'] == 'CLEAR', seconds=20)
    for kind, reason in (('missing', 'invalid_soc_evidence'),
                         ('expired', 'invalid_soc_evidence'),
                         ('stale-comms', 'bms_comms_stale')):
        at = datetime.now(timezone.utc)
        evidence = 'NULL' if kind == 'missing' else json.dumps(
            soc_receipt(at, expired=kind == 'expired'), separators=(',', ':'))
        seed({'BMS_SOC_Evidence_JSON': evidence,
              'BMS_Comms_Status': 'STALE' if kind == 'stale-comms' else 'OK',
              'SouthOutlet_AutoStatus': 'probe_waiting'})
        before = logs()
        execute(UID)
        wait_for(lambda: refusal_matches(states(), reason), seconds=20)
        after = logs()
        if not after.startswith(before):
            raise RuntimeError('isolated command log continuity lost')
        require_no_on_commands(after[len(before):])
        print(f'isolated_sky_control={phase}:{kind}:both_off', flush=True)

    # A positive control prevents a disabled/broken action or absent command
    # logger from making the rejection tests pass vacuously. No device is linked.
    at = datetime.now(timezone.utc)
    seed({'BMS_Comms_Status': 'OK',
          'BMS_SOC_Evidence_JSON': json.dumps(soc_receipt(at, expired=False), separators=(',', ':')),
          'SouthOutlet_LastCycleStart': (at - timedelta(hours=6)).isoformat(),
          'SouthOutlet_AutoStatus': 'probe_waiting'})
    before = logs()
    execute(UID)
    wait_for(lambda: states()['SouthOutlet_AutoStatus'].startswith('reason=cycle_started,'), seconds=20)
    wait_for(lambda: sorted(states()[name] for name in PUMPS) == ['OFF', 'ON']
             and any(on_command_seen(logs()[len(before):], name) for name in PUMPS), seconds=20)
    actual = states()
    after = logs()
    if (not after.startswith(before) or sorted(actual[name] for name in PUMPS) != ['OFF', 'ON']
            or not any(on_command_seen(after[len(before):], name) for name in PUMPS)):
        raise RuntimeError('isolated positive control or command trace missing')
    print(f'isolated_sky_control={phase}:fresh:single_unlinked_pump_on', flush=True)

    # Immediately cancel only this synthetic cycle through the real safety path.
    seed({'BMS_SOC_Evidence_JSON': 'NULL', 'SouthOutlet_AutoStatus': 'probe_waiting'})
    execute(UID)
    wait_for(lambda: refusal_matches(states(), 'invalid_soc_evidence'), seconds=20)
