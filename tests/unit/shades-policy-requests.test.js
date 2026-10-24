import { afterEach, describe, expect, it, vi } from 'vitest';
import { createShadePolicyRequests, SHADE_POLICY_REQUEST_TIMEOUT_MS } from '../../src/lib/shades/policy.js';

const response = value => ({ ok: true, json: async () => value });

afterEach(() => { vi.useRealTimers(); });

describe('bounded shade policy requests', () => {
  it('bounds response-body reads as well as transport and permits the next reconciliation', async () => {
    vi.useFakeTimers();
    let resolveBody;
    let signal;
    let calls = 0;
    const requests = createShadePolicyRequests({ fetchImpl: async (_url, options) => {
      signal = options.signal;
      if (++calls === 1) return { ok: true, json: () => new Promise(resolve => resolveBody = resolve) };
      return response({ fresh: true });
    } });
    const first = requests.request();
    const expired = expect(first).rejects.toMatchObject({ name: 'AbortError' });
    await vi.advanceTimersByTimeAsync(SHADE_POLICY_REQUEST_TIMEOUT_MS);
    await expired;
    expect(signal.aborted).toBe(true);
    resolveBody({ stale: true });
    await expect(requests.request()).resolves.toMatchObject({ snapshot: { fresh: true } });
    expect(vi.getTimerCount()).toBe(0);
  });

  it('unmount cancellation aborts every read and save, rejects late results and clears deadlines', async () => {
    vi.useFakeTimers();
    const signals = [];
    const resolveFetch = [];
    const deliveries = [];
    const requests = createShadePolicyRequests({ fetchImpl: (_url, options) => {
      signals.push(options.signal);
      return new Promise(resolve => resolveFetch.push(resolve));
    } });
    const read = requests.request();
    const save = requests.request({ method: 'POST', body: '{}' });
    read.then(value => deliveries.push(value), () => {});
    save.then(value => deliveries.push(value), () => {});
    const readAborted = expect(read).rejects.toMatchObject({ name: 'AbortError' });
    const saveAborted = expect(save).rejects.toMatchObject({ name: 'AbortError' });
    requests.dispose();
    await Promise.all([readAborted, saveAborted]);
    expect(signals.every(signal => signal.aborted)).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
    resolveFetch.forEach(resolve => resolve(response({ late: true })));
    await Promise.resolve();
    await Promise.resolve();
    expect(deliveries).toEqual([]);
    await expect(requests.request()).rejects.toMatchObject({ name: 'AbortError' });
  });
});
