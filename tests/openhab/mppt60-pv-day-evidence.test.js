import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../../openhab/rules/mppt60-pv-day-evidence.js', import.meta.url), 'utf8');
const resources = JSON.parse(readFileSync(new URL('../../openhab/mppt60-pv-day-evidence-resources.json', import.meta.url), 'utf8'));
const persistence = readFileSync(new URL('../../openhab/file-config/persistence/jdbc.persist', import.meta.url), 'utf8');
const item = 'MPPT60_PV_Day_Observation_JSON';
const output = 'MPPT60_PV_Day_Evidence_JSON';
const field = 'mppt60.pv_day_wh';
const dataThing = 'modbus:data:9eb978a141:mppt60Energy:energyFromPVTodayWh';
const poller = 'modbus:poller:9eb978a141:mppt60Energy';
const bridge = 'modbus:tcp:9eb978a141';
const channel = `${dataThing}:number`;

function harness() {
  const cache = new Map();
  const posts = [];
  const queued = [];
  const status = new Map([[dataThing, 'ONLINE'], [poller, 'ONLINE'], [bridge, 'ONLINE']]);
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
  const receipt = (value = '8298', overrides = {}) => {
    const body = JSON.stringify({ version: 1, field, observedAt: now, value });
    return { getItemName: () => item, getType: () => 'ItemStateEvent',
      getTopic: () => `openhab/items/${item}/state`,
      getSource: () => `org.openhab.core.thing$${channel}`,
      getItemState: () => body, ...overrides };
  };
  return { run, receipt, posts, queued, cache, status,
    advance: (ms = 30000) => { now += ms; },
    get now() { return now; }, get latest() { return posts.at(-1); },
    persistenceFail: value => { persistenceFailure = value; },
    postFail: value => { postFailure = value; } };
}

function ready() {
  const h = harness(); h.run(); h.advance(); h.run(h.receipt()); return h;
}

