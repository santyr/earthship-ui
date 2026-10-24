import { SHADE_SLOTS } from './catalog.js';

export const SHADE_POLICY_ITEMS = Object.freeze({
  kitchen: 'Shade_Kitchen_RecommendationAutomation',
  living: 'Shade_LivingRoom_RecommendationAutomation',
  bathroom: 'Shade_Bathroom_RecommendationAutomation',
  bedroom: 'Shade_Bedroom_RecommendationAutomation',
});
export const SHADE_POLICY_REVISION_ITEM = 'Shade_RecommendationAutomationRevision';
export const SHADE_POLICY_SESSION_ITEM = 'Shade_RecommendationAutomationSession';
const labels = Object.freeze({
  policy_unavailable: 'Paused — policy unavailable',
  override_unavailable: 'Paused — override unavailable',
  automation_off: 'Manual only — automation off',
  nightly_override: 'Paused — nightly override',
  awaiting_commissioning: 'Enabled — awaiting commissioning',
  automation_not_released: 'Enabled — automation not released',
  eligible: 'Enabled — subject to current advice and safety checks',
});
const switchState = (value) => value === 'ON' || value === 'OFF' ? value : null;

// This is the sole policy evaluator. Boolean last-change age is deliberately
// irrelevant: a current successful source read can confirm an all-night ON.
export function evaluateShadePolicy(input = {}, inventory = SHADE_SLOTS) {
  const zones = Object.fromEntries(Object.entries(SHADE_POLICY_ITEMS).map(([zone, policyItem]) => {
    const saved = input.connected === true && input.confirmed?.[zone] === true
      ? switchState(input.preferences?.[zone]) : null;
    const authoritative = saved !== null;
    const privateZone = zone === 'bathroom' || zone === 'bedroom';
    const nightKnown = input.overrideAuthoritative === true && switchState(input.override) !== null;
    let status = 'policy_unavailable';
    if (saved === 'OFF') status = 'automation_off';
    else if (saved === 'ON') {
      if (privateZone && !nightKnown) status = 'override_unavailable';
      else if (privateZone && input.override === 'ON') status = 'nightly_override';
      else if (input.commissioned !== true) status = 'awaiting_commissioning';
      else if (input.globalReleased !== true) status = 'automation_not_released';
      else status = 'eligible';
    }
    const eligible = ['awaiting_commissioning', 'automation_not_released', 'eligible'].includes(status);
    return [zone, { policyItem, saved, authoritative, eligible, status, label: labels[status],
      // Policy eligibility is distinct from complete execution authorization.
      adviceMode: status === 'eligible' ? 'conditional' : 'manual_only',
      members: inventory.filter((slot) => slot.room === zone).map((slot) => slot.number) }];
  }));
  return { schemaVersion: 1, sessionId: input.sessionId, generation: input.generation,
    sourceGeneration: input.sourceGeneration ?? null, connected: input.connected === true,
    commissioned: input.commissioned === true, globalReleased: input.globalReleased === true,
    override: { state: input.overrideAuthoritative === true ? switchState(input.override) : null,
      authoritative: input.connected === true && input.overrideAuthoritative === true && switchState(input.override) !== null }, zones };
}

export function shadeAdviceMetadata(snapshot) {
  return { policyBinding: { sessionId: snapshot.sessionId, generation: snapshot.generation,
    sourceGeneration: snapshot.sourceGeneration },
  zones: Object.fromEntries(Object.entries(snapshot.zones).map(([zone, value]) => [zone,
    { adviceMode: value.adviceMode, automationEligible: value.eligible, reason: value.status }])),
  executionAvailable: snapshot.connected === true && snapshot.commissioned === true
    && snapshot.globalReleased === true && Object.values(snapshot.zones).some((zone) => zone.status === 'eligible') };
}
const copy = (value) => structuredClone(value);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const binding = (policy) => ({ sessionId: policy.sessionId, generation: policy.generation, sourceGeneration: policy.sourceGeneration });
const mapped = (slot) => slot.positionItem && slot.availabilityItem && slot.stateItem;

