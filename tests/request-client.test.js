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

  it('stays pending on a non-terminal accepted result', async () => {
    vi.useFakeTimers();
    try {
      const { sendCommand, itemsStore, dep } = deps({ dep: { timeoutMs: 30_000 } });
      const promise = submitControlRequest(OWNED, {}, dep);
      const { requestId } = JSON.parse(sendCommand.mock.calls[0][1]);

      itemsStore.set({
        [OWNED.resultItem]: JSON.stringify({ requestId, status: 'accepted', reason: 'accepted', at: '' }),
      });
      await vi.advanceTimersByTimeAsync(30_000);

      await expect(promise).resolves.toEqual({ phase: 'unknown', reason: 'Outcome unknown' });
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
