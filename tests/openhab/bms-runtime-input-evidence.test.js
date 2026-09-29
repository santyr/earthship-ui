import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../../openhab/rules/bms-runtime-input-evidence.js', import.meta.url), 'utf8');
const resources = JSON.parse(readFileSync(new URL('../../openhab/bms-runtime-input-evidence-resources.json', import.meta.url), 'utf8'));
const item = readFileSync(new URL('../../openhab/file-config/items/bms-runtime-input-evidence.items', import.meta.url), 'utf8');
const jdbc = readFileSync(new URL('../../openhab/file-config/persistence/jdbc.persist', import.meta.url), 'utf8');
const OUTPUT = 'BMS_Runtime_Input_Evidence_JSON';
const SCHNEIDER_POLLER = 'modbus:poller:schneiderBatterySunSpec:battery802Core';
const SCHNEIDER_BRIDGE = 'modbus:tcp:schneiderBatterySunSpec';
const BMS_POLLER = 'modbus:poller:discoverBms190:bmsMain';
const BMS_BRIDGE = 'modbus:tcp:discoverBms190';
const specs = {
  current: { field: 'battery.dc_current_ca', item: 'DCData_Native_Current_Raw_cA',
    thing: 'modbus:data:schneiderBatterySunSpec:battery802Core:currentRawCentiA', value: '-309' },
  voltage: { field: 'battery.dc_voltage_cv', item: 'DCData_Native_Voltage_Raw_cV',
    thing: 'modbus:data:schneiderBatterySunSpec:battery802Core:voltageRawCentiV', value: '5297' },
  ttd: { field: 'battery.ttd_min', item: 'BMS_TimeToDischarge_Min',
    thing: 'modbus:data:discoverBms190:bmsMain:ttdMin', value: '5510' },
  ttf: { field: 'battery.ttf_min', item: 'BMS_TimeToFull_Min',
    thing: 'modbus:data:discoverBms190:bmsMain:ttfMin', value: '0' },
};

