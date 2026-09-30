import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { officeHallwayTemperature, OFFICE_HALLWAY_VALID_FROM } from '../src/lib/thermal/officeHallwayTemperature.js';

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

describe.each([['UI', officeHallwayTemperature], ['OpenHAB', context.bedroomTemperature]])('%s Office Hallway freshness (legacy bedroom stream)', (_label, parse) => {
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
  expect(registry.zones.bedroom.item).toBeNull();
});
