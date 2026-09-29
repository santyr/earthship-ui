import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../openhab/file-config/automation/js/temperature-highlow-24h.js', import.meta.url), 'utf8');
const INDOOR = 'AmbientWeatherWS2902A_IndoorSensor_Temperature';
const OUTDOOR = 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature';

function runRule(history = {}) {
  let definition;
  const updates = [];
  const warnings = [];
  const errors = [];
  const since = Symbol('24-hour cutoff');
  const items = {
    getItem(name) {
      return { name, postUpdate: value => updates.push([name, value]) };
    },
  };
  const persistence = {
    minimumSince(item, cutoff) {
      expect(cutoff).toBe(since);
      const value = history[item.name]?.min;
      return value == null ? null : { getState: () => value };
    },
    maximumSince(item, cutoff) {
      expect(cutoff).toBe(since);
      const value = history[item.name]?.max;
      return value == null ? null : { getState: () => value };
    },
  };
  runInNewContext(source, {
    Java: {
      type(name) {
        if (name === 'java.time.ZonedDateTime') {
          return { now: () => ({ minusHours: hours => {
            expect(hours).toBe(24);
            return since;
          } }) };
        }
        expect(name).toBe('org.openhab.core.persistence.extensions.PersistenceExtensions');
        return persistence;
      },
    },
    console: { warn: text => warnings.push(text), error: text => errors.push(text), info() {} },
    require(name) {
      expect(name).toBe('openhab');
      return {
        items,
        rules: { JSRule: rule => { definition = rule; } },
        triggers: { GenericCronTrigger: expression => ({ expression }) },
      };
    },
  });
  definition.execute();
  return { definition, updates, warnings, errors };
}

describe('staged file-backed 24-hour extrema writer', () => {
  it('preserves its UID and 15-minute cron', () => {
    const { definition } = runRule();
    expect(definition.id).toBe('temp-highlow-24h');
    expect(Array.from(definition.triggers)).toEqual([{ expression: '0 0/15 * * * ?' }]);
  });

  it('posts the four extrema from the same 24-hour persistence window', () => {
    const { updates, errors } = runRule({
      [INDOOR]: { min: '66 °F', max: '78 °F' },
      [OUTDOOR]: { min: '40 °F', max: '83 °F' },
    });
    expect(updates).toEqual([
      ['IndoorTemp_24h_Low', '66 °F'], ['IndoorTemp_24h_High', '78 °F'],
      ['OutdoorTemp_24h_Low', '40 °F'], ['OutdoorTemp_24h_High', '83 °F'],
    ]);
    expect(errors).toEqual([]);
  });

  it('withholds a source lacking persistence without suppressing the other', () => {
    const { updates, warnings } = runRule({ [OUTDOOR]: { min: '40 °F', max: '83 °F' } });
    expect(updates).toEqual([
      ['OutdoorTemp_24h_Low', '40 °F'], ['OutdoorTemp_24h_High', '83 °F'],
    ]);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain(INDOOR);
  });
});
