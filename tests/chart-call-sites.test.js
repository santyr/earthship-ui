import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';

describe('Energy chart containment', () => {
  it('lets both inline charts fill bounded flex parents instead of forcing pixel heights', async () => {
    const source = await readFile('src/screens/Energy.svelte', 'utf8');
    expect(source).not.toMatch(/<HistoryChart[^>]*\bheight=/s);
    expect(source).toMatch(/\.hero-chart\s*\{[^}]*min-height:\s*0/s);
    expect(source).toMatch(/\.pv-chart\s*\{[^}]*min-height:\s*0/s);
    expect(source).toMatch(/\.hero-chart\s*\{[^}]*overflow:\s*hidden/s);
    expect(source).toMatch(/\.pv-chart\s*\{[^}]*overflow:\s*hidden/s);
  });

  it('uses a period-neutral battery title because the picker controls the range', async () => {
    const source = await readFile('src/screens/Energy.svelte', 'utf8');
    expect(source).not.toContain("Battery — 24h + tonight's forecast");
    expect(source).toContain("Battery history + tonight's forecast");
  });
});

describe('Home extrema marker call sites', () => {
  it('marks measured Outdoor and Battery SoC without marking Forecast', async () => {
    const source = await readFile('src/screens/Home.svelte', 'utf8');
    const outdoor = source.slice(
      source.indexOf('function openOutdoorChart()'),
      source.indexOf('function openIndoorChart()'),
    );
    const battery = source.slice(
      source.indexOf('function openBatteryChart()'),
      source.indexOf('function openWindChart()'),
    );

    expect(outdoor.match(/markers:\s*\['min', 'max'\]/g)).toHaveLength(1);
    expect(outdoor).toContain("markerUnit: '°'");
    expect(battery).toContain("markers: ['min', 'max']");
    expect(battery).toContain("markerUnit: '%'");
  });
});

describe('Home chart presentation call sites', () => {
  it('pins only Bitcoin to candlesticks while existing charts remain implicit lines', async () => {
    const source = await readFile('src/screens/Home.svelte', 'utf8');
    const handlers = [
      ['openOutdoorChart', 'openIndoorChart'],
      ['openIndoorChart', 'openBatteryChart'],
      ['openBatteryChart', 'openWindChart'],
      ['openWindChart', 'openRainChart'],
      ['openRainChart', 'openSolarChart'],
      ['openSolarChart', 'openBaroChart'],
      ['openBaroChart', 'openBitcoinChart'],
    ];

    for (const [start, end] of handlers) {
      const chartCall = source.slice(
        source.indexOf(`function ${start}()`),
        source.indexOf(`function ${end}()`),
      );
      expect(chartCall).not.toContain('presentation:');
    }

    const bitcoin = source.slice(
      source.indexOf('function openBitcoinChart()'),
      source.indexOf('</script>'),
    );
    expect(bitcoin).toContain("presentation: 'candlestick'");
    expect(source.match(/presentation:\s*'candlestick'/g)).toHaveLength(1);
  });
});
