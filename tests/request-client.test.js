import { describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import { submitControlRequest, buildRequestPayload } from '../src/lib/controls/requestClient.js';
import { CONTROL_CATALOG } from '../src/lib/controls/catalog.js';

const OWNED = CONTROL_CATALOG.dishwasher; // NightLoadDevice_Request/_Result
const REQUEST_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/;

function deps(overrides = {}) {
  const sendCommand = overrides.sendCommand ?? vi.fn().mockResolvedValue(undefined);
  const itemsStore = overrides.items ?? writable({});
  return {
    sendCommand,
    itemsStore,
    dep: { client: { sendCommand }, items: itemsStore, ...overrides.dep },
  };
}

describe('buildRequestPayload', () => {
  it('generates unique requestIds matching the rule regex and an ISO requestedAt', () => {
    const a = buildRequestPayload();
    const b = buildRequestPayload({ device: 'dishwasher', command: 'ON' });

    expect(a.requestId).toMatch(REQUEST_ID_RE);
    expect(b.requestId).toMatch(REQUEST_ID_RE);
    expect(a.requestId).not.toBe(b.requestId);
    expect(a.requestedAt).toBe(new Date(a.requestedAt).toISOString());
    expect(b).toMatchObject({ device: 'dishwasher', command: 'ON' });
  });
});

describe('submitControlRequest', () => {
  it('POSTs the correlated request JSON exactly once to the request item', () => {
    const { sendCommand, dep } = deps();
    submitControlRequest(OWNED, { device: 'dishwasher', command: 'ON' }, dep);

    expect(sendCommand).toHaveBeenCalledTimes(1);
    const [item, body] = sendCommand.mock.calls[0];
    expect(item).toBe('NightLoadDevice_Request');
    const parsed = JSON.parse(body);
    expect(parsed).toMatchObject({ device: 'dishwasher', command: 'ON' });
    expect(parsed.requestId).toMatch(REQUEST_ID_RE);
    expect(parsed.requestedAt).toBe(new Date(parsed.requestedAt).toISOString());
  });

  it('resolves confirmed on a matching completed result', async () => {
    const { sendCommand, itemsStore, dep } = deps();
    const promise = submitControlRequest(OWNED, {}, dep);
    const { requestId } = JSON.parse(sendCommand.mock.calls[0][1]);

    itemsStore.set({
      [OWNED.resultItem]: JSON.stringify({ requestId, status: 'completed', reason: 'completed', at: '' }),
    });

    await expect(promise).resolves.toEqual({ phase: 'confirmed', reason: 'completed' });
  });

  it('treats the feeder complete status as confirmed too', async () => {
    const feeder = CONTROL_CATALOG.feedOnce;
    const { sendCommand, itemsStore, dep } = deps();
    const promise = submitControlRequest(feeder, {}, dep);
    const { requestId } = JSON.parse(sendCommand.mock.calls[0][1]);

    itemsStore.set({
      [feeder.resultItem]: JSON.stringify({ requestId, status: 'complete', reason: 'complete', at: '' }),
    });

    await expect(promise).resolves.toEqual({ phase: 'confirmed', reason: 'complete' });
  });

  it('resolves error with the rule reason on denied', async () => {
    const { sendCommand, itemsStore, dep } = deps();
    const promise = submitControlRequest(OWNED, {}, dep);
    const { requestId } = JSON.parse(sendCommand.mock.calls[0][1]);

    itemsStore.set({
      [OWNED.resultItem]: JSON.stringify({ requestId, status: 'denied', reason: 'busy', at: '' }),
    });

    await expect(promise).resolves.toEqual({ phase: 'error', reason: 'busy' });
  });

  it('resolves error on failed', async () => {
    const { sendCommand, itemsStore, dep } = deps();
    const promise = submitControlRequest(OWNED, {}, dep);
    const { requestId } = JSON.parse(sendCommand.mock.calls[0][1]);

    itemsStore.set({
      [OWNED.resultItem]: JSON.stringify({ requestId, status: 'failed', reason: 'execution_error', at: '' }),
    });

    await expect(promise).resolves.toEqual({ phase: 'error', reason: 'execution_error' });
  });

  it('resolves accepted (sent-unconfirmed) as terminal when the rule posts accepted', async () => {
    const { sendCommand, itemsStore, dep } = deps();
    const promise = submitControlRequest(OWNED, {}, dep);
    const { requestId } = JSON.parse(sendCommand.mock.calls[0][1]);

    itemsStore.set({
      [OWNED.resultItem]: JSON.stringify({ requestId, status: 'accepted', reason: 'accepted', at: '' }),
    });

    await expect(promise).resolves.toEqual({ phase: 'accepted', reason: 'accepted' });
  });

  it('resolves accepted on a running result too', async () => {
    const { sendCommand, itemsStore, dep } = deps();
    const promise = submitControlRequest(OWNED, {}, dep);
    const { requestId } = JSON.parse(sendCommand.mock.calls[0][1]);

    itemsStore.set({
      [OWNED.resultItem]: JSON.stringify({ requestId, status: 'running', reason: 'commanded', at: '' }),
    });

    await expect(promise).resolves.toEqual({ phase: 'accepted', reason: 'commanded' });
  });

  it('upgrades the recorded outcome to confirmed after an accepted resolution, without a second POST', async () => {
    const recordOutcome = vi.fn();
    const { sendCommand, itemsStore, dep } = deps({ dep: { recordOutcome, now: () => 1000 } });
    const promise = submitControlRequest(OWNED, {}, dep);
    const { requestId } = JSON.parse(sendCommand.mock.calls[0][1]);

    itemsStore.set({
      [OWNED.resultItem]: JSON.stringify({ requestId, status: 'accepted', reason: 'accepted', at: '' }),
    });
    await expect(promise).resolves.toEqual({ phase: 'accepted', reason: 'accepted' });

    // ~5 minutes later the rule posts the terminal result; the background
    // listener records the upgraded outcome (a later transitionAt wins).
    itemsStore.set({
      [OWNED.resultItem]: JSON.stringify({ requestId, status: 'completed', reason: 'completed', at: '' }),
    });

    expect(recordOutcome).toHaveBeenCalledTimes(1);
    expect(recordOutcome).toHaveBeenCalledWith(expect.objectContaining({
      phase: 'confirmed', reason: 'completed', transitionAt: 1000,
    }));
    expect(sendCommand).toHaveBeenCalledTimes(1);
  });

  it('upgrades the recorded outcome to error when the terminal result is a failure', async () => {
    const recordOutcome = vi.fn();
    const { sendCommand, itemsStore, dep } = deps({ dep: { recordOutcome } });
    const promise = submitControlRequest(OWNED, {}, dep);
    const { requestId } = JSON.parse(sendCommand.mock.calls[0][1]);

    itemsStore.set({
      [OWNED.resultItem]: JSON.stringify({ requestId, status: 'accepted', reason: 'accepted', at: '' }),
    });
    await promise;
    itemsStore.set({
      [OWNED.resultItem]: JSON.stringify({ requestId, status: 'failed', reason: 'provider_mismatch', at: '' }),
    });

    expect(recordOutcome).toHaveBeenCalledWith(expect.objectContaining({
      phase: 'error', reason: 'provider_mismatch',
    }));
  });

  it('stops the background listener after the bounded window and records no upgrade', async () => {
    vi.useFakeTimers();
    try {
      const recordOutcome = vi.fn();
      const { sendCommand, itemsStore, dep } = deps({
        dep: { recordOutcome, backgroundTimeoutMs: 6 * 60_000 },
      });
      const promise = submitControlRequest(OWNED, {}, dep);
      const { requestId } = JSON.parse(sendCommand.mock.calls[0][1]);

      itemsStore.set({
        [OWNED.resultItem]: JSON.stringify({ requestId, status: 'accepted', reason: 'accepted', at: '' }),
      });
      await promise;
      await vi.advanceTimersByTimeAsync(6 * 60_000);

      // A terminal result that arrives after the window is ignored.
      itemsStore.set({
        [OWNED.resultItem]: JSON.stringify({ requestId, status: 'completed', reason: 'completed', at: '' }),
      });

      expect(recordOutcome).not.toHaveBeenCalled();
      expect(sendCommand).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not resolve for a result carrying a different requestId', async () => {
    vi.useFakeTimers();
    try {
      const { sendCommand, itemsStore, dep } = deps({ dep: { timeoutMs: 30_000 } });
      const promise = submitControlRequest(OWNED, {}, dep);

      itemsStore.set({
        [OWNED.resultItem]: JSON.stringify({ requestId: 'ui-not-mine-0001', status: 'completed', reason: 'completed', at: '' }),
      });
      await vi.advanceTimersByTimeAsync(30_000);

      await expect(promise).resolves.toEqual({ phase: 'unknown', reason: 'Outcome unknown' });
      expect(sendCommand).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('times out to unknown at 30s and never re-POSTs', async () => {
    vi.useFakeTimers();
    try {
      const { sendCommand, dep } = deps({ dep: { timeoutMs: 30_000 } });
      const promise = submitControlRequest(OWNED, {}, dep);
      expect(sendCommand).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(29_999);
      await vi.advanceTimersByTimeAsync(1);

      await expect(promise).resolves.toEqual({ phase: 'unknown', reason: 'Outcome unknown' });
      expect(sendCommand).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('resolves unknown without retry on a transport error', async () => {
    const sendCommand = vi.fn().mockRejectedValue(new Error('Failed to fetch'));
    const { dep } = deps({ sendCommand });
    await expect(submitControlRequest(OWNED, {}, dep)).resolves.toEqual({
      phase: 'unknown',
      reason: 'Outcome unknown',
    });
    expect(sendCommand).toHaveBeenCalledTimes(1);
  });

  it('resolves error on an explicit non-2xx POST rejection', async () => {
    const sendCommand = vi.fn().mockRejectedValue(new Error('sendCommand NightLoadDevice_Request 400'));
    const { dep } = deps({ sendCommand });
    const result = await submitControlRequest(OWNED, {}, dep);
    expect(result.phase).toBe('error');
    expect(sendCommand).toHaveBeenCalledTimes(1);
  });
});
