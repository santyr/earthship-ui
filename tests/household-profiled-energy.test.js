import { expect, it } from 'vitest';
import { profiledObservation, profiledPerformance, PROFILE_NOW } from './fixtures/household-profiled-energy.js';
import { parseProfiledObservation, parseProfiledPerformance } from '../src/lib/household/profiledObservation.js';
it('retains separate hourly load and SoC scenarios with source expiry', () => {
  const raw = JSON.stringify(profiledObservation()); const v = parseProfiledObservation(raw, { nowMs: PROFILE_NOW });
  expect(v.total_ac_kwh).toBe(9.6); expect(v.trajectory[0].profiled_ac_w).toBe(400); expect(v.trajectory[0].constant_ac_w).toBe(500);
  expect(v.expired).toBe(false); expect(parseProfiledObservation(raw, { nowMs: PROFILE_NOW + 15 * 60000 }).expired).toBe(true);
});
it.each(['authority', 'private', 'gap', 'total', 'source_clock', 'expiry', 'support', 'spread', 'constant', 'duplicate'])('withholds invalid %s profile', damage => {
  const v = profiledObservation();
  if (damage === 'authority') v.automatic_actuation = true;
  if (damage === 'private') v.path = '/private';
  if (damage === 'gap') v.trajectory[2].at = v.trajectory[1].at;
  if (damage === 'total') v.total_ac_kwh = 1;
  if (damage === 'source_clock') v.trained_through = '2026-10-16T06:00:00Z';
  if (damage === 'expiry') v.valid_until = v.model_valid_until;
  if (damage === 'support') v.trajectory[0].minimum_support_days = 2;
  if (damage === 'spread') v.trajectory[0].training_spread_ac_w = [450, 500];
  if (damage === 'constant') v.trajectory[1].constant_ac_w = 501;
  let raw = JSON.stringify(v); if (damage === 'duplicate') raw = raw.replace('{', '{"status":"conditional",');
  expect(parseProfiledObservation(raw, { nowMs: PROFILE_NOW })).toBeNull();
});
it('keeps matched demand and four SoC errors distinct from collecting horizons', () => {
  const v = parseProfiledPerformance(JSON.stringify(profiledPerformance()), { nowMs: PROFILE_NOW });
  expect(v.by_horizon['1'].load.mae_kwh.profiled_load).toBe(.05); expect(v.by_horizon['1'].soc.mae_soc_pct.hold_soc).toBe(3);
  expect(v.by_horizon['6'].load.mae_kwh).toBeNull(); expect(v.evaluation_scope).toBe('rolling_as_issued_model_versions');
});
it.each(['authority', 'count', 'versions', 'arithmetic', 'extra', 'future'])('withholds invalid %s profile metrics', damage => {
  const v = profiledPerformance(); const row = v.by_horizon['1'].load;
  if (damage === 'authority') v.graduated = true;
  if (damage === 'count') row.attempted_count = 0;
  if (damage === 'versions') row.model_version_count = 2;
  if (damage === 'arithmetic') row.rmse_kwh = { profiled_load: .001, current_load: .1 };
  if (damage === 'extra') row.private = 'data';
  if (damage === 'future') v.generated_at = '2026-10-16T00:00:00Z';
  expect(parseProfiledPerformance(JSON.stringify(v), { nowMs: PROFILE_NOW })).toBeNull();
});
