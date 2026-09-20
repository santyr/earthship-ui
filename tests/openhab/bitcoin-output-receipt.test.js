import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { expect, it } from 'vitest';
const source = readFileSync(new URL('../../openhab/transform/bitcoin_output_receipt.js', import.meta.url), 'utf8');
function run(input, now = 1800000000000) {
  const forbidden = () => { throw new Error('unexpected capability'); };
  return JSON.parse(vm.runInNewContext(source, { input, Date: { now: () => now },
    require: forbidden, fetch: forbidden, Java: { type: forbidden },
    items: new Proxy({}, { get: forbidden }), actions: new Proxy({}, { get: forbidden }),
  }, { timeout: 1000 }));
}
it('preserves integer prices and timestamps unchanged receipts', () => {
  expect(run('81246')).toEqual({ version: 1, field: 'bitcoin.usd', receivedAt: 1800000000000, price: 81246 });
  expect(run('81246', 1800000030000).receivedAt).toBe(1800000030000);
});
it.each(['', '0', '-1', '01', ' 81246', '81246\n', '81246\r', '81246.0', '1e5', 'NaN',
  'Infinity', 'NULL', 'UNDEF', '9007199254740991', '9'.repeat(4096),
  'Error: token=secret', '81246\nError: private', null, 81246])
('rejects noncanonical output case %# without leaking its body', input => {
  const result = run(input);
  expect(result.price).toBeNull();
  expect(Object.keys(result)).toEqual(['version', 'field', 'receivedAt', 'price']);
  expect(JSON.stringify(result)).not.toContain('secret');
});
it.each([0, -1, NaN, Infinity, 1.5])('rejects invalid receipt clock %j', now => {
  expect(() => run('81246', now)).toThrow('invalid receipt clock');
});
