import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

describe('current AQI consumption contract', () => {
  it('uses Current_US_AQI for every scalar and never parses Forecast_AQI numerically', () => {
    const scalarSurfaces = [
      read('src/screens/Home.svelte'),
      read('src/screens/Weather.svelte'),
      read('src/lib/alerts/consoleAlerts.js'),
    ].join('\n');

    expect(scalarSurfaces).toContain('Current_US_AQI');
    expect(scalarSurfaces).not.toMatch(
      /(?:num|fmt|aqiColor|aqiBand)\(\$?items\.Forecast_AQI\)/,
    );
  });
});
