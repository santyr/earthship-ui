import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';
import { isAllowedProxyRequest, PROXY_DIRECT_COMMAND_ITEMS } from '../../src/lib/openhab/proxyPolicy.js';

const MANIFEST_URL = new URL('../../openhab/managed-resources.json', import.meta.url);

const OWNER_ITEMS = [
  'OverrideSwitch',
  'Dish_Washer_Power',
  'ShurefloPump_Power',
  'Goat_Plugs_Outlet1_Switch',
];

// The three duplicate child rules that the consolidated owner replaces.
const RETIRED_RULE_UIDS = ['ab8a59e1da', '4e234eabea', 'e647476610'];
// The two Goat Cam <-> FeederOverride coupling rules that must be preserved.
const COUPLING_RULE_UIDS = ['3e8f265498', 'GoatCamOff'];
// The two schedules that command OverrideSwitch.
const SCHEDULE_RULE_UIDS = ['1f692c798b', 'b1501047a9'];

async function nightLoad() {
  const manifest = await readFile(MANIFEST_URL, 'utf8').then(JSON.parse);
  return manifest.subsets['night-load'];
}

describe('override graph consolidation', () => {
  it('retires the three duplicate child rules only inside the reversible graph transaction', async () => {
    const subset = await nightLoad();
    expect(subset.graph?.reversible).toBe(true);
    const retired = subset.graph?.retiredRules ?? [];
    expect(retired.map((r) => r.uid).sort()).toEqual([...RETIRED_RULE_UIDS].sort());
    // Every retirement is backed up and reversible so it happens only within
    // the graph transaction, never as a standalone deletion.
    for (const rule of retired) {
      expect(rule.backedUp).toBe(true);
      expect(rule.transactional).toBe(true);
    }
  });

  it('preserves the two coupling rules as protected, immutable read-only dependencies', async () => {
    const subset = await nightLoad();
    const coupling = subset.graph?.couplingDependencies ?? [];
    expect(coupling.map((c) => c.uid).sort()).toEqual([...COUPLING_RULE_UIDS].sort());
    for (const rule of coupling) {
      expect(rule.mutable).toBe(false);
      expect(rule.retired ?? false).toBe(false);
    }
    // The coupling rules are never present in the retirement list.
    const retiredUids = new Set((subset.graph?.retiredRules ?? []).map((r) => r.uid));
    for (const uid of COUPLING_RULE_UIDS) expect(retiredUids.has(uid)).toBe(false);
  });

  it('keeps the OverrideSwitch schedules as preserved dependencies of the owner', async () => {
    const subset = await nightLoad();
    const schedules = subset.graph?.schedules ?? [];
    expect(schedules.map((s) => s.uid).sort()).toEqual([...SCHEDULE_RULE_UIDS].sort());
    for (const schedule of schedules) {
      expect(schedule.commands).toBe('OverrideSwitch');
    }
  });

  it('lists the four actuator items as protected dependencies plus FeederOverride', async () => {
    const subset = await nightLoad();
    expect(subset.protectedDependencies).toEqual(expect.arrayContaining([
      ...OWNER_ITEMS, 'FeederOverride',
    ]));
  });
});

describe('rest-safety static scan: no browser write path to the owner actuators', () => {
  it('denies direct POST/PUT to all four owner-only items in every release mode', () => {
    for (const item of OWNER_ITEMS) {
      for (const mode of ['maintenance', 'safe-compat', 'full']) {
        expect(isAllowedProxyRequest('POST', `/rest/items/${item}`, mode)).toBe(false);
        expect(isAllowedProxyRequest('PUT', `/rest/items/${item}/state`, mode)).toBe(false);
      }
    }
  });

  it('excludes the four owner items from the direct-command allowlist entirely', () => {
    for (const item of OWNER_ITEMS) {
      expect(PROXY_DIRECT_COMMAND_ITEMS).not.toContain(item);
    }
  });

  it('exposes only the validated owner request channels — never the actuators — to the browser', () => {
    // Task 5 wires the correlated request client: the two owner request items
    // become POST-able so the browser can submit a request the owner rule
    // validates and serializes. The owner actuators (asserted above) and the
    // *_Result items stay closed in every release mode.
    for (const item of ['NightLoadOverride_Request', 'NightLoadDevice_Request']) {
      expect(isAllowedProxyRequest('POST', `/rest/items/${item}`, 'safe-compat')).toBe(true);
      expect(isAllowedProxyRequest('POST', `/rest/items/${item}`, 'full')).toBe(true);
      expect(isAllowedProxyRequest('POST', `/rest/items/${item}`, 'maintenance')).toBe(false);
    }
    for (const item of ['NightLoadOverride_Result', 'NightLoadDevice_Result']) {
      expect(isAllowedProxyRequest('POST', `/rest/items/${item}`, 'full')).toBe(false);
    }
  });
});
