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
