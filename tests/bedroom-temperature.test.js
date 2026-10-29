import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { officeHallwayTemperature, OFFICE_HALLWAY_VALID_FROM } from '../src/lib/thermal/officeHallwayTemperature.js';

const at = Date.parse("2026-10-24T23:14:52Z");
const epoch = '831b737c-ab25-48d7-9a90-889746e56410';
const sensorEpoch = 'edbd6e3b-ed67-4a0f-9a00-405996be0528';
const receipt = () => ({ version: 2, streamEpoch: epoch, records: { bedroom: {
  version: 2, streamEpoch: epoch, sensorEpoch, model: 'AmbientWeather-WH31E', sensorId: 223,
  field: 'tempinf', status: 'valid', reason: 'accepted', temperatureF: 71.4,
  receivedAt: new Date(at).toISOString(), recordedAt: new Date(at).toISOString(),
  validUntil: new Date(at + 120_000).toISOString(),
} } });
const context = { require: () => ({ rules: { JSRule() {} }, triggers: {
  ItemStateUpdateTrigger() {}, GenericCronTrigger() {},
} }) };
vm.createContext(context);
vm.runInContext(readFileSync('openhab/file-config/automation/js/bedroom-temperature.js', 'utf8'), context);

describe.each([['UI', officeHallwayTemperature], ['OpenHAB', context.bedroomTemperature]])('%s Office Hallway freshness (legacy bedroom stream)', (_label, parse) => {
  it('rejects pre-boundary Office Hallway receipts while still unexpired', () => {
    const snapshot=receipt(); for(const field of ['receivedAt','recordedAt']) snapshot.records.bedroom[field]=new Date(at-1).toISOString(); snapshot.records.bedroom.validUntil=new Date(at+119999).toISOString();
    expect(parse(JSON.stringify(snapshot),at)).toBeNull();
  });
  it('accepts current v2 Office Hallway hardware-phase receipts including retransmissions', () => {
    expect(parse(JSON.stringify(receipt()), at)).toBe(71.4);
    expect(parse(JSON.stringify(receipt()), at + 119_999)).toBe(71.4);
  });
  it('rejects the old sensor phase even when stream and source identity match', () => {
    const snapshot = receipt();
    snapshot.records.bedroom.sensorEpoch = 'e40f17f0-baa9-4470-be6b-5bfd901b219b';
    expect(parse(JSON.stringify(snapshot), at)).toBeNull();
  });
  it('rejects unqualified v1, missing sensor epochs, and mixed receipt versions', () => {
    const legacy = receipt();
    legacy.version = 1; legacy.records.bedroom.version = 1;
    delete legacy.records.bedroom.sensorEpoch;
    expect(parse(JSON.stringify(legacy), at)).toBeNull();
    const missing = receipt(); delete missing.records.bedroom.sensorEpoch;
    expect(parse(JSON.stringify(missing), at)).toBeNull();
    for (const where of ['envelope', 'record']) {
      const mixed = receipt();
      (where === 'envelope' ? mixed : mixed.records.bedroom).version = 1;
      expect(parse(JSON.stringify(mixed), at)).toBeNull();
    }
  });
  it.each([-40, 140])('accepts the configured inclusive Fahrenheit boundary %s', (value) => {
    const snapshot = receipt(); snapshot.records.bedroom.temperatureF = value;
    expect(parse(JSON.stringify(snapshot), at)).toBe(value);
  });
  it.each([-40.01, 140.01, null, '71.4', true])('rejects invalid Fahrenheit value %s', (value) => {
    const snapshot = receipt(); snapshot.records.bedroom.temperatureF = value;
    expect(parse(JSON.stringify(snapshot), at)).toBeNull();
  });
  it('refuses malformed, oversized, non-finite and missing receipts', () => {
    for (const raw of ['UNDEF', '', '{', 'null', '[]', JSON.stringify(receipt()).replace('71.4', '1e999'), ' '.repeat(8193)]) {
      expect(parse(raw, at)).toBeNull();
    }
    expect(parse(JSON.stringify(receipt()), Number.NaN)).toBeNull();
    expect(parse(JSON.stringify(receipt()), Number.POSITIVE_INFINITY)).toBeNull();
  });
  it('requires canonical stream UUID agreement independently of sensor epoch', () => {
    const snapshot = receipt();
    snapshot.streamEpoch = sensorEpoch;
    snapshot.records.bedroom.streamEpoch = sensorEpoch;
    expect(parse(JSON.stringify(snapshot), at)).toBe(71.4);
    snapshot.records.bedroom.streamEpoch = epoch;
    expect(parse(JSON.stringify(snapshot), at)).toBeNull();
    snapshot.streamEpoch = snapshot.records.bedroom.streamEpoch = 'not-a-uuid';
    expect(parse(JSON.stringify(snapshot), at)).toBeNull();
  });
  it('requires acquisition and recorded timestamps to agree and bounded positive expiry', () => {
    for (const [field, value] of [
      ['recordedAt', new Date(at - 1).toISOString()],
      ['receivedAt', null], ['recordedAt', null], ['validUntil', null],
      ['validUntil', new Date(at).toISOString()],
      ['validUntil', new Date(at - 1).toISOString()],
    ]) {
      const snapshot = receipt(); snapshot.records.bedroom[field] = value;
      expect(parse(JSON.stringify(snapshot), at)).toBeNull();
    }
  });
  it('expires even if HTTP polling or change-only persistence holds the numeric value', () => {
    expect(parse(JSON.stringify(receipt()), at + 120_000)).toBeNull();
  });
  it.each(['sensorId', 'model', 'field', 'status', 'reason', 'streamEpoch', 'sensorEpoch', 'receivedAt', 'validUntil', 'temperatureF'])('refuses bad %s and never borrows Hallway', (field) => {
    const snapshot = receipt();
    snapshot.records.indoor = { ...snapshot.records.bedroom };
    snapshot.records.bedroom[field] = field === 'temperatureF' ? 141 : 'invalid';
    expect(parse(JSON.stringify(snapshot), at)).toBeNull();
  });
  it('refuses a missing independent sensor, future acquisition, and excessive expiry', () => {
    expect(parse(JSON.stringify({ ...receipt(), records: {} }), at)).toBeNull();
    expect(parse(JSON.stringify(receipt()), at - 1)).toBeNull();
    const snapshot = receipt(); snapshot.records.bedroom.validUntil = new Date(at + 120_001).toISOString();
    expect(parse(JSON.stringify(snapshot), at)).toBeNull();
  });
});

