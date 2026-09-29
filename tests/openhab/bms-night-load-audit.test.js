import { describe, expect, it } from 'vitest';
import { auditNightLoad } from '../../openhab/scripts/bms_night_load_audit.mjs';

const startMs = 1800000000000;
const endMs = startMs + 9 * 3600000;
const row = (time, state) => ({ time, state: String(state) });

describe('bounded read-only BMS night load audit', () => {
  it('uses a time-weighted held average with a prior carry', () => {
    const rows = [row(startMs - 1000, 100)];
    for (let minute = 1; minute <= 540; minute++) {
      rows.push(row(startMs + minute * 60000, minute >= 60 ? 200 : 100));
    }
    const result = auditNightLoad(rows, { startMs, endMs });
    expect(result.averageW).toBeCloseTo((100 + 8 * 200) / 9, 1);
    expect(result.carryAgeSeconds).toBe(1);
    expect(result.sourceFreshnessQualified).toBe(false);
  });

  it('refuses missing or stale carry, ambiguous ordering and source gaps', () => {
    const settings = { startMs, endMs };
    expect(() => auditNightLoad([row(startMs + 1, 100)], settings)).toThrow('missing start carry');
    expect(() => auditNightLoad([row(startMs - 121000, 100)], settings)).toThrow('stale');
    expect(() => auditNightLoad([row(startMs, 100), row(startMs, 101)], settings)).toThrow('unordered');
    expect(() => auditNightLoad([row(startMs, 100), row(startMs + 121000, 100)], settings)).toThrow('source gap');
    expect(() => auditNightLoad([row(startMs, -1)], settings)).toThrow('invalid');
  });

  it('refuses incomplete windows and future look-ahead rows', () => {
    const settings = { startMs, endMs };
    expect(() => auditNightLoad([], { startMs, endMs: startMs + 3600000 })).toThrow('bounded');
    expect(() => auditNightLoad([row(startMs, 100), row(endMs + 1, 100)], settings)).toThrow('out-of-window');
  });
});
