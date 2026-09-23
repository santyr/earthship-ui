import { expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../../openhab/file-config/items/openmeteo-current-aqi.items', import.meta.url), 'utf8');

it('preserves the managed current AQI observation identity, metadata and channel for staged migration', () => {
  const definitions = source.split('\n').map((line) => line.trim()).filter((line) => line && !line.startsWith('//'));
  expect(definitions).toEqual([
    'Number Current_US_AQI "Current US AQI" <airquality> ["Measurement"] { channel="openmeteo:air-quality:local:aq:current#us-aqi" }',
  ]);
});
