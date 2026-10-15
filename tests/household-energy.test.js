import { expect, it } from 'vitest';
import { energyObservation, energyPerformance, ENERGY_NOW } from './fixtures/household-energy.js';
import { parseEnergyObservation, parseEnergyPerformance } from '../src/lib/household/energyObservation.js';
it('preserves distinct potential/capture and exact elapsed forecast hours without renewing freshness', () => {
  const raw = JSON.stringify(energyObservation()); const view = parseEnergyObservation(raw, { nowMs: ENERGY_NOW });
  expect(view.potential_pv_24h_kwh).toBe(12); expect(view.captured_pv_24h_kwh).toBe(9.6); expect(view.trajectory).toHaveLength(24);
  expect(view.expired).toBe(false); expect(parseEnergyObservation(raw, { nowMs: ENERGY_NOW + 15 * 60000 }).expired).toBe(true);
});
it.each(['private', 'authority', 'gap', 'totals', 'storage', 'future', 'duplicates'])('withholds malformed %s energy data', damage => {
  const row = energyObservation();
  if (damage === 'private') row.path = '/private';
  if (damage === 'authority') row.automatic_actuation = true;
  if (damage === 'gap') row.trajectory[2].at = row.trajectory[1].at;
  if (damage === 'totals') row.potential_pv_24h_kwh = 1;
  if (damage === 'storage') row.trajectory[0].nominal_soc_pct = null;
  if (damage === 'future') row.generated_at = '2026-10-16T16:55:32Z';
  let raw = JSON.stringify(row); if (damage === 'duplicates') raw = raw.replace('{', '{"status":"private",');
  expect(parseEnergyObservation(raw, { nowMs: ENERGY_NOW })).toBeNull();
});
it('keeps matched three-model errors and empty horizons distinct', () => {
  const view = parseEnergyPerformance(JSON.stringify(energyPerformance()), { nowMs: ENERGY_NOW });
  expect(view.by_horizon['1'].mae_soc_pct).toEqual({ pv_load_scenario: 1, constant_power: 2, hold_soc: 3 });
  expect(view.by_horizon['6'].mae_soc_pct).toBeNull(); expect(view.expired).toBe(false);
});
it.each(['private', 'authority', 'counts', 'arithmetic', 'immature', 'nested'])('withholds invalid %s performance', damage => {
  const row = energyPerformance(); const first = row.by_horizon['1'];
  if (damage === 'private') row.credentials = 'private';
  if (damage === 'authority') row.graduated = true;
  if (damage === 'counts') first.attempted_count = 0;
  if (damage === 'arithmetic') first.rmse_skill.constant_power = 0.9;
  if (damage === 'immature') first.last_target_at = row.generated_at;
  if (damage === 'nested') first.mae_soc_pct.private = 1;
  expect(parseEnergyPerformance(JSON.stringify(row), { nowMs: ENERGY_NOW })).toBeNull();
});
