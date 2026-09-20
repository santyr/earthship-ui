import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../../openhab/rules/power-evidence.js', import.meta.url), 'utf8');
const definitions = [
  ['battery', 'Battery_Power_Observation_JSON', 'battery.dc_power_w', 'schneiderBatterySunSpec:battery802Core', -32767, 32767],
  ['pv_input', 'PV_Input_Power_Observation_JSON', 'pv.input_power_w', '9eb978a141:mppt60Input', 0, 4294967294],
  ['pv_output', 'PV_Output_Power_Observation_JSON', 'pv.output_power_w', '9eb978a141:mppt60Output', 0, 4294967294],
];
function harness() {
  const state = new Map();
  const posts = [];
  let now = 1800000000000, epoch = 0, fail = false;
  const denied = () => { throw new Error('forbidden capability'); };
  const run = event => vm.runInNewContext(source, {
    event, console: { warn: () => {} }, fetch: denied, setTimeout: denied,
    require: name => {
      expect(name).toBe('openhab');
      return { cache: { private: { get: k => state.get(k), put: (k, v) => state.set(k, v) } },
        items: { getItem: name => {
          expect(name).toBe('Power_Evidence_JSON');
          return { get state() { return denied(); }, sendCommand: denied,
            postUpdate: text => { if (fail) throw new Error('injected'); posts.push(JSON.parse(text)); } };
        } } };
    },
    Java: { type: name => {
      if (name === 'java.time.Instant') return { now: () => ({ toEpochMilli: () => now }) };
      if (name === 'java.util.UUID') return { randomUUID: () => ({ toString: () => `epoch-${++epoch}` }) };
      return denied();
    } },
  }, { timeout: 1000 });
  const event = (definition, value = '100', overrides = {}) => {
    const [, name, field, bridge] = definition;
    const record = { version: 1, field, observedAt: now, value };
    return { getItemName: () => name, getType: () => 'ItemStateEvent',
      getTopic: () => `openhab/items/${name}/state`,
      getSource: () => `org.openhab.core.thing$modbus:data:${bridge}:powerObservation:string`,
      getItemState: () => JSON.stringify(record), ...overrides };
  };
  return { run, event, posts, state, advance: (ms = 5000) => { now += ms; },
    get now() { return now; }, get latest() { return posts.at(-1); },
    fail: value => { fail = value; } };
}

describe.each(definitions)('%s observer', (...definition) => {
  const [trigger, name, field, , min, max] = definition;
  function ready() {
    const h = harness(); h.run(); h.advance(); h.run(h.event(definition)); return h;
  }
  it('requires post-start receipt and accepts original event with exact provenance', () => {
    const h = harness(); h.run(h.event(definition));
    expect(h.latest.fields[field].status).toBe('unavailable');
    h.advance(); h.run(h.event(definition));
    expect(h.latest.fields[field]).toEqual({ status: 'valid', reason: 'ok', watts: 100,
      observedAt: h.now, validUntil: h.now + 120000 });
    for (const [, , other] of definitions) if (other !== field) expect(h.latest.fields[other].status).toBe('unavailable');
  });
  it('accepts the generic-trigger original-event map', () => {
    const h = harness(); h.run(); h.advance();
    h.run({ raw: new Map([[`${trigger}.event`, h.event(definition)]]) });
    expect(h.latest.fields[field].status).toBe('valid');
  });
  it.each([min, 0, max])('preserves representable watts %s', watts => {
    const h = ready(); h.advance(); h.run(h.event(definition, String(watts)));
    expect(h.latest.fields[field].watts).toBe(watts);
  });
  it.each(['NULL', 'UNDEF', '', '1 W', '1e3', 'NaN', ' 100 ', '1.5'])('invalid value %s creates a barrier', value => {
    const h = ready(); h.advance(); h.run(h.event(definition, value));
    expect(h.latest.fields[field].status).toBe('unavailable');
    expect(h.latest.fields[field].watts).toBeNull();
    h.advance(); h.run(h.event(definition));
    expect(h.latest.fields[field].status).toBe('valid');
  });
  it.each([min - 1, max + 1])('rejects out of range/sentinel %s', value => {
    const h = ready(); h.advance(); h.run(h.event(definition, String(value)));
    expect(h.latest.fields[field].status).toBe('unavailable');
  });
  it.each(['getSource', 'getType', 'getTopic'])('rejects spoofed %s', key => {
    const h = ready(); h.advance(); h.run(h.event(definition, '100', { [key]: () => 'wrong' }));
    expect(h.latest.fields[field].status).toBe('unavailable');
  });
  it('does not trust wrapper state without original event', () => {
    const h = ready(); h.advance(); h.run({ itemName: name, itemState: '100' });
    expect(h.latest.fields[field].status).toBe('unavailable');
  });
  it('expires exactly at TTL, not according to timer timestamp', () => {
    const h = ready(); h.advance(119999); h.run();
    expect(h.latest.fields[field].status).toBe('valid');
    h.advance(1); h.run();
    expect(h.latest.fields[field].reason).toBe('input_stale');
  });
  it('retains unchanged receipts and their distinct expiry times', () => {
    const h = ready(); const first = h.latest;
    h.advance(); h.run(h.event(definition));
    expect(h.latest.fields[field].watts).toBe(first.fields[field].watts);
    expect(h.latest.fields[field].validUntil).toBe(first.fields[field].validUntil + 5000);
  });
  it('ignores delayed older receipts without extending freshness', () => {
    const h = ready(); const old = h.event(definition, '999');
    h.advance(); h.run(h.event(definition, '200')); const first = h.latest;
    h.advance(); h.run(old);
    expect(h.latest).toEqual(first);
  });
  it('rejects equal-time conflicts and requires a later receipt to recover', () => {
    const h = ready(); h.run(h.event(definition, '999'));
    expect(h.latest.fields[field].status).toBe('unavailable');
    h.run(h.event(definition));
    expect(h.latest.fields[field].status).toBe('unavailable');
    h.advance(); h.run(h.event(definition));
    expect(h.latest.fields[field].status).toBe('valid');
  });
  it('rejects malformed, extra, duplicate, future and expired envelopes', () => {
    for (const body of [
      () => 'x', () => '[]', () => 'x'.repeat(1025),
      h => JSON.stringify({version:1,field,observedAt:h.now,value:'100',extra:true}),
      h => `{"version":1,"version":1,"field":"${field}","observedAt":${h.now},"value":"100"}`,
      h => JSON.stringify({version:1,field,observedAt:h.now+1,value:'100'}),
    ]) {
      const h = ready(); h.advance(); h.run(h.event(definition, '100', {getItemState: () => body(h)}));
      expect(h.latest.fields[field].status).toBe('unavailable');
    }
    const h = ready(); h.advance(); const late = h.event(definition);
    h.advance(120000); h.run(late);
    expect(h.latest.fields[field].status).toBe('unavailable');
  });
});

