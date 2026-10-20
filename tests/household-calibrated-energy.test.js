import { expect, it } from 'vitest';
import { parseCalibratedEnergy } from '../src/lib/household/calibratedEnergy.js';
import { calibratedEnergy, CALIBRATED_NOW } from './fixtures/calibrated-energy.js';
it('keeps the separate same-issue calibrated scenario and actual training dates', () => {
 const v = calibratedEnergy(), parsed = parseCalibratedEnergy(JSON.stringify(v), { nowMs: CALIBRATED_NOW });
 expect(parsed.calibrated_potential_kwh).toBe(14); expect(parsed.load_trained_through).toBe(v.load_trained_through);
 expect(parseCalibratedEnergy(JSON.stringify(v), { nowMs: CALIBRATED_NOW + 20 * 60000 }).expired).toBe(true);
});
it.each(['authority', 'field', 'clock', 'target', 'soc', 'total', 'missingPoint', 'badTraining'])('rejects malformed %s', damage => {
 const v = calibratedEnergy();
 if (damage === 'authority') v.automatic_actuation = true;
 if (damage === 'field') v.private_path = '/private';
 if (damage === 'clock') v.generated_at = new Date(CALIBRATED_NOW + 1).toISOString();
 if (damage === 'target') v.trajectory[0].at = v.trajectory[1].at;
 if (damage === 'soc') v.trajectory[0].calibrated_soc_pct = 101;
 if (damage === 'total') v.load_total_ac_kwh = 0;
 if (damage === 'missingPoint') v.trajectory.pop();
 if (damage === 'badTraining') v.load_trained_through = '2027-01-01T00:00:00Z';
 expect(parseCalibratedEnergy(JSON.stringify(v), { nowMs: CALIBRATED_NOW })).toBeNull();
});
it('keeps qualified demand and PV when storage initial conditions are unavailable',()=>{
 const v=calibratedEnergy();v.profiled_storage_status='unavailable';v.profiled_storage_reason='required_source_unavailable';
 for(const key of ['initial_soc_pct','nominal_bank_kwh','profiled_captured_pv_kwh','raw_profiled_captured_pv_kwh'])v[key]=null;
 for(const row of v.trajectory)row.calibrated_soc_pct=row.raw_soc_pct=null;
 const parsed=parseCalibratedEnergy(JSON.stringify(v),{nowMs:CALIBRATED_NOW});expect(parsed.load_total_ac_kwh).toBe(9.6);expect(parsed.calibrated_potential_kwh).toBe(14);
});
