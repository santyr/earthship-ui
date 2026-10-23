import {MAX_SENSITIVITY_BYTES} from '../weather/sensitivity.js';
import {MAX_PRODUCTION_BYTES} from '../weather/productionForecast.js';
import {MAX_RAIN_BYTES} from '../weather/rainForecast.js';
import {MAX_MARGINAL_BYTES} from '../weather/marginalForecast.js';
import { OBSERVATION_MAX_BYTES } from './observation.js';
import {MAX_CAPABILITY_BYTES} from '../weather/capabilityForecast.js';

export const loadChronologicalSummary = signal => load('/api/household-chronological-summary', signal);
export const loadHouseholdObservation = signal => load('/api/household-observation', signal);
export const loadEnergyObservation = signal => load('/api/household-energy-observation', signal);
export const loadEnergyPerformance = signal => load('/api/household-energy-performance', signal);
export const loadProfiledObservation = signal => load('/api/household-profiled-energy-observation', signal);
export const loadProfiledPerformance = signal => load('/api/household-profiled-energy-performance', signal);
export const loadCapturedPvPerformance = signal => load('/api/household-captured-pv-performance', signal);
export const loadBatteryPerformance = signal => load('/api/household-battery-performance', signal);

async function load(path, signal, maximumBytes=OBSERVATION_MAX_BYTES) {
  const response = await fetch(path, { signal, cache: 'no-store', redirect: 'error' });
  if (!response.ok || !response.body?.getReader || Number(response.headers.get('content-length')) > maximumBytes) {
    await response.body?.cancel(); throw new Error('Observation unavailable');
  }
  const reader = response.body.getReader(), decoder = new TextDecoder('utf-8', { fatal: true });
  let length = 0, raw = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > maximumBytes) { await reader.cancel(); throw new Error('Observation unavailable'); }
      raw += decoder.decode(value, { stream: true });
    }
    return raw + decoder.decode();
  } finally { reader.releaseLock(); }
}

export const loadDailyPvPotential = signal => load('/api/daily-pv-potential', signal);

export const loadCalibratedEnergy = signal => load('/api/household-calibrated-energy-observation', signal);

export const loadCalibratedPerformance = signal => load('/api/household-calibrated-energy-performance', signal);

export const loadPvPerformance = signal => load('/api/daily-pv-performance', signal);

export const loadTerrainDaylight = signal => load('/api/terrain-daylight', signal);

export const loadWeatherCapabilities = signal => load('/api/weather-capabilities',signal,MAX_CAPABILITY_BYTES);

export const loadWeatherMarginals = signal => load('/api/weather-marginals',signal,MAX_MARGINAL_BYTES);

export const loadWeatherRainShadow = signal => load('/api/weather-rain-shadow',signal,MAX_RAIN_BYTES);

export const loadProductionWeather = signal => load('/api/weather-production',signal,MAX_PRODUCTION_BYTES);

export const loadWeatherSensitivity = signal => load('/api/weather-sensitivity',signal,MAX_SENSITIVITY_BYTES);
