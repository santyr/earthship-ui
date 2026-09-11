import { expect, it } from 'vitest';
import { estimateDailyLoadKWh as energy } from '../../src/lib/ui/dailyLoad.js';
const HOUR = 3_600_000;
const point = (time, state, unit) => ({ time, state, ...(unit ? { unit } : {}) });

it('integrates a single held midnight state through now', () => {
  expect(energy([point(0, '1000')], 0, 2 * HOUR)).toBe(2);
});
it('weights change intervals, including the final tail, without interpolating ramps', () => {
  expect(energy([point(0, '1000'), point(HOUR, '2000')], 0, 3 * HOUR)).toBe(5);
});
it('sorts changes and ignores out-of-window look-ahead', () => {
  expect(energy([point(HOUR, '2000'), point(0, '1000'), point(2 * HOUR, '999999'), point(-HOUR, '999999')], 0, 2 * HOUR)).toBe(3);
});
it.each([[], [point(HOUR, '1000')], [point(-HOUR, '1000')]])('refuses missing midnight coverage: %j', rows => {
  expect(energy(rows, 0, 2 * HOUR)).toBeNull();
});
it.each(['UNDEF', 'NULL', '', null, 'NaN', 'Infinity', '-100', '12junk', '1 kW'])('does not bridge invalid state %s', state => {
  expect(energy([point(0, 1000), point(HOUR, state)], 0, 2 * HOUR)).toBeNull();
});
it('accepts W units and scientific notation but refuses an incompatible unit', () => {
  expect(energy([point(0, '1e3 W', 'W')], 0, HOUR)).toBe(1);
  expect(energy([point(0, '1', 'kW')], 0, HOUR)).toBeNull();
});
it('rejects conflicting equal-time values but accepts identical duplicates', () => {
  expect(energy([point(0, 1000), point(0, 1001)], 0, HOUR)).toBeNull();
  expect(energy([point(0, 1000), point(0, 1000)], 0, HOUR)).toBe(1);
});
it('handles elapsed DST day lengths rather than assuming 24 hours', () => {
  for (const [start, end, hours] of [
    ['2026-03-08T00:00:00-07:00', '2026-03-09T00:00:00-06:00', 23],
    ['2026-11-01T00:00:00-06:00', '2026-11-02T00:00:00-07:00', 25],
  ]) expect(energy([point(Date.parse(start), 1000)], Date.parse(start), Date.parse(end))).toBe(hours);
});
it('handles zero duration and rejects invalid ranges, timestamps and overflow', () => {
  expect(energy([], 0, 0)).toBe(0);
  expect(energy([], 1, 0)).toBeNull();
  expect(energy([], NaN, HOUR)).toBeNull();
  expect(energy([point('bad', 1000)], 0, HOUR)).toBeNull();
  expect(energy([point(0, '1e308')], 0, HOUR)).toBeNull();
});
