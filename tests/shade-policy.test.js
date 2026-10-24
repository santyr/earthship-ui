import { describe, expect, it } from 'vitest';
import { evaluateShadePolicy, createShadeAdmissionHarness, shadeAdviceMetadata } from '../src/lib/shades/policyModel.js';

const preferences = { kitchen: 'ON', living: 'ON', bathroom: 'ON', bedroom: 'ON' };
const policy = (patch = {}) => ({ sessionId: 'session-1', generation: 1, sourceGeneration: 'source-1',
  connected: true, preferences, confirmed: Object.fromEntries(Object.keys(preferences).map((zone) => [zone, true])),
  override: 'OFF', overrideAuthoritative: true, globalReleased: false, commissioned: false, ...patch });
const inventory = [
  { number: 1, room: 'kitchen', positionItem: 'K_Position', availabilityItem: 'K_Available', stateItem: 'K_Report' },
  { number: 18, room: 'bathroom', positionItem: 'B_Position', availabilityItem: 'B_Available', stateItem: 'B_Report' },
  { number: 22, room: 'bedroom', positionItem: null, availabilityItem: null, stateItem: null },
];
const source = () => ({ policy: policy({ globalReleased: true, commissioned: true }),
  forecastRevision: 'forecast-1', observationGeneration: 'observation-1', positions: { 1: 40, 18: 70, 22: 20 },
  devices: { 1: { available: true, reportFresh: true }, 18: { available: true, reportFresh: true } },
  manualHoldsClear: true, safetyChecksPass: true });
const recommendation = { id: 'advice-1', policyBinding: { sessionId: 'session-1', generation: 1, sourceGeneration: 'source-1' }, forecastRevision: 'forecast-1', observationGeneration: 'observation-1',
  members: [{ slot: 1, targetPosition: 20 }, { slot: 18, targetPosition: 10 }, { slot: 22, targetPosition: 0 }] };

describe('authoritative shade recommendation policy', () => {
  it('blocks private zones throughout a stable or daytime ON override while preserving saved ON', () => {
    const result = evaluateShadePolicy(policy({ override: 'ON', lastChangedAt: 0 }), inventory);
    expect(result.zones.bathroom).toMatchObject({ saved: 'ON', eligible: false, status: 'nightly_override' });
    expect(result.zones.bedroom.status).toBe('nightly_override');
    expect(result.zones.kitchen).toMatchObject({ eligible: true, status: 'awaiting_commissioning' });
    expect(result.zones.living.eligible).toBe(true);
  });
  it.each([null, 'NULL', 'UNDEF', 'ON', 'OFF'])('requires reconciled authoritative override rather than %s receipt', (override) => {
    const result = evaluateShadePolicy(policy({ override, overrideAuthoritative: false }), inventory);
    expect(result.zones.bathroom.status).toBe('override_unavailable');
    expect(result.zones.bedroom.eligible).toBe(false);
    expect(result.zones.kitchen.eligible).toBe(true);
  });
  it('keeps restored OFF and unknown distinct, and reopening override never changes saved permission', () => {
    const result = evaluateShadePolicy(policy({ preferences: { ...preferences, kitchen: 'OFF', bedroom: null } }), inventory);
    expect(result.zones.kitchen).toMatchObject({ saved: 'OFF', status: 'automation_off', eligible: false });
    expect(result.zones.bedroom).toMatchObject({ saved: null, status: 'policy_unavailable', eligible: false });
    expect(evaluateShadePolicy(policy({ connected: false }), inventory).zones.kitchen.saved).toBe(null);
  });
  it('keeps disconnected advice manual-only and never advertises executable authority from release flags alone', () => {
    const evaluated = evaluateShadePolicy(policy({ connected: false, commissioned: true, globalReleased: true }));
    const metadata = shadeAdviceMetadata(evaluated);
    expect(metadata.executionAvailable).toBe(false);
    expect(Object.values(metadata.zones).every((zone) => zone.adviceMode === 'manual_only')).toBe(true);
  });
  it('does not turn a permission into commissioning or global execution authority', () => {
    expect(evaluateShadePolicy(policy(), inventory).zones.kitchen.status).toBe('awaiting_commissioning');
    expect(evaluateShadePolicy(policy({ commissioned: true }), inventory).zones.kitchen.status).toBe('automation_not_released');
    expect(evaluateShadePolicy(policy({ commissioned: true, globalReleased: true }), inventory).zones.kitchen.status).toBe('eligible');
  });
});

