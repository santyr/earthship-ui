import { describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

async function loadSubject() {
  try {
    return await import('../src/lib/controls/outcomeStore.js');
  } catch {
    return null;
  }
}

describe('control outcome store', () => {
  it('exposes a deterministic store factory', async () => {
    const subject = await loadSubject();

    expect(subject).not.toBeNull();
    expect(subject?.createOutcomeStore).toBeTypeOf('function');
  });

  it('keeps one latest outcome per control and replaces a prior alerting phase', async () => {
    const { createOutcomeStore } = await loadSubject();
    const store = createOutcomeStore({ now: () => 1_000 });

    store.record({
      controlId: 'living1',
      controlLabel: 'Living Room 1',
      phase: 'failed',
      reason: 'Rejected',
      transitionAt: 800,
    });
    store.record({
      controlId: 'living1',
      controlLabel: 'Living Room 1',
      phase: 'confirmed',
      reason: '',
      transitionAt: 900,
    });

    expect(get(store)).toEqual([
      expect.objectContaining({
        controlId: 'living1',
        phase: 'confirmed',
        transitionAt: 900,
      }),
    ]);
  });

  it('preserves a confirmed correlated outcome verbatim so it never raises a console alert', async () => {
    const { createOutcomeStore } = await loadSubject();
    const store = createOutcomeStore({ now: () => 5_000 });

    store.record({
      controlId: 'dishwasher',
      controlLabel: 'Dishwasher',
      phase: 'confirmed',
      reason: 'completed',
    });

    expect(get(store)).toEqual([
      expect.objectContaining({ controlId: 'dishwasher', phase: 'confirmed', reason: 'completed' }),
    ]);
  });

  it('normalizes error/unknown phases and expires each record 15 minutes after transitionAt', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(10_000);
    const { createOutcomeStore, CONTROL_OUTCOME_TTL_MS } = await loadSubject();
    const store = createOutcomeStore();

    store.record({
      controlId: 'living1',
      controlLabel: 'Living Room 1',
      phase: 'error',
      reason: 'Rejected',
    });
    store.record({
      controlId: 'living2',
      controlLabel: 'Living Room 2',
      phase: 'unknown',
      reason: 'Transport lost',
      transitionAt: 11_000,
    });

    expect(get(store).map(({ controlId, phase, transitionAt }) => ({
      controlId,
      phase,
      transitionAt,
    }))).toEqual([
      { controlId: 'living1', phase: 'failed', transitionAt: 10_000 },
      { controlId: 'living2', phase: 'outcome-unknown', transitionAt: 11_000 },
    ]);

    vi.advanceTimersByTime(CONTROL_OUTCOME_TTL_MS);
    expect(get(store).map((entry) => entry.controlId)).toEqual(['living2']);
    vi.advanceTimersByTime(1_000);
    expect(get(store)).toEqual([]);
    store.destroy();
    vi.useRealTimers();
  });
});
