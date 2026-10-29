import { execFileSync } from 'node:child_process';
import { beforeAll, expect, it } from 'vitest';
import { parseForecast10Day } from '../../src/lib/weather/forecastDetail.js';
const python = process.env.EARTHSHIP_TEST_PYTHON || 'python3';
const numericOwned = [
  'Forecast_Temp', 'Forecast_Cloudiness', 'Forecast_Radiation', 'Forecast_Daily_High',
  'Forecast_Daily_Low', 'Forecast_Daily_PrecipSum', 'Forecast_Tomorrow_High', 'Forecast_Tomorrow_Low',
];
const arrayOwned = ['Forecast_Hourly_JSON', 'Forecast_Daily_JSON'];
const owned = [...numericOwned, ...arrayOwned, 'Forecast_10Day_JSON'];
function assertWithdrawal(held, writes) {
  for (const item of numericOwned) expect(held[item], item).toBe('UNDEF');
  for (const item of arrayOwned) expect(held[item], item).toBe('[]');
  expect(JSON.parse(held.Forecast_10Day_JSON)).toMatchObject({
    providerStatus: 'UNAVAILABLE', source: null, issueSha256: null, days: [],
  });
  expect([...new Set(writes.map(([item]) => item))].sort()).toEqual([...owned].sort());
  expect(held.Current_US_AQI).toBe('501');
  expect(held.Forecast_AQI).toBe('Hazardous');
  expect(held.Thermal_Advisory).toBe('legacy');
}
let evidence;
beforeAll(() => {
  evidence = JSON.parse(execFileSync(python, ['-B', 'tests/helpers/current-publication.py'], {
    encoding: 'utf8', timeout: 15000,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
  }));
});
it('commits qualified provider detail last, preserving supported values and explicit unsupported fields', () => {
  const { available, states } = evidence;
  expect(available.result.status).toBe('PUBLISHED');
  expect(Object.keys(states).sort()).toEqual([...owned].sort());
  expect(available.result.automatic_actuation).toBe(false);
  expect(available.result.release_authorized).toBe(false);
  expect(available.writes.at(-1)[0]).toBe('Forecast_10Day_JSON');
  expect(JSON.parse(available.writes[0][1])).toMatchObject({ providerStatus: 'UNAVAILABLE', days: [] });
  const detail = JSON.parse(states.Forecast_10Day_JSON);
  expect(detail).toMatchObject({ provider: 'weathernext3', providerStatus: 'AVAILABLE', releaseAuthorized: false });
  expect(detail.days[0].hours[0]).toMatchObject({ tempF: 64.5, radiationWm2: 700, precipIn: 0,
    windMph: 4.5, precipPct: null, weatherCode: null, isDay: null });
  expect(detail.days[0].summary).toMatchObject({ highF: 65, lowF: 40, precipPct: null, weatherCode: null, pvKwh: null });
  expect(states).not.toHaveProperty('Current_US_AQI');
  expect(states).not.toHaveProperty('Forecast_AQI');
  expect(states).not.toHaveProperty('Forecast_PrecipProb');
  expect(states).not.toHaveProperty('Forecast_Daily_UVIndex');
  // Exercise the real producer/JS reader seam, retaining null probability/code.
  const parsed = parseForecast10Day(states.Forecast_10Day_JSON, { nowMs: Date.parse('2026-10-24T18:00:00Z') });
  expect(parsed.status).toBe('ready');
  expect(parsed.days[0].hours[0]).toMatchObject({ tempF: 64.5, precipPct: null, weatherCode: null });
});
it('withdraws held numeric and JSON forecasts when acquisition is unavailable', () => {
  const { unavailable } = evidence;
  expect(unavailable.result.status).toBe('WITHDRAWN');
  assertWithdrawal(unavailable.held, unavailable.writes);
  expect(unavailable.held.Forecast_Hourly_JSON).toBe('[]');
  expect(JSON.parse(unavailable.held.Forecast_10Day_JSON)).toMatchObject({ providerStatus: 'UNAVAILABLE', source: null, days: [] });
  expect(unavailable.held.Current_US_AQI).toBe('501'); // Outside publisher ownership: never write it.
  expect(unavailable.writes.every(([item]) => item.startsWith('Forecast_') && item !== 'Forecast_AQI')).toBe(true);
});
it('withdraws every owned forecast on a mismatched state readback', () => {
  const { mismatch } = evidence;
  expect(mismatch.result).toMatchObject({ status: 'FAILED', failed_item: 'Forecast_Temp', unconfirmed_withdrawals: [] });
  expect([...mismatch.result.withdrawal_attempts].sort()).toEqual([...owned].sort());
  assertWithdrawal(mismatch.held, mismatch.writes);
  expect(mismatch.held.Forecast_Temp).toBe('UNDEF');
  expect(JSON.parse(mismatch.held.Forecast_10Day_JSON)).toMatchObject({ providerStatus: 'UNAVAILABLE', providerReason: 'PUBLICATION_FAILED', days: [] });
});
it('refuses publication before any write without explicit cutover authorization and never renews original clocks', () => {
  expect(evidence.denied.error).toMatch(/authorization required/);
  expect(evidence.denied.writes).toEqual([]);
  expect(evidence.shifted_clock).toMatch(/exact original decision/);
});
it('preserves bounded native publisher deployment contracts and rejects unsafe command or resource changes', () => {
  expect(Object.keys(evidence.service_rejections)).toEqual([
    'unbounded memory', 'swap', 'extra tasks', 'deadline', 'CPU', 'different command', 'duplicate entrypoint',
  ]);
  for (const cause of Object.values(evidence.service_rejections)) expect(cause).toMatch(/contract|limits|one original publisher/);
});

it('missing, inaccessible and malformed original acquisition cannot select an alternate provider', () => {
  for (const [reason, states] of Object.entries(evidence.acquisition)) {
    const detail = JSON.parse(states.Forecast_10Day_JSON);
    expect(detail).toMatchObject({ provider: 'weathernext3', providerStatus: 'UNAVAILABLE',
      providerReason: reason, source: null, issueSha256: null, releaseAuthorized: false, days: [] });
    expect(states.Forecast_Temp).toBe('UNDEF');
    expect(states.Forecast_Hourly_JSON).toBe('[]');
  }
  expect(Object.keys(evidence.acquisition)).toEqual(['NO_ELIGIBLE_SOURCE', 'ARCHIVE_UNAVAILABLE', 'INVALID_SOURCE']);
});
