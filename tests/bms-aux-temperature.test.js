import { describe, expect, it } from 'vitest';
import { freshBmsTemperatureF } from '../src/lib/battery/auxTemperature.js';

const NOW = 200_000;
function evidence(value = 29300, observedAt = NOW - 1_000) {
  return JSON.stringify({ version: 1, basis: 'discover_bms_190_native_aux_v1',
    streamEpoch: '123e4567-e89b-42d3-a456-426614174000', sequence: 3,
    recordedAt: NOW - 500,
    fields: {
      'battery.remaining_ah': { status: 'valid', reason: 'ok',
        observedAt, validUntil: observedAt + 120_000, value: 300 },
      'battery.temperature_raw': { status: 'valid', reason: 'ok',
        observedAt, validUntil: observedAt + 120_000, value },
    },
  });
}

describe('current Discover BMS temperature', () => {
  it('converts a fresh native register using the installed OpenHAB formula', () => {
    expect(freshBmsTemperatureF(evidence(), NOW)).toBe(68);
  });

  it('withholds missing, expired, malformed, and out-of-range evidence', () => {
    for (const raw of [undefined, 'UNDEF', evidence(29300, NOW - 120_000),
      evidence(22000), evidence(34000), evidence().replace('native_aux_v1', 'unknown')]) {
      expect(freshBmsTemperatureF(raw, NOW)).toBeNull();
    }
  });
});
