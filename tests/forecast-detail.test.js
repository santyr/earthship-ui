import { describe, expect, it } from 'vitest';
import {
  FORECAST_DETAIL_MAX_BYTES,
  parseForecast10Day,
  parseLegacyDailyForecast,
  selectForecastWindow,
} from '../src/lib/weather/forecastDetail.js';

function hour(date, hourValue, offset = '-06:00') {
  return {
    at: `${date}T${String(hourValue).padStart(2, '0')}:00:00${offset}`,
    tempF: 60 + hourValue,
    precipPct: hourValue,
    radiationWm2: hourValue * 20,
    windMph: 5 + hourValue / 2,
    weatherCode: 1,
  };
}

function day(date, label, start = 0, end = 23) {
  return {
    date,
    label,
    summary: {
      highF: 80,
      lowF: 50,
      precipPct: 20,
      weatherCode: 1,
      pvKwh: 6.4,
    },
    hours: Array.from({ length: end - start + 1 }, (_, index) => (
      hour(date, start + index)
    )),
  };
}

function dayWithRain(date, label, precipSumIn, hourPrecipIn) {
  const base = day(date, label, 0, 0);
  base.summary.precipSumIn = precipSumIn;
  base.hours[0].precipIn = hourPrecipIn;
  return base;
}

function payload(days, generatedAt = '2026-07-18T12:00:00-06:00') {
  return JSON.stringify({
    version: 1,
    generatedAt,
    timezone: 'America/Denver',
    days,
  });
}

