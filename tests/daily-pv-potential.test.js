import { expect, it } from 'vitest';
import { parseDailyPvPotential, dailyPvForDate } from '../src/lib/energy/dailyPvPotential.js';
import { fixture, now } from './fixtures/daily-pv-potential.js';
it('provides independent daily array potential with expiry preserved',()=>{
 const raw=JSON.stringify(fixture());const view=parseDailyPvPotential(raw,{nowMs:now});expect(view).not.toBeNull();
 expect(dailyPvForDate(view,'2026-10-19')).toEqual(expect.objectContaining({potentialKwh:1.25,scope:'remaining'}));
 expect(parseDailyPvPotential(raw,{nowMs:now+90*60000})).toBeNull();expect(dailyPvForDate(view,'2026-10-20')).toBeNull();
});
it.each(['authority','unknownField','nan','negative','wrongDay','duplicateDay','missingCoverage','badTimezone','tooLong'])('rejects %s',damage=>{
 const v=fixture();if(damage==='authority')v.automatic_actuation=true;
 if(damage==='unknownField')v.private_path='/private';if(damage==='nan')v.days[0].potentialKwh=null;
 if(damage==='negative')v.days[0].potentialKwh=-1;if(damage==='wrongDay')v.days[0].date='2026-10-21';
 if(damage==='duplicateDay')v.days.push({...v.days[0]});if(damage==='missingCoverage')v.days[0].throughAt='2026-10-20T05:00:00Z';
 if(damage==='badTimezone')v.timezone='UTC';if(damage==='tooLong')v.validUntil=new Date(now+91*60000).toISOString();
 expect(parseDailyPvPotential(JSON.stringify(v),{nowMs:now})).toBeNull();
});
it('retains unknown weather coverage as unavailable rather than zero generation',()=>{
 const v=fixture();Object.assign(v.days[0],{status:'unavailable',reason:'incomplete_weather_or_geometry',potentialKwh:null});
 const view=parseDailyPvPotential(JSON.stringify(v),{nowMs:now});expect(view).not.toBeNull();expect(dailyPvForDate(view,'2026-10-19')).toBeNull();
});

it('accepts explicit provisional short-horizon calibration while keeping raw potential',async()=>{
 const {calibratedFixture}=await import('./fixtures/daily-pv-potential.js');const v=calibratedFixture();
 const parsed=parseDailyPvPotential(JSON.stringify(v),{nowMs:now});expect(parsed?.days[0].uncalibratedPotentialKwh).toBe(1.5);
 v.calibration.applyThroughAt=new Date(now+48*3600000).toISOString();expect(parseDailyPvPotential(JSON.stringify(v),{nowMs:now})).toBeNull();
});


it('accepts the extended policy with its own identity and rejects an altered scope',async()=>{
 const {calibratedFixture}=await import('./fixtures/daily-pv-potential.js');const v=calibratedFixture();
 v.schema='earthship-daily-pv-potential/v3';v.confidence='provisional_empirical_supported_horizon';
 v.calibration.policySha256='f'.repeat(64);v.calibration.applyThroughAt=new Date(now+336*3600000).toISOString();v.days[0].calibrationScope='empirical_supported_horizon';
 expect(parseDailyPvPotential(JSON.stringify(v),{nowMs:now})?.calibration.policySha256).toBe('f'.repeat(64));
 v.calibration.applyThroughAt=new Date(now+337*3600000).toISOString();expect(parseDailyPvPotential(JSON.stringify(v),{nowMs:now})).toBeNull();
});

it('accepts the explicit native-component production fit without importing old skill claims',async()=>{
 const {componentFixture}=await import('./fixtures/daily-pv-potential.js');const value=componentFixture();
 const parsed=parseDailyPvPotential(JSON.stringify(value),{nowMs:now});
 expect(parsed?.calibration.mode).toBe('experimental_production');expect(parsed?.days[0].calibrationScope).toBe('native_components_only');
 expect(parsed?.calibration.localTargetDates).toBe(29);expect(parsed?.calibration.baselineMaeW).toBeUndefined();
 value.calibration.physicalCalibrationQualified=true;expect(parseDailyPvPotential(JSON.stringify(value),{nowMs:now})).toBeNull();
});

it('keeps declared raw component fallbacks separate from the trained native coefficient',async()=>{
 const {componentFixture}=await import('./fixtures/daily-pv-potential.js');const value=componentFixture();value.calibration.mode='raw_component_fallback';
 Object.assign(value.days[0],{calibrationScope:'raw_total_only_fallback',potentialKwh:1.5,
  sourceSupport:{native_hours:0,fallback_hours:9,fallback_reasons:{native_direct_unavailable:9}}});
 expect(parseDailyPvPotential(JSON.stringify(value),{nowMs:now})?.days[0].potentialKwh).toBe(1.5);
 value.days[0].potentialKwh=1.2;expect(parseDailyPvPotential(JSON.stringify(value),{nowMs:now})).toBeNull();
});

it('refuses malformed component provenance and stale raw/source windows',async()=>{
 const {componentFixture}=await import('./fixtures/daily-pv-potential.js');
 for(const change of [v=>v.calibration.targets=23,v=>v.calibration.modelSha256='wrong',v=>v.days[0].sourceSupport.private_path='/private',
  v=>v.validUntil=v.generatedAt,v=>v.days[0].calibrationScope='native_and_fallback_all_calibrated']){
  const value=componentFixture();change(value);expect(parseDailyPvPotential(JSON.stringify(value),{nowMs:now})).toBeNull();
 }
});
