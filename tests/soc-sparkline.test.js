import { describe, expect, it } from 'vitest';
import { freshSocSparkline } from '../src/lib/charts/socSparkline.js';

const NOW = Date.parse('2026-09-24T17:00:00Z');
const RECORDED = NOW - 1_000;
const HISTORY = [{ time: NOW - 60_000, state: '76 %' }];

function receipt(changes = {}) {
  return JSON.stringify({
    version: 1,
    streamEpoch: '123e4567-e89b-42d3-a456-426614174000',
    recordedAt: RECORDED,
    status: 'valid',
    reason: 'ok',
    observedAt: NOW - 2_000,
    scaleObservedAt: NOW - 2_000,
    validUntil: NOW + 118_000,
    soc: 75,
    ...changes,
  });
}

describe('compact SoC chart endpoint', () => {
  it('appends a fresh receipt at its actual time and holds that value to now', () => {
    expect(freshSocSparkline(HISTORY, receipt(), NOW, 75)).toEqual({
      data: [...HISTORY, { time: RECORDED, state: 75 }],
      heldUntil: NOW,
    });
  });

  it('does not invent a current tail from stale or inconsistent evidence', () => {
    expect(freshSocSparkline(HISTORY, receipt({ validUntil: NOW }), NOW, 75)).toEqual({
      data: HISTORY, heldUntil: null,
    });
    expect(freshSocSparkline(HISTORY, receipt(), NOW, 76)).toEqual({
      data: HISTORY, heldUntil: null,
    });
    expect(freshSocSparkline([], receipt(), NOW, 75)).toEqual({
      data: [], heldUntil: null,
    });
    expect(freshSocSparkline([{ time: NOW, state: 75 }], receipt(), NOW, 75)).toEqual({
      data: [{ time: NOW, state: 75 }], heldUntil: null,
    });
  });

  it('holds existing receipt samples only when their values match', () => {
    const match = [{ time: RECORDED, state: '75 %' }];
    const mismatch = [{ time: RECORDED, state: '74 %' }];
    expect(freshSocSparkline(match, receipt(), NOW, 75)).toEqual({ data: match, heldUntil: NOW });
    expect(freshSocSparkline(mismatch, receipt(), NOW, 75)).toEqual({ data: mismatch, heldUntil: null });
  });
});
