import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../openhab/file-config/automation/js/astro-forecast-context.js', import.meta.url), 'utf8');
const sandbox = { module: { exports: {} } };
vm.runInNewContext(source, sandbox);
const { buildContext, quantity } = sandbox.module.exports;

function adapter() {
  const base = Date.parse('2026-09-30T06:00:00Z');
  const at = (index, hours) => new Date(base + index * 86400000 + hours * 3600000).toISOString();
  return {
    timezone: 'America/Denver', geolocation: '38.3739919,-105.7744609',
    recordedAt: at(0, 1), validUntil: at(1, 0),
    day: index => at(index, 0).slice(0, 10),
    event: (index, phase) => at(index, phase === 'SUN_RISE' ? 6.95 : phase === 'DAYLIGHT' ? 7 : 19),
    elevation: () => '50.0 °', azimuth: () => '180.0 °', radiation: () => '700.0 W/m²',
  };
}

describe('Astro observational solar-context exporter', () => {
  it('builds ten days and reuses adjacent sunrise calculations', () => {
    const api = adapter(); let rises = 0;
    const original = api.event;
    api.event = (index, phase, moment) => {
      if (phase === 'SUN_RISE') rises++;
      return original(index, phase, moment);
    };
    const raw = buildContext(api); const value = JSON.parse(raw);
    expect(value.days).toHaveLength(10);
    expect(rises).toBe(11);
    expect(value.days[0].daylightSeconds).toBe(43200);
    expect(value.days[0].nextSunriseAt).toBe(value.days[1].sunriseAt);
    expect(raw.length).toBeLessThan(16384);
  });
  it.each(['NaN °', ' °', '0.8 rad', 'Infinity °', '100.0 °'])(
    'refuses bad angular quantity %s', raw => expect(() => quantity(raw, '°', -90, 90)).toThrow());
  it('refuses invalid event ordering without publishing a partial context', () => {
    const api = adapter(); api.event = () => '2026-09-30T19:00:00Z';
    expect(() => buildContext(api)).toThrow();
  });
  it('has no actuator, network or notification call', () => {
    expect(source).not.toMatch(/sendCommand|executeCommandLine|fetch\(|sendNotification|nostr/);
    expect(source).toContain("GenericCronTrigger('0 10 0 * * ?')");
    expect(source).toContain('SystemStartlevelTrigger(100)');
  });
});
