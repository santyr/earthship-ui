import { existsSync, readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const sourceUrl = new URL('../../openhab/rules/bms-soc-evidence.js', import.meta.url);
const descriptorUrl = new URL('../../openhab/bms-soc-evidence-resources.json', import.meta.url);
const names = { raw: 'BMS_SOC_Raw_Observation_JSON', scale: 'BMS_SOC_Scale_Observation_JSON' };
const channels = { raw: 'socRawObservation', scale: 'socScaleObservation' };

function harness() {
  expect(existsSync(sourceUrl), 'evidence rule source exists').toBe(true);
  const source = readFileSync(sourceUrl, 'utf8');
  const values = new Map();
  const posts = [];
  const outputItems = [];
  const health = { BMS_Comms_Status: 'OK', BMS_DevicePresent: '1' };
  let now = Date.parse('2026-09-10T18:00:00Z');
  let fail = false;
  let uuid = 0;
  const denied = (name) => () => { throw new Error(`${name} is forbidden`); };

  const run = (event) => vm.runInNewContext(source, {
    event,
    fetch: denied('fetch'),
    setTimeout: denied('setTimeout'),
    setInterval: denied('setInterval'),
    require: (name) => {
      expect(name).toBe('openhab');
      return {
        cache: { private: { get: (key) => values.get(key), put: (key, value) => values.set(key, value) } },
        items: {
          getItem: (name) => {
            expect(['BMS_Comms_Status', 'BMS_DevicePresent', 'BMS_SOC_Evidence_JSON']).toContain(name);
            return {
              state: health[name] ?? 'NULL',
              postUpdate: (value) => {
                outputItems.push(name);
                expect(name).toBe('BMS_SOC_Evidence_JSON');
                if (fail) throw new Error('injected publication failure');
                posts.push(JSON.parse(value));
              },
              sendCommand: denied('sendCommand'),
            };
          },
        },
      };
    },
    Java: { type: (name) => {
      if (name === 'java.time.Instant') return { now: () => ({ toEpochMilli: () => now }) };
      if (name === 'java.util.UUID') return { randomUUID: () => ({ toString: () => `epoch-${++uuid}` }) };
      throw new Error(`unexpected Java class: ${name}`);
    } },
    console: { warn: () => {} },
  }, { timeout: 1000 });

  const envelope = (field, value, at = now) => vm.runInNewContext(
    readFileSync(new URL(`../../openhab/transform/bms_soc_${field}_observation.js`, import.meta.url), 'utf8'),
    { input: value, Date: { now: () => at } }, { timeout: 1000 },
  );
  const originalEvent = (field, value, at = now, overrides = {}) => ({
    getType: () => 'ItemStateEvent',
    getTopic: () => `openhab/items/${names[field]}/state`,
    getItemName: () => names[field],
    getItemState: () => ({ toString: () => envelope(field, value, at) }),
    getSource: () => `org.openhab.core.thing$modbus:data:schneiderBatterySunSpec:battery802Core:${channels[field]}:string`,
    ...overrides,
  });
  const wrappedEvent = (key, original) => ({ raw: new Map([
    [`${key}.event`, original],
    ['ruleUID', 'hex_bms_soc_evidence'],
  ]) });
  const update = (field, value, at = now, overrides = {}) =>
    run(wrappedEvent(field, originalEvent(field, value, at, overrides)));

  return {
    run, update, originalEvent, wrappedEvent, posts, outputItems, health, values,
    advance: (ms) => { now += ms; }, now: () => now,
    setNow: (ms) => { now = ms; }, setFail: (value) => { fail = value; },
    restart: () => values.clear(),
  };
}

function establishValid(h, raw = '99', scale = '0') {
  h.run(); h.advance(1);
  h.update('scale', scale); h.update('raw', raw);
  expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: Number(raw) * 10 ** Number(scale) });
}

