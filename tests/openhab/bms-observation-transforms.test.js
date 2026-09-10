import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const scripts = ['raw', 'scale'];
function execute(field, input, now) {
  const source = readFileSync(new URL(
    `../../openhab/transform/bms_soc_${field}_observation.js`, import.meta.url), 'utf8');
  let calls = 0;
  const forbidden = () => { throw new Error('forbidden transformation capability'); };
  const result = vm.runInNewContext(source, {
    input, Date: { now: () => { calls += 1; return now; } },
    require: forbidden, fetch: forbidden, setTimeout: forbidden,
    setInterval: forbidden, Java: { type: forbidden },
    items: new Proxy({}, { get: forbidden }),
    actions: new Proxy({}, { get: forbidden }),
    cache: new Proxy({}, { get: forbidden }),
  }, { timeout: 1000 });
  expect(calls).toBe(1);
  expect(typeof result).toBe('string');
  return JSON.parse(result);
}

describe.each(scripts)('%s source observation', field => {
  it.each(['99', '0', '-1', '-32768', '65535', '1.5', 'NULL', 'UNDEF', '',
    ' 99 ', '12 %', 'NaN', 'Infinity', '1e2', '"quoted"'])
  ('retains exact input text %j in a closed record', input => {
    expect(execute(field, input, 1789072800000)).toEqual({
      version: 1, field, observedAt: 1789072800000, value: input,
    });
  });
  it('stamps each unchanged observation without mutating earlier evidence', () => {
    const first = execute(field, '99', 1789072800000);
    const second = execute(field, '99', 1789072805000);
    expect(first.observedAt).toBe(1789072800000);
    expect(second.observedAt).toBe(1789072805000);
    expect(first.value).toBe(second.value);
  });
  it('does not hide clock rollback from the downstream validator', () => {
    expect(execute(field, '99', 1789072800000).observedAt).toBe(1789072800000);
    expect(execute(field, '99', 1789072799000).observedAt).toBe(1789072799000);
  });
});
