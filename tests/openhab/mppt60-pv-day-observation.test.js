import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../../openhab/transform/mppt60_pv_day_observation.js', import.meta.url), 'utf8');
const item = readFileSync(new URL('../../openhab/candidates/mppt60-pv-day-observation.items', import.meta.url), 'utf8');

describe('prepared MPPT daily PV acquisition observation', () => {
  it.each(['0', '8298', '8298.0', 'UNDEF', 'NULL', '-1', 'not a number'])
    ('preserves exact channel text %s for a downstream source validator', value => {
      const at = 1800000000123;
      const encoded = vm.runInNewContext(source, {
        input: value, Date: { now: () => at },
      }, { timeout: 1000 });
      expect(JSON.parse(encoded)).toEqual({
        version: 1, field: 'mppt60.pv_day_wh', observedAt: at, value,
      });
      expect(encoded).toBe(JSON.stringify(JSON.parse(encoded)));
    });

  it('creates a new receipt even when the daily counter is unchanged', () => {
    const first = JSON.parse(vm.runInNewContext(source, {
      input: '0', Date: { now: () => 1800000000123 },
    }, { timeout: 1000 }));
    const next = JSON.parse(vm.runInNewContext(source, {
      input: '0', Date: { now: () => 1800000030123 },
    }, { timeout: 1000 }));
    expect(next.value).toBe(first.value);
    expect(next.observedAt).toBe(first.observedAt + 30000);
  });

  it('adds a read-only link to the exact existing native counter channel', () => {
    expect(item).toContain('String MPPT60_PV_Day_Observation_JSON');
    expect(item).toContain('channel="modbus:data:9eb978a141:mppt60Energy:energyFromPVTodayWh:number"');
    expect(item).toContain('profile="transform:JS", toItemScript="mppt60_pv_day_observation.js"');
    expect(item).not.toMatch(/commandFromItemScript|stateFromItemScript|sendCommand/);
  });
});
