import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../../openhab/rules/inverter-ac-evidence.js', import.meta.url), 'utf8');
const resources = JSON.parse(readFileSync(new URL('../../openhab/inverter-ac-evidence-resources.json', import.meta.url), 'utf8'));
const item = 'Inverter_AC_Output_Observation_JSON';
const output = 'Inverter_AC_Evidence_JSON';
const field = 'inverter.ac_output_w';
const inverter = 'modbus:inverter-split-phase:1ed74db72c:e853aec444';
const bridge = 'modbus:tcp:1ed74db72c';
const channel = `${inverter}:acGeneral#ac-power`;

function harness() {
  const cache = new Map();
  const posts = [];
  const queued = [];
  const status = new Map([[inverter, 'ONLINE'], [bridge, 'ONLINE']]);
  const rawItem = { name: output };
  let now = 1800000000000, epoch = 0, persistenceFailure = null, postFailure = false;
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
            postUpdate: body => { if (postFailure) throw new Error('post failed'); posts.push(JSON.parse(body)); } };
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
          if (persistenceFailure === 'before') throw new Error('before enqueue');
          queued.push({ at, body });
          if (persistenceFailure === 'after') throw new Error('ambiguous enqueue');
        },
      };
      return denied();
    } },
  }, { timeout: 1000 });
  const receipt = (value = '100 W', overrides = {}) => {
    const body = JSON.stringify({ version: 1, field, observedAt: now, value });
    return { getItemName: () => item, getType: () => 'ItemStateEvent',
      getTopic: () => `openhab/items/${item}/state`,
      getSource: () => `org.openhab.core.thing$${channel}`,
      getItemState: () => body, ...overrides };
  };
  return { run, receipt, posts, queued, cache, status,
    advance: (ms = 5000) => { now += ms; },
    get now() { return now; }, get latest() { return posts.at(-1); },
    persistenceFail: value => { persistenceFailure = value; },
    postFail: value => { postFailure = value; } };
}

function ready() {
  const h = harness(); h.run(); h.advance(); h.run(h.receipt()); return h;
}

