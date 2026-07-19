import { readFile } from 'node:fs/promises';
import { beforeAll, describe, expect, it } from 'vitest';
import {
  SUBSET_VERSION_TOKENS,
  getSubset,
  buildSubsetRuleDto,
  buildSubsetApplyPlan,
  buildSubsetRollbackPlan,
  buildRetirementPlan,
  buildRetirementRollback,
  expectedPersistenceCoverage,
  graphImmutableUids,
  ruleHash,
  assertUnchangedGraphHashes,
} from '../../scripts/openhab-config.mjs';

const MANIFEST_URL = new URL('../../openhab/managed-resources.json', import.meta.url);
const ROOT = new URL('../../', import.meta.url);

let manifest;
let sources;

beforeAll(async () => {
  manifest = JSON.parse(await readFile(MANIFEST_URL, 'utf8'));
  const entries = await Promise.all(
    Object.values(manifest.subsets).map(async (subset) => [
      subset.rule.uid,
      await readFile(new URL(subset.rule.source, ROOT), 'utf8'),
    ]),
  );
  sources = Object.fromEntries(entries);
});

function sourceFor(subsetName) {
  return sources[manifest.subsets[subsetName].rule.uid];
}

// --- I4: registered script MIME type ---------------------------------------

describe('I4 rule action content type', () => {
  it('declares only application/javascript for every subset rule', () => {
    for (const subset of Object.values(manifest.subsets)) {
      expect(subset.rule.action.configuration.type).toBe('application/javascript');
    }
  });
});

// --- I5: manifest-driven subset planning -----------------------------------

describe('buildSubsetRuleDto', () => {
  it('embeds the versioned source into a replace-in-place DTO for greywater', () => {
    const subset = getSubset(manifest, 'greywater');
    const dto = buildSubsetRuleDto({
      subset, subsetName: 'greywater', source: sourceFor('greywater'), originalRule: { tags: ['keep'] },
    });
    expect(dto.uid).toBe('hex_southoutlet_cycle');
    expect(dto.tags).toEqual(['keep']);
    expect(dto.triggers).toEqual(subset.rule.triggers);
    expect(dto.actions[0].configuration.script).toBe(sourceFor('greywater'));
    expect(dto.actions[0].configuration.type).toBe('application/javascript');
  });

  it('builds a create DTO for the new night-load rule with defaults', () => {
    const subset = getSubset(manifest, 'night-load');
    const dto = buildSubsetRuleDto({ subset, subsetName: 'night-load', source: sourceFor('night-load') });
    expect(dto.uid).toBe('hex_night_load_override');
    expect(dto.tags).toEqual([]);
    expect(dto.visibility).toBe('VISIBLE');
  });

  it('rejects a source missing the subset version token', () => {
    const subset = getSubset(manifest, 'greywater');
    expect(() => buildSubsetRuleDto({
      subset, subsetName: 'greywater', source: '// no token here',
    })).toThrow(/versioned greywater owner source/);
  });

  it('maps each subset to its version token, present in its source', () => {
    for (const [subsetName, token] of Object.entries(SUBSET_VERSION_TOKENS)) {
      expect(sourceFor(subsetName)).toContain(token);
    }
  });
});

describe('buildSubsetApplyPlan — greywater (replace-in-place)', () => {
  let plan;
  beforeAll(() => {
    plan = buildSubsetApplyPlan({
      manifest,
      subsetName: 'greywater',
      source: sourceFor('greywater'),
      original: { rule: { uid: 'hex_southoutlet_cycle', tags: [] } },
    });
  });

  it('disables the target rule before mutating and never DELETEs anything', () => {
    expect(plan[0]).toMatchObject({
      method: 'POST', path: '/rest/rules/hex_southoutlet_cycle/enable', body: 'false', kind: 'disable-target',
    });
    expect(plan.some((op) => op.method === 'DELETE')).toBe(false);
  });

  it('creates the String and DateTime items and both metadata namespaces', () => {
    const itemPuts = plan.filter((op) => op.kind === 'item');
    expect(itemPuts.map((op) => op.body.type)).toEqual(
      expect.arrayContaining(['String', 'DateTime']),
    );
    const metaPaths = plan.filter((op) => op.kind === 'metadata').map((op) => op.path);
    expect(metaPaths).toEqual(expect.arrayContaining([
      '/rest/items/SouthOutlet_ManualRequest/metadata/autoupdate',
      '/rest/items/SouthOutlet_Outlet2_Switch/metadata/expire',
    ]));
    const expire = plan.find((op) => op.path.endsWith('/metadata/expire'));
    expect(expire.body.value).toBe('10m,command=OFF');
  });

  it('ends with a rule-replace PUT carrying the versioned script', () => {
    const last = plan.at(-1);
    expect(last).toMatchObject({ method: 'PUT', path: '/rest/rules/hex_southoutlet_cycle', kind: 'rule-replace' });
    expect(last.body.actions[0].configuration.script).toContain('EARTHSHIP_SOUTHOUTLET_VERSION');
  });
});

