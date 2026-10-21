import { afterEach, expect, it, vi } from 'vitest';
import { loadHouseholdObservation, loadWeatherCapabilities } from '../src/lib/household/observationClient.js';
import { observation } from './fixtures/household-observation.js';
import { capabilityFixture, CAPABILITY_NOW } from './fixtures/weather-capabilities.js';
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
it('transports a complete long-range capability report without expanding legacy route limits', async () => {
  const report=capabilityFixture();const first=report.groups.temperature.hours[0];
  report.groups.temperature.hours=Array.from({length:337},(_,i)=>({...first,valid_at:new Date(CAPABILITY_NOW+(i+1)*3600000).toISOString()}));
  const raw=JSON.stringify(report);expect(raw.length).toBeGreaterThan(32768);
  const fetcher=vi.fn(async()=>new Response(raw));vi.stubGlobal('fetch',fetcher);
  const signal=new AbortController().signal;
  expect(await loadWeatherCapabilities(signal)).toBe(raw);
  expect(fetcher.mock.calls[0]).toEqual(['/api/weather-capabilities',{signal,cache:'no-store',redirect:'error'}]);
  await expect(loadHouseholdObservation(signal)).rejects.toThrow('Observation unavailable');
});
it('cancels a chunked capability response when it exceeds its own 256-KiB ceiling',async()=>{
  const cancel=vi.fn();let chunks=0;
  const stream=new ReadableStream({pull(controller){chunks++;controller.enqueue(new Uint8Array(50000));},cancel});
  vi.stubGlobal('fetch',async()=>new Response(stream));
  await expect(loadWeatherCapabilities(new AbortController().signal)).rejects.toThrow('Observation unavailable');
  expect(cancel).toHaveBeenCalled();expect(chunks).toBeLessThanOrEqual(7);
});
