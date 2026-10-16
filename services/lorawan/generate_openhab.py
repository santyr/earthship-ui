"""Generate staged, inbound-only file config into a private destination."""
import argparse
import json
from pathlib import Path
from services.observations.registry import Registry


def quote(value):
    return json.dumps(str(value),ensure_ascii=True)


def generate(registry,mqtt):
    if set(mqtt)!={'host','port','username','password'} or type(mqtt['port']) is not int or not 1<=mqtt['port']<=65535:
        raise ValueError('private MQTT credential configuration required')
    broker='mqtt:broker:earthship_sensors'
    things=[f'Bridge {broker} "Sensor observation broker" [ host={quote(mqtt["host"])}, port={mqtt["port"]}, secure=false, username={quote(mqtt["username"])}, password={quote(mqtt["password"])} ]',
        f'Thing mqtt:topic:earthship_sensors:view "Earthship observations" ({broker}) {{',
        ' Channels:',
        ' Type string : view [ stateTopic="earthship/sensors/v1/view" ]',
        ' Type string : service [ stateTopic="earthship/sensors/v1/service" ]','}']
    items=['// Staged observational Items. No commands, no automatic restoreOnStartup.',
        'Group gEarthship_Sensors "Distributed sensors"',
        'String Earthship_Sensor_View_JSON "Sensor evidence" (gEarthship_Sensors) { channel="mqtt:topic:earthship_sensors:view:view" }',
        'String Earthship_Sensor_Service "Sensor service" (gEarthship_Sensors) { channel="mqtt:topic:earthship_sensors:view:service" }']
    channels=[('Contact','contact','contact_state'),('Valid','switch','valid'),('Health','string','health'),
        ('Quality','string','quality'),('LastObserved','datetime','last_observed_at'),('LastReceived','datetime','last_received_at'),
        ('LastTransition','datetime','last_transition_at'),('Battery','string','battery_condition'),
        ('BatteryPercent','number','battery_percent'),('BatteryVolts','number','battery_volts'),
        ('RSSI','number','rssi'),('SNR','number','snr'),('Available','switch','available'),('Tamper','string','tamper')]
    for device in registry.devices.values():
        if device['transport']!='lorawan' or not device['enabled'] or 'contact_state' not in device['capabilities']:continue
        sid=device['sensor_id'];uid=f'mqtt:topic:earthship_sensors:{sid}'
        things.extend([f'Thing {uid} {quote(device["name"])} ({broker}) {{',' Channels:'])
        for suffix,channel_type,key in channels:
            transformation='JSONPATH:$.'+key
            if channel_type=='contact':transformation+='∩REGEX:(OPEN|CLOSED)'
            elif channel_type=='number':transformation+='∩REGEX:(-?[0-9]+(?:[.][0-9]+)?)'
            elif channel_type=='datetime':transformation+='∩REGEX:([0-9]{4}-.*)'
            mapping=', on="true", off="false"' if channel_type=='switch' else ''
            things.append(f' Type {channel_type} : {key} [ stateTopic="earthship/sensors/v1/{sid}/state", transformationPattern={quote(transformation)}{mapping} ]')
            item_type={'contact':'Contact','switch':'Switch','string':'String','datetime':'DateTime','number':'Number'}[channel_type]
            items.append(f'{item_type} Sensor_{sid}_{suffix} {quote(device["name"]+" "+suffix)} (gEarthship_Sensors) {{ channel="{uid}:{key}" }}')
        things.append('}')
    policies={d['sensor_id']:{k:d[k] for k in ('state_stale_seconds','communication_stale_seconds','offline_seconds')}
        for d in registry.devices.values() if d['transport']=='lorawan' and d['enabled']}
    rule='''// Only derived validity/health are updated. Last-known contact is never changed.
const { rules, triggers, items } = require('openhab');
const policies = POLICY;
rules.JSRule({ name: 'Earthship sensor supervision', id: 'earthship_sensor_supervision',
  triggers: [triggers.GenericCronTrigger('0/30 * * * * ?'), triggers.SystemStartlevelTrigger(100)],
  execute: () => {
    const now = Date.now();
    let view = null;
    try { view = JSON.parse(items.getItem('Earthship_Sensor_View_JSON').state); } catch (_) {}
    const sourceLive = view && view.schema === 'earthship-sensor-view/v1' &&
      Number.isFinite(Date.parse(view.expires_at)) && Date.parse(view.generated_at) <= now &&
      now < Date.parse(view.expires_at) && items.getItem('Earthship_Sensor_Service').state === 'online';
    for (const [id, policy] of Object.entries(policies)) {
      const prefix = 'Sensor_' + id + '_';
      const received = Date.parse(items.getItem(prefix + 'LastReceived').state);
      const observed = Date.parse(items.getItem(prefix + 'LastObserved').state);
      const age = (now - received) / 1000;
      const health = !Number.isFinite(age) || age < 0 ? 'UNKNOWN' :
        age >= policy.offline_seconds ? 'OFFLINE' : !sourceLive || age >= policy.communication_stale_seconds ? 'STALE' : 'ONLINE';
      const valid = sourceLive && health === 'ONLINE' && Number.isFinite(observed) && observed <= now &&
        now - observed < policy.state_stale_seconds * 1000 &&
        ['qualified', 'synthetic', 'documented_unverified'].includes(items.getItem(prefix + 'Quality').state);
      items.getItem(prefix + 'Valid').postUpdate(valid ? 'ON' : 'OFF');
      items.getItem(prefix + 'Health').postUpdate(health);
      items.getItem(prefix + 'Available').postUpdate(sourceLive && health === 'ONLINE' ? 'ON' : 'OFF');
    }
  }
});
'''.replace('POLICY',json.dumps(policies,separators=(',',':')))
    return {'things/earthship-sensors.things':'\n'.join(things)+'\n',
        'items/earthship-sensors.items':'\n'.join(items)+'\n',
        'automation/js/earthship-sensor-supervision.js':rule}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--registry',required=True);parser.add_argument('--mqtt',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();secret=Path(args.mqtt)
    if secret.stat().st_mode&0o077:raise ValueError('MQTT credentials must have mode 0600')
    files=generate(Registry.read(args.registry),json.loads(secret.read_text()))
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True,mode=0o700)
    for name,body in files.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body);path.chmod(0o600)
    print('Staged inbound-only OpenHAB files; no live deployment performed.')


if __name__=='__main__':main()
