import { expect,it } from 'vitest';
import { parseEnergyAnalyticsResult } from '../src/lib/energy/analyticsResult.js';
import { analyticsV5Fixture, GENERATED_AT_MS } from './fixtures/analyticsV5.js';
import { energyAnalyticsFixture,energyAnalyticsV2Fixture,energyAnalyticsV3Fixture,energyAnalyticsV4Fixture } from './fixtures/energyAnalytics.js';
const parse=(v,now=GENERATED_AT_MS)=>parseEnergyAnalyticsResult(JSON.stringify(v),now);
it.each([energyAnalyticsFixture,energyAnalyticsV2Fixture,energyAnalyticsV3Fixture,energyAnalyticsV4Fixture])('suppresses stale legacy scalars and booleans for every schema',fixture=>{
 const v=fixture();Object.assign(v.forecast,{status:'stale',pv24hKwh:777,nextMorningSocPct:88,fullToday:true,fullTomorrow:false});
 const r=parse(v);expect(r.forecast.pv24hKwh).toBeNull();expect(r.forecast.nextMorningSocPct).toBeNull();expect(r.forecast.fullToday).toBeNull();expect(r.forecast.fullTomorrow).toBeNull();expect(r.energy.latest.pvKwh).toBe(8);
});
it.each(['future','expired','old_parent'])('suppresses %s legacy values',kind=>{
 const v=energyAnalyticsV4Fixture();if(kind==='future')v.forecast.issuedAt='2026-08-20T19:00:00Z';if(kind==='expired')v.forecast.validFor='2026-08-20T17:59:00Z';
 const r=parse(v,GENERATED_AT_MS+(kind==='old_parent'?16*60000:0));expect(r.forecast.pv24hKwh).toBeNull();
});
it('accepts qualified v5 and preserves distinct scopes, issues and null cohort',()=>{
 const r=parse(analyticsV5Fixture());expect(r.accounting.policy).toBe('qualified_power_evidence_v1');expect(r.acLoad.latest.observedKwh).toBe(12.5);expect(r.forecast.dailyPv.today.potentialKwh).toBe(4);expect(r.forecast.householdEnergy.cohortId).toBeNull();expect(r.forecast.pv24hKwh).toBeUndefined();
});
it.each([
 ['legacy alias',v=>v.forecast.pv24hKwh=5],['unknown nested',v=>v.forecast.dailyPv.extra=1],['physical claim',v=>v.forecast.dailyPv.physicalCalibrationQualified=true],['future source',v=>v.forecast.weather.sourceProfiles.extended.firstSeenAt='2027-01-01T00:00:00Z'],['bad digest',v=>v.forecast.householdEnergy.receiptSha256='bad'],['scope swap',v=>v.forecast.dailyPv.tomorrow.scope='remaining'],['unsafe accounting',v=>v.energy.latest.loadKwh=4],['unsafe AC',v=>v.acLoad.latest.coverage=0],['missing accounting',v=>delete v.accounting],['boolean number',v=>v.forecast.householdEnergy.potentialNext24hKwh=true],['extra profile',v=>v.forecast.weather.sourceProfiles.unknown={}]
])('rejects v5 %s',(_n,change)=>{const v=analyticsV5Fixture();change(v);expect(parse(v).forecast).toBeNull();});
it('expires independent products on clock advance without a new fetch',()=>{
 const v=analyticsV5Fixture();const r=parse(v,GENERATED_AT_MS+15*60000);expect(r.forecast.householdEnergy.potentialNext24hKwh).toBeNull();expect(r.forecast.householdEnergy.status).toBe('stale');expect(r.forecast.dailyPv.today.potentialKwh).toBe(4);expect(r.forecast.status).toBe('degraded');
 const stale=parse(v,GENERATED_AT_MS+16*60000);expect(stale.forecast.dailyPv.today.potentialKwh).toBeNull();expect(stale.energy.latest.pvKwh).toBe(8);
});

it.each([
 ['ordinary','2026-10-25T05:46:00Z','2026-10-25T06:00:00Z','2026-10-26T06:00:00Z'],
 ['spring DST','2026-03-08T06:46:00Z','2026-03-08T07:00:00Z','2026-03-09T06:00:00Z'],
 ['fall DST','2026-11-01T05:46:00Z','2026-11-01T06:00:00Z','2026-11-02T07:00:00Z'],
])('retained Item suppresses previous relative day labels across %s midnight',async(_label,issue,midnight,end)=>{
 const {analyticsV5MidnightFixture}=await import('./fixtures/analyticsV5.js');
 const v=analyticsV5MidnightFixture(issue,midnight,end),raw=JSON.stringify(v);
 const before=parseEnergyAnalyticsResult(raw,Date.parse(v.generatedAt));
 expect(before.forecast.dailyPv.today.potentialKwh).toBe(4);expect(before.forecast.dailyPv.tomorrow.potentialKwh).toBe(12);
 const after=parseEnergyAnalyticsResult(raw,Date.parse(midnight)+60000);
 expect(after.state).not.toBe('stale');expect(after.forecast.dailyPv.status).toBe('current');
 expect(after.forecast.dailyPv.today).toBeNull();expect(after.forecast.dailyPv.tomorrow).toBeNull();
 expect(after.forecast.householdEnergy.potentialNext24hKwh).toBe(15);expect(after.acLoad.latest.observedKwh).toBe(12.5);
 expect(JSON.stringify(v)).toBe(raw);
});
