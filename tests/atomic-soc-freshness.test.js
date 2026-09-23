import { expect, it } from 'vitest';
import { atomicSocFreshness } from '../src/lib/alerts/atomicSoc.js';

const NOW = Date.parse('2026-09-23T23:40:00Z');
const EPOCH = '123e4567-e89b-42d3-a456-426614174000';
function receipt(changes = {}) {
  return JSON.stringify({ version: 1, streamEpoch: EPOCH, recordedAt: NOW,
    status: 'valid', reason: 'ok', observedAt: NOW - 1000,
    scaleObservedAt: NOW - 1000, validUntil: NOW + 119_000,
    soc: 75, ...changes });
}

it('accepts a fresh unchanged-value atomic SoC receipt', () => {
  expect(atomicSocFreshness(receipt(), NOW)).toEqual({
    recordedAt: NOW, validUntil: NOW + 119_000, soc: 75,
  });
});

it.each([
  null, 'UNDEF', receipt({ status: 'invalid' }), receipt({ reason: 'stale' }),
  receipt({ recordedAt: NOW + 1 }), receipt({ observedAt: NOW + 1 }),
  receipt({ scaleObservedAt: NOW + 1 }), receipt({ validUntil: NOW + 120_000 }),
  receipt({ soc: -1 }), receipt({ soc: 101 }), receipt({ soc: null }),
  receipt({ streamEpoch: 'not-a-uuid' }),
  receipt().replace('"soc":75', '"soc":75,"soc":76'),
  receipt() + ' ',
])('refuses invalid, duplicate or noncanonical receipt %s', raw => {
  expect(atomicSocFreshness(raw, NOW)).toBeNull();
});

it('expires from atomic source validity even when SoC did not change', () => {
  expect(atomicSocFreshness(receipt(), NOW + 118_999)).not.toBeNull();
  expect(atomicSocFreshness(receipt(), NOW + 119_000)).toBeNull();
});