// Executable CONTRACT HARNESS for a future commissioned owner, not a scheduler
// or device owner. No network, manual path, callback dispatch, timers or STOP.
// Real admission MUST share its serialization boundary with policy inhibition;
// copying this check in front of an unrelated motor dispatcher is insufficient.
export function createShadeAdmissionHarness({ inventory = SHADE_SLOTS, current, recomputeEffects } = {}) {
  let serial = Promise.resolve();
  let nextId = 0;
  const queue = new Map();
  const serialize = (operation) => {
    const result = serial.then(operation);
    serial = result.catch(() => {});
    return result;
  };
  const fingerprint = (state) => ({ policy: binding(state.policy), positions: state.positions,
    forecastRevision: state.forecastRevision, observationGeneration: state.observationGeneration,
    devices: state.devices, manualHoldsClear: state.manualHoldsClear, safetyChecksPass: state.safetyChecksPass,
    inventory: inventory.map(({ number, room, positionItem, availabilityItem, stateItem }) =>
      ({ number, room, positionItem, availabilityItem, stateItem })) });
  const reject = (reason) => ({ status: 'rejected', reason, deviceCommands: 0 });
  function prepare(recommendation, state) {
    const evaluated = evaluateShadePolicy(state.policy, inventory);
    if (recommendation?.source !== undefined || !recommendation?.id
        || !same(recommendation.policyBinding, binding(state.policy))) return reject('policy_changed');
    if (recommendation.forecastRevision !== state.forecastRevision
        || recommendation.observationGeneration !== state.observationGeneration) return reject('source_changed');
    if (!state.policy.globalReleased || !state.policy.commissioned) return reject('execution_not_released');
    if (state.manualHoldsClear !== true || state.safetyChecksPass !== true) return reject('owner_checks_failed');
    if (!Array.isArray(recommendation.members) || !recommendation.members.length
        || new Set(recommendation.members.map((member) => member.slot)).size !== recommendation.members.length) return reject('invalid_members');
    const members = [], excluded = [];
    const positions = copy(state.positions ?? {});
    for (const member of recommendation.members) {
      const slot = inventory.find((candidate) => candidate.number === member.slot);
      const zone = evaluated.zones[slot?.room];
      let reason = !zone?.eligible ? zone?.status ?? 'unknown_member' : null;
      if (!reason && !mapped(slot)) reason = 'unmapped';
      if (!reason && (state.devices?.[member.slot]?.available !== true || state.devices?.[member.slot]?.reportFresh !== true)) reason = 'device_unavailable';
      if (!reason && (!Number.isFinite(positions[member.slot]) || positions[member.slot] < 0 || positions[member.slot] > 100)) reason = 'observation_unavailable';
      if (!Number.isInteger(member.targetPosition) || member.targetPosition < 0 || member.targetPosition > 100) return reject('invalid_target');
      if (reason) excluded.push({ slot: member.slot, reason });
      else { members.push(copy(member)); positions[member.slot] = member.targetPosition; }
    }
    if (!members.length) return reject('no_eligible_members');
    // Never reuse full-batch effects for a smaller admitted subset.
    if (typeof recomputeEffects !== 'function') return reject('effects_recompute_required');
    const effects = recomputeEffects(positions, copy(members), copy(recommendation));
    if (!effects || typeof effects !== 'object' || effects.then) return reject('effects_recompute_required');
    return { members, excluded, effects: copy(effects) };
  }
  return {
    admit: (recommendation) => serialize(() => {
      const state = copy(current());
      const result = prepare(recommendation, state);
      if (result.status) return result;
      const record = { id: `shade-mock-${++nextId}`, status: 'queued_mock', ...result,
        originalRecommendation: copy(recommendation), bound: copy(fingerprint(state)), deviceCommands: 0 };
      queue.set(record.id, record);
      return copy(record);
    }),
    inhibit: (commit) => serialize(async () => {
      await commit();
      const now = fingerprint(current());
      for (const [id, record] of queue) {
        if (record.status === 'queued_mock' && !same(record.bound, now)) {
          queue.set(id, { ...record, status: 'invalidated', reason: 'policy_changed' });
        }
      }
      return { status: 'inhibition_committed', deviceCommands: 0, inFlight: 'No commissioned owner; STOP unsupported' };
    }),
    finalize: (id) => serialize(() => {
      const record = queue.get(id);
      if (!record) return reject('unknown_request');
      if (record.status !== 'queued_mock') return copy(record);
      const state = copy(current());
      const result = prepare(record.originalRecommendation, state);
      const changed = !same(record.bound, fingerprint(state));
      const next = changed || result.status
        ? { ...record, status: 'invalidated', reason: result.reason ?? 'source_changed' }
        : { ...record, ...result, status: 'mock_admitted' };
      queue.set(id, next);
      return copy(next);
    }),
  };
}
