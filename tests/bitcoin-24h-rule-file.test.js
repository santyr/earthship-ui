import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../openhab/file-config/automation/js/bitcoin-24h-change.js', import.meta.url), 'utf8');

function runRule(current, prior) {
  let definition;
  const updates = [];
  const cutoff = Symbol('24 hours ago');
  const rawItem = {};
  const price = { rawItem, numericState: current };
  const output = { postUpdate: value => updates.push(value) };
  const persistedState = (item, at) => {
    expect(item).toBe(rawItem);
    expect(at).toBe(cutoff);
    return prior == null ? null : { getState: () => prior };
  };
  runInNewContext(source, {
    console: { info() {} },
    Java: { type(name) {
      if (name === 'java.time.ZonedDateTime') {
        return { now: () => ({ minusHours(hours) {
          expect(hours).toBe(24);
          return cutoff;
        } }) };
      }
      expect(name).toBe('org.openhab.core.persistence.extensions.PersistenceExtensions');
      return { persistedState };
    } },
    require(name) {
      expect(name).toBe('openhab');
      return {
        items: { getItem: item => item === 'BTC_USD_Price' ? price : output },
        rules: { JSRule: rule => { definition = rule; } },
        triggers: { ItemStateUpdateTrigger: item => ({ item }) },
      };
    },
  });
  definition.execute();
  return { definition, updates };
}

describe('staged file-backed Bitcoin 24-hour change writer', () => {
  it('retains the managed UID and every-update trigger', () => {
    const { definition } = runRule(100, 80);
    expect(definition.id).toBe('hex_btc_24h_change');
    expect(Array.from(definition.triggers)).toEqual([{ item: 'BTC_USD_Price' }]);
  });

  it('uses the held 24-hour persisted price to calculate the percent change', () => {
    expect(runRule(100, 80).updates).toEqual(['25']);
    expect(runRule(80, 100).updates).toEqual(['-20']);
  });

  it('preserves zero-prior behavior and withholds unavailable states', () => {
    expect(runRule(100, 0).updates).toEqual(['100']);
    expect(runRule(0, 0).updates).toEqual(['0']);
    expect(runRule(null, 100).updates).toEqual(['UNDEF']);
    expect(runRule(100, null).updates).toEqual(['UNDEF']);
    expect(runRule(100, 'UNDEF').updates).toEqual(['UNDEF']);
  });
});
