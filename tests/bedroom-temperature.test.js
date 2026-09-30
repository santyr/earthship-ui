import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { bedroomTemperature } from '../src/lib/thermal/bedroomTemperature.js';

const at = Date.parse('2026-09-30T23:00:00Z');
const epoch = '831b737c-ab25-48d7-9a90-889746e56410';
const receipt = () => ({ version: 1, streamEpoch: epoch, records: { bedroom: {
  version: 1, streamEpoch: epoch, model: 'AmbientWeather-WH31E', sensorId: 223,
  field: 'tempinf', status: 'valid', reason: 'accepted', temperatureF: 71.4,
  receivedAt: new Date(at).toISOString(), recordedAt: new Date(at).toISOString(),
  validUntil: new Date(at + 120_000).toISOString(),
} } });
const context = { require: () => ({ rules: { JSRule() {} }, triggers: {
  ItemStateUpdateTrigger() {}, GenericCronTrigger() {},
} }) };
vm.createContext(context);
vm.runInContext(readFileSync('openhab/file-config/automation/js/bedroom-temperature.js', 'utf8'), context);

describe.each([['UI', bedroomTemperature], ['OpenHAB', context.bedroomTemperature]])('%s Bedroom freshness', (_label, parse) => {
  it('accepts an original, source-bound receipt including identical retransmissions', () => {
    expect(parse(JSON.stringify(receipt()), at)).toBe(71.4);
    expect(parse(JSON.stringify(receipt()), at + 119_999)).toBe(71.4);
  });
  it('expires even if HTTP polling or change-only persistence holds the numeric value', () => {
    expect(parse(JSON.stringify(receipt()), at + 120_000)).toBeNull();
  });
  it.each(['sensorId', 'model', 'field', 'status', 'reason', 'streamEpoch', 'receivedAt', 'validUntil', 'temperatureF'])('refuses bad %s and never borrows Hallway', (field) => {
    const snapshot = receipt();
    snapshot.records.indoor = { ...snapshot.records.bedroom };
    snapshot.records.bedroom[field] = field === 'temperatureF' ? 141 : 'invalid';
    expect(parse(JSON.stringify(snapshot), at)).toBeNull();
  });
  it('refuses missing Bedroom, future acquisition, and excessive expiry', () => {
    expect(parse(JSON.stringify({ ...receipt(), records: {} }), at)).toBeNull();
    expect(parse(JSON.stringify(receipt()), at - 1)).toBeNull();
    const snapshot = receipt(); snapshot.records.bedroom.validUntil = new Date(at + 120_001).toISOString();
    expect(parse(JSON.stringify(snapshot), at)).toBeNull();
  });
});
