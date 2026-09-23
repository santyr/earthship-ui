import { expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../../openhab/file-config/items/openmeteo-forecast-aqi.items', import.meta.url), 'utf8');
const ownership = JSON.parse(readFileSync(new URL('../../openhab/file-config/ownership.json', import.meta.url), 'utf8'));

it('stages the exact managed Forecast_AQI identity without claiming live file ownership', () => {
  const definitions = source.split('\n').map((line) => line.trim()).filter((line) => line && !line.startsWith('//'));
  expect(definitions).toEqual([
    'String Forecast_AQI "US Air Quality Index" ["forecast"] { channel="openmeteo:air-quality:local:aq:forecastHourly#us-aqi-as-string" }',
  ]);
  expect(ownership.resources.some((resource) => resource.id === 'Forecast_AQI'
    || resource.id === 'Forecast_AQI -> openmeteo:air-quality:local:aq:forecastHourly#us-aqi-as-string')).toBe(false);
});
