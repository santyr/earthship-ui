// Isolated execution of the actual producer. No OpenHAB or network access.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../../../openhab/rules/bms-aux-evidence.js', import.meta.url), 'utf8');
const OUTPUT = 'BMS_Aux_Evidence_JSON';
export const POLLER = 'modbus:poller:discoverBms190:bmsMain';
export const BRIDGE = 'modbus:tcp:discoverBms190';
export const specs = {
  capacity: { field: 'battery.remaining_ah', item: 'BMS_Capacity_Remaining_Ah',
    thing: 'modbus:data:discoverBms190:bmsMain:capRemainAh', value: '320' },
  temperature: { field: 'battery.temperature_raw', item: 'BMS_Temperature_Raw',
    thing: 'modbus:data:discoverBms190:bmsMain:tempRaw', value: '29300' },
};

export function harness(start = 1800000000000) {
  const cache = new Map(), posts = [], queued = [];
  const online = new Map([BRIDGE, POLLER, ...Object.values(specs).map(spec => spec.thing)]
    .map(uid => [uid, 'ONLINE']));
  const rawItem = { name: OUTPUT };
  let now = start, epochs = 0, failAfterEnqueue = false;
  const denied = () => { throw new Error('forbidden capability'); };
  const stamp = micros => ({ micros,
    getNano: () => (micros % 1000000) * 1000,
    withNano: nanos => stamp(Math.floor(micros / 1000000) * 1000000 + nanos / 1000),
    isAfter: other => micros > other.micros,
    plusNanos: nanos => stamp(micros + nanos / 1000),
  });
  const run = event => vm.runInNewContext(source, {
    event, console: { warn: () => {} }, fetch: denied, setTimeout: denied,
    require: name => {
      assert.equal(name, 'openhab');
      return {
        cache: { private: { get: key => cache.get(key), put: (key, value) => cache.set(key, value) } },
        things: { getThing: uid => online.has(uid) ? { status: online.get(uid) } : null },
        items: { getItem: name => {
          assert.equal(name, OUTPUT);
          return { rawItem, get state() { return denied(); }, sendCommand: denied,
            postUpdate: body => posts.push(JSON.parse(body)) };
        } },
      };
    },
    Java: { type: name => {
      if (name === 'java.time.Instant') return { now: () => ({ toEpochMilli: () => now }) };
      if (name === 'java.util.UUID') return { randomUUID: () => ({ toString: () =>
        `00000000-0000-0000-0000-${String(++epochs).padStart(12, '0')}` }) };
      if (name === 'java.time.ZonedDateTime') return { now: () => stamp(now * 1000) };
      if (name === 'org.openhab.core.persistence.extensions.PersistenceExtensions') return {
        persist: (target, at, body, service) => {
          assert.equal(target, rawItem); assert.equal(service, 'jdbc');
          queued.push({ at, body });
          if (failAfterEnqueue) throw new Error('ambiguous enqueue');
        },
      };
      return denied();
    } },
  }, { timeout: 1000 });
  const raw = (name, value = specs[name].value, overrides = {}) => {
    const spec = specs[name];
    return { getItemName: () => spec.item, getType: () => 'ItemStateEvent',
      getTopic: () => `openhab/items/${spec.item}/state`,
      getSource: () => `org.openhab.core.thing$${spec.thing}:number`,
      getItemState: () => value, ...overrides };
  };
  return { run, event: (name, value, overrides) =>
    ({ raw: new Map([[`${name}.event`, raw(name, value, overrides)]]) }),
    posts, queued, cache, online,
    advance: (ms = 30000) => { now += ms; },
    failAfterEnqueue: value => { failAfterEnqueue = value; },
    get now() { return now; }, get latest() { return posts.at(-1); } };
}
