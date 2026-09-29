import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../openhab/file-config/automation/js/update_days_until_season.js', import.meta.url), 'utf8');

function loadRule(timeLeft, season) {
  let definition;
  const updates = [];
  const states = { Sun_TimeLeft: timeLeft, Sun_NextSeason: season };
  const items = {
    getItem(name) {
      if (name === 'DaysUntilNextSeason') return { postUpdate: value => updates.push(value) };
      if (!(name in states)) throw new Error(`unexpected Item ${name}`);
      return { state: { toString: () => states[name] } };
    },
  };
  runInNewContext(source, {
    require(name) {
      expect(name).toBe('openhab');
      return {
        items,
        rules: { JSRule: rule => { definition = rule; } },
        triggers: { ItemStateChangeTrigger: name => ({ type: 'change', name }) },
      };
    },
  });
  return { definition, updates };
}

describe('staged file-backed season countdown rule', () => {
  it('preserves the managed rule identity and sole state-change trigger', () => {
    const { definition } = loadRule('172800 s', 'SPRING');
    expect(definition.id).toBe('update_days_until_season');
    expect(definition.name).toBe('Update Days Until Next Season');
    expect(definition.description).toBe('Updates the season countdown display');
    expect(Array.from(definition.triggers)).toEqual([{ type: 'change', name: 'Sun_TimeLeft' }]);
  });

  it.each([
    ['172800 s', 'SPRING', '2 days until Spring 🌱'],
    ['86399 s', 'SUMMER', '0 days until Summer ☀️'],
    ['259200 s', 'AUTUMN', '3 days until Autumn 🍂'],
    ['0 s', 'WINTER', '0 days until Winter ❄️'],
  ])('posts only the same countdown for %s and %s', (timeLeft, season, expected) => {
    const { definition, updates } = loadRule(timeLeft, season);
    definition.execute();
    expect(updates).toEqual([expected]);
  });
});
