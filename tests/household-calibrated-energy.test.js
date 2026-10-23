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

it('accepts a versioned calibration policy without changing the numerical model identity',()=>{
 const v=calibratedEnergy();v.schema='earthship-household-calibrated-energy-observation/v3';v.calibration_policy_sha256='b'.repeat(64);
 const parsed=parseCalibratedEnergy(JSON.stringify(v),{nowMs:CALIBRATED_NOW});expect(parsed?.calibration_policy_sha256).toBe('b'.repeat(64));
 v.calibration_policy_sha256='bad';expect(parseCalibratedEnergy(JSON.stringify(v),{nowMs:CALIBRATED_NOW})).toBeNull();
});

it('accepts the new component model with explicit native and raw fallback support',async()=>{
 const {componentEnergy}=await import('./fixtures/calibrated-energy.js');const v=componentEnergy();
 const parsed=parseCalibratedEnergy(JSON.stringify(v),{nowMs:CALIBRATED_NOW});
 expect(parsed?.procedure_sha256).toBe(v.procedure_sha256);expect(parsed?.source_support.fallback_hours).toBe(13);
});
it.each(['scope','support','mode','deadline','baseline'])('refuses unsupported new component %s',async damage=>{
 const {componentEnergy}=await import('./fixtures/calibrated-energy.js');const v=componentEnergy();
 if(damage==='scope')v.calibration_scope='native_components_only';
 if(damage==='support')v.source_support.fallback_reasons.no_daylight_support=12;
 if(damage==='mode')v.calibration_mode='qualified';
 if(damage==='deadline'){v.generated_at=new Date(Date.parse(v.issued_at)+86000).toISOString();}
 if(damage==='baseline')v.baseline_rule='old_total_radiation';
 expect(parseCalibratedEnergy(JSON.stringify(v),{nowMs:CALIBRATED_NOW+120000})).toBeNull();
});