describe('independent inverter AC evidence producer', () => {
  it('requires a post-start original binding event and labels inverter output only', () => {
    const h = harness(); h.run(h.receipt());
    expect(h.latest.fields[field].status).toBe('unavailable');
    h.advance(); h.run(h.receipt());
    expect(h.latest.basis).toBe('inverter_output');
    expect(h.latest.fields[field]).toEqual({ status: 'valid', reason: 'ok',
      observedAt: h.now, validUntil: h.now + 30000, watts: 100 });
  });

  it('accepts only the original generic-trigger event', () => {
    const h = harness(); h.run(); h.advance();
    h.run({ raw: new Map([['ac.event', h.receipt()]]) });
    expect(h.latest.fields[field].status).toBe('valid');
    h.advance(); h.run({ itemName: item, itemState: '200 W' });
    expect(h.latest.fields[field].reason).toBe('invalid_input');
    h.advance(); h.run({ raw: new Map([['ac.event', h.receipt()], ['event', h.receipt()]]) });
    expect(h.latest.fields[field].reason).toBe('invalid_input');
  });

  it.each([0, 20000])('accepts bounded integer Watt value %s', watts => {
    const h = ready(); h.advance(); h.run(h.receipt(`${watts} W`));
    expect(h.latest.fields[field].watts).toBe(watts);
  });

  it.each(['NULL', 'UNDEF', '100', '100.5 W', '-1 W', '020 W', '20001 W', 'NaN W'])
    ('invalid raw input %s creates a barrier', value => {
      const h = ready(); h.advance(); h.run(h.receipt(value));
      expect(h.latest.fields[field].reason).toBe('invalid_input');
      h.advance(); h.run(h.receipt());
      expect(h.latest.fields[field].status).toBe('valid');
    });

  it.each(['getSource', 'getType', 'getTopic', 'getItemName'])
    ('rejects spoofed %s', key => {
      const h = ready(); h.advance(); h.run(h.receipt('100 W', { [key]: () => 'wrong' }));
      expect(h.latest.fields[field].reason).toBe('invalid_input');
    });

  it('rejects malformed, duplicate-key, future and expired envelopes', () => {
    for (const make of [
      () => 'x', () => '{}',
      h => `{"version":1,"version":1,"field":"${field}","observedAt":${h.now},"value":"100 W"}`,
      h => JSON.stringify({ version:1, field, observedAt:h.now+1, value:'100 W' }),
      h => JSON.stringify({ version:1, field, observedAt:h.now, value:'100 W', extra:1 }),
    ]) {
      const h = ready(); h.advance(); h.run(h.receipt('100 W', { getItemState: () => make(h) }));
      expect(h.latest.fields[field].reason).toBe('invalid_input');
    }
    const h = ready(); h.advance(); const old = h.receipt(); h.advance(30000); h.run(old);
    expect(h.latest.fields[field].reason).toBe('invalid_input');
  });

  it('renews unchanged values with distinct expiry and expires at TTL', () => {
    const h = ready(); const first = h.latest;
    h.advance(); h.run(h.receipt());
    expect(h.latest.fields[field].watts).toBe(first.fields[field].watts);
    expect(h.latest.fields[field].validUntil).toBe(first.fields[field].validUntil + 5000);
    h.advance(29999); h.run(); expect(h.latest.fields[field].status).toBe('valid');
    h.advance(1); h.run(); expect(h.latest.fields[field].reason).toBe('input_stale');
  });

  it('closes on inverter or bridge loss and requires a post-recovery receipt', () => {
    for (const uid of [inverter, bridge]) {
      const h = ready(); h.status.set(uid, 'OFFLINE'); h.run();
      expect(h.latest.fields[field].reason).toBe('source_unavailable');
      h.status.set(uid, 'ONLINE'); h.advance(); h.run();
      expect(h.latest.fields[field].reason).toBe('input_unavailable');
      h.advance(); h.run(h.receipt());
      expect(h.latest.fields[field].status).toBe('valid');
    }
  });

  it('resets stream epoch and source validity after cache restart or clock rollback', () => {
    for (const reset of [h => h.cache.clear(), h => h.advance(-10000)]) {
      const h = ready(); const epoch = h.latest.streamEpoch; reset(h); h.run();
      expect(h.latest.streamEpoch).not.toBe(epoch);
      expect(h.latest.fields[field].status).toBe('unavailable');
    }
  });

  it('persists immutable snapshots with monotonic same-millisecond timestamps', () => {
    const h = ready(); h.run(h.receipt('200 W'));
    expect(h.queued.map(x => JSON.parse(x.body).fields[field].watts)).toEqual([null, 100, null]);
    expect(h.queued[2].at.micros-h.queued[1].at.micros).toBe(1000);
  });

  it.each(['before', 'after'])('consumes sequence after %s enqueue failure', failure => {
    const h = harness(); h.run(); h.advance(); h.persistenceFail(failure);
    h.run(h.receipt()); h.persistenceFail(null); h.run();
    expect(h.latest.sequence).toBe(3);
    expect(h.queued.map(x => JSON.parse(x.body).sequence))
      .toEqual(failure === 'before' ? [1,3] : [1,2,3]);
  });

  it('retries a failed Item publication without fabricating another persisted row', () => {
    const h = ready(); h.advance(); h.postFail(true); h.run(h.receipt('200 W'));
    const count = h.queued.length; h.postFail(false); h.run();
    expect(h.queued).toHaveLength(count);
    expect(h.latest.fields[field].watts).toBe(200);
  });

  it('never posts a superseded valid snapshot after an offline barrier enqueue fails', () => {
    const h = ready(); h.advance(); h.postFail(true); h.run(h.receipt('200 W'));
    h.status.set(inverter, 'OFFLINE'); h.persistenceFail('before');
    h.postFail(false); h.run();
    expect(h.latest.fields[field].watts).toBe(100);
    h.persistenceFail(null); h.advance(); h.run();
    expect(h.latest.fields[field].reason).toBe('source_unavailable');
    expect(h.posts.some(x => x.fields[field].watts === 200)).toBe(false);
  });

  it('starts disabled, observational and separate from the three-field stream', () => {
    expect(resources.createOnly).toBe(true);
    expect(resources.itemSource).toBe('openhab/file-config/items/inverter-ac-evidence.items');
    expect(resources.persistenceExclusion).toBe('!Inverter_AC_Evidence_JSON');
    expect(readFileSync(new URL('../../openhab/file-config/items/inverter-ac-evidence.items', import.meta.url), 'utf8'))
      .toContain(`String ${output}`);
    expect(resources.rule.enabled).toBe(false);
    expect(resources.rule.source).toBe('openhab/rules/inverter-ac-evidence.js');
    expect(resources.rule.triggers.map(x => x.type)).toEqual([
      'core.GenericEventTrigger', 'core.ThingStatusChangeTrigger',
      'core.ThingStatusChangeTrigger', 'timer.GenericCronTrigger',
      'core.SystemStartlevelTrigger',
    ]);
    expect(readFileSync(new URL('../../openhab/managed-resources.json', import.meta.url), 'utf8'))
      .not.toContain('hex_inverter_ac_evidence');
  });
});
