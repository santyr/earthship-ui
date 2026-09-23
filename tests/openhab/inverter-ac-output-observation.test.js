import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../../openhab/transform/inverter_ac_output_observation.js', import.meta.url), 'utf8');
const item = readFileSync(new URL('../../openhab/file-config/drafts/inverter-ac-output-observation.items', import.meta.url), 'utf8');

describe('prepared inverter AC output observation', () => {
  it.each(['209 W', '0 W', 'UNDEF', 'NULL', '-12 W', 'not a number'])
    ('preserves the exact source text %s with one host transform timestamp', value => {
      const at = 1800000000123;
      const encoded = vm.runInNewContext(source, {
        input: value, Date: { now: () => at },
      }, { timeout: 1000 });
      expect(JSON.parse(encoded)).toEqual({
        version: 1, field: 'inverter.ac_output_w', observedAt: at, value,
      });
      expect(encoded).toBe(JSON.stringify(JSON.parse(encoded)));
    });

  it('adds only a read-side link to the existing inverter channel', () => {
    expect(item).toContain('PREPARED ONLY');
    expect(item).toContain('String Inverter_AC_Output_Observation_JSON');
    expect(item).toContain('channel="modbus:inverter-split-phase:1ed74db72c:e853aec444:acGeneral#ac-power"');
    expect(item).toContain('profile="transform:JS", toItemScript="inverter_ac_output_observation.js"');
    expect(item).not.toMatch(/commandFromItemScript|stateFromItemScript|sendCommand/);
  });
});