function harness() {
  const cache = new Map(), posts = [], queued = [];
  const online = new Map([SCHNEIDER_POLLER, SCHNEIDER_BRIDGE, BMS_POLLER, BMS_BRIDGE,
    ...Object.values(specs).map(spec => spec.thing)].map(uid => [uid, 'ONLINE']));
  const rawItem = { name: OUTPUT };
  const denied = () => { throw new Error('forbidden capability'); };
  let now = 1800000000000, epochs = 0, failAfterEnqueue = false;
  const stamp = micros => ({ micros,
    getNano: () => (micros % 1000000) * 1000,
    withNano: nanos => stamp(Math.floor(micros / 1000000) * 1000000 + nanos / 1000),
    isAfter: other => micros > other.micros,
    plusNanos: nanos => stamp(micros + nanos / 1000),
  });
  const run = event => vm.runInNewContext(source, {
    event, console: { warn: () => {} }, fetch: denied, setTimeout: denied,
    require: name => {
      expect(name).toBe('openhab');
      return {
        cache: { private: { get: key => cache.get(key), put: (key, value) => cache.set(key, value) } },
        things: { getThing: uid => online.has(uid) ? { status: online.get(uid) } : null },
        items: { getItem: name => {
          expect(name).toBe(OUTPUT);
          return { rawItem, get state() { return denied(); }, sendCommand: denied,
            postUpdate: body => posts.push(JSON.parse(body)) };
        } },
      };
    },
    Java: { type: name => {
      if (name === 'java.time.Instant') return { now: () => ({ toEpochMilli: () => now }) };
      if (name === 'java.util.UUID') return { randomUUID: () => ({ toString: () => `epoch-${++epochs}` }) };
      if (name === 'java.time.ZonedDateTime') return { now: () => stamp(now * 1000) };
      if (name === 'org.openhab.core.persistence.extensions.PersistenceExtensions') return {
        persist: (target, at, body, service) => {
          expect(target).toBe(rawItem); expect(service).toBe('jdbc');
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
  const event = (name, value, overrides) =>
    ({ raw: new Map([[`${name}.event`, raw(name, value, overrides)]]) });
  return { run, event, cache, posts, queued, online,
    advance: ms => { now += ms; }, failAfterEnqueue: value => { failAfterEnqueue = value; },
    get now() { return now; }, get latest() { return posts.at(-1); } };
}

function ready() {
  const h = harness(); h.run(); h.advance(1000);
  for (const name of Object.keys(specs)) h.run(h.event(name));
  return h;
}

describe('source-bound battery runtime input evidence', () => {
  it('requires original post-start events for four separate native fields', () => {
    const h = harness(); h.run(h.event('current'));
    expect(h.latest.fields[specs.current.field].status).toBe('unavailable');
    h.advance(1000);
    for (const name of Object.keys(specs)) h.run(h.event(name));
    for (const [name, spec] of Object.entries(specs)) {
      expect(h.latest.fields[spec.field]).toEqual({ status: 'valid', reason: 'ok',
        observedAt: h.now, validUntil: h.now + (name === 'current' || name === 'voltage' ? 90000 : 120000),
        value: Number(spec.value) });
    }
  });

  it.each(['getType', 'getTopic', 'getSource', 'getItemState'])('barriers spoofed %s immediately', key => {
    const h = ready(); h.advance(1000);
    h.run(h.event('current', specs.current.value, { [key]: () => 'spoofed' }));
    expect(h.latest.fields[specs.current.field].reason).toBe('invalid_input');
    expect(h.latest.fields[specs.voltage.field].status).toBe('valid');
  });

  it.each([['current', '-32768'], ['current', '-0'], ['voltage', '3999'],
    ['voltage', '06500'], ['ttd', '100001'], ['ttf', '1.0']])('rejects invalid %s value %s', (name, value) => {
    const h = ready(); h.advance(1000); h.run(h.event(name, value));
    expect(h.latest.fields[specs[name].field].reason).toBe('invalid_input');
  });

  it('coalesces high-rate normal values to 30 seconds but not fault/expiry barriers', () => {
    const h = ready(); const count = h.queued.length;
    for (let n = 1; n <= 20; n++) {
      h.advance(1000); h.run(h.event('current', String(-309 - n)));
    }
    expect(h.queued).toHaveLength(count);
    h.advance(10000); h.run();
    expect(h.queued).toHaveLength(count + 1);
    expect(h.latest.fields[specs.current.field].value).toBe(-329);
    h.online.set(specs.current.thing, 'OFFLINE'); h.run();
    expect(h.latest.fields[specs.current.field].reason).toBe('source_unavailable');
    h.online.set(specs.current.thing, 'ONLINE'); h.advance(1000); h.run();
    expect(h.latest.fields[specs.current.field].reason).toBe('input_unavailable');
    h.advance(1000); h.run(h.event('current'));
    expect(h.latest.fields[specs.current.field].status).toBe('valid');
    h.advance(121000); h.run();
    expect(h.latest.fields[specs.current.field].reason).toBe('input_stale');
  });

  it('does not treat Item-level updates as original acquisition or bridge recovery as a sample', () => {
    const h = ready(); h.advance(1000);
    h.run({ itemName: specs.ttd.item, itemState: '5400' });
    expect(h.latest.fields[specs.ttd.field].reason).toBe('invalid_input');
    h.online.set(BMS_BRIDGE, 'OFFLINE'); h.run();
    expect(h.latest.fields[specs.ttf.field].reason).toBe('source_unavailable');
    h.online.set(BMS_BRIDGE, 'ONLINE'); h.advance(1000); h.run();
    expect(h.latest.fields[specs.ttf.field].reason).toBe('input_unavailable');
  });

  it('rejects ambiguous and null original-event wrappers without accepting either value', () => {
    const h = ready(); h.advance(1000);
    const current = h.event('current');
    const voltage = h.event('voltage');
    h.run({ raw: new Map([...current.raw, ...voltage.raw]) });
    expect(h.latest.fields[specs.current.field].reason).toBe('invalid_input');
    expect(h.latest.fields[specs.voltage.field].reason).toBe('invalid_input');
    expect(h.latest.fields[specs.ttd.field].status).toBe('valid');
    h.advance(1000);
    h.run({ raw: new Map([['ttd.event', null]]) });
    expect(h.latest.fields[specs.ttd.field].reason).toBe('invalid_input');
  });

  it('does not keep writing unavailable-only state after the initial barrier', () => {
    const h = harness(); h.run();
    expect(h.queued).toHaveLength(1);
    h.advance(300000); h.run();
    expect(h.queued).toHaveLength(1);
  });

  it('consumes a sequence on ambiguous JDBC enqueue and restarts with a new epoch', () => {
    const h = ready(); const before = h.latest.sequence;
    h.advance(30000); h.failAfterEnqueue(true); h.run();
    h.failAfterEnqueue(false); h.advance(30000); h.run();
    expect(h.latest.sequence).toBe(before + 2);
    const epoch = h.latest.streamEpoch; h.cache.clear(); h.run();
    expect(h.latest.streamEpoch).not.toBe(epoch);
    expect(h.latest.fields[specs.current.field].status).toBe('unavailable');
  });

  it('is disabled, unlinked, and observational only', () => {
    expect(resources.rule.enabled).toBe(false);
    expect(resources.rule.triggers.filter(t => t.type === 'core.GenericEventTrigger')).toHaveLength(4);
    expect(resources.persistenceExclusion).toBe('!BMS_Runtime_Input_Evidence_JSON');
    expect(jdbc).toMatch(/\*,[^\n]*!BMS_Runtime_Input_Evidence_JSON\s*:\s*strategy\s*=\s*everyChange/);
    expect(jdbc).toMatch(/^[^\n]*BMS_Runtime_Input_Evidence_JSON\s*:\s*strategy\s*=\s*restoreOnStartup/m);
    expect(item).toContain('String BMS_Runtime_Input_Evidence_JSON');
    expect(item).not.toMatch(/channel=/);
    expect(source).not.toMatch(/sendCommand|sendHttp|executeCommandLine/);
  });
});
