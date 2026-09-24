import { describe, expect, it } from 'vitest';
import { parsePredictionReceipt } from '../src/lib/forecast/predictionReceipt.js';

const DAY = '2026-09-24';
const NOW = Date.parse('2026-09-24T07:00:00-06:00');
const valid = {
  version: 1,
  predictionDay: DAY,
  issuedAt: '2026-09-24T06:40:29-06:00',
  pvTodayKwh: 3.3,
  curtailmentHoursToday: 0,
  overnightTroughSocPct: null,
  thermalAdvisory: 'none|No thermal action needed',
};

const parse = (value, nowMs = NOW) => parsePredictionReceipt(JSON.stringify(value), { nowMs });

describe('dated once-daily forecast receipt', () => {
  it('accepts current-day provenance and retains valid zero and null values', () => {
    expect(parse(valid)).toEqual({ predictionDay: DAY,
      issuedAtMs: Date.parse(valid.issuedAt), pvTodayKwh: 3.3,
      curtailmentHoursToday: 0, overnightTroughSocPct: null,
      thermalAdvisory: 'none|No thermal action needed' });
  });

  it('withholds yesterday after local midnight, even if direct Items hold values', () => {
    expect(parse(valid, Date.parse('2026-09-25T00:01:00-06:00'))).toBeNull();
  });

  it('rejects future, malformed, missing and unbounded receipts', () => {
    expect(parse({ ...valid, issuedAt: '2026-09-25T06:40:29-06:00' })).toBeNull();
    expect(parse({ ...valid, predictionDay: '2026-09-23' })).toBeNull();
    expect(parse({ ...valid, curtailmentHoursToday: 25 })).toBeNull();
    expect(parse({ ...valid, overnightTroughSocPct: undefined })).toBeNull();
    expect(parse({ ...valid, thermalAdvisory: undefined })).toBeNull();
    expect(parsePredictionReceipt('UNDEF', { nowMs: NOW })).toBeNull();
    expect(parsePredictionReceipt('x'.repeat(1025), { nowMs: NOW })).toBeNull();
  });
});
