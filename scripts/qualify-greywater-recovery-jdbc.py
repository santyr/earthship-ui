#!/usr/bin/env python3
"""Qualify pump recovery in disposable networkless OpenHAB/PostgreSQL only.

Exact action sources, synthetic unlinked Items and genuine JDBC denial/readback,
JVM replacement and original-action rollback. The fixture omits the automatic
cron to make fault dispatch deterministic; it retains the native manual trigger.
No production writes, hardware, host mounts, exposed ports or external network.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import copy
import importlib.util
import json
from pathlib import Path
import re
import secrets
import sys
import time

import sky_control_probe as sky

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'openhab/rules/southoutlet-cycle-current.js'
CANDIDATE_SHA = '4c34780e544d80af8eb36d047a949fa30e0198bb50fa57650285052db3c52d9b'
PUMPS = sky.PUMPS
UID = sky.UID
LEDGER = 'SouthOutlet_ManualRequest'
LABEL = 'hex.greywater.jdbc.qualification'


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


aqi = load('greywater_jdbc_support', 'qualify-openmeteo-aqi-jdbc.py')
provider = load('greywater_provider_support', 'qualify-season-rule-provider.py')
runtime = provider.runtime


def sha(body):
    return sha256(body).hexdigest()


def fault_sql(table, *, deny):
    if not re.fullmatch(r'[Ii]tem[0-9]+', table):
        raise RuntimeError('unique generated ledger table required')
    verb = 'REVOKE' if deny else 'GRANT'
    target = 'FROM' if deny else 'TO'
    return f'{verb} INSERT ON TABLE public."{table}" {target} greywater_qualification;'


def check_refusal(states, logs):
    if not sky.refusal_matches(states, 'ledger_recovery_failed'):
        raise RuntimeError('durability refusal and both synthetic pumps OFF required')
    sky.require_no_on_commands(logs)


def wait_for(check, *, seconds=90):
    def ready():
        try:
            return check()
        except (RuntimeError, ValueError, IndexError):
            return False  # Bounded observation retry, never a success inference.
    return provider.wait_for(ready, seconds=seconds)


def main():
    candidate = SOURCE.read_bytes()
    if sha(candidate) != CANDIDATE_SHA:
        raise RuntimeError('reviewed source-only candidate drift')
    live = runtime.oh.get('/rules/' + UID)  # The only live read: DTO, never credentials printed.
    original = sky.control_payload(live, live['actions'][0]['configuration']['script'].encode())
    original['triggers'] = [x for x in original['triggers'] if x['type'] == 'core.ItemCommandTrigger']
    proposed = copy.deepcopy(original)
    proposed['actions'][0]['configuration']['script'] = candidate.decode()
    bundles = sorted(runtime.GRAAL.glob('org.graalvm.*/25.0.1/*.jar'))
    if len(bundles) != 22 or not runtime.ADDON.is_file():
        raise RuntimeError('cached matched JavaScript resources missing')
    marker = secrets.token_hex(8)
    with aqi.Database() as database:
        container = None
        try:
            def sql(statement):
                return runtime.run(['docker', 'exec', '-i', database.cid, 'psql', '-U', 'postgres',
                                    '-d', 'postgres', '-At', '-v', 'ON_ERROR_STOP=1'],
                                   statement.encode()).decode().strip()

            wait_for(lambda: sql('SELECT 1;') == '1', seconds=60)
            sql("CREATE ROLE greywater_qualification LOGIN PASSWORD '" + database.password
                + "'; GRANT ALL ON SCHEMA public TO greywater_qualification;")
            command = ('cp -a /openhab/dist/conf/. /openhab/conf/; '
                       'cp -a /openhab/dist/userdata/. /openhab/userdata/; '
                       'touch /tmp/bootstrap-ready; while [ ! -f /tmp/ready ]; do sleep 1; done; '
                       'while true; do while [ ! -f /tmp/boot-permit ]; do sleep 1; done; '
                       'rm /tmp/boot-permit; /openhab/start.sh server & jvm_child=$!; '
                       'wait "$jvm_child"; touch /tmp/jvm-stopped; done')
            container = runtime.run(['docker', 'run', '-d', '--init', '--label', LABEL + '=' + marker,
                '--network', database.network, '--read-only', '--user', '9001:9001', '--cap-drop', 'ALL',
                '--memory', '2048m', '--memory-swap', '2048m', '--cpus', '2', '--pids-limit', '256',
                '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=64m,uid=9001,gid=9001',
                '--tmpfs', '/openhab/conf:rw,nosuid,nodev,size=64m,uid=9001,gid=9001',
                '--tmpfs', '/openhab/userdata:rw,exec,nosuid,nodev,size=512m,uid=9001,gid=9001',
                '--tmpfs', '/openhab/addons:rw,nosuid,nodev,size=160m,uid=9001,gid=9001',
                '-e', 'EXTRA_JAVA_OPTS=-Xmx512m -Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
                '--entrypoint', '/bin/sh', runtime.IMAGE, '-c', command]).decode().strip()
            info = json.loads(runtime.run(['docker', 'inspect', container]))[0]
            host = info['HostConfig']
            if (info['Config']['Labels'].get(LABEL) != marker
                    or host['NetworkMode'] != database.network or host['Privileged']
                    or host.get('Binds') or host.get('Devices') or host.get('PortBindings')
                    or info['AppArmorProfile'] != 'docker-default'):
                raise RuntimeError('isolated OpenHAB resource/network policy mismatch')
            wait_for(lambda: runtime.run(['docker', 'exec', container, 'test', '-f',
                                                  '/tmp/bootstrap-ready']) == b'', seconds=30)
            database.stage(container)
            runtime.install(container, 'conf/services/jdbc.cfg', (
                'url=jdbc:postgresql://127.0.0.1:5432/postgres\nuser=greywater_qualification\n'
                'password=' + database.password + '\n').encode())
            fixture = sky.ITEMS.replace(b'String SouthOutlet_ManualRequest\n',
                                        b'String SouthOutlet_ManualRequest {autoupdate="false"}\n')
            fixture += b'String SkyCondition\n'
            runtime.install(container, 'conf/items/greywater-recovery.items', fixture)
            runtime.install(container, 'conf/persistence/jdbc.persist',
                            (ROOT / 'openhab/file-config/persistence/jdbc.persist').read_bytes())
            runtime.install_bundles(container, bundles)
            runtime.run(['docker', 'exec', container, 'touch', '/tmp/boot-permit', '/tmp/ready'])
            wait_for(lambda: provider._startup_item(container, LEDGER), seconds=240)
            time.sleep(20)
            client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                      '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
            wait_for(lambda: provider._active_bundle(client, 'org.graalvm.js.js-language'))
            runtime.install_bundles(container, [runtime.ADDON])
            wait_for(lambda: provider._active_bundle(client, 'org.openhab.automation.jsscripting'))
            runtime.run(client + ['openhab:users add qualification ' + secrets.token_hex(20)
                                  + ' administrator'], b'\n')
            output = runtime.run(client + ["openhab:users addApiToken qualification qualification ''"], b'\n').decode()
            tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', output)
            if len(tokens) != 1:
                raise RuntimeError('isolated API token unavailable; output withheld')
            header = ('Authorization: Bearer ' + tokens[0] + '\n').encode()

            def rest(method, path, body=None, *, content_type='application/json'):
                code, payload = aqi.request(container, header, path, method,
                    None if body is None else str(body) if content_type == 'text/plain' else json.dumps(body),
                    content_type)
                try: result = json.loads(payload) if payload else None
                except ValueError: result = payload
                return code, result

            def state(name):
                code, value = rest('GET', '/items/' + name)
                if code != 200: raise RuntimeError('isolated Item read unavailable')
                return value['state']

            def seed(values):
                for name, value in values.items():
                    if rest('PUT', '/items/' + name + '/state', str(value), content_type='text/plain')[0] != 202:
                        raise RuntimeError('isolated state seed refused')
                wait_for(lambda: all(sky.fixture_state_matches(
                    'SouthOutlet_LastCycleStart' if name == 'SouthOutlet_LastAutoRun' else name,
                    state(name), str(value))
                                             for name, value in values.items()), seconds=20)

            def events():
                return runtime.run(['docker', 'exec', container, 'cat',
                                    '/openhab/userdata/logs/events.log']).decode()

            def states():
                return {name: state(name) for name in (*PUMPS, 'SouthOutlet_AutoStatus')}

            def fresh_inputs():
                now = datetime.now(timezone.utc)
                receipt = sky.soc_receipt(now, expired=False)
                receipt['soc'] = 99
                seed({'BMS_SOC_Evidence_JSON': json.dumps(receipt, separators=(',', ':'))})

            def dispatch(reason):
                fresh_inputs()
                seed({'SouthOutlet_AutoStatus': 'qualification_waiting'})
                if rest('POST', '/rules/' + UID + '/runnow', {})[0] not in (200, 202, 204):
                    raise RuntimeError('isolated rule dispatch refused')
                wait_for(lambda: state('SouthOutlet_AutoStatus').split(',', 1)[0]
                                  == 'reason=' + reason, seconds=30)

            def history():
                code, result = rest('GET', '/persistence/items/' + LEDGER + '?serviceId=jdbc')
                if code != 200 or not isinstance(result.get('data'), list):
                    raise RuntimeError('actual isolated JDBC history unavailable')
                return result['data']

            if rest('POST', '/rules', proposed)[0] != 201:
                raise RuntimeError('isolated candidate creation refused')
            wait_for(lambda: provider._healthy_control(rest))
            if rest('GET', '/rules/' + UID)[1]['actions'] != proposed['actions']:
                raise RuntimeError('initial isolated action source mismatch')
            now = datetime.now(timezone.utc)
            accepted = json.dumps({'version': 'greywater-request-ledger/v1', 'entries': [{
                'requestId': 'jdbc-recovery-' + marker, 'status': 'accepted', 'reason': 'accepted',
                'at': (now - timedelta(minutes=10)).isoformat().replace('+00:00', 'Z'),
            }]}, separators=(',', ':'))
            seed({'DCData_Voltage': '53.6', 'BMS_SOC': '99', 'BMS_Comms_Status': 'OK',
                  'SouthOutlet_LowSocCutoff': '45', 'SkyCondition': 'CLEAR', 'Sun_Position_Elevation': '37',
                  PUMPS[0]: 'OFF', PUMPS[1]: 'OFF', LEDGER: accepted,
                  'SouthOutlet_LastAutoRun': (now - timedelta(hours=4)).isoformat(),
                  'SouthOutlet_LastCycleStart': (now - timedelta(hours=4)).isoformat()})
            wait_for(lambda: sql("SELECT EXISTS (SELECT FROM information_schema.tables "
                                         "WHERE table_schema='public' AND lower(table_name)='items');") == 't')
            wait_for(lambda: history() and history()[-1]['state'] == accepted, seconds=90)
            prefix = history()
            names = sql("SELECT table_name FROM information_schema.columns WHERE table_schema='public' "
                        "AND lower(column_name)='value' AND lower(table_name) LIKE 'item%';").splitlines()
            ledger_tables = [name for name in names if re.fullmatch(r'[Ii]tem[0-9]+', name)
                             and sql('SELECT EXISTS(SELECT FROM public."' + name
                                     + '" WHERE value::text = $q$' + accepted + '$q$);') == 't']
            if len(ledger_tables) != 1:
                raise RuntimeError('unique synthetic ledger table mapping required')
            table = ledger_tables[0]
            sql(fault_sql(table, deny=True))
            if sql("SELECT has_table_privilege('greywater_qualification', 'public.\"" + table
                   + "\"', 'INSERT');") != 'f':
                raise RuntimeError('actual JDBC INSERT denial not effective')
            before_events = events()
            for _ in range(3):
                dispatch('ledger_recovery_failed')
                check_refusal(states(), events()[len(before_events):])
                if history() != prefix: raise RuntimeError('denied recovery changed durable prefix')
            request_id = 'jdbc-manual-' + marker
            fresh_inputs()
            request = {'requestId': request_id, 'requestedAt': datetime.now(timezone.utc).isoformat()}
            if rest('POST', '/items/' + LEDGER, json.dumps(request), content_type='text/plain')[0] not in (200, 202):
                raise RuntimeError('isolated native manual command refused')
            wait_for(lambda: json.loads(state('SouthOutlet_ManualResult')).get('requestId') == request_id)
            result = json.loads(state('SouthOutlet_ManualResult'))
            if result['status'] != 'denied' or result['reason'] != 'ledger_recovery_failed':
                raise RuntimeError('native manual request bypassed durability hold')
            check_refusal(states(), events()[len(before_events):])
            print('actual_jdbc_denial_repeated_auto_and_native_manual=passed', flush=True)

            # Persist a synthetic orphan ON state before restart: no command,
            # channel or device exists. Restore must not imply a live timer.
            seed({PUMPS[1]: 'ON'})
            wait_for(lambda: rest('GET', '/persistence/items/' + PUMPS[1] + '?serviceId=jdbc')[1]
                              .get('data', [{}])[-1].get('state') == 'ON')
            old_pids = provider.java_pids(container)
            if len(old_pids) != 1: raise RuntimeError('one isolated JVM required')
            try: runtime.run(client + ['system:shutdown -f'], b'\n')
            except RuntimeError: pass
            wait_for(lambda: old_pids[0] not in provider.java_pids(container), seconds=60)
            wait_for(lambda: provider._jvm_stopped(container), seconds=30)
            runtime.run(['docker', 'exec', container, 'touch', '/tmp/boot-permit'])
            wait_for(lambda: provider._startup_item(container, LEDGER), seconds=240)
            wait_for(lambda: provider._healthy_control(rest), seconds=120)
            restored = rest('GET', '/rules/' + UID)[1]
            if restored['actions'] != proposed['actions'] or restored['triggers'] != proposed['triggers']:
                raise RuntimeError('isolated restarted candidate source/trigger drift')
            wait_for(lambda: state(LEDGER) == accepted and state(PUMPS[1]) == 'ON', seconds=90)
            new_pids = provider.java_pids(container)
            if len(new_pids) != 1 or new_pids == old_pids: raise RuntimeError('isolated JVM not replaced')
            dispatch('ledger_recovery_failed')
            check_refusal(states(), events()[len(before_events):])
            if history() != prefix: raise RuntimeError('failed restart recovery changed JDBC prefix')
            print('full_jvm_accepted_restore_orphan_off_and_durable_hold=passed', flush=True)

            sql(fault_sql(table, deny=False))
            dispatch('ledger_recovered')
            check = states()
            if any(check[name] != 'OFF' for name in PUMPS): raise RuntimeError('recovery started a pump')
            sky.require_no_on_commands(events()[len(before_events):])
            wait_for(lambda: history()[-1]['state'] == state(LEDGER), seconds=30)
            if history()[:len(prefix)] != prefix: raise RuntimeError('original history prefix changed')
            positive_logs = events()
            dispatch('cycle_started')
            wait_for(lambda: sum(sky.on_command_seen(events()[len(positive_logs):], name)
                                          for name in PUMPS) == 1, seconds=15)
            if sum(state(name) == 'ON' for name in PUMPS) != 1:
                raise RuntimeError('positive recovery control must start exactly one synthetic pump')
            seed({'BMS_SOC_Evidence_JSON': 'NULL', 'SouthOutlet_AutoStatus': 'qualification_waiting'})
            rest('POST', '/rules/' + UID + '/runnow', {})
            wait_for(lambda: sky.refusal_matches(states(), 'invalid_soc_evidence'), seconds=20)
            print('durable_recovery_then_positive_cycle_and_safety_off=passed', flush=True)

            for payload, label in ((original, 'original-action-rollback'), (proposed, 'candidate-return')):
                if rest('PUT', '/rules/' + UID, payload)[0] not in (200, 201, 202):
                    raise RuntimeError('isolated action handoff refused')
                wait_for(lambda: provider._healthy_control(rest))
                if rest('GET', '/rules/' + UID)[1]['actions'] != payload['actions']:
                    raise RuntimeError('isolated action readback differs')
                seed({'SouthOutlet_AutoStatus': 'qualification_waiting'})
                rest('POST', '/rules/' + UID + '/runnow', {})
                wait_for(lambda: sky.refusal_matches(states(), 'invalid_soc_evidence'))
                if history()[:len(prefix)] != prefix: raise RuntimeError('rollback changed original history')
                print(label + '=verified', flush=True)
        finally:
            if container is not None:
                info = json.loads(runtime.run(['docker', 'inspect', container]))[0]
                if info['Config']['Labels'].get(LABEL) != marker:
                    raise RuntimeError('owned isolated OpenHAB cleanup marker mismatch')
                runtime.run(['docker', 'rm', '-f', '-v', container], timeout=90)
                print('owned_isolated_openhab_removed=true', flush=True)
    print(json.dumps({'status': 'passed', 'candidate_sha256': CANDIDATE_SHA,
                      'production_writes': 0, 'synthetic_outputs_unlinked': True,
                      'fixture_automatic_cron_omitted': True}), flush=True)


if __name__ == '__main__':
    main()
