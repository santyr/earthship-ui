import { describe, expect, it } from 'vitest';
import { energyForecastPresentation } from '../src/lib/energy/forecastPresentation.js';
import { energyForecastFixture } from './fixtures/energyForecast.js';

const nowMs = Date.parse('2026-10-24T12:46:00Z');
const present = value => energyForecastPresentation(JSON.stringify(value), { nowMs });

describe('curtailment from the active energy forecast', () => {
  it('shows the potential energy the storage scenario cannot capture, over the same 24 hours', () => {
    expect(present(energyForecastFixture())).toMatchObject({
      curtailment24hKwh: 3, curtailmentPct: 25,
    });
  });

  it('retains zero when all potential is captured, including floating-point roundoff', () => {
    const value = energyForecastFixture();
    value.captured_pv_24h_kwh = 12 + 1e-8;
    value.trajectory.forEach(row => { row.captured_pv_kwh = .5; });
    expect(present(value)).toMatchObject({ curtailment24hKwh: 0, curtailmentPct: 0 });
  });

  it('does not infer zero curtailment when PV is available but storage inputs are missing', () => {
    const value = energyForecastFixture();
    Object.assign(value, { storage_status: 'unavailable', storage_reason: 'soc_unavailable',
      captured_pv_24h_kwh: null, household_ac_load_w_assumption: null,
      initial_soc_pct: null, nominal_bank_kwh: null });
    value.trajectory.forEach(row => Object.assign(row, { captured_pv_kwh: null, nominal_soc_pct: null }));
    expect(present(value)).toMatchObject({ potential24hKwh: 12,
      curtailment24hKwh: null, curtailmentPct: null });
  });

  it('handles a valid night-only forecast without dividing by zero', () => {
    const value = energyForecastFixture();
    Object.assign(value, { potential_pv_24h_kwh: 0, potential_pv_remaining_today_kwh: 0, captured_pv_24h_kwh: 0 });
    value.trajectory.forEach(row => Object.assign(row, { potential_pv_kwh: 0, captured_pv_kwh: 0 }));
    expect(present(value)).toMatchObject({ curtailment24hKwh: 0, curtailmentPct: 0 });
  });

  it('withholds expired, future, malformed and inconsistent forecasts', () => {
    const value = energyForecastFixture();
    expect(energyForecastPresentation(JSON.stringify(value), { nowMs: Date.parse(value.valid_until) })).toBeNull();
    expect(present(energyForecastFixture('2026-10-24T13:00:00Z'))).toBeNull();
    expect(energyForecastPresentation('UNDEF', { nowMs })).toBeNull();
    expect(present({ ...value, captured_pv_24h_kwh: 13 })).toBeNull();
  });
});
