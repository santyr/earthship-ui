import { describe, expect, it } from 'vitest';
import * as presentation from '../src/lib/energy/storageForecast.js';
import { calibratedEnergy, CALIBRATED_NOW } from './fixtures/calibrated-energy.js';
import { energyObservation } from './fixtures/household-energy.js';
const render = (value, options = {}) => presentation.storageForecastPresentation?.(JSON.stringify(value), { nowMs: CALIBRATED_NOW, ...options });
describe('Energy predicted SoC', () => {
  it('uses the qualified calibrated trajectory with its original issue and hourly targets', () => {
    const value = calibratedEnergy();
    const result = render(value);
    expect(result?.source).toBe('learned_load_calibrated_pv');
    expect(result.points).toEqual([
      [Date.parse(value.issued_at), value.initial_soc_pct],
      ...value.trajectory.map(p => [Date.parse(p.at), p.calibrated_soc_pct]),
    ]);
    expect(result.validUntilMs).toBe(Date.parse(value.valid_until));
  });
  it('expires at the original deadline rather than extending a retrieved issue', () => {
    const value = calibratedEnergy();
    expect(render(value, { nowMs: Date.parse(value.valid_until) })).toBeNull();
  });
  it('can display the separately qualified constant-load fallback without inventing calibration', () => {
    const fallback = energyObservation();
    const result = render(null, { fallbackRaw: JSON.stringify(fallback) });
    expect(result?.source).toBe('constant_load_raw_pv');
    expect(result.points.at(-1)).toEqual([Date.parse(fallback.trajectory.at(-1).at), 100]);
  });
  it('does not render invalid, expired, or storage-unavailable observations', () => {
    expect(render(null)).toBeNull();
    const value = calibratedEnergy(); value.automatic_actuation = true;
    expect(render(value)).toBeNull();
    const raw = energyObservation(); raw.storage_status = 'unavailable';
    expect(render(null, { fallbackRaw: JSON.stringify(raw) })).toBeNull();
    expect(render(null, { fallbackRaw: JSON.stringify(energyObservation()), nowMs: CALIBRATED_NOW + 3600000 })).toBeNull();
  });
});