describe('source-only MPPT daily PV evidence producer', () => {
  it('requires a post-start original Modbus event and labels only the native Wh counter', () => {
    const h = harness(); h.run(h.receipt());
    expect(h.latest.fields[field].status).toBe('unavailable');
    h.advance(); h.run(h.receipt());
    expect(h.latest.basis).toBe('mppt60_native_pv_day_wh');
    expect(h.latest.fields[field]).toEqual({ status: 'valid', reason: 'ok',
      observedAt: h.now, validUntil: h.now + 90000, wh: 8298 });
  });

  it('accepts only the original event, not a reconstructed Item update', () => {
    const h = harness(); h.run(); h.advance();
    h.run({ raw: new Map([['pv.event', h.receipt()]]) });
    expect(h.latest.fields[field].status).toBe('valid');
    h.advance(); h.run({ itemName: item, itemState: '8298' });
    expect(h.latest.fields[field].reason).toBe('invalid_input');
    h.advance(); h.run({ raw: new Map([['pv.event', h.receipt()], ['event', h.receipt()]]) });
    expect(h.latest.fields[field].reason).toBe('invalid_input');
  });

  it.each(['getSource', 'getType', 'getTopic', 'getItemName'])('rejects spoofed %s', key => {
    const h = ready(); h.advance(); h.run(h.receipt('8298', { [key]: () => 'wrong' }));
    expect(h.latest.fields[field].reason).toBe('invalid_input');
  });

  it.each(['UNDEF', 'NULL', '-1', '01', '8298.0', '100001', 'NaN'])
    ('makes invalid native counter text %s an explicit barrier', value => {
      const h = ready(); h.advance(); h.run(h.receipt(value));
      expect(h.latest.fields[field].reason).toBe('invalid_input');
      h.advance(); h.run(h.receipt('0'));
      expect(h.latest.fields[field].wh).toBe(0);
    });

  it('rejects duplicate-key, future, expired and conflicting equal-time envelopes', () => {
    for (const body of [
      h => `{"version":1,"version":1,"field":"${field}","observedAt":${h.now},"value":"8298"}`,
      h => JSON.stringify({ version: 1, field, observedAt: h.now + 1, value: '8298' }),
      h => JSON.stringify({ version: 1, field, observedAt: h.now, value: '8298', extra: 1 }),
    ]) {
      const h = ready(); h.advance(); h.run(h.receipt('8298', { getItemState: () => body(h) }));
      expect(h.latest.fields[field].reason).toBe('invalid_input');
    }
    const h = ready(); h.advance(); const old = h.receipt(); h.advance(90000); h.run(old);
    expect(h.latest.fields[field].reason).toBe('invalid_input');
    const same = ready(); same.run(same.receipt('8300'));
    expect(same.latest.fields[field].reason).toBe('invalid_input');
  });

  it('renews unchanged counter evidence once per minute and expires without a new poll', () => {
    const h = ready(); const first = h.latest;
    h.advance(); h.run(h.receipt());
    expect(h.queued).toHaveLength(2);
    h.advance(); h.run(h.receipt());
    expect(h.latest.fields[field].validUntil).toBe(first.fields[field].validUntil + 60000);
    h.advance(89999); h.run(); expect(h.latest.fields[field].status).toBe('valid');
    h.advance(1); h.run(); expect(h.latest.fields[field].reason).toBe('input_stale');
  });

  it('closes on data Thing, poller or bridge loss and requires a post-recovery receipt', () => {
    for (const uid of [dataThing, poller, bridge]) {
      const h = ready(); h.status.set(uid, 'OFFLINE'); h.run();
      expect(h.latest.fields[field].reason).toBe('source_unavailable');
      h.status.set(uid, 'ONLINE'); h.advance(); h.run();
      expect(h.latest.fields[field].reason).toBe('input_unavailable');
      h.advance(); h.run(h.receipt());
      expect(h.latest.fields[field].status).toBe('valid');
    }
  });

  it('starts a new unavailable epoch after cache restart or clock rollback', () => {
    for (const reset of [h => h.cache.clear(), h => h.advance(-10000)]) {
      const h = ready(); const epoch = h.latest.streamEpoch; reset(h); h.run();
      expect(h.latest.streamEpoch).not.toBe(epoch);
      expect(h.latest.fields[field].status).toBe('unavailable');
    }
  });

  it.each(['before', 'after'])('consumes sequence after %s enqueue failure', failure => {
    const h = harness(); h.run(); h.advance(); h.persistenceFail(failure);
    h.run(h.receipt()); h.persistenceFail(null); h.run();
    expect(h.latest.sequence).toBe(3);
    expect(h.queued.map(x => JSON.parse(x.body).sequence))
      .toEqual(failure === 'before' ? [1, 3] : [1, 2, 3]);
  });

  it('retries a failed Item post without inventing a persisted row', () => {
    const h = ready(); h.advance(); h.postFail(true); h.run(h.receipt('8300'));
    const count = h.queued.length; h.postFail(false); h.run();
    expect(h.queued).toHaveLength(count);
    expect(h.latest.fields[field].wh).toBe(8300);
  });

  it('is disabled by default with an explicit JDBC exclusion and no command path', () => {
    expect(resources.createOnly).toBe(true);
    expect(resources.rule.enabled).toBe(false);
    expect(resources.rule.triggers.map(x => x.type)).toEqual([
      'core.GenericEventTrigger', 'core.ThingStatusChangeTrigger',
      'core.ThingStatusChangeTrigger', 'core.ThingStatusChangeTrigger',
      'timer.GenericCronTrigger', 'core.SystemStartlevelTrigger',
    ]);
    expect(resources.persistenceExclusion).toBe('!MPPT60_PV_Day_Evidence_JSON');
    expect(resources.observationPersistenceExclusion).toBe('!MPPT60_PV_Day_Observation_JSON');
    expect(resources.persistenceCandidate).toBe('openhab/file-config/persistence/jdbc.persist');
    expect(persistence).toContain('!MPPT60_PV_Day_Evidence_JSON');
    expect(persistence).toContain('!MPPT60_PV_Day_Observation_JSON');
    expect(persistence).toMatch(/MPPT60_PV_Day_Evidence_JSON(?:, [A-Za-z0-9_]+)* : strategy = restoreOnStartup/);
    expect(source).not.toMatch(/sendCommand|oh_put|\/rest\/items/);
  });
});
