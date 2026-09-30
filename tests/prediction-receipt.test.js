import { describe, expect, it } from 'vitest';
import { parsePredictionReceipt, parsePreDuskTroughReceipt, selectTroughForecast } from '../src/lib/forecast/predictionReceipt.js';

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

  it('keeps diagnostic PV components out of the displayed forecast contract', () => {
    const withDiagnostics = { ...valid, pvDiagnostics: { version: 1,
      radiationKwhM2: 4.12, resourceGain: 1.3, resourceKwh: 5.356,
      directDemandKwh: 4, socReferencePct: 72, chargeDeficitKwh: 6.036,
      demandKwh: 10.036, limitingBranch: 'resource' } };
    expect(parse(withDiagnostics)).toEqual(parse(valid));
  });

  it('keeps the original SoC input proof separate from display authority', () => {
    const at = Date.parse(valid.issuedAt);
    const enriched = { ...valid, energySocOrigin: { version: 1,
      assessedAtMs: at + 1000, recordedAtMs: at, validUntilMs: at + 120000,
      streamEpoch: '123e4567-e89b-42d3-a456-426614174000',
      evidenceSha256: 'a'.repeat(64), socPct: 72 } };
    expect(JSON.stringify(enriched).length).toBeLessThanOrEqual(1024);
    expect(parse(enriched)).toEqual(parse(valid));
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

describe('separate pre-dusk trough receipt', () => {
  const lateNow = Date.parse('2026-09-24T18:10:00-06:00');
  const late = {
    version: 1, basis: 'atomic_soc_pre_dusk_v1', predictionDay: DAY,
    issuedAt: '2026-09-24T17:40:40-06:00',
    sunsetAt: '2026-09-24T18:56:19-06:00',
    morningIssuedAt: valid.issuedAt,
    socRecordedAt: '2026-09-24T17:40:29-06:00',
    socStreamEpoch: '123e4567-e89b-42d3-a456-426614174000',
    socEvidenceSha256: 'a'.repeat(64),
    socAtIssuePct: 99, overnightDropPct: 19.333,
    overnightTroughSocPct: 80,
  };
  const parseLate = (value, nowMs = lateNow) => parsePreDuskTroughReceipt(JSON.stringify(value), { nowMs });

  it('uses a source-bound later issue without rewriting morning PV provenance', () => {
    const morning = parse({ ...valid, overnightTroughSocPct: 63 }, lateNow);
    const selected = selectTroughForecast(parseLate(late));
    expect(selected).toEqual({ value: 80, basis: 'pre-dusk',
      itemName: 'Predicted_SoC_Trough_PreDusk', issuedAtMs: Date.parse(late.issuedAt),
      targetEndAtMs: Date.parse('2026-09-25T11:00:00-06:00') });
    expect(morning.pvTodayKwh).toBe(3.3);
  });

  it('withholds expired, future, mismatched, or wrong-day late evidence', () => {
    expect(parseLate({ ...late, socRecordedAt: '2026-09-24T17:37:00-06:00' })).toBeNull();
    expect(parseLate({ ...late, issuedAt: '2026-09-24T18:20:00-06:00' })).toBeNull();
    expect(parseLate({ ...late, sunsetAt: '2026-09-25T18:56:19-06:00' })).toBeNull();
    expect(parseLate({ ...late, overnightTroughSocPct: 79 })).toBeNull();
    expect(parseLate({ ...late, socStreamEpoch: undefined })).toBeNull();
    expect(parseLate({ ...late, socEvidenceSha256: 'unverified' })).toBeNull();
    expect(parseLate(late, Date.parse('2026-09-25T11:00:00-06:00'))).toBeNull();
  });

  it('never uses a morning estimate as the displayed forecast', () => {
    expect(selectTroughForecast(null)).toBeNull();
    const morning = parse({ ...valid, overnightTroughSocPct: 12 }, lateNow);
    expect(morning.overnightTroughSocPct).toBe(12);
    expect(selectTroughForecast(parseLate(late)).value).toBe(80);
  });

  it('keeps the original pre-dusk issue through its following-morning target', () => {
    for (const at of ['00:01:00', '06:40:00', '10:59:59']) {
      expect(parseLate(late, Date.parse(`2026-09-25T${at}-06:00`))?.overnightTroughSocPct).toBe(80);
    }
    expect(parseLate(late, Date.parse('2026-09-25T11:00:00-06:00'))).toBeNull();
    expect(parseLate(late, Date.parse('2026-09-26T01:00:00-06:00'))).toBeNull();
  });

  it('expires at local 11:00 across the daylight-saving transition', () => {
    const autumn = { ...late, predictionDay: '2026-10-31',
      issuedAt: '2026-10-31T16:55:00-06:00', sunsetAt: '2026-10-31T18:10:00-06:00',
      morningIssuedAt: '2026-10-31T06:40:00-06:00', socRecordedAt: '2026-10-31T16:54:50-06:00' };
    expect(parseLate(autumn, Date.parse('2026-11-01T10:59:59-07:00'))?.overnightTroughSocPct).toBe(80);
    expect(parseLate(autumn, Date.parse('2026-11-01T11:00:00-07:00'))).toBeNull();
  });
});
