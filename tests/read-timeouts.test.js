import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createClient } from '../src/lib/openhab/client.js';
import { loadConfig } from '../src/lib/config.js';
beforeEach(() => { vi.useFakeTimers(); vi.stubGlobal('fetch', vi.fn()); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it.each(['getAllItems', 'getAllThings', 'getItem', 'getHistory'])('bounds a hung %s read and aborts its transport', async method => {
  fetch.mockReturnValue(new Promise(() => {}));
  const client = createClient({ openhabUrl: '', apiToken: '', readTimeoutMs: 50 });
  const pending = method === 'getItem' || method === 'getHistory' ? client[method]('A') : client[method]();
  const result = pending.catch(error => error);
  await vi.advanceTimersByTimeAsync(50);
  expect(fetch.mock.calls[0][1].signal?.aborted).toBe(true);
  expect((await result).name).toBe('TimeoutError');
  expect(vi.getTimerCount()).toBe(0);
});

it('bounds configuration reads including a hung response body', async () => {
  fetch.mockResolvedValue({ ok: true, json: () => new Promise(() => {}) });
  const result = loadConfig({ timeoutMs: 50 }).catch(error => error);
  await vi.advanceTimersByTimeAsync(50);
  expect(fetch.mock.calls[0][1].signal?.aborted).toBe(true);
  expect((await result).name).toBe('TimeoutError');
});

it('honors caller cancellation even when the transport ignores it', async () => {
  fetch.mockReturnValue(new Promise(() => {}));
  const controller = new AbortController();
  const result = createClient({ openhabUrl: '', apiToken: '' }).getAllItems({ signal: controller.signal }).catch(error => error);
  controller.abort();
  await vi.advanceTimersByTimeAsync(0);
  expect(fetch.mock.calls[0][1].signal?.aborted).toBe(true);
  expect((await result).name).toBe('AbortError');
  expect(vi.getTimerCount()).toBe(0);
});

it('cancels a stalled history body reader at the deadline', async () => {
  const cancel = vi.fn().mockResolvedValue(undefined);
  fetch.mockResolvedValue({ ok: true, body: { getReader: () => ({ read: () => new Promise(() => {}), cancel, releaseLock() {} }) } });
  const result = createClient({ openhabUrl: '', apiToken: '', readTimeoutMs: 50 }).getHistory('A').catch(error => error);
  await vi.advanceTimersByTimeAsync(50);
  expect((await result).name).toBe('TimeoutError');
  expect(cancel).toHaveBeenCalledOnce();
});

it('does not start reading a body if a canceled transport resolves late', async () => {
  let resolve;
  fetch.mockReturnValue(new Promise(r => { resolve = r; }));
  const controller = new AbortController();
  const result = createClient({ openhabUrl: '', apiToken: '' }).getItem('A', { signal: controller.signal }).catch(error => error);
  controller.abort();
  expect((await result).name).toBe('AbortError');
  const json = vi.fn().mockResolvedValue({ state: 'LATE' });
  resolve({ ok: true, json });
  await vi.advanceTimersByTimeAsync(0);
  expect(json).not.toHaveBeenCalled();
});

it.each(['getAllItems', 'getAllThings'])('rejects malformed %s collections as failed reads', async method => {
  fetch.mockResolvedValue({ ok: true, json: async () => [null] });
  await expect(createClient({ openhabUrl: '', apiToken: '' })[method]()).rejects.toThrow(/invalid snapshot/);
});
