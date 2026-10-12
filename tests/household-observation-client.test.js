import { afterEach, expect, it, vi } from 'vitest';
import { loadHouseholdObservation } from '../src/lib/household/observationClient.js';
import { observation } from './fixtures/household-observation.js';
afterEach(() => { vi.unstubAllGlobals(); });
it('requests only the fixed endpoint and preserves original bytes', async () => {
  const raw = JSON.stringify(observation());
  const fetcher = vi.fn(async () => new Response(raw)); vi.stubGlobal('fetch', fetcher);
  const signal = new AbortController().signal;
  expect(await loadHouseholdObservation(signal)).toBe(raw);
  expect(fetcher).toHaveBeenCalledWith('/api/household-observation', { signal, cache: 'no-store', redirect: 'error' });
});
it('cancels an oversized response stream before exposing its body', async () => {
  const cancel = vi.fn(); let chunks = 0;
  const stream = new ReadableStream({ pull(controller) { chunks++; controller.enqueue(new Uint8Array(20000)); }, cancel });
  vi.stubGlobal('fetch', async () => new Response(stream));
  await expect(loadHouseholdObservation(new AbortController().signal)).rejects.toThrow('Observation unavailable');
  expect(cancel).toHaveBeenCalled(); expect(chunks).toBeLessThanOrEqual(3);
});
it('refuses an unavailable endpoint', async () => {
  vi.stubGlobal('fetch', async () => new Response('{"status":"unavailable"}', { status: 503 }));
  await expect(loadHouseholdObservation(new AbortController().signal)).rejects.toThrow('Observation unavailable');
});
