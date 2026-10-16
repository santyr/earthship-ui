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
    bindingVersion: '5.2.3', timezone: 'America/Denver', geolocation: '38.3739919,-105.7744609',
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


describe('Astro binding provenance', () => {
  it.each(['5.2.3', '5.2.4', '5.3.0', '5.10.0', '6.0.0', '10.0.0'])('records actual supported binding %s', version => {
    const api = adapter(); api.bindingVersion = version;
    expect(JSON.parse(buildContext(api)).calculationVersion).toBe('openhab-astro-' + version);
  });
  it.each(['5.2.1', '5.2.2', '5.1.99', '4.99.99', '05.2.3', '2147483648.0.0', '5.2.3-SNAPSHOT', undefined])('refuses unsupported binding %s', version => {
    const api = adapter(); api.bindingVersion = version;
    expect(() => buildContext(api)).toThrow();
  });
});

function runPublisher({ online = true, actionsMissing = false, version = '5.2.3', missingMethod = false } = {}) {
  const warnings = [], updates = [], geometryHours = [];
  const base = Date.parse('2026-10-12T06:00:00Z');
  const instant = (index, hour) => new Date(base + index*86400000 + hour*3600000).toISOString();
  const date = index => ({ plusDays: n => date(index+n), toString: () => instant(index,0).slice(0,10),
    atTime: (hour,minute) => ({ atZone: () => ({ index, hour, minute, toInstant: () => instant(index,hour) }) }),
    atStartOfDay: () => ({ toInstant: () => instant(index,0) }) });
  const actions = {
    getEventTime: (phase, at) => ({ toInstant: () => instant(at.index, phase === 'SUN_RISE' ? 6.95 : phase === 'DAYLIGHT' ? 7 : 19) }),
    getElevation: at => { geometryHours.push(at.hour); return '40 °'; },
    getAzimuth: at => { geometryHours.push(at.hour); return '180 °'; },
    getTotalRadiation: at => { geometryHours.push(at.hour); return '700 W/m²'; },
  };
  if (missingMethod) delete actions.getElevation;
  const context = { console:{ warn:value => warnings.push(value) } };
  vm.runInNewContext(source,context);
  context.require = () => ({
    things:{ getThing: () => ({ status:online ? 'ONLINE' : 'OFFLINE', rawThing:{ getConfiguration: () => ({ get: () => '38.3739919,-105.7744609' }) } }) },
    items:{ getItem: () => ({ postUpdate:value => updates.push(value) }) },
    actions:{ get: () => actionsMissing ? null : actions },
    osgi:{ getService: () => ({ getTimeZone: () => ({ getId: () => 'America/Denver' }) }) },
  });
  context.Java = { type:name => {
    if (name === 'org.osgi.framework.FrameworkUtil') return { getBundle: () => ({ getBundleContext: () => ({ getBundles: () => [{ getSymbolicName: () => 'org.openhab.binding.astro', getVersion: () => version }] }) }) };
    if (name === 'java.time.ZonedDateTime') return { now: () => ({ toLocalDate: () => date(0), toInstant: () => instant(0,10) }) };
    return {};
  } };
  context.publish();
  return { warnings, updates, geometryHours };
}

describe('native publisher availability and civil noon', () => {
  it.each([
    [{ online:false },'source_offline'],
    [{ actionsMissing:true },'actions_missing'],
    [{ version:'5.2.2' },'binding_unsupported'],
    [{ missingMethod:true },'actions_incomplete'],
  ])('withholds incomplete native context with a bounded reason', (options,reason) => {
    const result = runPublisher(options);
    expect(result.updates).toHaveLength(0);
    expect(result.warnings[0]).toBe('Astro forecast context withheld: '+reason);
  });
  it('publishes exactly ten civil-noon geometry points after native recovery', () => {
    const result = runPublisher();
    expect(result.warnings).toHaveLength(0);
    expect(result.updates).toHaveLength(1);
    expect(result.geometryHours).toHaveLength(30);
    expect(result.geometryHours.every(hour => hour === 12)).toBe(true);
    expect(JSON.parse(result.updates[0]).calculationVersion).toBe('openhab-astro-5.2.3');
  });
});
