import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';
import { SHADE_POLICY_ITEMS, SHADE_POLICY_REVISION_ITEM, SHADE_POLICY_SESSION_ITEM } from '../../src/lib/shades/policyModel.js';

const rulePath = new URL('../../openhab/file-config/automation/js/shade-recommendation-policy.js', import.meta.url);
function fixture(initial = {}, persisted = {}) {
  let clock = 10_000, generation = 0, rule, failPersistence = false;
  const states = { ...Object.fromEntries(Object.values(SHADE_POLICY_ITEMS).map((name) => [name, 'NULL'])), OverrideSwitch: 'OFF', ...initial };
  const history = Object.fromEntries(Object.entries(persisted).map(([name, state]) => [name, { state, at: clock - 100 }]));
  const updates = [], commands = [], locks = [];
  const item = (name) => ({ get state() { return states[name]; }, postUpdate: (state) => { states[name] = state; updates.push({ name, state }); },
    sendCommand: (command) => { commands.push({ name, command }); }, persistence: {
      persist: () => { if (!failPersistence) history[name] = { state: states[name], at: clock }; },
      previousState: () => history[name] ? { state: history[name].state, timestamp: { toInstant: () => ({ toEpochMilli: () => history[name].at }) } } : null,
    } });
  const shared = new Map();
  const context = { console, Date: { now: () => clock }, require: () => ({ items: { getItem: item },
    cache: { shared: { get: (key, create) => { if (!shared.has(key)) shared.set(key, create()); return shared.get(key); } } },
    rules: { JSRule: (definition) => { rule = definition; } },
    triggers: { ItemStateChangeTrigger: (name) => ({ kind: 'change', name }), SystemStartlevelTrigger: (level) => ({ kind: 'start', level }) } }),
    Java: { type: (name) => name === 'java.util.UUID' ? { randomUUID: () => `00000000-0000-4000-8000-${String(++generation).padStart(12, '0')}` }
      : name === 'java.lang.Thread' ? { sleep: (ms) => { clock += ms; } }
        : class { lock() { locks.push('lock'); } unlock() { locks.push('unlock'); } } },
  };
  vm.runInNewContext(readFileSync(rulePath, 'utf8'), context);
  return { states, history, commands, updates, locks, rule: () => rule,
    run: (event = { type: 'SystemStartlevelEvent' }) => rule.execute(event),
    failPersistence: () => { failPersistence = true; },
    receipt: () => JSON.parse(states[SHADE_POLICY_REVISION_ITEM]) };
}

describe('prepared OpenHAB shade policy owner', () => {
  it('defaults only fresh preferences OFF after restoration and persists a unique receipt without moving any device', () => {
    const f = fixture();
    f.run({ itemName: 'OverrideSwitch' });
    expect(f.states[SHADE_POLICY_REVISION_ITEM]).toBeUndefined();
    f.run();
    expect(Object.values(SHADE_POLICY_ITEMS).map((name) => f.states[name])).toEqual(['OFF', 'OFF', 'OFF', 'OFF']);
    expect(f.receipt()).toMatchObject({ durable: true, preferences: { kitchen: 'OFF', living: 'OFF', bathroom: 'OFF', bedroom: 'OFF' }, override: 'OFF' });
    expect(f.history[SHADE_POLICY_REVISION_ITEM].state).toBe(f.states[SHADE_POLICY_REVISION_ITEM]);
    expect(f.commands).toHaveLength(0);
    expect(f.updates.every(({ name }) => name !== 'OverrideSwitch')).toBe(true);
  });
  it('does not restore readiness from a previous runtime and binds ready marker to current receipt', () => {
    const f = fixture({ [SHADE_POLICY_SESSION_ITEM]: 'old-session' });
    expect(f.states[SHADE_POLICY_SESSION_ITEM]).toBe('UNDEF');
    f.run();
    expect(f.states[SHADE_POLICY_SESSION_ITEM]).toBe(f.receipt().ownerSession);
    expect(f.receipt().ownerSession).not.toBe('old-session');
  });
  it('preserves saved ON and OFF through restart and does not reset the choice when override changes', () => {
    const f = fixture({}, { [SHADE_POLICY_ITEMS.kitchen]: 'ON', [SHADE_POLICY_ITEMS.bathroom]: 'OFF' });
    f.run();
    expect(f.states[SHADE_POLICY_ITEMS.kitchen]).toBe('ON');
    expect(f.states[SHADE_POLICY_ITEMS.bathroom]).toBe('OFF');
    const first = f.receipt().generation;
    f.states.OverrideSwitch = 'ON'; f.run({ itemName: 'OverrideSwitch' });
    expect(f.receipt().generation).not.toBe(first);
    expect(f.receipt().preferences.kitchen).toBe('ON');
    expect(f.receipt().preferences.bathroom).toBe('OFF');
    expect(f.commands).toHaveLength(0);
  });
  it('advances UUID on every private permission transition including unseen ON OFF ON and serializes all receipts', () => {
    const f = fixture(); f.run();
    const seen = [f.receipt().generation];
    for (const state of ['ON', 'OFF', 'ON']) {
      f.states[SHADE_POLICY_ITEMS.bedroom] = state; f.run({ itemName: SHADE_POLICY_ITEMS.bedroom });
      seen.push(f.receipt().generation);
    }
    expect(new Set(seen).size).toBe(4);
    expect(f.locks).toEqual(Array(4).fill(['lock', 'unlock']).flat());
  });
  it('never publishes durable authority if persistence fails, even when an older persisted value matches', () => {
    const f = fixture(); f.run(); f.failPersistence();
    f.run({ itemName: 'OverrideSwitch' });
    expect(f.receipt().durable).toBe(false);
    expect(f.commands).toHaveLength(0);
  });
  it('declares only four policy Switches plus a revision and non-restored session and leaves wildcard JDBC semantics intact', () => {
    const source = readFileSync(new URL('../../openhab/file-config/items/shade-recommendation-policy.items', import.meta.url), 'utf8');
    for (const name of Object.values(SHADE_POLICY_ITEMS)) expect(source).toContain(`Switch ${name} `);
    expect(source).toContain(`String ${SHADE_POLICY_REVISION_ITEM} `);
    expect(source).toContain(`String ${SHADE_POLICY_SESSION_ITEM} `);
    expect(source).not.toMatch(/Rollershutter|Switch OverrideSwitch/);
    const ownership = JSON.parse(readFileSync(new URL('../../openhab/file-config/ownership.json', import.meta.url), 'utf8'));
    for (const name of [...Object.values(SHADE_POLICY_ITEMS), SHADE_POLICY_REVISION_ITEM, SHADE_POLICY_SESSION_ITEM]) {
      expect(ownership.resources.filter((entry) => entry.kind === 'item' && entry.id === name)).toMatchObject([{ provider: 'file', migration: 'prepared' }]);
    }
    const jdbc = readFileSync(new URL('../../openhab/file-config/persistence/jdbc.persist', import.meta.url), 'utf8');
    expect(jdbc).toContain('strategy = everyChange, restoreOnStartup');
    expect(jdbc).toContain(`!${SHADE_POLICY_SESSION_ITEM}`);
  });
});
