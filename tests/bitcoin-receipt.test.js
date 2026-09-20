import { expect, it } from 'vitest';
import { bitcoinReceiptState } from '../src/lib/ui/bitcoinReceipt.js';
const now = 1800000000000;
const encode = (overrides = {}) => JSON.stringify({version: 1, field: 'bitcoin.usd', receivedAt: now, price: 81246, ...overrides});
it('uses embedded receipt time, including unchanged-price updates', () => {
  expect(bitcoinReceiptState(encode(), 81246, now).status).toBe('recent');
  expect(bitcoinReceiptState(encode(), 81246, now + 90000).status).toBe('stale');
  expect(bitcoinReceiptState(encode({receivedAt: now + 90000}), 81246, now + 90000).status).toBe('recent');
});
it('does not renew a restored receipt or infer success from retained price', () => {
  expect(bitcoinReceiptState(encode({receivedAt: now - 90000}), 81246, now).status).toBe('stale');
  expect(bitcoinReceiptState(encode({price: null}), 81246, now).status).toBe('invalid');
  expect(bitcoinReceiptState(encode(), 81247, now).status).toBe('mismatch');
});
it.each([undefined, '', 'NULL', 'UNDEF', '{}', '[]', 'null', 'bad', 'x'.repeat(513)])('rejects missing or malformed receipt %#', raw => {
  expect(bitcoinReceiptState(raw, 81246, now).status).toBe('unknown');
});
it.each([{version: 2}, {version: true}, {field: 'other'}, {extra: 1}, {receivedAt: now + 1},
  {receivedAt: 0}, {receivedAt: '1800000000000'}, {receivedAt: 1.5}, {price: 0}, {price: -1},
  {price: true}, {price: '81246'}, {price: 1.5}, {price: 9007199254740991}])('rejects invalid envelope %#', overrides => {
  expect(bitcoinReceiptState(encode(overrides), 81246, now).status).toBe('unknown');
});
it.each([NaN, Infinity, 0, -1, 9007199254740991, '1800000000000'])('rejects invalid clock %#', clock => {
  expect(bitcoinReceiptState(encode(), 81246, clock).status).toBe('unknown');
});
