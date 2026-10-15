import { OBSERVATION_MAX_BYTES } from './observation.js';

export const loadHouseholdObservation = signal => load('/api/household-observation', signal);
export const loadBatteryPerformance = signal => load('/api/household-battery-performance', signal);

async function load(path, signal) {
  const response = await fetch(path, { signal, cache: 'no-store', redirect: 'error' });
  if (!response.ok || !response.body?.getReader || Number(response.headers.get('content-length')) > OBSERVATION_MAX_BYTES) {
    await response.body?.cancel(); throw new Error('Observation unavailable');
  }
  const reader = response.body.getReader(), decoder = new TextDecoder('utf-8', { fatal: true });
  let length = 0, raw = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > OBSERVATION_MAX_BYTES) { await reader.cancel(); throw new Error('Observation unavailable'); }
      raw += decoder.decode(value, { stream: true });
    }
    return raw + decoder.decode();
  } finally { reader.releaseLock(); }
}
