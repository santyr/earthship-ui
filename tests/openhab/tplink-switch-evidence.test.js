import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../../openhab/rules/tplink-switch-evidence.js', import.meta.url), 'utf8');
const resources = JSON.parse(readFileSync(new URL('../../openhab/tplink-switch-evidence-resources.json', import.meta.url), 'utf8'));
const persistence = readFileSync(new URL('../../openhab/file-config/persistence/jdbc.persist', import.meta.url), 'utf8');
const outputDefinition = readFileSync(new URL('../../openhab/file-config/items/tplink-switch-evidence.items', import.meta.url), 'utf8');
const output = 'TPLink_Switch_Evidence_JSON';
const specs = {
  dishwasher: { field: 'load.dishwasher_state', item: 'Dishwasher_Switch_Observation_JSON',
    thing: 'tplinksmarthome:hs103:a34b4957dc', channel: 'tplinksmarthome:hs103:a34b4957dc:switch' },
  cistern: { field: 'load.shurflo_pump_state', item: 'Cistern_Pump_Switch_Observation_JSON',
    thing: 'tplinksmarthome:hs103:08482dd378', channel: 'tplinksmarthome:hs103:08482dd378:switch' },
};

function harness() {
  const cache = new Map();
  const posts = [];
  const queued = [];
  const status = new Map(Object.values(specs).map(spec => [spec.thing, 'ONLINE']));
  const rawItem = { name: output };
  let now = 1800000000000, epoch = 0, persistFailure = null;
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
      expect(name).toBe('openhab');
      return {
        cache: { private: { get: key => cache.get(key), put: (key, value) => cache.set(key, value) } },
        things: { getThing: uid => status.has(uid) ? { status: status.get(uid) } : null },
        items: { getItem: name => {
          expect(name).toBe(output);
          return { rawItem, get state() { return denied(); }, sendCommand: denied,
            postUpdate: body => posts.push(JSON.parse(body)) };
        } },
      };
    },
    Java: { type: name => {
      if (name === 'java.time.Instant') return { now: () => ({ toEpochMilli: () => now }) };
      if (name === 'java.util.UUID') return { randomUUID: () => ({ toString: () => `epoch-${++epoch}` }) };
      if (name === 'java.time.ZonedDateTime') return { now: () => stamp(now * 1000) };
      if (name === 'org.openhab.core.persistence.extensions.PersistenceExtensions') return {
        persist: (target, at, body, service) => {
          expect(target).toBe(rawItem); expect(service).toBe('jdbc');
          if (persistFailure === 'before') throw new Error('before enqueue');
          queued.push({ at, body });
          if (persistFailure === 'after') throw new Error('ambiguous enqueue');
        },
      };
      return denied();
    } },
  }, { timeout: 1000 });
  const receipt = (name, value = 'OFF', overrides = {}) => {
    const spec = specs[name];
    const body = JSON.stringify({ version: 1, observedAt: now, value });
    return { getItemName: () => spec.item, getType: () => 'ItemStateEvent',
      getTopic: () => `openhab/items/${spec.item}/state`,
      getSource: () => `org.openhab.core.thing$${spec.channel}`,
      getItemState: () => body, ...overrides };
  };
  const event = (name, value = 'OFF', overrides = {}) =>
    ({ raw: new Map([[`${name}.event`, receipt(name, value, overrides)]]) });
  return { run, receipt, event, posts, queued, cache, status,
    advance: (ms = 30000) => { now += ms; },
    persistenceFail: value => { persistFailure = value; },
    get now() { return now; }, get latest() { return posts.at(-1); } };
}

function ready() {
  const h = harness(); h.run(); h.advance(); h.run(h.event('dishwasher'));
  h.run(h.event('cistern', 'ON')); return h;
}