it('ambiguous original-event maps invalidate all fields', () => {
  const h = harness(); h.run();
  for (const d of definitions) { h.advance(); h.run(h.event(d)); }
  h.run({raw:new Map([['battery.event',h.event(definitions[0])],['pv_input.event',h.event(definitions[1])]])});
  expect(Object.values(h.latest.fields).every(f=>f.status==='unavailable')).toBe(true);
});
it('cache restart and clock rollback cannot reuse old evidence', () => {
  for (const reset of [h=>h.state.clear(), h=>h.advance(-10000)]) {
    const h = harness(); h.run(); h.advance(); h.run(h.event(definitions[0]));
    const old = h.latest.streamEpoch; reset(h); h.run();
    expect(h.latest.streamEpoch).not.toBe(old);
    expect(Object.values(h.latest.fields).every(f=>f.status==='unavailable')).toBe(true);
  }
});
it('publication failure does not acknowledge the missing update', () => {
  const h = harness(); h.run(); h.advance(); h.fail(true); h.run(h.event(definitions[0]));
  expect(h.latest.fields['battery.dc_power_w'].status).toBe('unavailable');
  h.fail(false); h.run();
  expect(h.latest.fields['battery.dc_power_w'].status).toBe('valid');
  expect(h.latest.sequence).toBe(2);
});

it('orders same-millisecond publications with a per-epoch sequence', () => {
  const h = harness(); h.run(); h.advance();
  h.run(h.event(definitions[0])); h.run(h.event(definitions[1]));
  expect(h.posts.at(-2).recordedAt).toBe(h.latest.recordedAt);
  expect(h.posts.map(p=>p.sequence)).toEqual([1,2,3]);
  h.state.clear(); h.run(); expect(h.latest.sequence).toBe(1);
});

it('descriptor remains disabled, observational and outside automatic deployment', () => {
  const resource = JSON.parse(readFileSync(new URL('../../openhab/power-evidence-resources.json', import.meta.url), 'utf8'));
  expect(resource.createOnly).toBe(true);
  expect(resource.rule.enabled).toBe(false);
  expect(resource.rule.source).toBe('openhab/rules/power-evidence.js');
  expect(resource.items.map(i=>[i.name,i.type])).toEqual([['Power_Evidence_JSON','String']]);
  expect(resource.rule.triggers).toHaveLength(4);
  for (const [id,name] of definitions) {
    expect(resource.rule.triggers.find(t=>t.id===id)).toEqual({id,type:'core.GenericEventTrigger',
      configuration:{topic:`openhab/items/${name}/state`,types:'ItemStateEvent',source:'',payload:''}});
  }
  expect(readFileSync(new URL('../../openhab/managed-resources.json', import.meta.url), 'utf8'))
    .not.toContain('hex_power_evidence');
});