describe('non-actuating commissioned-owner admission contract', () => {
  it('expands actual members, filters protected/unmapped slots and recomputes effects with excluded positions unchanged', async () => {
    const current = source(); current.policy.override = 'ON';
    const owner = createShadeAdmissionHarness({ inventory, current: () => current, recomputeEffects: (positions) => ({ positions }) });
    const queued = await owner.admit(recommendation);
    expect(queued.status).toBe('queued_mock');
    expect(queued.members).toEqual([{ slot: 1, targetPosition: 20 }]);
    expect(queued.effects).toEqual({ positions: { 1: 20, 18: 70, 22: 20 } });
    expect(queued.originalRecommendation).toEqual(recommendation);
    expect(queued.excluded).toEqual([{ slot: 18, reason: 'nightly_override' }, { slot: 22, reason: 'nightly_override' }]);
    expect(await owner.finalize(queued.id)).toMatchObject({ status: 'mock_admitted', deviceCommands: 0 });
  });
  it('rejects earlier advice after inhibition, retains receipts and never revives ON OFF ON queued work', async () => {
    const current = source();
    const owner = createShadeAdmissionHarness({ inventory, current: () => current, recomputeEffects: (positions) => ({ positions }) });
    const queued = await owner.admit(recommendation);
    await owner.inhibit(() => { current.policy = policy({ generation: 2, sourceGeneration: 'source-2', preferences: { ...preferences, kitchen: 'OFF' } }); });
    await owner.inhibit(() => { current.policy = policy({ generation: 3, sourceGeneration: 'source-3', globalReleased: true, commissioned: true }); });
    expect(await owner.finalize(queued.id)).toMatchObject({ status: 'invalidated', reason: 'policy_changed', deviceCommands: 0 });
    expect(queued.status).toBe('queued_mock');
    expect(queued.originalRecommendation).toEqual(recommendation);
  });
  it('binds queued work to observations, forecast, actual membership and session identity', async () => {
    for (const alter of [
      (s) => { s.observationGeneration = 'manual-change'; },
      (s) => { s.forecastRevision = 'new-forecast'; },
      (s) => { s.positions[1] = 41; },
      (s) => { s.policy.sessionId = 'restarted'; },
      () => { inventory[0].room = 'bathroom'; },
    ]) {
      inventory[0].room = 'kitchen';
      const current = source();
      const owner = createShadeAdmissionHarness({ inventory, current: () => current, recomputeEffects: (positions) => ({ positions }) });
      const queued = await owner.admit(recommendation);
      alter(current);
      expect((await owner.finalize(queued.id)).status).toBe('invalidated');
    }
    inventory[0].room = 'kitchen';
  });
  it('has no manual source bypass or real dispatcher, and requires fresh effects after subset changes', async () => {
    const current = source(); current.policy.preferences = { ...preferences, kitchen: 'OFF' };
    const owner = createShadeAdmissionHarness({ inventory, current: () => current });
    expect(await owner.admit({ ...recommendation, source: 'manual' })).toMatchObject({ status: 'rejected', deviceCommands: 0 });
    expect(owner.dispatch).toBeUndefined();
    current.policy.preferences = preferences;
    expect(await owner.admit(recommendation)).toMatchObject({ status: 'rejected', reason: 'effects_recompute_required' });
  });
  it('excludes unhealthy or stale individual devices even when their last position is known', async () => {
    const current = source(); current.devices[1].available = false; current.devices[18].reportFresh = false;
    const owner = createShadeAdmissionHarness({ inventory, current: () => current, recomputeEffects: (positions) => ({ positions }) });
    expect(await owner.admit(recommendation)).toMatchObject({ status: 'rejected', reason: 'no_eligible_members' });
  });
  it('serializes inhibition before a later admission and does not invent STOP for physically running moves', async () => {
    const current = source();
    const owner = createShadeAdmissionHarness({ inventory, current: () => current, recomputeEffects: (positions) => ({ positions }) });
    const committed = owner.inhibit(() => { current.policy = policy({ generation: 2, sourceGeneration: 'source-2', preferences: { kitchen: 'OFF', living: 'OFF', bathroom: 'OFF', bedroom: 'OFF' } }); });
    const later = owner.admit(recommendation);
    await committed;
    expect(await later).toMatchObject({ status: 'rejected', deviceCommands: 0 });
    expect(owner.stop).toBeUndefined();
  });
});