describe('TP-Link switch evidence producer', () => {
  it('requires post-start original events from the two exact switch channels', () => {
    const h = harness(); h.run(h.event('dishwasher'));
    expect(h.latest.fields[specs.dishwasher.field].status).toBe('unavailable');
    h.advance(); h.run(h.event('dishwasher'));
    expect(h.latest.fields[specs.dishwasher.field]).toEqual({ status: 'valid', reason: 'ok',
      observedAt: h.now, validUntil: h.now + 90000, value: 'OFF' });
    expect(h.latest.fields[specs.cistern.field].status).toBe('unavailable');
    h.run(h.event('cistern', 'ON'));
    expect(h.latest.fields[specs.cistern.field].value).toBe('ON');
  });

  it.each(['getSource', 'getType', 'getTopic', 'getItemState'])('rejects an invalid %s', key => {
    const h = ready(); h.advance();
    h.run(h.event('dishwasher', 'OFF', { [key]: () => 'spoofed' }));
    expect(h.latest.fields[specs.dishwasher.field].reason).toBe('invalid_input');
    expect(h.latest.fields[specs.cistern.field].status).toBe('valid');
  });

  it.each(['UNDEF', 'NULL', 'ON ', '0', 'unexpected'])('rejects non-switch source text %s', value => {
    const h = ready(); h.advance(); h.run(h.event('cistern', value));
    expect(h.latest.fields[specs.cistern.field].reason).toBe('invalid_input');
  });

  it('does not accept an Item-level optimistic prediction as a source event', () => {
    const h = ready(); h.advance();
    h.run({ itemName: specs.dishwasher.item, itemState: 'ON' });
    expect(h.latest.fields[specs.dishwasher.field].reason).toBe('invalid_input');
  });

  it('renews unchanged reports, expires stale evidence, and does not infer another plug', () => {
    const h = ready(); const first = h.latest;
    h.advance(60000); h.run(h.event('dishwasher'));
    expect(h.latest.fields[specs.dishwasher.field].validUntil)
      .toBe(first.fields[specs.dishwasher.field].validUntil + 60000);
    expect(h.latest.fields[specs.cistern.field].status).toBe('valid');
    h.advance(30000); h.run();
    expect(h.latest.fields[specs.cistern.field].reason).toBe('input_stale');
    expect(h.latest.fields[specs.dishwasher.field].status).toBe('valid');
  });

  it('closes one field on Thing loss and requires a post-recovery event', () => {
    const h = ready(); h.status.set(specs.cistern.thing, 'OFFLINE'); h.run();
    expect(h.latest.fields[specs.cistern.field].reason).toBe('source_unavailable');
    expect(h.latest.fields[specs.dishwasher.field].status).toBe('valid');
    h.status.set(specs.cistern.thing, 'ONLINE'); h.advance(); h.run();
    expect(h.latest.fields[specs.cistern.field].reason).toBe('input_unavailable');
    h.advance(); h.run(h.event('cistern', 'ON'));
    expect(h.latest.fields[specs.cistern.field].status).toBe('valid');
  });

  it('starts a new unavailable epoch after cache restart', () => {
    const h = ready(); const epoch = h.latest.streamEpoch;
    h.cache.clear(); h.run();
    expect(h.latest.streamEpoch).not.toBe(epoch);
    expect(h.latest.fields[specs.dishwasher.field].status).toBe('unavailable');
    expect(h.latest.fields[specs.cistern.field].status).toBe('unavailable');
  });

  it('consumes sequence identity on ambiguous JDBC enqueue', () => {
    const h = ready(); h.advance(); h.persistenceFail('after');
    h.run(h.event('dishwasher', 'ON')); h.persistenceFail(null); h.run();
    expect(h.latest.sequence).toBe(5);
    expect(h.queued.map(row => JSON.parse(row.body).sequence)).toEqual([1, 2, 3, 4, 5]);
  });

  it('is disabled by default and excludes explicit evidence from wildcard persistence', () => {
    expect(resources.rule.enabled).toBe(false);
    expect(resources.rule.triggers.map(trigger => trigger.type)).toEqual([
      'core.GenericEventTrigger', 'core.GenericEventTrigger',
      'core.ThingStatusChangeTrigger', 'core.ThingStatusChangeTrigger',
      'timer.GenericCronTrigger', 'core.SystemStartlevelTrigger',
    ]);
    expect(resources.persistenceExclusion).toBe('!TPLink_Switch_Evidence_JSON');
    expect(persistence).toContain('!TPLink_Switch_Evidence_JSON');
    expect(persistence).toMatch(/MPPT60_PV_Day_Evidence_JSON,\s*TPLink_Switch_Evidence_JSON(?:,\s*\w+)*\s*:\s*strategy = restoreOnStartup/);
    expect(outputDefinition).toContain('String TPLink_Switch_Evidence_JSON');
    expect(source).not.toMatch(/sendCommand|sendHttp|executeCommandLine/);
  });
});
