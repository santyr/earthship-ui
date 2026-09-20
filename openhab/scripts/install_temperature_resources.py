"""Create-only receipt collection resources; no sensor state or command writes.

Run explicitly with --apply. A temporary triggerless rule uses provider.add,
not REST Item/link upserts. An ambiguous result is never automatically retried.
"""
import json
from pathlib import Path
import sys
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import openhab_sanity_check as oh

MANIFEST = Path(__file__).resolve().parents[1] / 'weather-temperature-evidence-resources.json'
HTTP_DEFAULTS = {'authMode': 'BASIC', 'ignoreSSLErrors': False, 'delay': 0, 'commandMethod': 'GET'}


def request(method, path, payload=None, text=False):
    data = payload.encode() if text else (None if payload is None else json.dumps(payload).encode())
    req = Request(oh.BASE + path, data=data, method=method, headers={
        'Authorization': 'Bearer ' + oh.token(),
        'Content-Type': 'text/plain' if text else 'application/json'})
    with urlopen(req, timeout=20) as response:
        return response.status


def absent(path):
    try:
        oh.get(path)
    except HTTPError as exc:
        if exc.code == 404:
            return True
        raise
    return False


def action(marker):
    return '''
const FrameworkUtil = Java.type('org.osgi.framework.FrameworkUtil');
const Registry = Java.type('org.openhab.core.items.ItemRegistry');
const StringItem = Java.type('org.openhab.core.library.items.StringItem');
const ThingUID = Java.type('org.openhab.core.thing.ThingUID');
const ChannelUID = Java.type('org.openhab.core.thing.ChannelUID');
const Link = Java.type('org.openhab.core.thing.link.ItemChannelLink');
const Configuration = Java.type('org.openhab.core.config.core.Configuration');
const context = FrameworkUtil.getBundle(Registry.class).getBundleContext();
const refs = [];
function service(name) {
  const ref = context.getServiceReference(name);
  if (ref === null) throw new Error('Missing install service');
  refs.push(ref);
  const value = context.getService(ref);
  if (value === null) throw new Error('Unavailable install service');
  return value;
}
try {
  const ir = service('org.openhab.core.items.ItemRegistry');
  const ip = service('org.openhab.core.items.ManagedItemProvider');
  const tr = service('org.openhab.core.thing.ThingRegistry');
  const lr = service('org.openhab.core.thing.link.ItemChannelLinkRegistry');
  const lp = service('org.openhab.core.thing.link.ManagedItemChannelLinkProvider');
  const name = 'Weather_Temperature_Evidence_JSON';
  const uid = 'http:url:weatherTemperatureEvidence';
  const thing = tr.get(new ThingUID(uid));
  if (thing === null || String(thing.getStatusInfo().getStatusDetail()) !== 'DISABLED')
    throw new Error('New source must be disabled before linking');
  if (ir.get(name) !== null || ip.get(name) !== null)
    throw new Error('Item collision; refusing upsert');
  const config = new Configuration();
  config.put('profile', 'system:default');
  const link = new Link(name, new ChannelUID(uid + ':snapshot'), config);
  if (lr.get(link.getUID()) !== null || lp.get(link.getUID()) !== null)
    throw new Error('Link collision; refusing upsert');
  const item = new StringItem(name);
  item.setLabel('Weather temperature receipt evidence');
  item.setCategory('');
  ip.add(item);
  lp.add(link);
  console.info(MARKER + ' PASS created=2');
} finally {
  for (const ref of refs) context.ungetService(ref);
}
'''.replace('MARKER', json.dumps(marker))


def same_rule(actual, expected):
    return {k: v for k, v in actual.items() if k not in {
        'status', 'editable', 'configDescriptions', 'templateState'}} == expected


