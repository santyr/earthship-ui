import { expect, it } from 'vitest';
import { parseSourceTimestamp } from '../src/lib/openhab/timestamp.js';

const NOW = Date.parse('2026-09-05T18:00:00Z');
it.each([
  [NOW, NOW],
  ['2026-09-05T11:59:59.123456789-0600', NOW - 877],
  ['2026-09-05T11:59:59.123-0600[America/Denver]', NOW - 877],
  ['2026-09-05T17:59:59+0000', NOW - 1000],
  ['2026-09-05T11:59:59.123456789-06:00[America/Denver]', NOW - 877],
  ['2026-09-05T17:59:59Z', NOW - 1000],
  ['2024-02-29T00:00:00+00:00', Date.parse('2024-02-29T00:00:00Z')],
])('parses %s without changing its instant', (value, expected) => {
  expect(parseSourceTimestamp(value, NOW)).toBe(expected);
});
it.each([
  undefined, null, '', 'NULL', 'UNDEF', true, {}, [], NaN, Infinity,
  0, -1, NOW + 1, String(NOW), '2026-09-05T18:00:01Z',
  '2026-09-05T17:00:00', '2026-02-29T01:00:00Z',
  '2026-04-31T01:00:00Z', '2026-13-01T01:00:00Z',
  '2026-01-00T01:00:00Z', '2026-01-01T24:00:00Z',
  '2026-01-01T12:60:00Z', '2026-01-01T12:00:60Z',
  '2026-01-01T12:00:00+24:00', '2026-01-01T12:00:00+01:60',
  '2026-01-01T12:00:00+2400', '2026-01-01T12:00:00+0160',
  '2026-01-01T12:00:00+060', '2026-09-05T12:00:01-0600',
  '2026-01-01T12:00:00Z[]', '2026-01-01T12:00:00Z[broken',
  '2026-01-01T12:00:00Z trailing',
])('rejects unusable evidence %s', (value) => {
  expect(parseSourceTimestamp(value, NOW)).toBeNull();
});
