import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../../openhab/transform/tplink_switch_observation.js', import.meta.url), 'utf8');
const item = readFileSync(new URL('../../openhab/file-config/items/tplink-switch-observation.items', import.meta.url), 'utf8');

describe('prepared TP-Link switch acquisition observations', () => {
  it.each(['ON', 'OFF', 'UNDEF', 'NULL', 'unexpected'])
    ('preserves exact channel text %s for a downstream validator', value => {
      const at = 1800000000123;
      const encoded = vm.runInNewContext(source, {
        input: value, Date: { now: () => at },
      }, { timeout: 1000 });
      expect(JSON.parse(encoded)).toEqual({ version: 1, observedAt: at, value });
      expect(encoded).toBe(JSON.stringify(JSON.parse(encoded)));
    });

  it('emits a new receipt for an unchanged switch position', () => {
    const first = JSON.parse(vm.runInNewContext(source, {
      input: 'OFF', Date: { now: () => 1800000000123 },
    }, { timeout: 1000 }));
    const next = JSON.parse(vm.runInNewContext(source, {
      input: 'OFF', Date: { now: () => 1800000030123 },
    }, { timeout: 1000 }));
    expect(next.value).toBe(first.value);
    expect(next.observedAt).toBe(first.observedAt + 30000);
  });

  it('adds only read-side links to the two existing TP-Link switch channels', () => {
    const definitions = item.split('\n').filter(line => line.startsWith('String '));
    expect(definitions).toHaveLength(2);
    expect(definitions[0]).toContain('String Dishwasher_Switch_Observation_JSON');
    expect(definitions[0]).toContain('channel="tplinksmarthome:hs103:a34b4957dc:switch"');
    expect(definitions[1]).toContain('String Cistern_Pump_Switch_Observation_JSON');
    expect(definitions[1]).toContain('channel="tplinksmarthome:hs103:08482dd378:switch"');
    for (const definition of definitions) {
      expect(definition).toContain('profile="transform:JS", toItemScript="tplink_switch_observation.js"');
      expect(definition).not.toMatch(/commandFromItemScript|stateFromItemScript|sendCommand/);
    }
  });
});
