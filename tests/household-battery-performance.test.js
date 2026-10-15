import { expect, it } from 'vitest';
import { batteryPerformance } from './fixtures/household-battery-performance.js';
import { parseBatteryPerformance } from '../src/lib/household/batteryPerformance.js';
const nowMs = Date.parse('2026-10-12T03:00:35Z');
it('preserves original errors and marks historical reports stale without renewing clocks', () => {
  const raw = JSON.stringify(batteryPerformance()), current = parseBatteryPerformance(raw, { nowMs });
  expect(current.by_horizon['1'].mae_soc_pct).toEqual({ constant_power: 2.55859375, hold_soc: 5 });
  expect(current.expired).toBe(false);
  const old = parseBatteryPerformance(raw, { nowMs: nowMs + 31 * 60_000 });
  expect(old.expired).toBe(true); expect(old.generated_at).toBe('2026-10-12T03:00:30Z');
});
it.each(['private', 'authority', 'count', 'nan', 'clock', 'target', 'empty', 'units', 'days', 'nested'])(
  'withholds malformed %s reports', damage => {
    const row = batteryPerformance();
    if (damage === 'private') row.original_path = '/private';
    if (damage === 'authority') row.automatic_actuation = true;
    if (damage === 'count') row.by_horizon['1'].count = 2;
    if (damage === 'nan') row.by_horizon['1'].mae_soc_pct.constant_power = null;
    if (damage === 'clock') row.generated_at = '2026-10-13T03:00:30Z';
    if (damage === 'target') row.by_horizon['1'].last_target_at = row.generated_at;
    if (damage === 'empty') row.by_horizon['6'].mae_soc_pct = { constant_power: 0, hold_soc: 0 };
    if (damage === 'units') row.sampling_basis = 'every_five_minutes';
    if (damage === 'days') row.unique_origin_days = 0;
    if (damage === 'nested') row.by_horizon['1'].mae_soc_pct.private = 'secret';
    expect(parseBatteryPerformance(JSON.stringify(row), { nowMs })).toBeNull();
  });
it('refuses duplicate keys before exposing any original body', () => {
  const raw = JSON.stringify(batteryPerformance()).replace('{', '{"cohort_id":{"private":"secret"},');
  expect(parseBatteryPerformance(raw, { nowMs })).toBeNull();
});
