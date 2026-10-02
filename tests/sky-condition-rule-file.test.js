import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../openhab/file-config/automation/js/sky-condition-calculator.js', import.meta.url), 'utf8');
const NOW = Date.parse('2026-09-29T11:30:00Z');

function runRule(overrides = {}, missingItems = []) {
  const states = {
    Sun_SunPhaseName: 'DAY',
    Sun_TotalRadiation: '100 W/m²',
    AmbientWeatherWS2902A_SolarRadiation: '50 W/m²',
    WeatherData_HealthStatus: 'OK',
    WeatherData_WH65B_AgeSeconds: '30 s',
    SunPhaseIcon: 'iconify:mdi:weather-sunny',
    MoonPhaseicon: 'iconify:mdi:moon-waning-crescent',
    SkyCondition: 'CLEAR',
    SkyConditionIcon: 'iconify:mdi:weather-sunny',
    SkyCondition_LastEval: 'NULL',
    SkyCondition_Diagnostic: 'NULL',
    ...overrides,
  };
  const updates = [];
  let definition;
  class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : [NOW])); }
    static now() { return NOW; }
  }
  const items = {
    getItem(name) {
      if (!(name in states) || missingItems.includes(name)) throw new Error(`unexpected Item ${name}`);
      return {
        state: states[name],
        postUpdate(value) { updates.push([name, value]); states[name] = value; },
      };
    },
  };
  runInNewContext(source, {
    Date: FixedDate,
    console: { info() {}, debug() {} },
    require(name) {
      expect(name).toBe('openhab');
      return {
        items,
        rules: { JSRule(rule) { definition = rule; } },
        triggers: {
          ItemStateChangeTrigger: name => ({ type: 'change', name }),
          GenericCronTrigger: expression => ({ type: 'cron', expression }),
        },
      };
    },
  });
  definition.execute();
  return { definition, states, updates };
}

describe('staged file-backed sky-condition rule', () => {
  it('preserves the live UID, four Item-change triggers and two-minute timer', () => {
    const { definition } = runRule();
    expect(definition.id).toBe('sky-condition-calculator');
    expect(Array.from(definition.triggers)).toEqual([
      { type: 'change', name: 'Sun_SunPhaseName' },
      { type: 'change', name: 'Sun_TotalRadiation' },
      { type: 'change', name: 'AmbientWeatherWS2902A_SolarRadiation' },
      { type: 'change', name: 'WeatherData_HealthStatus' },
      { type: 'cron', expression: '0 0/2 * * * ?' },
    ]);
  });

  it('selects the partly-cloudy icon from a fresh radiation ratio', () => {
    const { states, updates } = runRule();
    expect(states.SkyCondition).toBe('PARTLY_CLOUDY');
    expect(states.SkyConditionIcon).toBe('iconify:bi:cloud-sun-fill');
    expect(updates.map(([name]) => name)).toEqual([
      'SkyCondition', 'SkyConditionIcon', 'SkyCondition_LastEval', 'SkyCondition_Diagnostic',
    ]);
  });

  it('uses a moon-phase icon at night even when weather is stale', () => {
    const { states } = runRule({ Sun_SunPhaseName: 'NIGHT', WeatherData_HealthStatus: 'STALE' });
    expect(states.SkyCondition).toBe('NIGHT');
    expect(states.SkyConditionIcon).toBe('iconify:mdi:moon-waning-crescent');
  });

  const moonFaultCases = ['DAY', 'NIGHT', 'UNKNOWN'].flatMap(phase =>
    ['0 W/m²', '50 W/m²', '100 W/m²'].flatMap(radiation =>
      ['OK', 'STALE'].flatMap(health =>
        ['iconify:mdi:moon-full', 'NULL', 'UNDEF', '', 'missing'].map(moon =>
          [phase, radiation, health, moon]))));

  it.each(moonFaultCases)('Moon input cannot alter control condition: %s / %s / %s / %s',
    (phase, radiation, health, moon) => {
      const inputs = {
        Sun_SunPhaseName: phase,
        AmbientWeatherWS2902A_SolarRadiation: radiation,
        WeatherData_HealthStatus: health,
      };
      const baseline = runRule(inputs);
      const result = runRule({ ...inputs, MoonPhaseicon: moon },
        moon === 'missing' ? ['MoonPhaseicon'] : []);
      expect(result.states.SkyCondition).toBe(baseline.states.SkyCondition);
      expect(result.updates.every(([name]) => [
        'SkyCondition', 'SkyConditionIcon', 'SkyCondition_LastEval', 'SkyCondition_Diagnostic',
      ].includes(name))).toBe(true);
      if (phase === 'NIGHT' && moon !== 'iconify:mdi:moon-full') {
        expect(result.states.SkyConditionIcon).toBe('iconify:mdi:weather-night');
      }
    });

  it('marks aged weather stale and accepts a fresh degraded station', () => {
    expect(runRule({ WeatherData_WH65B_AgeSeconds: '181 s' }).states.SkyCondition).toBe('STALE');
    expect(runRule({ WeatherData_HealthStatus: 'DEGRADED' }).states.SkyCondition).toBe('PARTLY_CLOUDY');
  });

  it('does not repost unchanged outputs or diagnostic values within 60 seconds', () => {
    const { updates } = runRule({
      SkyCondition: 'PARTLY_CLOUDY',
      SkyConditionIcon: 'iconify:bi:cloud-sun-fill',
      SkyCondition_LastEval: '2026-09-29T11:29:30.000Z',
      SkyCondition_Diagnostic: 'condition=PARTLY_CLOUDY,reason=ratio,weatherFresh=true',
    });
    expect(updates).toEqual([]);
  });
});
