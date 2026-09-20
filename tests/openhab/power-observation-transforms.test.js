import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const fields = [
  ['battery', 'battery.dc_power_w', '40291', 'int16', 'Battery_Power_Observation_JSON'],
  ['pv_input', 'pv.input_power_w', '80', 'uint32', 'PV_Input_Power_Observation_JSON'],
  ['pv_output', 'pv.output_power_w', '92', 'uint32', 'PV_Output_Power_Observation_JSON'],
];
const descriptor = JSON.parse(readFileSync(new URL('../../openhab/power-observation-resources.json', import.meta.url), 'utf8'));

function execute(key, input, now) {
  const source = readFileSync(new URL(`../../openhab/transform/power_${key}_observation.js`, import.meta.url), 'utf8');
  const forbidden = () => { throw new Error('unexpected transformation capability'); };
  let reads = 0;
  const value = vm.runInNewContext(source, {
    input, Date: { now: () => { reads += 1; return now; } },
    require: forbidden, fetch: forbidden, setTimeout: forbidden, setInterval: forbidden,
    Java: { type: forbidden }, items: new Proxy({}, { get: forbidden }),
    cache: new Proxy({}, { get: forbidden }), actions: new Proxy({}, { get: forbidden }),
  }, { timeout: 1000 });
  expect(reads).toBe(1);
  return JSON.parse(value);
}

describe.each(fields)('%s acquisition receipt', (key, field, address, type, item) => {
  it.each(['0', '-32768', '4294967295', '-45', '123', 'NULL', 'UNDEF', '', 'NaN', ' 12 ', '12 W'])
  ('preserves raw value %j without declaring validity', input => {
    expect(execute(key, input, 1800000000000)).toEqual({
      version: 1, field, observedAt: 1800000000000, value: input,
    });
  });
  it('stamps unchanged samples and preserves backward clock evidence', () => {
    const first = execute(key, '0', 1800000000000);
    expect(execute(key, '0', 1800000005000).observedAt).toBe(first.observedAt + 5000);
    expect(execute(key, '0', 1799999999000).observedAt).toBe(first.observedAt - 1000);
  });
  it('uses an isolated disabled data Thing on the existing poller', () => {
    const link = descriptor.links.find(l => l.itemName === item);
    const thing = descriptor.things.find(t => `${t.UID}:string` === link.channelUID);
    expect(thing.enabled).toBe(false);
    expect(thing.thingTypeUID).toBe('modbus:data');
    expect(thing.bridgeUID).toMatch(/^modbus:poller:/);
    expect(thing.configuration).toEqual({ readStart: address, readValueType: type,
      readTransform: [`JS(power_${key}_observation.js)`], updateUnchangedValuesEveryMillis: 30000 });
    expect(descriptor.items.find(i => i.name === item).type).toBe('String');
    expect(descriptor.transformations.find(t => t.uid === `power_${key}_observation.js`).source)
      .toBe(`openhab/transform/power_${key}_observation.js`);
  });
});

it('adds only acquisition resources, never controls, pollers or automatic deployment', () => {
  expect(descriptor.createOnly).toBe(true);
  expect(descriptor.things).toHaveLength(3);
  expect(descriptor.items).toHaveLength(3);
  expect(descriptor.links).toHaveLength(3);
  expect(Object.keys(descriptor).sort()).toEqual(['version', 'createOnly', 'transformations', 'things', 'links', 'items'].sort());
  const managed = readFileSync(new URL('../../openhab/managed-resources.json', import.meta.url), 'utf8');
  for (const item of descriptor.items) expect(managed).not.toContain(item.name);
});
