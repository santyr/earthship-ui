import { describe, expect, it } from 'vitest';
import { shadePolicyPresentation, validateShadePolicySnapshot } from '../../src/lib/shades/policy.js';

function snapshot() {
  return { schemaVersion: 1, generation: 7, sessionId: 'backend-session', connected: true,
    zones: Object.fromEntries(['kitchen', 'living', 'bathroom', 'bedroom'].map(zone => [zone, {
      saved: 'ON', authoritative: true, status: 'awaiting_commissioning', label: 'Enabled — awaiting commissioning',
    }])) };
}

describe('shade policy presentation never grants authority', () => {
  it('distinguishes confirmed ON, confirmed OFF and unknown without evaluating execution', () => {
    const state = snapshot();
    expect(shadePolicyPresentation(state, 'kitchen')).toMatchObject({ checked: true, savedLabel: 'Saved ON', label: 'Enabled — awaiting commissioning' });
    state.zones.kitchen = { saved: 'OFF', authoritative: true, status: 'automation_off', label: 'Manual only — automation off' };
    expect(shadePolicyPresentation(state, 'kitchen')).toMatchObject({ checked: false, savedLabel: 'Saved OFF', label: 'Manual only — automation off' });
    state.zones.kitchen.authoritative = false;
    expect(shadePolicyPresentation(state, 'kitchen')).toMatchObject({ checked: 'mixed', savedLabel: 'Unknown', label: 'Paused — policy unavailable', canSave: false });
    expect(shadePolicyPresentation(state, 'kitchen')).not.toHaveProperty('eligible');
  });

  it('uses the backend nightly overlay without changing saved ON', () => {
    const state = snapshot();
    state.zones.bathroom.status = 'nightly_override';
    state.zones.bathroom.label = 'Paused — nightly override';
    expect(shadePolicyPresentation(state, 'bathroom')).toMatchObject({ checked: true, savedLabel: 'Saved ON', label: 'Paused — nightly override' });
  });

  it.each([
    ['override_unavailable', 'Paused — override unavailable'],
    ['automation_not_released', 'Enabled — automation not released'],
    ['eligible', 'Enabled — subject to current advice and safety checks'],
  ])('presents backend %s without calculating a browser execution decision', (status, label) => {
    const state = snapshot();
    state.zones.bedroom.status = status;
    state.zones.bedroom.label = label;
    expect(shadePolicyPresentation(state, 'bedroom')).toMatchObject({ checked: true, label });
    expect(shadePolicyPresentation(state, 'bedroom')).not.toHaveProperty('eligible');
  });

  it('does not turn a cached choice into confirmation after loss of backend authority', () => {
    const state = snapshot();
    state.connected = false;
    expect(shadePolicyPresentation(state, 'kitchen')).toMatchObject({ checked: 'mixed', canSave: false });
    expect(shadePolicyPresentation(null, 'bedroom')).toMatchObject({ checked: 'mixed', canSave: false });
  });

  it('rejects malformed sessions, generations, zone states and unknown status codes', () => {
    expect(validateShadePolicySnapshot(snapshot())).toBe(true);
    for (const mutate of [state => state.sessionId = '', state => state.generation = -1,
      state => delete state.zones.bedroom, state => state.zones.kitchen.saved = 'TRUE',
      state => state.zones.kitchen.status = 'active', state => state.schemaVersion = 2]) {
      const state = snapshot(); mutate(state);
      expect(validateShadePolicySnapshot(state)).toBe(false);
      expect(shadePolicyPresentation(state, 'kitchen').checked).toBe('mixed');
    }
  });
});
