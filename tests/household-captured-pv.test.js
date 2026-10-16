import { expect, it } from 'vitest';
import { parseCapturedPvPerformance } from '../src/lib/household/capturedPvPerformance.js';
import { capturedPvPerformance } from './fixtures/household-captured-pv.js';
const nowMs = Date.parse('2026-10-12T03:00:35Z');
const parse = v => parseCapturedPvPerformance(JSON.stringify(v), { nowMs });
it('accepts negative skill, empty leads and paired model-specific metrics without fabricating zeroes', () => {
  const v = parse(capturedPvPerformance()); expect(v).not.toBeNull();
  expect(v.expired).toBe(false); expect(v.by_horizon['1'].models.constant_load_pv.rmse_skill).toBe(-.5);
  expect(v.by_horizon['6'].models.profiled_load_pv.mae_kwh).toBeNull();
});
it('accepts zero measured errors and null skill when persistence has zero error', () => {
  const r = capturedPvPerformance(), m = r.by_horizon['1'].models.constant_load_pv;
  Object.assign(m, { mae_kwh: 0, bias_kwh: 0, rmse_kwh: 0, persistence_mae_kwh: 0, persistence_rmse_kwh: 0, rmse_skill: null });
  expect(parse(r)).not.toBeNull();
});
it('retains stale data with an explicit expiry independent of report collection', () => {
  const r = capturedPvPerformance();
  expect(parseCapturedPvPerformance(JSON.stringify(r), { nowMs: Date.parse(r.valid_until) }).expired).toBe(true);
});
it.each([
  ['private top-level bytes', r => { r.private_path = '/private'; }],
  ['private cohort bytes', r => { r.cohort.private_path = '/private'; }],
  ['private native cohort bytes', r => { r.cohort.original_solar_cohort.credential = 'never-public'; }],
  ['authority', r => { r.automatic_actuation = true; }],
  ['calibration', r => { r.physical_calibration_qualified = true; }],
  ['potential meter scope', r => { r.potential_array_accuracy = 'qualified'; }],
  ['future report', r => { r.generated_at = '2026-10-12T04:00:30Z'; }],
  ['wrong freshness duration', r => { r.valid_until = '2026-10-12T03:31:30Z'; }],
  ['mismatched horizon', r => { r.by_horizon['6'].horizon_hours = 1; }],
  ['pair count', r => { r.by_horizon['1'].models.constant_load_pv.count = 3; }],
  ['unobserved zero error', r => { r.by_horizon['6'].models.constant_load_pv.mae_kwh = 0; }],
  ['inconsistent bias', r => { r.by_horizon['1'].models.constant_load_pv.bias_kwh = .4; }],
  ['inconsistent rmse', r => { r.by_horizon['1'].models.constant_load_pv.rmse_kwh = .2; }],
  ['inconsistent skill', r => { r.by_horizon['1'].models.constant_load_pv.rmse_skill = .5; }],
  ['missing independent days', r => { r.unique_origin_days = 0; }],
  ['future target', r => { r.by_horizon['1'].models.constant_load_pv.last_target_at = '2026-10-12T03:01:00Z'; }],
])('withholds %s', (_, mutate) => { const r = capturedPvPerformance(); mutate(r); expect(parse(r)).toBeNull(); });
it('rejects duplicate keys, oversized transport and nonfinite numeric values', () => {
  const raw = JSON.stringify(capturedPvPerformance());
  expect(parseCapturedPvPerformance(raw.replace('"cohort_id":', '"cohort_id":"' + 'a'.repeat(64) + '","cohort_id":'), { nowMs })).toBeNull();
  expect(parseCapturedPvPerformance(raw + ' '.repeat(32768), { nowMs })).toBeNull();
  expect(parseCapturedPvPerformance(raw.replace('"mae_kwh":0.3', '"mae_kwh":1e999'), { nowMs })).toBeNull();
});
it('admits an empty report only with a null latest target, rejecting nested private data and invalid clocks', async () => {
  const { emptyCapturedPvPerformance } = await import('./fixtures/household-captured-pv.js');
  expect(parse(emptyCapturedPvPerformance())).not.toBeNull();
  for (const invalid of [{ private_path: '/never-expose', raw_receipt: {} }, ['/private'], 'invalid-time', 0]) {
    const r = emptyCapturedPvPerformance(); r.last_target_at = invalid;
    expect(parse(r)).toBeNull();
  }
});