describe('ten-day forecast contract', () => {
  it('normalizes ten ordered days and preserves provider nulls', () => {
    const days = Array.from({ length: 10 }, (_, index) => {
      const date = `2026-07-${String(18 + index).padStart(2, '0')}`;
      return day(date, index === 0 ? 'Today' : `Day ${index + 1}`);
    });
    days[0].hours[0].windMph = null;

    const result = parseForecast10Day(payload(days), {
      nowMs: Date.parse('2026-07-18T13:00:00-06:00'),
    });

    expect(result.status).toBe('ready');
    expect(result.days).toHaveLength(10);
    expect(result.days[0].hours[0].windMph).toBeNull();
  });

  it('rejects unsupported, duplicate, unordered, oversize, and offset-free payloads', () => {
    const validDay = day('2026-07-18', 'Today');
    expect(parseForecast10Day(JSON.stringify({
      version: 2,
      generatedAt: '2026-07-18T12:00:00-06:00',
      timezone: 'America/Denver',
      days: [validDay],
    })).status).toBe('unavailable');
    expect(parseForecast10Day(payload([validDay, validDay])).reason).toMatch(/duplicate/i);
    expect(parseForecast10Day(payload([
      day('2026-07-19', 'Tomorrow'),
      validDay,
    ])).reason).toMatch(/ascending/i);
    expect(parseForecast10Day(payload([{
      ...validDay,
      hours: [{ ...validDay.hours[0], at: '2026-07-18T00:00:00' }],
    }])).reason).toMatch(/offset/i);
    expect(parseForecast10Day('x'.repeat(FORECAST_DETAIL_MAX_BYTES + 1)).reason)
      .toMatch(/size/i);
  });

  it('marks forecasts older than four hours stale without dropping data', () => {
    const result = parseForecast10Day(
      payload([day('2026-07-18', 'Today')], '2026-07-18T08:00:00-06:00'),
      { nowMs: Date.parse('2026-07-18T12:00:01-06:00') },
    );
    expect(result.status).toBe('stale');
    expect(result.days).toHaveLength(1);
  });

  it('selects today from the next whole hour across midnight', () => {
    const result = parseForecast10Day(payload([
      day('2026-07-18', 'Today'),
      day('2026-07-19', 'Tomorrow'),
    ]), { nowMs: Date.parse('2026-07-18T20:32:00-06:00') });
    const selected = selectForecastWindow(result, '2026-07-18', {
      nowMs: Date.parse('2026-07-18T20:32:00-06:00'),
    });
    expect(selected.mode).toBe('rolling');
    expect(selected.hours).toHaveLength(10);
    expect(selected.hours[0].at).toContain('T21:00:00');
    expect(selected.hours.at(-1).at).toContain('2026-07-19T06:00:00');
  });

  it('selects exactly 08:00 through 17:00 for a future day', () => {
    const result = parseForecast10Day(payload([
      day('2026-07-18', 'Today'),
      day('2026-07-19', 'Tomorrow'),
    ]), { nowMs: Date.parse('2026-07-18T12:00:00-06:00') });
    const selected = selectForecastWindow(result, '2026-07-19', {
      nowMs: Date.parse('2026-07-18T12:00:00-06:00'),
    });
    expect(selected.mode).toBe('daytime');
    expect(selected.hours.map(({ at }) => at.slice(11, 13))).toEqual([
      '08', '09', '10', '11', '12', '13', '14', '15', '16', '17',
    ]);
  });

  it('preserves chronological ordering through a repeated DST hour', () => {
    const dstDay = day('2026-11-01', 'Today', 0, 0);
    dstDay.hours = [
      hour('2026-11-01', 0, '-06:00'),
      hour('2026-11-01', 1, '-06:00'),
      hour('2026-11-01', 1, '-07:00'),
      hour('2026-11-01', 2, '-07:00'),
      hour('2026-11-01', 3, '-07:00'),
    ];
    const result = parseForecast10Day(
      payload([dstDay], '2026-11-01T00:00:00-06:00'),
      { nowMs: Date.parse('2026-11-01T00:30:00-06:00') },
    );
    const selected = selectForecastWindow(result, '2026-11-01', {
      nowMs: Date.parse('2026-11-01T00:30:00-06:00'),
    });

    expect(selected.hours.map(({ at }) => at)).toEqual(dstDay.hours.slice(1).map(({ at }) => at));
    expect(selected.hours.map(({ atMs }) => atMs)).toEqual(
      [...selected.hours.map(({ atMs }) => atMs)].sort((a, b) => a - b),
    );
  });

  it('retains exact partial coverage and maps nullable legacy fallback values', () => {
    const result = parseForecast10Day(payload([
      day('2026-07-19', 'Tomorrow', 8, 14),
    ]), { nowMs: Date.parse('2026-07-18T12:00:00-06:00') });
    const selected = selectForecastWindow(result, '2026-07-19', {
      nowMs: Date.parse('2026-07-18T12:00:00-06:00'),
    });
    expect(selected.hours).toHaveLength(7);
    expect(selected.missingHours).toBe(3);

    expect(parseLegacyDailyForecast(JSON.stringify([
      { d: 'Today', hi: 80, lo: null, p: 'UNDEF', w: 1, pv: 6.4 },
    ]))).toEqual([expect.objectContaining({
      date: null,
      label: 'Today',
      summary: expect.objectContaining({
        highF: 80,
        lowF: null,
        precipPct: null,
        pvKwh: 6.4,
      }),
    })]);
  });

  it('parses precipSumIn and precipIn rain amounts when present', () => {
    const result = parseForecast10Day(payload([
      dayWithRain('2026-07-18', 'Today', 0.24, 0.05),
    ]), { nowMs: Date.parse('2026-07-18T12:00:00-06:00') });

    expect(result.days[0].summary.precipSumIn).toBe(0.24);
    expect(result.days[0].hours[0].precipIn).toBe(0.05);
  });

  it('parses rain amounts as null without throwing when absent from older payloads', () => {
    const result = parseForecast10Day(payload([
      day('2026-07-18', 'Today', 0, 0),
    ]), { nowMs: Date.parse('2026-07-18T12:00:00-06:00') });

    expect(result.status).toBe('ready');
    expect(result.days[0].summary.precipSumIn).toBeNull();
    expect(result.days[0].hours[0].precipIn).toBeNull();
  });

  it('maps legacy daily "a" to precipSumIn, defaulting to null when absent', () => {
    expect(parseLegacyDailyForecast(JSON.stringify([
      { d: 'Today', hi: 80, lo: 50, p: 20, w: 1, pv: 6.4, a: 0.31 },
      { d: 'Tomorrow', hi: 80, lo: 50, p: 20, w: 1, pv: 6.4 },
    ]))).toEqual([
      expect.objectContaining({
        summary: expect.objectContaining({ precipSumIn: 0.31 }),
      }),
      expect.objectContaining({
        summary: expect.objectContaining({ precipSumIn: null }),
      }),
    ]);
  });
});
