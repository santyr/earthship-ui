import { describe, expect, it } from 'vitest';
import { hourlyForecastFromDetail, selectForecastWindow } from '../src/lib/weather/forecastDetail.js';
import { buildWeatherDetailOption } from '../src/lib/weather/detailChart.js';

const HOUR = 3600000;
const nowMs = Date.parse('2026-10-24T14:15:00Z');
function row(at, tempF = 60) {
  return { at, atMs: Date.parse(at), tempF, precipPct: 0, precipIn: 0,
    radiationWm2: 100, windMph: 5, weatherCode: 1, cloudPct: 20, isDay: true };
}
function forecast(hours, at = nowMs) {
  return { status: 'ready', timezone: 'America/Denver', generatedAtMs: at,
    days: [{ date: '2026-10-24', hours }] };
}
const rolling = Array.from({ length: 13 }, (_, i) => row(`2026-10-24T${String(i + 9).padStart(2, '0')}:00:00-06:00`, 60 + i));

describe('fixed forecast time coverage', () => {
  it.each([0, 3, 11])('counts missing rolling slot %i without borrowing the thirteenth hour', missing => {
    const selected = selectForecastWindow(forecast(rolling.filter((_, i) => i !== missing)), '2026-10-24', { nowMs });
    expect(selected.hours).toHaveLength(11);
    expect(selected.missingHours).toBe(1);
    expect(selected.expectedHours).toBe(12);
    expect(selected.slots).toHaveLength(12);
    expect(selected.slots.map(h => h.atMs)).toEqual(Array.from({ length: 12 }, (_, i) => Date.parse('2026-10-24T15:00:00Z') + i * HOUR));
    expect(selected.slots[missing]).toMatchObject({ missing: true, tempF: null, precipIn: null, radiationWm2: null, windMph: null });
    expect(selected.hours.some(h => h.atMs === Date.parse('2026-10-25T03:00:00Z'))).toBe(false);
  });

  it('preserves all original values and order for a complete rolling window, including an exact boundary', () => {
    for (const at of [nowMs, Date.parse('2026-10-24T15:00:00Z')]) {
      const selected = selectForecastWindow(forecast(rolling, at), '2026-10-24', { nowMs: at });
      expect(selected.hours).toEqual(rolling.slice(0, 12));
      expect(selected.slots).toEqual(rolling.slice(0, 12));
      expect(selected.missingHours).toBe(0);
    }
  });

  it('keeps local 07:00–18:00 daytime slots separate from the current rolling window', () => {
    const hours = Array.from({ length: 14 }, (_, i) => row(`2026-10-25T${String(i + 6).padStart(2, '0')}:00:00-06:00`, i));
    const selected = selectForecastWindow(forecast(hours.filter(h => ![7, 11, 18].includes(Number(h.at.slice(11, 13))))), '2026-10-25', { nowMs });
    expect(selected.mode).toBe('daytime');
    expect(selected.hours).toHaveLength(9);
    expect(selected.missingHours).toBe(3);
    expect(selected.slots.map(h => h.at.slice(11, 13))).toEqual(['07','08','09','10','11','12','13','14','15','16','17','18']);
    expect(selected.slots.filter(h => h.missing).map(h => h.at.slice(11, 13))).toEqual(['07','11','18']);
  });

  it.each([
    ['2026-03-07T18:00:00Z', '2026-03-08', '-06:00'],
    ['2026-10-31T18:00:00Z', '2026-11-01', '-07:00'],
  ])('resolves future daytime after a Denver offset change on %s', (at, date, offset) => {
    const clock = Date.parse(at);
    const hours = Array.from({ length: 12 }, (_, i) => row(`${date}T${String(i + 7).padStart(2, '0')}:00:00${offset}`, i));
    const selected = selectForecastWindow(forecast(hours, clock), date, { nowMs: clock });
    expect(selected.mode).toBe('daytime');
    expect(selected.hours).toEqual(hours);
    expect(selected.slots).toEqual(hours);
    expect(selected.missingHours).toBe(0);
  });

  it('plots twelve aligned positions and breaks every curve at an absent core hour', () => {
    const selected = selectForecastWindow(forecast(rolling.filter((_, i) => i !== 3)), '2026-10-24', { nowMs });
    const option = buildWeatherDetailOption({ hours: selected.slots });
    expect(option.xAxis.data).toHaveLength(12);
    expect(option.xAxis.data.slice(2, 5)).toEqual(['11 AM','12 PM','1 PM']);
    for (const series of option.series) {
      expect(series.data).toHaveLength(12);
      expect(series.data[3]).toBeNull();
      if (series.type === 'line') expect(series.connectNulls).toBe(false);
    }
    expect(option.series.find(s => s.name === 'Temperature').data.slice(2, 5)).toEqual([62, null, 64]);
  });

  it('preserves every value and order in a complete fourteen-hour strip', () => {
    const hours = Array.from({ length: 15 }, (_, i) => row(`2026-10-24T${String(i + 8).padStart(2, '0')}:00:00-06:00`, i));
    const strip = hourlyForecastFromDetail(forecast(hours), { nowMs });
    expect(strip.map(h => [h.at, h.t, h.p, h.a, h.r, h.w, h.c])).toEqual(
      hours.slice(0, 14).map(h => [h.at, h.tempF, h.precipPct, h.precipIn, h.radiationWm2, h.weatherCode, h.cloudPct]),
    );
    expect(strip.some(h => h.missing)).toBe(false);
  });

  it.each([0, 5, 13])('keeps the fourteen-hour strip current-hour convention with missing slot %i', missing => {
    const hours = Array.from({ length: 15 }, (_, i) => row(`2026-10-24T${String(i + 8).padStart(2, '0')}:00:00-06:00`, i));
    const strip = hourlyForecastFromDetail(forecast(hours.filter((_, i) => i !== missing)), { nowMs });
    expect(strip).toHaveLength(14);
    expect(strip[0].at).toBe('2026-10-24T08:00:00-06:00');
    expect(strip.at(-1).at).toBe('2026-10-24T21:00:00-06:00');
    expect(strip[missing]).toMatchObject({ missing: true, t: null, p: null, a: null, r: null, w: null, c: null });
  });

  it.each([
    ['spring', '2026-03-08T08:15:00Z', '2026-03-08', ['2026-03-08T01:00:00-07:00', '2026-03-08T03:00:00-06:00', '2026-03-08T04:00:00-06:00'], ['3 AM', '4 AM'], ['1a','3a','4a']],
    ['fall', '2026-11-01T06:15:00Z', '2026-11-01', ['2026-11-01T00:00:00-06:00', '2026-11-01T01:00:00-06:00', '2026-11-01T01:00:00-07:00'], ['1 AM UTC-06:00', '1 AM UTC-07:00'], ['12a','1a UTC-06:00','1a UTC-07:00']],
    ['midnight', '2026-10-25T05:15:00Z', '2026-10-24', ['2026-10-24T23:00:00-06:00', '2026-10-25T00:00:00-06:00', '2026-10-25T01:00:00-06:00'], ['12 AM', '1 AM'], ['11p','12a','1a']],
  ])('keeps elapsed hours and unambiguous Denver labels through %s', (_, at, date, times, detailLabels, stripLabels) => {
    const clock = Date.parse(at), product = forecast(times.map(t => row(t)), clock);
    const selected = selectForecastWindow(product, date, { nowMs: clock });
    expect(selected.hours.map(h => h.at)).toEqual(times.slice(1));
    expect(selected.slots).toHaveLength(12);
    expect(selected.slots[0].atMs).toBe(Math.ceil(clock / HOUR) * HOUR);
    expect(selected.slots.at(-1).atMs - selected.slots[0].atMs).toBe(11 * HOUR);
    expect(buildWeatherDetailOption({ hours: selected.slots }).xAxis.data.slice(0, 2)).toEqual(detailLabels);
    expect(hourlyForecastFromDetail(product, { nowMs: clock }).slice(0, 3).map(h => h.h)).toEqual(stripLabels);
  });
});