def main():
    manifest = json.loads(MANIFEST.read_text())
    thing = manifest['things'][0]
    uid = thing['UID']
    name = manifest['items'][0]['name']
    link = manifest['links'][0]
    resume = sys.argv[1:] == ['--resume-disabled-thing']
    if (not resume and not absent('/things/' + uid)) or not absent('/items/' + name):
        raise RuntimeError('Resource exists; inspect rather than replay installer')
    if any(x['itemName'] == name or x['channelUID'] == link['channelUID'] for x in oh.get('/links')):
        raise RuntimeError('Existing link collision')
    if sys.argv[1:] != ['--apply'] and not resume:
        print('preflight=PASS mode=dry-run')
        return
    if not resume:
        if request('POST', '/things', thing) != 201:
            raise RuntimeError('Thing creation unverified')
        request('PUT', '/things/' + uid + '/enable', 'false', text=True)
    current = oh.get('/things/' + uid)
    if current.get('statusInfo', {}).get('statusDetail') != 'DISABLED':
        raise RuntimeError('Source not disabled; refusing linking')
    if (current['configuration'] != {**HTTP_DEFAULTS, **thing['configuration']}
            or current['thingTypeUID'] != thing['thingTypeUID'] or current['label'] != thing['label']):
        raise RuntimeError('Thing configuration mismatch')
    channels = current['channels']
    if set(c['id'] for c in channels) != {'snapshot', 'last-success', 'last-failure'}:
        raise RuntimeError('Unexpected source channels')
    if any(c.get('linkedItems') for c in channels):
        raise RuntimeError('Source must be unlinked')
    channel = next(c for c in channels if c['id'] == 'snapshot')
    if any(channel.get(k) != v for k, v in thing['channels'][0].items()):
        raise RuntimeError('Source channel mismatch')
    marker = 'hex_temperature_install_' + uuid.uuid4().hex
    rule = {'uid': marker, 'name': 'Temporary temperature receipt resource installation',
            'description': 'Add-only metadata; no Item state writes or hardware commands.',
            'triggers': [], 'conditions': [], 'configuration': {}, 'tags': [], 'visibility': 'VISIBLE',
            'actions': [{'id': 'install', 'type': 'script.ScriptAction', 'inputs': {},
                         'configuration': {'type': 'application/javascript', 'script': action(marker)}}]}
    if not absent('/rules/' + marker):
        raise RuntimeError('Installer collision')
    log = Path('/var/log/openhab/openhab.log')
    stat = log.stat()
    try:
        if request('POST', '/rules', rule) != 201:
            raise RuntimeError('Installer creation unverified')
        if not same_rule(oh.get('/rules/' + marker), rule):
            raise RuntimeError('Installer readback mismatch')
        for _ in range(20):
            if oh.get('/rules/' + marker).get('status', {}).get('status') == 'IDLE':
                break
            time.sleep(.5)
        else:
            raise RuntimeError('Installer not ready')
        if request('POST', '/rules/' + marker + '/runnow', {}) != 200:
            raise RuntimeError('Installer request not accepted')
        for _ in range(20):
            if log.stat().st_ino != stat.st_ino:
                raise RuntimeError('Log rotated; inspect without retrying')
            with log.open() as handle:
                handle.seek(stat.st_size)
                receipt = marker + ' PASS created=2' in handle.read(262144)
            if receipt:
                break
            time.sleep(.5)
        else:
            raise RuntimeError('Installer receipt missing; no automatic retry')
    finally:
        if not absent('/rules/' + marker):
            if not same_rule(oh.get('/rules/' + marker), rule):
                raise RuntimeError('Installer changed; cleanup refused')
            request('DELETE', '/rules/' + marker)
            if not absent('/rules/' + marker):
                raise RuntimeError('Installer cleanup unverified')
    item = oh.get('/items/' + name)
    if any(item.get(k) != v for k, v in manifest['items'][0].items()):
        raise RuntimeError('Item definition mismatch; source remains disabled')
    installed = [x for x in oh.get('/links') if x['itemName'] == name]
    if len(installed) != 1 or any(installed[0].get(k) != v for k, v in link.items()):
        raise RuntimeError('Link mismatch; source remains disabled')
    channel = next(c for c in oh.get('/things/' + uid)['channels'] if c['uid'] == link['channelUID'])
    if any(channel.get(k) != v for k, v in thing['channels'][0].items()):
        raise RuntimeError('Channel mismatch; source remains disabled')
    request('PUT', '/things/' + uid + '/enable', 'true', text=True)
    print('installation=PASS definitions_verified=true source_enabled=true temporary_rule_removed=true')


if __name__ == '__main__':
    main()
