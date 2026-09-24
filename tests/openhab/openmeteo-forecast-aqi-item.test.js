import { expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../../openhab/file-config/items/openmeteo-forecast-aqi.items', import.meta.url), 'utf8');
const ownership = JSON.parse(readFileSync(new URL('../../openhab/file-config/ownership.json', import.meta.url), 'utf8'));

it('declares the exact file-owned Forecast_AQI Item and channel link', () => {
  const definitions = source.split('\n').map((line) => line.trim()).filter((line) => line && !line.startsWith('//'));
  expect(definitions).toEqual([
    'String Forecast_AQI "US Air Quality Index" ["forecast"] { channel="openmeteo:air-quality:local:aq:forecastHourly#us-aqi-as-string" }',
  ]);
  const expectedSource = 'items/openmeteo-forecast-aqi.items';
  const expectedDestination = '/etc/openhab/items/openmeteo-forecast-aqi.items';
  for (const [kind, id] of [
    ['item', 'Forecast_AQI'],
    ['link', 'Forecast_AQI -> openmeteo:air-quality:local:aq:forecastHourly#us-aqi-as-string'],
  ]) {
    const matching = ownership.resources.filter((resource) => resource.kind === kind && resource.id === id);
    expect(matching).toHaveLength(1);
    expect(matching[0]).toMatchObject({ provider: 'file', migration: 'verified',
      source: expectedSource, destination: expectedDestination });
  }
});