describe('buildSubsetApplyPlan — night-load (create + retirement)', () => {
  let plan;
  beforeAll(() => {
    plan = buildSubsetApplyPlan({
      manifest, subsetName: 'night-load', source: sourceFor('night-load'), original: {},
    });
  });

  it('retires the three duplicate child rules by DISABLE, never DELETE', () => {
    const retire = plan.filter((op) => op.kind === 'retire-disable');
    expect(retire.map((op) => op.uid)).toEqual(['ab8a59e1da', '4e234eabea', 'e647476610']);
    for (const op of retire) {
      expect(op).toMatchObject({ method: 'POST', body: 'false' });
      expect(op.path).toMatch(/\/enable$/);
    }
    expect(plan.some((op) => op.method === 'DELETE')).toBe(false);
  });

  it('creates (not replaces) the new owner rule and does not pre-disable it', () => {
    expect(plan.some((op) => op.kind === 'disable-target')).toBe(false);
    const last = plan.at(-1);
    expect(last).toMatchObject({ method: 'PUT', path: '/rest/rules/hex_night_load_override', kind: 'rule-create' });
  });

  it('leaves schedules and coupling rules entirely out of the plan', () => {
    const untouched = graphImmutableUids(getSubset(manifest, 'night-load'));
    expect(untouched).toEqual(expect.arrayContaining(['3e8f265498', 'GoatCamOff', '1f692c798b', 'b1501047a9']));
    for (const uid of untouched) {
      expect(plan.some((op) => op.path.includes(uid))).toBe(false);
    }
  });
});

describe('buildSubsetRollbackPlan', () => {
  it('restores a replaced greywater rule and deletes items with no captured original', () => {
    const plan = buildSubsetRollbackPlan({
      manifest,
      subsetName: 'greywater',
      original: { rule: { uid: 'hex_southoutlet_cycle', tags: [] }, items: {}, metadata: {} },
    });
    expect(plan[0]).toMatchObject({ method: 'POST', path: '/rest/rules/hex_southoutlet_cycle/enable', body: 'false' });
    expect(plan[1]).toMatchObject({ method: 'PUT', path: '/rest/rules/hex_southoutlet_cycle', kind: 'rule-restore' });
    // No captured items/metadata -> DELETE them (undo the creation).
    expect(plan.some((op) => op.kind === 'item-delete' && op.path === '/rest/items/SouthOutlet_LastCycleStart')).toBe(true);
    expect(plan.some((op) => op.kind === 'metadata-delete')).toBe(true);
  });

  it('deletes a newly-created night-load rule and re-enables the retired child rules', () => {
    const plan = buildSubsetRollbackPlan({ manifest, subsetName: 'night-load', original: {} });
    expect(plan.some((op) => op.kind === 'rule-delete' && op.path === '/rest/rules/hex_night_load_override')).toBe(true);
    const reversed = plan.filter((op) => op.kind === 'retire-reverse');
    expect(reversed.map((op) => op.uid)).toEqual(['ab8a59e1da', '4e234eabea', 'e647476610']);
    for (const op of reversed) expect(op).toMatchObject({ method: 'POST', body: 'true' });
  });

  it('honours a receipt-bound backup that a retired rule was already disabled', () => {
    const subset = getSubset(manifest, 'night-load');
    const rollback = buildRetirementRollback(subset, { ab8a59e1da: { enabled: false } });
    expect(rollback.find((op) => op.uid === 'ab8a59e1da').body).toBe('false');
    expect(rollback.find((op) => op.uid === '4e234eabea').body).toBe('true');
  });
});

describe('retirement plan', () => {
  it('is empty for subsets without a graph (feeder, greywater)', () => {
    expect(buildRetirementPlan(getSubset(manifest, 'feeder'))).toEqual([]);
    expect(buildRetirementPlan(getSubset(manifest, 'greywater'))).toEqual([]);
  });
});

describe('persistence coverage + untouched-graph hashes', () => {
  it('reports the declared JDBC coverage for a subset', () => {
    expect(expectedPersistenceCoverage(getSubset(manifest, 'greywater'))).toEqual({
      serviceId: 'jdbc',
      strategy: 'everyChange',
      restoreOnStartup: true,
      items: [
        'SouthOutlet_ManualRequest',
        'SouthOutlet_ManualResult',
        'SouthOutlet_LastCycleStart',
        'SouthOutlet_LastCycle',
      ],
    });
  });

  it('passes when every untouched schedule/coupling hash is unchanged, fails on drift', () => {
    const subset = getSubset(manifest, 'night-load');
    const uids = graphImmutableUids(subset);
    const before = Object.fromEntries(uids.map((uid) => [uid, ruleHash({ uid, actions: [] })]));
    expect(assertUnchangedGraphHashes(subset, before, before)).toEqual({ ok: true, reasons: [] });

    const drifted = { ...before, GoatCamOff: ruleHash({ uid: 'GoatCamOff', actions: [{ id: 'changed' }] }) };
    const result = assertUnchangedGraphHashes(subset, before, drifted);
    expect(result.ok).toBe(false);
    expect(result.reasons).toEqual([expect.stringMatching(/GoatCamOff was modified/)]);
  });

  it('fails when a captured hash for an untouched rule is missing', () => {
    const subset = getSubset(manifest, 'night-load');
    const result = assertUnchangedGraphHashes(subset, {}, {});
    expect(result.ok).toBe(false);
    expect(result.reasons.length).toBe(graphImmutableUids(subset).length);
  });
});