describe('atomic BMS SoC evidence observer', () => {
  it('keeps source time when an unchanged scale arrives after delayed raw', () => {
    const h = harness(); h.run(); h.advance(1); h.update('scale', '0');
    const at = h.now(); h.advance(1000); h.update('raw', '99', at);
    expect(h.posts.at(-1)).toMatchObject({ status: 'valid', observedAt: at });
    h.advance(60000); h.update('scale', '0');
    expect(h.posts.at(-1)).toMatchObject({ observedAt: at, scaleObservedAt: h.now(), validUntil: at + 120000 });
  });

  it('requires another raw observation when scale arrives second or changes', () => {
    const h = harness(); h.run(); h.advance(1);
    h.update('raw', '990'); h.update('scale', '-1');
    expect(h.posts.at(-1).status).toBe('unavailable');
    h.advance(1); h.update('raw', '990');
    expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: 99 });
    h.advance(1); h.update('scale', '-2');
    expect(h.posts.at(-1).status).toBe('unavailable');
    h.advance(1); h.update('raw', '990');
    expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: 9.9 });
  });

  it('does not miss a queued health fault after the snapshot has recovered', () => {
    const h = harness(); establishValid(h); h.advance(1);
    h.run({ itemName: 'BMS_Comms_Status', newState: 'STALE' });
    expect(h.health.BMS_Comms_Status).toBe('OK');
    expect(h.posts.at(-1).status).toBe('unavailable');
    h.advance(1); h.update('scale', '0'); h.update('raw', '80');
    expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: 80 });
  });

  it.each([
    { getType: () => 'ItemStateUpdatedEvent' },
    { getTopic: () => 'openhab/items/BMS_SOC_Raw_Observation_JSON/statechanged' },
    { getSource: () => 'org.openhab.core.persistence.jdbc' },
    { getSource: () => null },
    { getItemState: () => '{' },
    { getItemState: () => '' },
  ])('invalidates bad event provenance or body %#', (overrides) => {
    const h = harness(); establishValid(h); h.advance(1);
    h.update('raw', '99', h.now(), overrides);
    expect(h.posts.at(-1)).toMatchObject({ status: 'unavailable', observedAt: null, soc: null });
  });

  it.each([
    (e) => ({ ...e, extra: true }), (e) => ({ ...e, version: 2 }), (e) => ({ ...e, field: 'scale' }),
    (e) => ({ ...e, value: 99 }), (e) => ({ ...e, observedAt: String(e.observedAt) }),
    (e) => ({ ...e, observedAt: e.observedAt + 1 }), (e) => ({ ...e, observedAt: 1.5 }),
    () => null, () => [], () => ({}),
  ])('rejects malformed closed envelopes %#', (mutate) => {
    const h = harness(); establishValid(h); h.advance(1);
    const body = JSON.stringify(mutate({ version: 1, field: 'raw', observedAt: h.now(), value: '99' }));
    h.update('raw', '99', h.now(), { getItemState: () => body });
    expect(h.posts.at(-1).status).toBe('unavailable');
  });

  it.each(['version', 'field', 'observedAt', 'value'])('rejects envelope missing %s', (missing) => {
    const h = harness(); establishValid(h); h.advance(1);
    const body = { version: 1, field: 'raw', observedAt: h.now(), value: '99' };
    delete body[missing];
    h.update('raw', '99', h.now(), { getItemState: () => JSON.stringify(body) });
    expect(h.posts.at(-1).status).toBe('unavailable');
  });

  it.each([
    ['raw', 'org.openhab.core.thing$modbus:data:schneiderBatterySunSpec:battery802Core:socScaleObservation:string'],
    ['scale', 'org.openhab.core.thing$modbus:data:schneiderBatterySunSpec:battery802Core:socRawObservation:string'],
  ])('invalidates foreign %s binding source', (field, source) => {
    const h = harness(); establishValid(h); h.advance(1);
    h.update(field, field === 'raw' ? '99' : '0', h.now(), { getSource: () => source });
    expect(h.posts.at(-1)).toMatchObject({ status: 'unavailable', soc: null });
  });

  it('accepts direct, observed trigger-key, and plain-event compatibility shapes', () => {
    const h = harness(); h.run(); h.advance(1);
    h.run(h.originalEvent('scale', '0'));
    h.run(h.wrappedEvent('raw', h.originalEvent('raw', '42')));
    expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: 42 });
    h.advance(1);
    h.run({ raw: new Map([['event', h.originalEvent('raw', '43')]]) });
    expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: 43 });
  });

  it.each(['raw', 'scale'])('accepts natural %s.event source wrappers', (field) => {
    const h = harness(); h.run(); h.advance(1);
    h.update('scale', '0');
    h.update('raw', '44');
    expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: 44 });
    expect(h.values.get('earthship.bms-soc-evidence.v1')[field]).not.toBeNull();
  });

  it.each([
    ['comms', 'BMS_Comms_Status'],
    ['device', 'BMS_DevicePresent'],
  ])('invalidates cached evidence through natural %s.event health wrappers', (key, itemName) => {
    const h = harness(); establishValid(h); h.advance(1);
    const event = { getItemName: () => itemName };
    h.run(h.wrappedEvent(key, event));
    expect(h.posts.at(-1)).toMatchObject({ status: 'unavailable', observedAt: null, soc: null });
  });

  it('rejects ambiguous original-event wrapper candidates', () => {
    const h = harness(); establishValid(h); h.advance(1);
    h.run({ raw: new Map([
      ['raw.event', h.originalEvent('raw', '98')],
      ['scale.event', h.originalEvent('scale', '0')],
    ]) });
    expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: 99 });
    expect(h.values.get('earthship.bms-soc-evidence.v1').raw.value).toBe(99);
  });

  it.each([null, {}, new Map(), new Map([['raw.event', null]])])(
    'fails closed for malformed raw wrapper %#', (raw) => {
      const h = harness(); establishValid(h); const count = h.posts.length; h.advance(1);
      h.run({ raw });
      expect(h.posts).toHaveLength(count);
      expect(h.values.get('earthship.bms-soc-evidence.v1').raw.value).toBe(99);
    },
  );

  it('ignores duplicate and out-of-order trusted events', () => {
    const h = harness(); establishValid(h); const state = h.values.get('earthship.bms-soc-evidence.v1');
    const at = state.raw.at; const count = h.posts.length; h.advance(1000);
    h.update('raw', '98', at); h.update('raw', '97', at - 1);
    expect(h.posts).toHaveLength(count);
    expect(h.values.get('earthship.bms-soc-evidence.v1').raw).toMatchObject({ at, value: 99 });
  });

  it.each([
    ['raw', '-1'], ['raw', '65535'], ['raw', '1.0'], ['raw', '1e2'], ['raw', ' 99'], ['raw', '99 %'],
    ['scale', '-32768'], ['scale', '32768'], ['scale', '1.0'], ['scale', '1e1'], ['scale', '+ 1'],
  ])('rejects strict or out-of-range %s text %j', (field, value) => {
    const h = harness(); establishValid(h); h.advance(1); h.update(field, value);
    expect(h.posts.at(-1)).toMatchObject({ status: 'unavailable', soc: null });
  });

  it.each([
    ['above 100', '101', '0'], ['overflow', '1', '32767'], ['nonzero underflow', '1', '-32767'],
  ])('rejects scaled SoC %s', (_label, raw, scale) => {
    const h = harness(); h.run(); h.advance(1); h.update('scale', scale); h.update('raw', raw);
    expect(h.posts.at(-1)).toMatchObject({ status: 'unavailable', reason: 'invalid_scaled_soc' });
  });

  it('accepts zero without treating scale underflow as nonzero evidence', () => {
    const h = harness(); h.run(); h.advance(1); h.update('scale', '-32767'); h.update('raw', '0');
    expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: 0 });
  });

  it('accepts exact age 120000 and rejects age 120001', () => {
    const exact = harness(); exact.run(); exact.advance(1); exact.update('scale', '0');
    const at = exact.now(); exact.advance(120000); exact.update('raw', '99', at);
    expect(exact.posts.at(-1)).toMatchObject({ status: 'valid', soc: 99 });
    const stale = harness(); stale.run(); stale.advance(1); stale.update('scale', '0');
    const staleAt = stale.now(); stale.advance(120001); stale.update('raw', '99', staleAt);
    expect(stale.posts.at(-1)).toMatchObject({ status: 'unavailable', soc: null });
  });

  it('rejects pre-barrier queued observations', () => {
    const h = harness(); const queuedAt = h.now(); h.run(); h.advance(1);
    h.update('scale', '0', queuedAt); h.update('raw', '99', queuedAt);
    expect(h.posts.at(-1)).toMatchObject({ status: 'unavailable', soc: null });
  });

  it('invalid scale recovery cannot reuse pre-fault raw evidence', () => {
    const h = harness(); establishValid(h); h.advance(1); h.update('scale', 'bad');
    expect(h.posts.at(-1).status).toBe('unavailable');
    h.advance(1); h.update('scale', '0');
    expect(h.posts.at(-1).status).toBe('unavailable');
    h.advance(1); h.update('raw', '80');
    expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: 80 });
  });

  it.each([
    ['BMS_Comms_Status', 'STALE'], ['BMS_Comms_Status', 'NULL'],
    ['BMS_DevicePresent', '0'], ['BMS_DevicePresent', 'UNDEF'],
  ])('health %s=%s clears inputs and requires post-barrier evidence', (name, value) => {
    const h = harness(); establishValid(h); h.advance(1); h.health[name] = value; h.run({ itemName: name });
    expect(h.posts.at(-1)).toMatchObject({ status: 'unavailable', reason: 'source_unavailable' });
    h.health[name] = name === 'BMS_Comms_Status' ? 'OK' : '1'; h.advance(1); h.run({ itemName: name });
    h.advance(1);
    h.update('scale', '0'); h.update('raw', '80');
    expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: 80 });
  });

  it('restart ignores restored Item snapshots and creates a new unavailable epoch', () => {
    const h = harness(); establishValid(h); const first = h.posts.at(-1); h.restart(); h.advance(1);
    h.health.BMS_SOC_Raw_Observation_JSON = 'restored'; h.run({ itemName: 'startup' });
    expect(h.posts.at(-1)).toMatchObject({ status: 'unavailable', soc: null });
    expect(h.posts.at(-1).streamEpoch).not.toBe(first.streamEpoch);
    h.advance(1); h.update('scale', '0'); h.update('raw', '99');
    expect(h.posts.at(-1).status).toBe('valid');
  });

  it('clock rollback starts a new unavailable epoch and needs new evidence', () => {
    const h = harness(); establishValid(h); const first = h.posts.at(-1);
    h.setNow(h.now() - 1000); h.run();
    expect(h.posts.at(-1).status).toBe('unavailable');
    expect(h.posts.at(-1).streamEpoch).not.toBe(first.streamEpoch);
    h.advance(1); h.update('scale', '0'); h.update('raw', '99');
    expect(h.posts.at(-1).status).toBe('valid');
  });

  it('expires old evidence and publishes valid heartbeats at 60000ms', () => {
    const h = harness(); establishValid(h); const initial = h.posts.length;
    h.advance(59999); h.run(); expect(h.posts).toHaveLength(initial);
    h.advance(1); h.run(); expect(h.posts).toHaveLength(initial + 1);
    h.advance(60001); h.run();
    expect(h.posts.at(-1)).toMatchObject({ status: 'unavailable', reason: 'input_stale', observedAt: null });
  });

  it('publication failure does not advance receipt and retries normally', () => {
    const h = harness(); h.run(); h.advance(1); h.update('scale', '0'); h.setFail(true); h.update('raw', '99');
    expect(h.values.get('earthship.bms-soc-evidence.v1').lastPublished.status).toBe('unavailable');
    h.setFail(false); h.run();
    expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: 99 });
  });

  it('publishes only one output with the closed version-1 schema', () => {
    const h = harness(); establishValid(h);
    expect(new Set(h.outputItems)).toEqual(new Set(['BMS_SOC_Evidence_JSON']));
    expect(Object.keys(h.posts.at(-1)).sort()).toEqual([
      'observedAt', 'reason', 'recordedAt', 'scaleObservedAt', 'soc', 'status',
      'streamEpoch', 'validUntil', 'version',
    ]);
  });
});

