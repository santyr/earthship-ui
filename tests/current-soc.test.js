import { describe, expect, it } from 'vitest';
import { freshCurrentSoc } from '../src/lib/battery/currentSoc.js';

const NOW = 200_000;
function evidence(soc, observedAt = NOW - 1_000) {
  return JSON.stringify({ version: 1,
    streamEpoch: '123e4567-e89b-42d3-a456-426614174000',
    recordedAt: NOW - 500, status: 'valid', reason: 'ok',
    observedAt, scaleObservedAt: observedAt,
    validUntil: observedAt + 120_000, soc });
}

describe('current battery SoC display', () => {
  it('uses source-bound SoC instead of a held numeric Item', () => {
    expect(freshCurrentSoc({ BMS_Comms_Status: 'OK', BMS_DevicePresent: '1',
      BMS_SOC: '10', BMS_SOC_Evidence_JSON: evidence(75) }, NOW)).toBe(75);
  });

  it('withholds a current percentage without fresh source and healthy BMS', () => {
    const healthy = { BMS_Comms_Status: 'OK', BMS_DevicePresent: '1',
      BMS_SOC: '10', BMS_SOC_Evidence_JSON: evidence(75) };
    for (const changed of [
      { BMS_SOC_Evidence_JSON: undefined },
      { BMS_SOC_Evidence_JSON: evidence(75, NOW - 120_000) },
      { BMS_Comms_Status: 'ERROR' },
      { BMS_DevicePresent: '0' },
    ]) expect(freshCurrentSoc({ ...healthy, ...changed }, NOW)).toBeNull();
  });
});