it('shares the conservative post-relocation history boundary with the learning registry', () => {
  const registry = JSON.parse(readFileSync('openhab/thermal-zone-sensors.json', 'utf8'));
  expect(registry.zones.office_hallway.observations_valid_from).toBe(OFFICE_HALLWAY_VALID_FROM);
  expect(registry.zones.bedroom.item).toBe('Bedroom_Temperature');
});


describe('OpenHAB temperature writer', () => {
  function writer(raw, now = at) {
    const updates = [];
    let rule;
    class FixedDate extends Date { static now() { return now; } }
    const ruleContext = {
      Date: FixedDate,
      require: () => ({ rules: { JSRule(value) { rule = value; } }, triggers: {
        ItemStateUpdateTrigger() {}, GenericCronTrigger() {},
      }, items: { getItem(name) {
        if (name === 'Weather_Temperature_Evidence_JSON') return { state: raw };
        if (name === 'Bedroom_Temperature') return { postUpdate(value) { updates.push(value); } };
        throw new Error(`Unexpected Item ${name}`);
      } } }),
    };
    vm.createContext(ruleContext);
    vm.runInContext(readFileSync('openhab/file-config/automation/js/bedroom-temperature.js', 'utf8'), ruleContext);
    rule.execute();
    return updates;
  }
  it('publishes the current v2 receipt as explicit Fahrenheit to the legacy Item', () => {
    expect(writer(JSON.stringify(receipt()))).toEqual(['71.4 °F']);
  });
  it('posts UNDEF when the receipt expires despite a held temperature', () => {
    expect(writer(JSON.stringify(receipt()), at + 120_000)).toEqual(['UNDEF']);
  });
  it('posts UNDEF for invalid or wrong-phase receipts without borrowing another room', () => {
    const wrong = receipt(); wrong.records.bedroom.sensorEpoch = 'e40f17f0-baa9-4470-be6b-5bfd901b219b';
    const absent = receipt(); absent.records.indoor = absent.records.bedroom; delete absent.records.bedroom;
    expect(writer(JSON.stringify(wrong))).toEqual(['UNDEF']);
    expect(writer(JSON.stringify(absent))).toEqual(['UNDEF']);
    expect(writer('UNDEF')).toEqual(['UNDEF']);
  });
});