describe('create-only disabled atomic source resources', () => {
  const descriptor = JSON.parse(readFileSync(descriptorUrl,'utf8'));
  const cases = [
    ['raw','socRawObservation','BMS_SOC_Raw_Observation_JSON','40255','uint16'],
    ['scale','socScaleObservation','BMS_SOC_Scale_Observation_JSON','40300','int16'],
  ];
  it('declares only three new String Items with existing persistence policy',()=>{
    expect(descriptor.version).toBe(1);
    expect(descriptor.createOnly).toBe(true);
    expect(descriptor.items.map(i=>i.name).sort()).toEqual([
      'BMS_SOC_Evidence_JSON','BMS_SOC_Raw_Observation_JSON','BMS_SOC_Scale_Observation_JSON']);
    expect(descriptor.items.every(i=>i.type==='String')).toBe(true);
    expect(descriptor.persistence).toEqual({serviceId:'jdbc',strategy:'everyChange',
      restoreOnStartup:true,items:descriptor.items.map(i=>i.name)});
  });
  it.each(cases)('maps %s to a disabled read-only child and exact original event',
    (field,suffix,item,register,valueType)=>{
      const uid=`modbus:data:schneiderBatterySunSpec:battery802Core:${suffix}`;
      const thing=descriptor.things.find(t=>t.UID===uid);
      expect(thing).toMatchObject({enabled:false,thingTypeUID:'modbus:data',
        bridgeUID:'modbus:poller:schneiderBatterySunSpec:battery802Core'});
      expect(thing.configuration).toEqual({readStart:register,readValueType:valueType,
        readTransform:[`JS(bms_soc_${field}_observation.js)`],updateUnchangedValuesEveryMillis:30000});
      expect(descriptor.links.find(l=>l.itemName===item)).toEqual({itemName:item,
        channelUID:`${uid}:string`,configuration:{profile:'system:default'}});
      expect(descriptor.rule.triggers.find(t=>t.id===field)).toEqual({id:field,
        type:'core.GenericEventTrigger',configuration:{topic:`openhab/items/${item}/state`,
          types:'ItemStateEvent',source:'',payload:''}});
      expect(descriptor.transformations.find(t=>t.uid===`bms_soc_${field}_observation.js`))
        .toEqual({uid:`bms_soc_${field}_observation.js`,type:'js',
          source:`openhab/transform/bms_soc_${field}_observation.js`});
    });
  it('has no extra resources, timestamp companions or control triggers',()=>{
    expect(descriptor.things).toHaveLength(2);
    expect(descriptor.links).toHaveLength(2);
    expect(descriptor.transformations).toHaveLength(2);
    expect(descriptor.rule).toMatchObject({uid:'hex_bms_soc_evidence',enabled:false,
      source:'openhab/rules/bms-soc-evidence.js'});
    expect(descriptor.rule.triggers.slice(2)).toEqual([
      {id:'comms',type:'core.ItemStateChangeTrigger',configuration:{itemName:'BMS_Comms_Status'}},
      {id:'device',type:'core.ItemStateChangeTrigger',configuration:{itemName:'BMS_DevicePresent'}},
      {id:'expiry',type:'timer.GenericCronTrigger',configuration:{cronExpression:'0 * * * * ?'}},
      {id:'startup',type:'core.SystemStartlevelTrigger',configuration:{startlevel:100}},
    ]);
  });
});
